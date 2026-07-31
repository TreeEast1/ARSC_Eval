"""Build the model-output-blind Round 10 severity contact sheets.

No checkpoint, prediction cache, logit, confidence, or metric artifact is
opened by this script. The same 100 prefixed images are shown at all four
nonzero levels of each frozen corruption family.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.corruption_dose_response import (
    FAMILIES,
    LEVELS,
    PARAMETERS,
    make_pixel_corruption,
)
from arsc_eval.data import read_jsonl
from arsc_eval.utils import load_config, resolve_paths


AUDIT_SEED = 20260810
SAMPLE_COUNT = 100
ROWS_PER_PAGE = 10
OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/experiment.yaml")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest().upper()


def fit_thumbnail(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "black")
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    left = (size[0] - copy.width) // 2
    top = (size[1] - copy.height) // 2
    canvas.paste(copy, (left, top))
    return canvas


def main() -> int:
    args = parse_args()
    for path in (
        OUTPUT_DIR / "build_summary.json",
        OUTPUT_DIR / "audit_manifest.csv",
    ):
        if path.exists():
            raise RuntimeError(f"audit output already exists: {path}")
    config = load_config(args.config)
    paths = resolve_paths(config)
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    if len(records) != 4557:
        raise RuntimeError("frozen test population must contain 4557 rows")
    rng = np.random.default_rng(AUDIT_SEED)
    selected_indices = np.sort(
        rng.choice(len(records), size=SAMPLE_COUNT, replace=False)
    ).astype(np.int64)
    selected = [records[int(index)] for index in selected_indices]
    image_root = paths["dataset_root"] / "data"
    page_dir = OUTPUT_DIR / "pages"
    page_dir.mkdir(parents=True, exist_ok=False)

    manifest_path = OUTPUT_DIR / "audit_manifest.csv"
    with manifest_path.open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "audit_index",
                "dataset_index",
                "file_name",
                "family",
                "level",
                "parameter",
                "action_and_rationale_labels_still_applicable",
                "scene_semantics_preserved",
                "review_notes",
            ],
        )
        writer.writeheader()
        for audit_index, (dataset_index, record) in enumerate(
            zip(selected_indices, selected), start=1
        ):
            for family in FAMILIES:
                for level in LEVELS[1:]:
                    writer.writerow(
                        {
                            "audit_index": audit_index,
                            "dataset_index": int(dataset_index),
                            "file_name": record["file_name"],
                            "family": family,
                            "level": level,
                            "parameter": PARAMETERS[family][level],
                            "action_and_rationale_labels_still_applicable": "",
                            "scene_semantics_preserved": "",
                            "review_notes": "",
                        }
                    )

    thumb_size = (300, 169)
    label_height = 22
    page_records = []
    aggregate_distances: dict[str, list[float]] = {}
    identity_exact = True
    repeat_exact = True
    for family in FAMILIES:
        transforms = {
            level: make_pixel_corruption(family, level)
            for level in LEVELS
        }
        distance_totals = np.zeros(len(LEVELS), dtype=np.float64)
        pixel_totals = np.zeros(len(LEVELS), dtype=np.int64)
        for page_start in range(0, SAMPLE_COUNT, ROWS_PER_PAGE):
            page_number = page_start // ROWS_PER_PAGE + 1
            current = selected[
                page_start : page_start + ROWS_PER_PAGE
            ]
            width = len(LEVELS) * thumb_size[0]
            height = label_height + len(current) * (
                thumb_size[1] + label_height
            )
            page = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(page)
            font = ImageFont.load_default()
            for column, level in enumerate(LEVELS):
                label = (
                    f"level {level} / {family}="
                    f"{PARAMETERS[family][level]:g}"
                )
                draw.text(
                    (column * thumb_size[0] + 5, 5),
                    label,
                    fill="black",
                    font=font,
                )
            for row, record in enumerate(current):
                with Image.open(
                    image_root / record["file_name"]
                ) as source:
                    original = source.convert("RGB")
                original_array = np.asarray(
                    original, dtype=np.int16
                )
                variants = [
                    transforms[level](original, record["file_name"])
                    for level in LEVELS
                ]
                identity_exact = bool(
                    identity_exact
                    and np.array_equal(
                        np.asarray(variants[0]), original_array
                    )
                )
                repeated = transforms[4](
                    original, record["file_name"]
                )
                repeat_exact = bool(
                    repeat_exact
                    and np.array_equal(
                        np.asarray(repeated), np.asarray(variants[4])
                    )
                )
                y = label_height + row * (
                    thumb_size[1] + label_height
                )
                for column, variant in enumerate(variants):
                    array = np.asarray(variant, dtype=np.int16)
                    distance_totals[column] += np.abs(
                        array - original_array
                    ).sum(dtype=np.float64)
                    pixel_totals[column] += array.size
                    page.paste(
                        fit_thumbnail(variant, thumb_size),
                        (column * thumb_size[0], y),
                    )
                audit_index = page_start + row + 1
                draw.text(
                    (5, y + thumb_size[1] + 4),
                    f"{audit_index:03d} {record['file_name']}",
                    fill="black",
                    font=font,
                )
            page_path = (
                page_dir / f"{family}_page_{page_number:02d}.png"
            )
            page.save(page_path, format="PNG")
            page_records.append(
                {
                    "family": family,
                    "page": page_number,
                    "path": str(
                        page_path.relative_to(PROJECT_ROOT)
                    ).replace("\\", "/"),
                    "sha256": sha256_file(page_path),
                    "first_audit_index": page_start + 1,
                    "last_audit_index": page_start + len(current),
                }
            )
        aggregate_distances[family] = (
            distance_totals / pixel_totals
        ).tolist()

    distance_nondecreasing = {
        family: bool(
            np.all(
                np.diff(np.asarray(values, dtype=np.float64))
                >= -1e-15
            )
        )
        for family, values in aggregate_distances.items()
    }
    summary = {
        "status": "AWAITING_MODEL_OUTPUT_BLIND_REVIEW",
        "outcomes_read_or_computed": False,
        "sample_seed": AUDIT_SEED,
        "sample_count": SAMPLE_COUNT,
        "selected_dataset_indices": selected_indices.tolist(),
        "selected_indices_array_sha256": array_sha256(
            selected_indices
        ),
        "same_images_across_all_families_and_levels": True,
        "families": list(FAMILIES),
        "nonzero_levels_per_family": 4,
        "review_rows": SAMPLE_COUNT * len(FAMILIES) * 4,
        "manifest": str(
            manifest_path.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "manifest_sha256": sha256_file(manifest_path),
        "pages": page_records,
        "technical_gate": {
            "level_zero_exact_identity_all_images_and_families": (
                identity_exact
            ),
            "repeated_level_four_transform_exact_all_images": (
                repeat_exact
            ),
            "mean_absolute_rgb_change_by_family_and_level": (
                aggregate_distances
            ),
            "aggregate_distance_nondecreasing": (
                distance_nondecreasing
            ),
            "passed": bool(
                identity_exact
                and repeat_exact
                and all(distance_nondecreasing.values())
            ),
        },
        "manual_gate": {
            "minimum_rate_per_decision_per_stratum": 0.95,
            "minimum_joint_pass_rate_per_stratum": 0.95,
            "any_failed_stratum_stops_complete_grid": True,
        },
    }
    summary_path = OUTPUT_DIR / "build_summary.json"
    with summary_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "pages": len(page_records),
                "review_rows": summary["review_rows"],
                "technical_gate": summary["technical_gate"],
                "summary": str(
                    summary_path.relative_to(PROJECT_ROOT)
                ).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0 if summary["technical_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
