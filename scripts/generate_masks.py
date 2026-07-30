"""Generate critical and matched non-critical mean-filled masks."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import (
    RATIONALE_NAMES,
    TARGET_RATIONALE_TO_DETECTIONS,
)
from arsc_eval.data import read_jsonl
from arsc_eval.utils import load_config, resolve_paths, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    return max(0, right - left) * max(0, bottom - top)


def matched_noncritical_box(
    critical: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    box_width = critical[2] - critical[0]
    box_height = critical[3] - critical[1]
    if box_width <= 0 or box_height <= 0:
        return None
    max_x = width - box_width
    max_y = height - box_height
    if max_x < 0 or max_y < 0:
        return None
    x_positions = sorted(
        {int(round(max_x * index / 8)) for index in range(9)}
    )
    y_positions = sorted(
        {int(round(max_y * index / 4)) for index in range(5)}
    )
    critical_center = (
        (critical[0] + critical[2]) / 2,
        (critical[1] + critical[3]) / 2,
    )
    candidates = []
    for left in x_positions:
        for top in y_positions:
            candidate = (
                left,
                top,
                left + box_width,
                top + box_height,
            )
            if intersection_area(candidate, critical) != 0:
                continue
            center = (
                (candidate[0] + candidate[2]) / 2,
                (candidate[1] + candidate[3]) / 2,
            )
            distance = math.dist(center, critical_center)
            candidates.append((distance, candidate))
    return max(candidates, default=(None, None), key=lambda item: item[0])[1]


def clipped_box(
    xyxy: list[float], width: int, height: int
) -> tuple[int, int, int, int] | None:
    left = max(0, min(width - 1, int(math.floor(xyxy[0]))))
    top = max(0, min(height - 1, int(math.floor(xyxy[1]))))
    right = max(left + 1, min(width, int(math.ceil(xyxy[2]))))
    bottom = max(top + 1, min(height, int(math.ceil(xyxy[3]))))
    if right - left < 3 or bottom - top < 3:
        return None
    return left, top, right, bottom


def build_mask_record(
    record: dict,
    target_reasons: list[str],
    result,
    image_root: Path,
    critical_root: Path,
    noncritical_root: Path,
    skipped: Counter,
    detected_classes: Counter,
) -> dict | None:
    allowed_classes = set().union(
        *(
            TARGET_RATIONALE_TO_DETECTIONS[reason]
            for reason in target_reasons
        )
    )
    selected = None
    if result.boxes is not None:
        boxes = result.boxes.xyxy.detach().cpu().numpy()
        confidences = result.boxes.conf.detach().cpu().numpy()
        class_ids = result.boxes.cls.detach().cpu().numpy().astype(int)
        for box, confidence, class_id in zip(
            boxes, confidences, class_ids, strict=True
        ):
            class_name = str(result.names[int(class_id)])
            if class_name not in allowed_classes:
                continue
            candidate = (float(confidence), class_name, box.tolist())
            if selected is None or candidate[0] > selected[0]:
                selected = candidate
    if selected is None:
        skipped["no_matching_detection"] += 1
        return None

    source_path = image_root / record["file_name"]
    with Image.open(source_path) as source:
        image = source.convert("RGB")
    width, height = image.size
    critical_box = clipped_box(selected[2], width, height)
    if critical_box is None:
        skipped["invalid_detection_box"] += 1
        return None
    noncritical_box = matched_noncritical_box(critical_box, width, height)
    if noncritical_box is None:
        skipped["no_noncritical_region"] += 1
        return None
    pixels = np.asarray(image)
    fill = tuple(
        int(round(value)) for value in pixels.mean(axis=(0, 1)).tolist()
    )
    critical_image = image.copy()
    ImageDraw.Draw(critical_image).rectangle(critical_box, fill=fill)
    noncritical_image = image.copy()
    ImageDraw.Draw(noncritical_image).rectangle(noncritical_box, fill=fill)
    critical_path = critical_root / record["file_name"]
    noncritical_path = noncritical_root / record["file_name"]
    critical_image.save(critical_path, quality=95, subsampling=0)
    noncritical_image.save(noncritical_path, quality=95, subsampling=0)
    detected_classes[selected[1]] += 1
    manifest_record = dict(record)
    manifest_record.update(
        {
            "clean_path": str(source_path.relative_to(PROJECT_ROOT)),
            "critical_path": str(critical_path.relative_to(PROJECT_ROOT)),
            "noncritical_path": str(
                noncritical_path.relative_to(PROJECT_ROOT)
            ),
            "target_rationales": target_reasons,
            "detected_class": selected[1],
            "detector_confidence": selected[0],
            "critical_box_xyxy": list(critical_box),
            "noncritical_box_xyxy": list(noncritical_box),
            "mask_fill_rgb": list(fill),
        }
    )
    return manifest_record


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    settings = config["critical_mask"]
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    image_root = paths["dataset_root"] / "data"
    mask_root = paths["processed_root"] / "masks"
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
                skipped,
                detected_classes,
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
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    minimum = int(settings["minimum_target_samples"])
    summary = {
        "detector": str(settings["detector"]),
        "confidence_threshold": float(settings["confidence_threshold"]),
        "mask_fill": settings["mask_fill"],
        "eligible_by_rationale": len(candidates),
        "valid_mask_pairs": len(manifest_records),
        "minimum_target_samples": minimum,
        "minimum_met": len(manifest_records) >= minimum,
        "skipped": dict(skipped),
        "detected_class_counts": dict(detected_classes),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "localization_mapping": {
            name: sorted(values)
            for name, values in TARGET_RATIONALE_TO_DETECTIONS.items()
        },
        "traffic_sign_limitation": (
            "COCO has no generic traffic-sign class; the fixed detector's "
            "stop-sign class is used for the BDD-OIA traffic_sign rationale."
        ),
    }
    write_json(
        paths["output_dir"] / "critical_mask_generation.json", summary
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
