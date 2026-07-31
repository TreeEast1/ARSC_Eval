"""Build immutable labelled semantic-audit artifacts for Round 10 repair.

This script is model-output blind. It reads only the frozen test manifest and
source JPEGs, displays ground-truth label names, and applies the amended
self-contained pixel operators in memory.
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

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.corruption_dose_response_v2 import (
    FAMILIES,
    LEVELS,
    PARAMETERS,
    make_pixel_corruption_v2,
)
from arsc_eval.data import (
    deterministic_noise,
    make_benign_perturbation,
    read_jsonl,
)
from arsc_eval.round10_protocol_validation import (
    expected_sample_indices,
    expected_semantic_keys,
    semantic_key_sha256,
)
from arsc_eval.utils import load_config, resolve_paths


AUDIT_SEED = 20260810
SAMPLE_COUNT = 100
ROWS_PER_PAGE = 10
OUTPUT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit_amendment01"
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


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def fit_thumbnail(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "black")
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    left = (size[0] - copy.width) // 2
    top = (size[1] - copy.height) // 2
    canvas.paste(copy, (left, top))
    return canvas


def positive_names(vector: list[int], names: list[str]) -> list[str]:
    if len(vector) != len(names) or any(value not in (0, 1) for value in vector):
        raise RuntimeError("invalid frozen label vector")
    return [name for value, name in zip(vector, names) if value == 1]


def main() -> int:
    args = parse_args()
    if OUTPUT_DIR.exists():
        raise RuntimeError(f"repair audit directory already exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    page_dir = OUTPUT_DIR / "pages_labelled"
    page_dir.mkdir()

    config = load_config(args.config)
    paths = resolve_paths(config)
    records = read_jsonl(paths["processed_root"] / "test.jsonl")
    if len(records) != 4557:
        raise RuntimeError("frozen test population must contain 4557 rows")
    selected_indices = expected_sample_indices(
        len(records),
        sample_count=SAMPLE_COUNT,
        seed=AUDIT_SEED,
    )
    selected = [records[int(index)] for index in selected_indices]
    image_root = paths["dataset_root"] / "data"

    label_sidecar_path = OUTPUT_DIR / "label_sidecar.jsonl"
    with label_sidecar_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        for audit_index, (dataset_index, record) in enumerate(
            zip(selected_indices, selected),
            start=1,
        ):
            item = {
                "audit_index": audit_index,
                "dataset_index": int(dataset_index),
                "file_name": record["file_name"],
                "action_vector": record["actions"],
                "action_names": positive_names(
                    record["actions"],
                    ACTION_NAMES,
                ),
                "rationale_vector": record["rationales"],
                "rationale_names": positive_names(
                    record["rationales"],
                    RATIONALE_NAMES,
                ),
            }
            stream.write(
                json.dumps(
                    item,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )

    raw_manifest_path = OUTPUT_DIR / "raw_manifest.csv"
    fieldnames = [
        "audit_index",
        "dataset_index",
        "file_name",
        "family",
        "level",
        "parameter",
        "action_and_rationale_labels_still_applicable",
        "scene_semantics_preserved",
        "review_notes",
    ]
    with raw_manifest_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for audit_index, (dataset_index, record) in enumerate(
            zip(selected_indices, selected),
            start=1,
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
                            (
                                "action_and_rationale_labels_"
                                "still_applicable"
                            ): "",
                            "scene_semantics_preserved": "",
                            "review_notes": "",
                        }
                    )

    thumb_size = (300, 169)
    header_height = 22
    label_height = 34
    row_height = label_height + thumb_size[1]
    font = ImageFont.load_default()
    page_records = []
    aggregate_distances: dict[str, list[float]] = {}
    identity_exact = True
    repeat_exact = True
    historical_bridge_exact = True
    for family in FAMILIES:
        transforms = {
            level: make_pixel_corruption_v2(family, level)
            for level in LEVELS
        }
        legacy = make_benign_perturbation(
            family,
            brightness_factor=1.10,
            blur_radius=1.0,
            noise_std_255=5.0,
            noise_seed=20260731,
        )
        distance_totals = np.zeros(len(LEVELS), dtype=np.float64)
        pixel_totals = np.zeros(len(LEVELS), dtype=np.int64)
        for page_start in range(0, SAMPLE_COUNT, ROWS_PER_PAGE):
            page_number = page_start // ROWS_PER_PAGE + 1
            current = selected[
                page_start : page_start + ROWS_PER_PAGE
            ]
            width = len(LEVELS) * thumb_size[0]
            height = header_height + len(current) * row_height
            page = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(page)
            for column, level in enumerate(LEVELS):
                draw.text(
                    (column * thumb_size[0] + 5, 5),
                    (
                        f"level {level} / {family}="
                        f"{PARAMETERS[family][level]:g}"
                    ),
                    fill="black",
                    font=font,
                )
            for row, record in enumerate(current):
                with Image.open(
                    image_root / record["file_name"]
                ) as source:
                    original = source.convert("RGB")
                original_array = np.asarray(
                    original,
                    dtype=np.int16,
                )
                variants = [
                    transforms[level](original, record["file_name"])
                    for level in LEVELS
                ]
                identity_exact = bool(
                    identity_exact
                    and np.array_equal(
                        np.asarray(variants[0]),
                        original_array,
                    )
                )
                repeated = transforms[4](
                    original,
                    record["file_name"],
                )
                repeat_exact = bool(
                    repeat_exact
                    and np.array_equal(
                        np.asarray(repeated),
                        np.asarray(variants[4]),
                    )
                )
                historical = legacy(original, record["file_name"])
                historical_bridge_exact = bool(
                    historical_bridge_exact
                    and np.array_equal(
                        np.asarray(historical),
                        np.asarray(variants[2]),
                    )
                )

                audit_index = page_start + row + 1
                actions = positive_names(record["actions"], ACTION_NAMES)
                rationales = positive_names(
                    record["rationales"],
                    RATIONALE_NAMES,
                )
                y = header_height + row * row_height
                label_text = (
                    f"{audit_index:03d} {record['file_name']} | "
                    f"A:{','.join(actions) or '<empty>'}"
                )
                rationale_text = (
                    f"R:{','.join(rationales) or '<empty>'}"
                )
                draw.text(
                    (5, y + 2),
                    label_text,
                    fill="black",
                    font=font,
                )
                draw.text(
                    (5, y + 17),
                    rationale_text,
                    fill="black",
                    font=font,
                )
                image_y = y + label_height
                for column, variant in enumerate(variants):
                    array = np.asarray(variant, dtype=np.int16)
                    distance_totals[column] += np.abs(
                        array - original_array
                    ).sum(dtype=np.float64)
                    pixel_totals[column] += array.size
                    page.paste(
                        fit_thumbnail(variant, thumb_size),
                        (column * thumb_size[0], image_y),
                    )
            page_path = (
                page_dir
                / f"{family}_labelled_page_{page_number:02d}.png"
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
    page_hash_map = {
        item["path"]: item["sha256"] for item in page_records
    }
    raw_hash = sha256_file(raw_manifest_path)
    sidecar_hash = sha256_file(label_sidecar_path)
    row_key_hash = semantic_key_sha256(expected_semantic_keys())
    summary = {
        "schema_version": (
            "ARSC_ROUND10_SEMANTIC_AUDIT_AMENDMENT01_BUILD_V1"
        ),
        "status": "AWAITING_LABEL_VISIBLE_MODEL_OUTPUT_BLIND_REVIEW",
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
        "raw_manifest": str(
            raw_manifest_path.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "raw_manifest_sha256": raw_hash,
        "raw_manifest_is_immutable": True,
        "label_sidecar": str(
            label_sidecar_path.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "label_sidecar_sha256": sidecar_hash,
        "row_key_sha256": row_key_hash,
        "pages": page_records,
        "labelled_page_sha256": page_hash_map,
        "labelled_page_map_sha256": canonical_sha256(page_hash_map),
        "labels_visible_on_every_page_row": True,
        "technical_gate": {
            "level_zero_exact_identity_all_images_and_families": (
                identity_exact
            ),
            "repeated_level_four_transform_exact_all_images": (
                repeat_exact
            ),
            "historical_level_two_pixel_exact_all_images_and_families": (
                historical_bridge_exact
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
                and historical_bridge_exact
                and all(distance_nondecreasing.values())
            ),
        },
        "manual_gate": {
            "decisions_per_pair": [
                "action_and_rationale_labels_still_applicable",
                "scene_semantics_preserved",
            ],
            "minimum_rate_per_decision_per_stratum": 0.95,
            "minimum_joint_pass_rate_per_stratum": 0.95,
            "any_failed_stratum_stops_complete_grid": True,
            "default_true_requires_1200_pair_label_visible_attestation": True,
        },
        "legacy_bridge_note": (
            "The legacy helper is used only for the outcome-blind pixel-exact "
            "audit; the amended executable operator is self-contained."
        ),
    }
    summary_path = OUTPUT_DIR / "build_summary.json"
    with summary_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "pages": len(page_records),
                "review_rows": summary["review_rows"],
                "raw_manifest_sha256": raw_hash,
                "label_sidecar_sha256": sidecar_hash,
                "row_key_sha256": row_key_hash,
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
