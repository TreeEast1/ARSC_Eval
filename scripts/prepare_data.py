"""Validate official BDD-OIA splits and build merged manifests."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.utils import load_config, resolve_paths, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument(
        "--skip-image-verification",
        action="store_true",
        help="Only check existence, not JPEG decodability.",
    )
    return parser.parse_args()


def is_binary(values: list[object]) -> bool:
    return all(value in (0, 1, False, True) for value in values)


def verify_image(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            image.verify()
        return None
    except Exception as error:  # Pillow exposes format-specific exceptions.
        return f"{type(error).__name__}: {error}"


def process_split(
    split: str,
    dataset_root: Path,
    processed_root: Path,
    verify_images: bool,
) -> dict:
    action_path = dataset_root / f"{split}_25k_images_actions.json"
    rationale_path = dataset_root / f"{split}_25k_images_reasons.json"
    actions_payload = json.loads(action_path.read_text(encoding="utf-8"))
    rationales_payload = json.loads(rationale_path.read_text(encoding="utf-8"))

    images = actions_payload.get("images", [])
    annotations = actions_payload.get("annotations", [])
    reasons_by_name = {
        record.get("file_name"): record.get("reason")
        for record in rationales_payload
        if isinstance(record, dict)
    }
    duplicate_action_names = len(images) - len(
        {record.get("file_name") for record in images}
    )
    duplicate_reason_names = len(rationales_payload) - len(reasons_by_name)

    action_positive = np.zeros(len(ACTION_NAMES), dtype=np.int64)
    rationale_positive = np.zeros(len(RATIONALE_NAMES), dtype=np.int64)
    invalid_reasons = Counter()
    missing_images = []
    corrupt_images = []
    empty_rationale_count = 0
    extra_fifth_action_present = 0
    extra_fifth_action_positive = 0
    manifest_records = []

    annotations_by_id = {
        annotation.get("id"): annotation for annotation in annotations
    }
    for image_record in images:
        file_name = image_record.get("file_name")
        annotation = annotations_by_id.get(image_record.get("id"))
        image_path = dataset_root / "data" / str(file_name)
        actions = annotation.get("category") if annotation else None
        reasons = reasons_by_name.get(file_name)
        valid = True

        if not image_path.exists():
            missing_images.append(str(file_name))
            invalid_reasons["missing_image"] += 1
            valid = False
        elif verify_images:
            image_error = verify_image(image_path)
            if image_error:
                corrupt_images.append(
                    {"file_name": str(file_name), "error": image_error}
                )
                invalid_reasons["corrupt_image"] += 1
                valid = False

        if not isinstance(actions, list) or len(actions) < 4:
            invalid_reasons["invalid_action_dimension"] += 1
            valid = False
            actions4 = [0, 0, 0, 0]
        else:
            actions4 = actions[:4]
            if not is_binary(actions4):
                invalid_reasons["non_binary_action"] += 1
                valid = False
            else:
                action_positive += np.asarray(actions4, dtype=np.int64)
            if len(actions) >= 5:
                extra_fifth_action_present += 1
                extra_fifth_action_positive += int(actions[4] == 1)
            if sum(actions4) == 0:
                # These are official confuse/unknown entries, outside the
                # requested four-action prediction task.
                invalid_reasons["no_four_action_label"] += 1
                valid = False

        if not isinstance(reasons, list) or len(reasons) != len(RATIONALE_NAMES):
            invalid_reasons["invalid_rationale_dimension"] += 1
            valid = False
            reasons21 = [0] * len(RATIONALE_NAMES)
        else:
            reasons21 = reasons
            if not is_binary(reasons21):
                invalid_reasons["non_binary_rationale"] += 1
                valid = False
            else:
                rationale_positive += np.asarray(reasons21, dtype=np.int64)
                if sum(reasons21) == 0:
                    empty_rationale_count += 1

        if valid:
            manifest_records.append(
                {
                    "file_name": str(file_name),
                    "actions": [int(value) for value in actions4],
                    "rationales": [int(value) for value in reasons21],
                }
            )

    manifest_path = processed_root / f"{split}.jsonl"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in manifest_records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    action_names = {record.get("file_name") for record in images}
    reason_names = set(reasons_by_name)
    return {
        "official_samples": len(images),
        "valid_samples": len(manifest_records),
        "invalid_samples": len(images) - len(manifest_records),
        "action_positive_counts": {
            name: int(value)
            for name, value in zip(ACTION_NAMES, action_positive, strict=True)
        },
        "rationale_positive_counts": {
            name: int(value)
            for name, value in zip(
                RATIONALE_NAMES, rationale_positive, strict=True
            )
        },
        "missing_images": len(missing_images),
        "missing_image_names": missing_images,
        "corrupt_images": len(corrupt_images),
        "corrupt_image_details": corrupt_images,
        "invalid_reason_counts": dict(invalid_reasons),
        "empty_rationale_labels": empty_rationale_count,
        "extra_fifth_action_field_present": extra_fifth_action_present,
        "extra_fifth_action_positive": extra_fifth_action_positive,
        "duplicate_action_file_names": duplicate_action_names,
        "duplicate_rationale_file_names": duplicate_reason_names,
        "action_rationale_name_mismatch": len(action_names ^ reason_names),
        "manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
    }


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    dataset_root = paths["dataset_root"]
    processed_root = paths["processed_root"]
    output_dir = paths["output_dir"]

    split_summary = {
        split: process_split(
            split,
            dataset_root,
            processed_root,
            verify_images=not args.skip_image_verification,
        )
        for split in ("train", "val", "test")
    }
    referenced_names = set()
    for split in ("train", "val", "test"):
        payload = json.loads(
            (
                dataset_root / f"{split}_25k_images_actions.json"
            ).read_text(encoding="utf-8")
        )
        referenced_names.update(
            record["file_name"] for record in payload["images"]
        )
    all_images = {path.name for path in (dataset_root / "data").glob("*.jpg")}

    download_metadata_path = dataset_root.parent / "download_metadata.json"
    download_metadata = (
        json.loads(download_metadata_path.read_text(encoding="utf-8"))
        if download_metadata_path.exists()
        else {}
    )
    summary = {
        "dataset": "BDD-OIA official last-frame release",
        "source_google_drive_file_id": download_metadata.get(
            "google_drive_file_id"
        ),
        "source_archive_bytes": download_metadata.get("bytes"),
        "source_archive_sha256": download_metadata.get("sha256"),
        "action_labels": ACTION_NAMES,
        "rationale_labels": RATIONALE_NAMES,
        "splits": split_summary,
        "totals": {
            "official_samples": sum(
                item["official_samples"] for item in split_summary.values()
            ),
            "valid_samples": sum(
                item["valid_samples"] for item in split_summary.values()
            ),
            "invalid_samples": sum(
                item["invalid_samples"] for item in split_summary.values()
            ),
            "missing_images": sum(
                item["missing_images"] for item in split_summary.values()
            ),
            "corrupt_images": sum(
                item["corrupt_images"] for item in split_summary.values()
            ),
            "jpg_files_in_archive": len(all_images),
            "unreferenced_jpg_files": len(all_images - referenced_names),
        },
        "validation_policy": {
            "invalid_sample_definition": (
                "missing/corrupt image, malformed/non-binary label, or no "
                "positive label among the requested four actions"
            ),
            "empty_rationale_policy": (
                "retained when the four-action label is valid"
            ),
            "extra_fifth_action_policy": (
                "reported for provenance and ignored; the experiment predicts "
                "only Forward/Stop/Left/Right"
            ),
            "official_split_preserved": True,
        },
    }
    output_path = output_dir / "data_summary.json"
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
