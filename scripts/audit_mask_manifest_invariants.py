"""Audit mask-manifest engineering invariants and provenance.

This complements, but never replaces, the model-output-blind semantic audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import read_jsonl
from arsc_eval.utils import write_json
from generate_masks_v2 import box_area, intersection_area


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--exclude-sample-manifest", action="append", default=[]
    )
    parser.add_argument("--generator")
    parser.add_argument("--detector-weights")
    parser.add_argument("--maximum-offset", type=float, default=0.35)
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_slice(box: list[int], width: int, height: int) -> tuple[slice, slice]:
    # PIL ImageDraw.rectangle includes its right/bottom endpoints and clips at
    # the image boundary.
    left, top, right, bottom = box
    return (
        slice(max(0, top), min(height, bottom + 1)),
        slice(max(0, left), min(width, right + 1)),
    )


def main() -> int:
    args = parse_args()
    manifest_path = rooted(args.manifest)
    records = read_jsonl(manifest_path)
    file_names = [record["file_name"] for record in records]
    duplicate_names = len(file_names) - len(set(file_names))

    excluded_names: set[str] = set()
    exclusion_hashes = {}
    for exclusion in args.exclude_sample_manifest:
        path = rooted(exclusion)
        excluded_names.update(
            record["file_name"] for record in read_jsonl(path)
        )
        exclusion_hashes[str(path.relative_to(PROJECT_ROOT))] = sha256(path)
    overlap_names = sorted(set(file_names).intersection(excluded_names))

    failures: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    rationale_counts: Counter[str] = Counter()
    maximum_observed_offset = 0.0
    rendered_patch_shape_mismatches: list[dict[str, object]] = []
    for record in records:
        clean_path = rooted(record["clean_path"])
        critical_path = rooted(record["critical_path"])
        control_path = rooted(record["noncritical_path"])
        for path in (clean_path, critical_path, control_path):
            if not path.exists():
                failures["missing_file"] += 1
        if not all(
            path.exists() for path in (clean_path, critical_path, control_path)
        ):
            continue
        if critical_path.suffix.lower() != ".png":
            failures["critical_not_png"] += 1
        if control_path.suffix.lower() != ".png":
            failures["control_not_png"] += 1

        rationales = record.get("localized_rationales", [])
        actions = record.get("localized_action_indices", [])
        if len(rationales) != 1 or len(actions) != 1:
            failures["non_unique_rationale_action_binding"] += 1
        if rationales:
            rationale_counts[rationales[0]] += 1
        if "light_state" in record:
            state_counts[record["light_state"]] += 1

        critical_box = record["critical_box_xyxy"]
        control_box = record["noncritical_box_xyxy"]
        critical_size = (
            critical_box[2] - critical_box[0],
            critical_box[3] - critical_box[1],
        )
        control_size = (
            control_box[2] - control_box[0],
            control_box[3] - control_box[1],
        )
        if critical_size != control_size:
            failures["box_size_mismatch"] += 1
        if intersection_area(tuple(critical_box), tuple(control_box)):
            failures["critical_control_overlap"] += 1
        if not np.isclose(
            box_area(tuple(control_box)) / box_area(tuple(critical_box)), 1.0
        ):
            failures["area_ratio_not_one"] += 1
        offset = float(record["control_matching"]["center_offset_norm"])
        maximum_observed_offset = max(maximum_observed_offset, offset)
        if offset > float(args.maximum_offset) + 1e-12:
            failures["offset_above_limit"] += 1
        if (
            record["control_matching"].get("signal_like_pixel_count", 0)
            > record["control_matching"].get(
                "maximum_signal_like_pixel_count", float("inf")
            )
        ):
            failures["control_signal_guard_violation"] += 1

        clean = np.asarray(Image.open(clean_path).convert("RGB"))
        critical = np.asarray(Image.open(critical_path).convert("RGB"))
        control = np.asarray(Image.open(control_path).convert("RGB"))
        if clean.shape != critical.shape or clean.shape != control.shape:
            failures["image_dimension_mismatch"] += 1
            continue
        height, width = clean.shape[:2]
        fill = np.asarray(record["mask_fill_rgb"], dtype=np.uint8)
        critical_slice = patch_slice(critical_box, width, height)
        control_slice = patch_slice(control_box, width, height)
        expected_critical = clean.copy()
        expected_critical[critical_slice] = fill
        expected_control = clean.copy()
        expected_control[control_slice] = fill
        if not np.array_equal(critical, expected_critical):
            failures["critical_pixels_not_exact_fill_only"] += 1
        if not np.array_equal(control, expected_control):
            failures["control_pixels_not_exact_fill_only"] += 1
        critical_patch_shape = expected_critical[critical_slice].shape
        control_patch_shape = expected_control[control_slice].shape
        if critical_patch_shape != control_patch_shape:
            failures["rendered_patch_shape_mismatch"] += 1
            rendered_patch_shape_mismatches.append(
                {
                    "file_name": record["file_name"],
                    "critical_box_xyxy": critical_box,
                    "noncritical_box_xyxy": control_box,
                    "critical_patch_shape": list(critical_patch_shape),
                    "noncritical_patch_shape": list(control_patch_shape),
                }
            )

    failures["duplicate_file_name"] += duplicate_names
    failures["prior_audit_overlap"] += len(overlap_names)
    hashes = {
        str(manifest_path.relative_to(PROJECT_ROOT)): sha256(manifest_path)
    }
    for optional in (args.generator, args.detector_weights):
        if optional:
            path = rooted(optional)
            hashes[str(path.relative_to(PROJECT_ROOT))] = sha256(path)
    hashes.update(exclusion_hashes)
    summary = {
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "pairs": len(records),
        "state_counts": dict(state_counts),
        "rationale_counts": dict(rationale_counts),
        "excluded_prior_audit_names": len(excluded_names),
        "prior_audit_overlap_names": overlap_names,
        "maximum_allowed_offset": float(args.maximum_offset),
        "maximum_observed_offset": maximum_observed_offset,
        "failures": dict(failures),
        "rendered_patch_shape_mismatches": rendered_patch_shape_mismatches,
        "all_invariants_passed": not any(failures.values()),
        "sha256": hashes,
        "environment": {
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": Image.__version__,
            "python": sys.version,
        },
    }
    write_json(rooted(args.output), summary)
    print(json.dumps(summary, indent=2))
    return 0 if summary["all_invariants_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
