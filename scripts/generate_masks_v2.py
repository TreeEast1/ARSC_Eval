"""Generate spatially matched critical/control masks for the validity study.

Version 2 preserves the critical box area exactly, keeps the control box near
the same image position, and rejects control regions overlapping any detector
object. It writes to a new masks_v2 directory and never replaces the pilot
masks.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import (
    ACTION_NAMES,
    RATIONALE_TO_ACTION_INDEX,
    RATIONALE_NAMES,
    TARGET_RATIONALE_TO_DETECTIONS,
)
from arsc_eval.data import read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json

Box = tuple[int, int, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--device", default="0")
    parser.add_argument(
        "--max-control-offset",
        type=float,
        default=0.35,
        help="Maximum normalized center distance between mask boxes.",
    )
    return parser.parse_args()


def intersection_area(a: Box, b: Box) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    return max(0, right - left) * max(0, bottom - top)


def box_area(box: Box) -> int:
    return (box[2] - box[0]) * (box[3] - box[1])


def clipped_box(
    xyxy: list[float], width: int, height: int
) -> Box | None:
    left = max(0, min(width - 1, int(math.floor(xyxy[0]))))
    top = max(0, min(height - 1, int(math.floor(xyxy[1]))))
    right = max(left + 1, min(width, int(math.ceil(xyxy[2]))))
    bottom = max(top + 1, min(height, int(math.ceil(xyxy[3]))))
    if right - left < 3 or bottom - top < 3:
        return None
    return left, top, right, bottom


def normalized_center(box: Box, width: int, height: int) -> tuple[float, float]:
    return (
        (box[0] + box[2]) / (2.0 * width),
        (box[1] + box[3]) / (2.0 * height),
    )


def matched_noncritical_box(
    critical: Box,
    detection_boxes: list[Box],
    width: int,
    height: int,
    max_offset: float,
) -> tuple[Box, dict[str, float]] | None:
    """Find an exact-area nearby control avoiding all detected objects."""
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

    candidates: list[tuple[float, float, float, Box]] = []
    for top in sorted(y_positions):
        for left in sorted(x_positions):
            candidate = (
                left,
                top,
                left + box_width,
                top + box_height,
            )
            if intersection_area(candidate, critical):
                continue
            if any(
                intersection_area(candidate, detected)
                for detected in detection_boxes
            ):
                continue
            center = normalized_center(candidate, width, height)
            dx = abs(center[0] - critical_center[0])
            dy = abs(center[1] - critical_center[1])
            offset = math.hypot(dx, dy)
            if offset > max_offset:
                continue
            # Vertical location is especially important in road scenes. The
            # last term makes the deterministic tie-break prefer left/top.
            score = 4.0 * dy + dx
            tie_break = candidate[1] * width + candidate[0]
            candidates.append((score, offset, tie_break, candidate))

    if not candidates:
        return None
    _, offset, _, selected = min(candidates)
    selected_center = normalized_center(selected, width, height)
    diagnostics = {
        "center_offset_norm": float(offset),
        "x_center_offset_norm": float(
            abs(selected_center[0] - critical_center[0])
        ),
        "y_center_offset_norm": float(
            abs(selected_center[1] - critical_center[1])
        ),
        "area_ratio": float(box_area(selected) / box_area(critical)),
    }
    return selected, diagnostics


def detector_records(result, width: int, height: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if result.boxes is None:
        return records
    boxes = result.boxes.xyxy.detach().cpu().numpy()
    confidences = result.boxes.conf.detach().cpu().numpy()
    class_ids = result.boxes.cls.detach().cpu().numpy().astype(int)
    for xyxy, confidence, class_id in zip(
        boxes, confidences, class_ids, strict=True
    ):
        box = clipped_box(xyxy.tolist(), width, height)
        if box is None:
            continue
        records.append(
            {
                "box": box,
                "confidence": float(confidence),
                "class_name": str(result.names[int(class_id)]),
            }
        )
    return records


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
    matched_rationales: Counter,
) -> dict | None:
    source_path = image_root / record["file_name"]
    with Image.open(source_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    detections = detector_records(result, width, height)

    matching: list[dict[str, Any]] = []
    for detection in detections:
        reason_matches = sorted(
            reason
            for reason in target_reasons
            if detection["class_name"]
            in TARGET_RATIONALE_TO_DETECTIONS[reason]
        )
        if reason_matches:
            matching.append({**detection, "reason_matches": reason_matches})
    if not matching:
        skipped["no_matching_detection"] += 1
        return None

    selected = max(
        matching,
        key=lambda item: (
            item["confidence"],
            -box_area(item["box"]),
            item["class_name"],
        ),
    )
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

    detected_classes[selected["class_name"]] += 1
    for reason in selected["reason_matches"]:
        matched_rationales[reason] += 1
    localized_action_indices = sorted(
        {
            RATIONALE_TO_ACTION_INDEX[reason]
            for reason in selected["reason_matches"]
        }
    )
    manifest_record = dict(record)
    manifest_record.update(
        {
            "clean_path": str(source_path.relative_to(PROJECT_ROOT)),
            "critical_path": str(critical_path.relative_to(PROJECT_ROOT)),
            "noncritical_path": str(
                noncritical_path.relative_to(PROJECT_ROOT)
            ),
            "target_rationales": target_reasons,
            "localized_rationales": selected["reason_matches"],
            "localized_action_indices": localized_action_indices,
            "localized_action_names": [
                ACTION_NAMES[index] for index in localized_action_indices
            ],
            "detected_class": selected["class_name"],
            "detector_confidence": selected["confidence"],
            "critical_box_xyxy": list(selected["box"]),
            "noncritical_box_xyxy": list(noncritical_box),
            "mask_fill_rgb": list(fill),
            "detected_objects_in_image": len(detections),
            "control_matching": control_diagnostics,
        }
    )
    return manifest_record


def distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "minimum": float(array.min()),
        "median": float(np.median(array)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(array.max()),
    }


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    settings = config["critical_mask"]
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    image_root = paths["dataset_root"] / "data"
    mask_root = paths["processed_root"] / "masks_v2"
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
    matched_rationales = Counter()
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
            manifest_record = build_mask_record(
                record,
                target_reasons,
                result,
                image_root,
                critical_root,
                noncritical_root,
                float(args.max_control_offset),
                skipped,
                detected_classes,
                matched_rationales,
            )
            if manifest_record is not None:
                manifest_records.append(manifest_record)
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
    minimum = int(settings["minimum_target_samples"])
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
    summary = {
        "version": "v2_spatially_matched_control",
        "detector": str(settings["detector"]),
        "confidence_threshold": float(settings["confidence_threshold"]),
        "mask_fill": settings["mask_fill"],
        "image_format": "lossless PNG for both masked variants",
        "eligible_by_rationale": len(candidates),
        "valid_mask_pairs": len(manifest_records),
        "minimum_target_samples": minimum,
        "minimum_met": len(manifest_records) >= minimum,
        "skipped": dict(skipped),
        "detected_class_counts": dict(detected_classes),
        "localized_rationale_counts": dict(matched_rationales),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "control_policy": {
            "area": "exact width and height match",
            "position": (
                "nearest candidate with 4x vertical displacement penalty"
            ),
            "maximum_normalized_center_offset": float(
                args.max_control_offset
            ),
            "object_exclusion": (
                "zero intersection with every detector box above the "
                "configured confidence threshold"
            ),
        },
        "spatial_diagnostics": spatial,
        "localization_mapping": {
            name: sorted(values)
            for name, values in TARGET_RATIONALE_TO_DETECTIONS.items()
        },
        "traffic_sign_limitation": (
            "COCO has no generic traffic-sign class; stop-sign detections "
            "are the only localization proxy for traffic_sign."
        ),
        "audit_status": "pending stratified manual audit",
    }
    output_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v2_generation.json"
    )
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
