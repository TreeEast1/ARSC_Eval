"""Extract interpretable color/shape features from the audited v3 lights.

This is a measurement-development analysis.  Its output may inform a new v4
rule, but v4 must be evaluated on a filename-disjoint manual audit.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
AUDIT_CSV = ROOT / "outputs" / "validity" / "mask_audit_v3" / "manual_review.csv"
MANIFEST = ROOT / "data" / "processed" / "masks_v3" / "manifest.jsonl"
OUTPUT = ROOT / "outputs" / "validity" / "v3_light_audit_features.csv"


def state_mask(hsv: np.ndarray, state: str) -> np.ndarray:
    hue = hsv[..., 0]
    saturation = hsv[..., 1]
    value = hsv[..., 2]
    if state == "red":
        hue_match = (hue <= 8) | (hue >= 174)
    else:
        hue_match = (hue >= 42) & (hue <= 90)
    return hue_match & (saturation >= 140) & (value >= 140)


def component_features(mask: np.ndarray) -> dict[str, float]:
    count = int(mask.sum())
    area = int(mask.size)
    result = {
        "strict_pixel_count": count,
        "strict_area_fraction": count / max(area, 1),
        "strict_y_centroid": -1.0,
        "strict_largest_component": 0,
        "strict_largest_fraction": 0.0,
        "strict_component_fill": 0.0,
    }
    if count == 0:
        return result
    ys, _ = np.nonzero(mask)
    result["strict_y_centroid"] = float(
        ys.mean() / max(mask.shape[0] - 1, 1)
    )
    component_count, _, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    if component_count <= 1:
        return result
    largest_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    largest = int(stats[largest_index, cv2.CC_STAT_AREA])
    component_box_area = int(
        stats[largest_index, cv2.CC_STAT_WIDTH]
        * stats[largest_index, cv2.CC_STAT_HEIGHT]
    )
    result["strict_largest_component"] = largest
    result["strict_largest_fraction"] = largest / max(area, 1)
    result["strict_component_fill"] = largest / max(component_box_area, 1)
    return result


def summarize(rows: list[dict[str, object]]) -> None:
    for state in ("red", "green"):
        for passed in (False, True):
            subset = [
                row
                for row in rows
                if row["state"] == state and row["passed"] == passed
            ]
            print(
                json.dumps(
                    {
                        "state": state,
                        "passed": passed,
                        "n": len(subset),
                        "median_confidence": float(
                            np.median(
                                [row["detector_confidence"] for row in subset]
                            )
                        )
                        if subset
                        else None,
                        "median_aspect": float(
                            np.median([row["box_aspect_h_w"] for row in subset])
                        )
                        if subset
                        else None,
                        "median_strict_pixels": float(
                            np.median(
                                [row["strict_pixel_count"] for row in subset]
                            )
                        )
                        if subset
                        else None,
                        "median_strict_fraction": float(
                            np.median(
                                [row["strict_area_fraction"] for row in subset]
                            )
                        )
                        if subset
                        else None,
                        "median_y": float(
                            np.median(
                                [row["strict_y_centroid"] for row in subset]
                            )
                        )
                        if subset
                        else None,
                    }
                )
            )


def main() -> int:
    reviews = {}
    with AUDIT_CSV.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["Detected_Class"] == "traffic light":
                reviews[row["File_Name"]] = (
                    row["Critical_Binding_Correct"] == "yes"
                )
    manifests = {}
    with MANIFEST.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["file_name"] in reviews:
                manifests[record["file_name"]] = record

    output_rows = []
    for file_name, passed in reviews.items():
        record = manifests[file_name]
        box = tuple(record["critical_box_xyxy"])
        with Image.open(ROOT / record["clean_path"]) as source:
            crop = np.asarray(source.convert("RGB").crop(box))
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        state = record["light_state"]
        features = component_features(state_mask(hsv, state))
        width = box[2] - box[0]
        height = box[3] - box[1]
        diagnostics = record["light_state_diagnostics"]
        output_rows.append(
            {
                "file_name": file_name,
                "passed": passed,
                "state": state,
                "detector_confidence": record["detector_confidence"],
                "box_width": width,
                "box_height": height,
                "box_aspect_h_w": height / max(width, 1),
                "red_score": diagnostics["red_score"],
                "green_score": diagnostics["green_score"],
                "dominance_ratio": diagnostics["dominance_ratio"],
                **features,
            }
        )

    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    summarize(output_rows)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
