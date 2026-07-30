"""Generate a high-precision BDD-OIA mask subset for CEG diagnostics.

This version addresses the failed v2 binding audit:

* generic traffic-light boxes are retained only when a fixed HSV rule matches
  the annotated red/green state;
* directional green-light rationales are not localized because COCO boxes do
  not identify arrow direction;
* car/person/rider instances must lie in a deterministic ego-road corridor,
  and the most road-relevant instance is selected rather than the globally
  highest-confidence detection;
* each selected box binds to exactly one rationale and action dimension.

The color rule and geometric filter are fixed before the independent v3 audit.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import (
    ACTION_NAMES,
    RATIONALE_NAMES,
    RATIONALE_TO_ACTION_INDEX,
    TARGET_RATIONALE_TO_DETECTIONS,
)
from arsc_eval.data import read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json
from generate_masks_v2 import (
    box_area,
    detector_records,
    distribution,
    matched_noncritical_box,
)

Box = tuple[int, int, int, int]
NON_DIRECTIONAL_LIGHT_REASONS = {"green_light", "red_light"}
ROAD_OBJECT_REASONS = {"car", "person", "rider"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--device", default="0")
    parser.add_argument("--max-control-offset", type=float, default=0.35)
    return parser.parse_args()


def traffic_light_state(
    image: Image.Image, box: Box
) -> tuple[str | None, dict[str, float]]:
    """Classify an illuminated red/green signal with a fixed HSV rule."""
    crop = np.asarray(image.crop(box), dtype=np.uint8)
    if crop.size == 0:
        return None, {"red_score": 0.0, "green_score": 0.0}
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0]
    saturation = hsv[..., 1].astype(np.float64) / 255.0
    value = hsv[..., 2].astype(np.float64) / 255.0
    red = ((hue <= 10) | (hue >= 170)) & (saturation >= 0.45) & (value >= 0.45)
    green = (hue >= 35) & (hue <= 95) & (saturation >= 0.35) & (value >= 0.40)
    y = np.linspace(0.0, 1.0, crop.shape[0], dtype=np.float64)[:, None]
    red_position_weight = np.where(y <= 0.60, 1.5, 0.75)
    green_position_weight = np.where(y >= 0.40, 1.5, 0.75)
    pixel_weight = saturation * value * value
    area = float(crop.shape[0] * crop.shape[1])
    red_score = float(
        (pixel_weight * red * red_position_weight).sum() / area
    )
    green_score = float(
        (pixel_weight * green * green_position_weight).sum() / area
    )
    strongest = max(red_score, green_score)
    weakest = min(red_score, green_score)
    dominance = strongest / max(weakest, 1e-8)
    diagnostics = {
        "red_score": red_score,
        "green_score": green_score,
        "dominance_ratio": float(dominance),
    }
    if strongest < 0.008 or dominance < 1.5:
        return None, diagnostics
    return ("red" if red_score > green_score else "green"), diagnostics


def road_relevance(
    detection: dict[str, Any], width: int, height: int
) -> float | None:
    """Return a fixed perspective-aware relevance score or reject the box."""
    left, top, right, bottom = detection["box"]
    center_x = (left + right) / (2.0 * width)
    bottom_y = bottom / height
    if left <= 1 or right >= width - 1 or bottom_y < 0.48:
        return None
    corridor_half_width = min(
        0.38,
        0.12 + 0.30 * max(0.0, (bottom_y - 0.45) / 0.55),
    )
    horizontal_offset = abs(center_x - 0.5)
    if horizontal_offset > corridor_half_width:
        return None
    area_fraction = box_area(detection["box"]) / float(width * height)
    return float(
        bottom_y
        - 1.5 * horizontal_offset
        + 0.10 * detection["confidence"]
        + 0.05 * math.sqrt(area_fraction)
    )


def select_critical(
    image: Image.Image,
    target_reasons: list[str],
    detections: list[dict[str, Any]],
) -> dict[str, Any] | None:
    width, height = image.size
    candidates: list[dict[str, Any]] = []

    active_light_states = []
    if "green_light" in target_reasons:
        active_light_states.append(("green_light", "green"))
    if "red_light" in target_reasons:
        active_light_states.append(("red_light", "red"))
    # Conflicting light-state annotations cannot identify one critical box.
    if len(active_light_states) == 1:
        reason, desired_state = active_light_states[0]
        for detection in detections:
            if detection["class_name"] != "traffic light":
                continue
            state, state_diagnostics = traffic_light_state(
                image, detection["box"]
            )
            if state != desired_state:
                continue
            candidates.append(
                {
                    **detection,
                    "localized_rationale": reason,
                    "selection_policy": "hsv_light_state_match",
                    "selection_score": (
                        2.0
                        + state_diagnostics[f"{desired_state}_score"]
                        + 0.05 * detection["confidence"]
                    ),
                    "light_state": state,
                    "light_state_diagnostics": state_diagnostics,
                }
            )

    if "traffic_sign" in target_reasons:
        for detection in detections:
            if detection["class_name"] == "stop sign":
                candidates.append(
                    {
                        **detection,
                        "localized_rationale": "traffic_sign",
                        "selection_policy": "explicit_stop_sign_class",
                        "selection_score": 2.0 + detection["confidence"],
                    }
                )

    for reason in sorted(ROAD_OBJECT_REASONS.intersection(target_reasons)):
        allowed_classes = TARGET_RATIONALE_TO_DETECTIONS[reason]
        for detection in detections:
            if detection["class_name"] not in allowed_classes:
                continue
            relevance = road_relevance(detection, width, height)
            if relevance is None:
                continue
            candidates.append(
                {
                    **detection,
                    "localized_rationale": reason,
                    "selection_policy": "ego_road_corridor",
                    "selection_score": 1.0 + relevance,
                    "road_relevance_score": relevance,
                }
            )

    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item["selection_score"],
            item["confidence"],
            -box_area(item["box"]),
            item["class_name"],
        ),
    )


def build_mask_record(
    record: dict,
    target_reasons: list[str],
    result,
    image_root: Path,
    critical_root: Path,
    noncritical_root: Path,
    max_control_offset: float,
    skipped: Counter,
    detected_classes: Counter,
    localized_rationales: Counter,
    selection_policies: Counter,
) -> dict | None:
    source_path = image_root / record["file_name"]
    with Image.open(source_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    detections = detector_records(result, width, height)
    selected = select_critical(image, target_reasons, detections)
    if selected is None:
        skipped["no_high_precision_binding"] += 1
        return None

    control = matched_noncritical_box(
        selected["box"],
        [item["box"] for item in detections],
        width,
        height,
        max_control_offset,
    )
    if control is None:
        skipped["no_spatially_matched_control"] += 1
        return None
    noncritical_box, control_diagnostics = control
    pixels = np.asarray(image)
    fill = tuple(
        int(round(value)) for value in pixels.mean(axis=(0, 1)).tolist()
    )
    critical_image = image.copy()
    ImageDraw.Draw(critical_image).rectangle(selected["box"], fill=fill)
    noncritical_image = image.copy()
    ImageDraw.Draw(noncritical_image).rectangle(noncritical_box, fill=fill)
    output_name = f"{Path(record['file_name']).stem}.png"
    critical_path = critical_root / output_name
    noncritical_path = noncritical_root / output_name
    critical_image.save(critical_path)
    noncritical_image.save(noncritical_path)

    rationale = selected["localized_rationale"]
    action_index = RATIONALE_TO_ACTION_INDEX[rationale]
    detected_classes[selected["class_name"]] += 1
    localized_rationales[rationale] += 1
    selection_policies[selected["selection_policy"]] += 1
    manifest_record = dict(record)
    manifest_record.update(
        {
            "clean_path": str(source_path.relative_to(PROJECT_ROOT)),
            "critical_path": str(critical_path.relative_to(PROJECT_ROOT)),
            "noncritical_path": str(
                noncritical_path.relative_to(PROJECT_ROOT)
            ),
            "target_rationales": target_reasons,
            "localized_rationales": [rationale],
            "localized_action_indices": [action_index],
            "localized_action_names": [ACTION_NAMES[action_index]],
            "detected_class": selected["class_name"],
            "detector_confidence": selected["confidence"],
            "critical_box_xyxy": list(selected["box"]),
            "noncritical_box_xyxy": list(noncritical_box),
            "mask_fill_rgb": list(fill),
            "detected_objects_in_image": len(detections),
            "control_matching": control_diagnostics,
            "selection_policy": selected["selection_policy"],
            "selection_score": selected["selection_score"],
        }
    )
    for optional in (
        "light_state",
        "light_state_diagnostics",
        "road_relevance_score",
    ):
        if optional in selected:
            manifest_record[optional] = selected[optional]
    return manifest_record


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    settings = config["critical_mask"]
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    image_root = paths["dataset_root"] / "data"
    mask_root = paths["processed_root"] / "masks_v3"
    critical_root = mask_root / "critical"
    noncritical_root = mask_root / "noncritical"
    critical_root.mkdir(parents=True, exist_ok=True)
    noncritical_root.mkdir(parents=True, exist_ok=True)

    rationale_indices = {
        name: index for index, name in enumerate(RATIONALE_NAMES)
    }
    candidates = []
    for record in records:
        target_reasons = [
            name
            for name in TARGET_RATIONALE_TO_DETECTIONS
            if record["rationales"][rationale_indices[name]] == 1
        ]
        if target_reasons:
            candidates.append((record, target_reasons))

    detector = YOLO(str(settings["detector"]))
    manifest_records = []
    skipped = Counter()
    detected_classes = Counter()
    localized_rationales = Counter()
    selection_policies = Counter()
    batch_size = int(settings["detector_batch_size"])
    for start in range(0, len(candidates), batch_size):
        candidate_batch = candidates[start : start + batch_size]
        sources = [
            str((image_root / record["file_name"]).resolve())
            for record, _ in candidate_batch
        ]
        detections = detector.predict(
            source=sources,
            stream=False,
            imgsz=640,
            conf=float(settings["confidence_threshold"]),
            batch=batch_size,
            device=args.device,
            verbose=False,
        )
        for (record, target_reasons), result in zip(
            candidate_batch, detections, strict=True
        ):
            mask_record = build_mask_record(
                record,
                target_reasons,
                result,
                image_root,
                critical_root,
                noncritical_root,
                float(args.max_control_offset),
                skipped,
                detected_classes,
                localized_rationales,
                selection_policies,
            )
            if mask_record is not None:
                manifest_records.append(mask_record)
        print(
            json.dumps(
                {
                    "processed": min(start + batch_size, len(candidates)),
                    "eligible": len(candidates),
                    "valid_masks": len(manifest_records),
                }
            ),
            flush=True,
        )

    manifest_path = mask_root / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in manifest_records:
            handle.write(
                json.dumps(record, separators=(",", ":")) + "\n"
            )
    spatial = {
        name: distribution(
            [
                record["control_matching"][name]
                for record in manifest_records
            ]
        )
        for name in (
            "center_offset_norm",
            "x_center_offset_norm",
            "y_center_offset_norm",
            "area_ratio",
        )
    }
    minimum = int(settings["minimum_target_samples"])
    summary = {
        "version": "v3_high_precision_binding",
        "detector": str(settings["detector"]),
        "confidence_threshold": float(settings["confidence_threshold"]),
        "image_format": "lossless PNG for both masked variants",
        "eligible_by_rationale": len(candidates),
        "valid_mask_pairs": len(manifest_records),
        "pilot_minimum_target_samples": minimum,
        "pilot_minimum_met": len(manifest_records) >= minimum,
        "skipped": dict(skipped),
        "detected_class_counts": dict(detected_classes),
        "localized_rationale_counts": dict(localized_rationales),
        "selection_policy_counts": dict(selection_policies),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "pre_registered_binding_policy": {
            "traffic_lights": (
                "fixed HSV red/green state match; directional green-light "
                "rationales excluded"
            ),
            "road_objects": (
                "fixed perspective-aware ego-road corridor and relevance score"
            ),
            "traffic_sign": "explicit COCO stop-sign class only",
            "one_rationale_action_binding_per_image": True,
        },
        "control_policy": {
            "area": "exact width and height match",
            "position": (
                "nearest candidate with 4x vertical displacement penalty"
            ),
            "maximum_normalized_center_offset": float(
                args.max_control_offset
            ),
            "object_exclusion": (
                "zero intersection with every detector box above threshold"
            ),
        },
        "spatial_diagnostics": spatial,
        "audit_status": "pending independent stratified manual audit",
    }
    output_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v3_generation.json"
    )
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
