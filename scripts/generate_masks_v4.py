"""Generate a filename-disjoint, high-precision traffic-light CEG subset.

v4 is a measurement-development response to the independent v3 audit.  Its
fixed rules were selected on the v3 audit only and therefore require a new
manual audit on filenames excluded from both earlier rounds.

The subset intentionally trades coverage for precision:

* strict aggregate red/green HSV evidence plus lamp-position/box-shape gates;
* no road-object localization, because v3 showed that a generic detector does
  not establish that a car/person/rider is action-inducing;
* controls avoid low-confidence, margin-expanded detections and any visible
  red/amber/green signal-like pixels.
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
)
from arsc_eval.data import read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json
from generate_masks_v2 import (
    box_area,
    detector_records,
    distribution,
    intersection_area,
    normalized_center,
)

Box = tuple[int, int, int, int]
LIGHT_STATES = {"green_light": "green", "red_light": "red"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--device", default="0")
    parser.add_argument("--selection-confidence", type=float, default=0.35)
    parser.add_argument("--exclusion-confidence", type=float, default=0.10)
    parser.add_argument("--max-control-offset", type=float, default=0.35)
    return parser.parse_args()


def strict_state_mask(hsv: np.ndarray, state: str) -> np.ndarray:
    hue = hsv[..., 0]
    saturation = hsv[..., 1]
    value = hsv[..., 2]
    if state == "red":
        hue_match = (hue <= 8) | (hue >= 174)
    elif state == "green":
        hue_match = (hue >= 42) & (hue <= 90)
    else:
        raise ValueError(f"unsupported state: {state}")
    return hue_match & (saturation >= 140) & (value >= 140)


def strict_light_evidence(
    image: Image.Image, box: Box, state: str
) -> tuple[bool, dict[str, float]]:
    crop = np.asarray(image.crop(box), dtype=np.uint8)
    if crop.size == 0:
        return False, {
            "strict_pixel_count": 0,
            "strict_area_fraction": 0.0,
            "strict_y_centroid": -1.0,
            "box_aspect_h_w": 0.0,
        }
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    mask = strict_state_mask(hsv, state)
    count = int(mask.sum())
    area = int(mask.size)
    height, width = mask.shape
    aspect = height / max(width, 1)
    if count:
        ys, _ = np.nonzero(mask)
        y_centroid = float(ys.mean() / max(height - 1, 1))
    else:
        y_centroid = -1.0
    fraction = count / max(area, 1)

    if state == "green":
        passed = count >= 10 and aspect >= 1.90 and y_centroid >= 0.55
    else:
        passed = count >= 40 and y_centroid <= 0.50
        # A large red region in a squat detector box is commonly a sign,
        # reflection, or tail light rather than an illuminated signal lamp.
        if fraction > 0.30 and aspect < 1.45:
            passed = False
    return passed, {
        "strict_pixel_count": count,
        "strict_area_fraction": float(fraction),
        "strict_y_centroid": y_centroid,
        "box_aspect_h_w": float(aspect),
    }


def expanded_box(box: Box, width: int, height: int) -> Box:
    box_width = box[2] - box[0]
    box_height = box[3] - box[1]
    margin_x = max(6, int(round(0.25 * box_width)))
    margin_y = max(6, int(round(0.25 * box_height)))
    return (
        max(0, box[0] - margin_x),
        max(0, box[1] - margin_y),
        min(width, box[2] + margin_x),
        min(height, box[3] + margin_y),
    )


def signal_like_pixel_count(image_rgb: np.ndarray, box: Box) -> int:
    crop = image_rgb[box[1] : box[3], box[0] : box[2]]
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0]
    saturation = hsv[..., 1]
    value = hsv[..., 2]
    signal_hue = (hue <= 100) | (hue >= 165)
    mask = signal_hue & (saturation >= 140) & (value >= 140)
    return int(mask.sum())


def matched_clean_control(
    image_rgb: np.ndarray,
    critical: Box,
    exclusion_boxes: list[Box],
    width: int,
    height: int,
    max_offset: float,
) -> tuple[Box, dict[str, float]] | None:
    """Find an exact-size nearby empty control using the fixed v4 guards."""
    box_width = critical[2] - critical[0]
    box_height = critical[3] - critical[1]
    max_x = width - box_width
    max_y = height - box_height
    if box_width <= 0 or box_height <= 0 or max_x < 0 or max_y < 0:
        return None

    critical_center = normalized_center(critical, width, height)
    x_step = max(4, box_width // 2)
    x_positions = set(range(0, max_x + 1, x_step))
    x_positions.add(max_x)
    vertical_offsets = (
        0.0,
        -0.025,
        0.025,
        -0.05,
        0.05,
        -0.10,
        0.10,
        -0.15,
        0.15,
        -0.20,
        0.20,
    )
    y_positions = {
        max(0, min(max_y, int(round(critical[1] + offset * height))))
        for offset in vertical_offsets
    }
    maximum_signal_pixels = max(2, int(math.floor(0.002 * box_area(critical))))
    candidates: list[tuple[float, float, int, int, Box]] = []
    for top in sorted(y_positions):
        for left in sorted(x_positions):
            candidate = (left, top, left + box_width, top + box_height)
            if intersection_area(candidate, critical):
                continue
            if any(
                intersection_area(candidate, excluded)
                for excluded in exclusion_boxes
            ):
                continue
            signal_pixels = signal_like_pixel_count(image_rgb, candidate)
            if signal_pixels > maximum_signal_pixels:
                continue
            center = normalized_center(candidate, width, height)
            dx = abs(center[0] - critical_center[0])
            dy = abs(center[1] - critical_center[1])
            offset = math.hypot(dx, dy)
            if offset > max_offset:
                continue
            score = 4.0 * dy + dx
            tie_break = candidate[1] * width + candidate[0]
            candidates.append(
                (score, offset, signal_pixels, tie_break, candidate)
            )
    if not candidates:
        return None
    _, offset, signal_pixels, _, selected = min(candidates)
    center = normalized_center(selected, width, height)
    return selected, {
        "center_offset_norm": float(offset),
        "x_center_offset_norm": float(
            abs(center[0] - critical_center[0])
        ),
        "y_center_offset_norm": float(
            abs(center[1] - critical_center[1])
        ),
        "area_ratio": float(box_area(selected) / box_area(critical)),
        "signal_like_pixel_count": int(signal_pixels),
        "maximum_signal_like_pixel_count": int(maximum_signal_pixels),
    }


def select_light(
    image: Image.Image,
    state: str,
    detections: list[dict[str, Any]],
    selection_confidence: float,
) -> dict[str, Any] | None:
    candidates = []
    for detection in detections:
        if (
            detection["class_name"] != "traffic light"
            or detection["confidence"] < selection_confidence
        ):
            continue
        passed, evidence = strict_light_evidence(
            image, detection["box"], state
        )
        if not passed:
            continue
        candidates.append(
            {
                **detection,
                "strict_light_evidence": evidence,
                "selection_score": (
                    evidence["strict_area_fraction"]
                    + 0.05 * detection["confidence"]
                ),
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
        ),
    )


def build_record(
    record: dict,
    rationale: str,
    state: str,
    result,
    image_root: Path,
    critical_root: Path,
    noncritical_root: Path,
    selection_confidence: float,
    max_control_offset: float,
    skipped: Counter,
) -> dict | None:
    source_path = image_root / record["file_name"]
    with Image.open(source_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    detections = detector_records(result, width, height)
    selected = select_light(
        image, state, detections, selection_confidence
    )
    if selected is None:
        skipped["no_strict_state_binding"] += 1
        return None

    image_rgb = np.asarray(image)
    exclusion_boxes = [
        expanded_box(item["box"], width, height) for item in detections
    ]
    control = matched_clean_control(
        image_rgb,
        selected["box"],
        exclusion_boxes,
        width,
        height,
        max_control_offset,
    )
    if control is None:
        skipped["no_clean_spatial_control"] += 1
        return None
    noncritical_box, control_diagnostics = control

    fill = tuple(
        int(round(value)) for value in image_rgb.mean(axis=(0, 1)).tolist()
    )
    output_name = f"{Path(record['file_name']).stem}.png"
    critical_path = critical_root / output_name
    noncritical_path = noncritical_root / output_name
    critical_image = image.copy()
    ImageDraw.Draw(critical_image).rectangle(selected["box"], fill=fill)
    critical_image.save(critical_path)
    noncritical_image = image.copy()
    ImageDraw.Draw(noncritical_image).rectangle(noncritical_box, fill=fill)
    noncritical_image.save(noncritical_path)

    action_index = RATIONALE_TO_ACTION_INDEX[rationale]
    output = dict(record)
    output.update(
        {
            "clean_path": str(source_path.relative_to(PROJECT_ROOT)),
            "critical_path": str(critical_path.relative_to(PROJECT_ROOT)),
            "noncritical_path": str(
                noncritical_path.relative_to(PROJECT_ROOT)
            ),
            "target_rationales": [rationale],
            "localized_rationales": [rationale],
            "localized_action_indices": [action_index],
            "localized_action_names": [ACTION_NAMES[action_index]],
            "detected_class": "traffic light",
            "detector_confidence": selected["confidence"],
            "critical_box_xyxy": list(selected["box"]),
            "noncritical_box_xyxy": list(noncritical_box),
            "mask_fill_rgb": list(fill),
            "detected_objects_in_image": len(detections),
            "control_matching": control_diagnostics,
            "selection_policy": "v4_strict_state_light",
            "selection_score": selected["selection_score"],
            "light_state": state,
            "strict_light_evidence": selected["strict_light_evidence"],
        }
    )
    return output


def main() -> int:
    args = parse_args()
    if args.exclusion_confidence >= args.selection_confidence:
        raise ValueError(
            "exclusion confidence must be lower than selection confidence"
        )
    config = load_config(args.config)
    paths = resolve_paths(config)
    settings = config["critical_mask"]
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    image_root = paths["dataset_root"] / "data"
    mask_root = paths["processed_root"] / "masks_v4"
    critical_root = mask_root / "critical"
    noncritical_root = mask_root / "noncritical"
    critical_root.mkdir(parents=True, exist_ok=True)
    noncritical_root.mkdir(parents=True, exist_ok=True)

    rationale_indices = {
        name: index for index, name in enumerate(RATIONALE_NAMES)
    }
    candidates = []
    for record in records:
        active = [
            (rationale, state)
            for rationale, state in LIGHT_STATES.items()
            if record["rationales"][rationale_indices[rationale]] == 1
        ]
        if len(active) == 1:
            rationale, state = active[0]
            candidates.append((record, rationale, state))

    detector = YOLO(str(settings["detector"]))
    manifest_records = []
    skipped = Counter()
    batch_size = int(settings["detector_batch_size"])
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        sources = [
            str((image_root / record["file_name"]).resolve())
            for record, _, _ in batch
        ]
        results = detector.predict(
            source=sources,
            stream=False,
            imgsz=640,
            conf=float(args.exclusion_confidence),
            batch=batch_size,
            device=args.device,
            verbose=False,
        )
        for (record, rationale, state), result in zip(
            batch, results, strict=True
        ):
            output = build_record(
                record,
                rationale,
                state,
                result,
                image_root,
                critical_root,
                noncritical_root,
                float(args.selection_confidence),
                float(args.max_control_offset),
                skipped,
            )
            if output is not None:
                manifest_records.append(output)
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
            [record["control_matching"][name] for record in manifest_records]
        )
        for name in (
            "center_offset_norm",
            "x_center_offset_norm",
            "y_center_offset_norm",
            "area_ratio",
        )
    }
    summary = {
        "version": "v4_disjoint_high_precision_traffic_light",
        "detector": str(settings["detector"]),
        "selection_confidence": float(args.selection_confidence),
        "exclusion_confidence": float(args.exclusion_confidence),
        "image_format": "lossless PNG for both masked variants",
        "eligible_single_state_images": len(candidates),
        "valid_mask_pairs": len(manifest_records),
        "skipped": dict(skipped),
        "state_counts": dict(
            Counter(record["light_state"] for record in manifest_records)
        ),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "development_provenance": (
            "rules fixed from masks_v3 audit; v4 requires a filename-disjoint "
            "audit excluding v2 and v3 audit samples"
        ),
        "pre_registered_binding_policy": {
            "scope": "non-directional red/green traffic lights only",
            "red": (
                "strict HSV pixels >=40, y centroid <=0.50; if colored area "
                ">0.30 then detector-box aspect ratio must be >=1.45"
            ),
            "green": (
                "strict HSV pixels >=10, detector-box aspect ratio >=1.90, "
                "and colored-pixel y centroid >=0.55"
            ),
        },
        "control_policy": {
            "area": "exact width and height match",
            "position": "nearest candidate with 4x vertical penalty",
            "maximum_normalized_center_offset": float(
                args.max_control_offset
            ),
            "object_exclusion": (
                "zero overlap with detections at exclusion confidence after "
                "25%/minimum-6px box expansion"
            ),
            "signal_color_guard": (
                "at most max(2, floor(0.002*area)) strict "
                "red/amber/green pixels"
            ),
        },
        "spatial_diagnostics": spatial,
        "audit_status": "pending independent filename-disjoint manual audit",
    }
    output_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v4_generation.json"
    )
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
