"""Run the preregistered BDD100K-train v5 metadata-only population gate.

This script never imports model code, opens checkpoints, generates masks, or
reads prediction caches. It intersects frozen BDD-OIA manifests with official
BDD100K traffic-light state metadata and verifies filename, clip-group, and
image-byte independence before applying the frozen population thresholds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import RATIONALE_NAMES

EXPECTED_DATASET_REVISION = "d82c5188d392714ba8091d68014f7b9838ceadf2"
DEFAULT_MODEL_MANIFESTS = [
    "data/processed/train.jsonl",
    "data/processed/val.jsonl",
]
DEFAULT_PRIOR_MANIFESTS = [
    "data/processed/masks_v2/manifest.jsonl",
    "data/processed/masks_v3/manifest.jsonl",
    "data/processed/masks_v4/manifest.jsonl",
    "data/processed/masks_v4/manifest_confirmatory.jsonl",
    "outputs/validity/mask_audit_v2/sample_manifest.jsonl",
    "outputs/validity/mask_audit_v3/sample_manifest.jsonl",
    "outputs/validity/mask_audit_v4/sample_manifest.jsonl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labels",
        default=(
            "data/external/bdd100k/"
            "bdd100k_enriched_annotations_for_bdd_oia.json"
        ),
    )
    parser.add_argument(
        "--protocol",
        default="outputs/validity/bdd100k_train_v5_metadata_protocol.json",
    )
    parser.add_argument(
        "--bdd-oia-test", default="data/processed/test.jsonl"
    )
    parser.add_argument(
        "--image-root", default="data/raw/lastframe"
    )
    parser.add_argument(
        "--model-manifest",
        action="append",
        dest="model_manifests",
    )
    parser.add_argument(
        "--prior-manifest",
        action="append",
        dest="prior_manifests",
    )
    parser.add_argument(
        "--output",
        default="outputs/validity/bdd100k_train_v5_metadata_gate.json",
    )
    parser.add_argument(
        "--candidate-manifest",
        default="outputs/validity/bdd100k_train_v5_candidates.jsonl",
    )
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def project_relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def clip_group(file_name: str) -> str:
    stem = Path(file_name).stem
    if stem.endswith(("_1", "_3")):
        stem = stem[:-2]
    return stem


def is_keyframe(file_name: str) -> bool:
    return Path(file_name).stem == clip_group(file_name)


def normalize_light_color(value: object) -> str:
    color = str(value).strip().lower()
    return {
        "r": "red",
        "g": "green",
        "y": "yellow",
        "na": "none",
    }.get(color, color)


def state_boxes(row: dict, target_state: str) -> list[list[float]]:
    categories = row.get("ann_categories", [])
    boxes = row.get("ann_bboxes", [])
    colors = row.get("ann_traffic_light_colors", [])
    if not (len(categories) == len(boxes) == len(colors)):
        raise ValueError(
            f"misaligned annotation arrays for {row.get('image_id')}"
        )
    matches = []
    for category, box, color in zip(categories, boxes, colors):
        if (
            str(category).strip().lower() == "traffic light"
            and normalize_light_color(color) == target_state
        ):
            if len(box) != 4:
                raise ValueError(
                    f"invalid box for {row.get('image_id')}: {box}"
                )
            matches.append([float(value) for value in box])
    return matches


def sole_target_state(record: dict) -> str | None:
    red_index = RATIONALE_NAMES.index("red_light")
    green_index = RATIONALE_NAMES.index("green_light")
    red = int(record["rationales"][red_index]) == 1
    green = int(record["rationales"][green_index]) == 1
    if red == green:
        return None
    return "red" if red else "green"


def manifest_names(records: list[dict]) -> set[str]:
    return {str(record["file_name"]) for record in records}


def manifest_groups(records: list[dict]) -> set[str]:
    return {clip_group(str(record["file_name"])) for record in records}


def validate_frozen_inputs(protocol: dict) -> list[dict]:
    checks = []
    for item in protocol["frozen_inputs"]:
        path = rooted(item["path"])
        observed_bytes = path.stat().st_size
        observed_hash = sha256_file(path)
        passed = (
            observed_bytes == int(item["bytes"])
            and observed_hash == str(item["sha256"]).upper()
        )
        checks.append(
            {
                "path": item["path"],
                "role": item["role"],
                "expected_bytes": int(item["bytes"]),
                "observed_bytes": observed_bytes,
                "expected_sha256": str(item["sha256"]).upper(),
                "observed_sha256": observed_hash,
                "passed": passed,
            }
        )
    if not all(check["passed"] for check in checks):
        raise RuntimeError("one or more frozen protocol inputs changed")
    return checks


def hash_named_images(
    names: set[str], image_root: Path
) -> tuple[dict[str, str], list[str]]:
    hashes = {}
    missing = []
    for name in sorted(names):
        path = image_root / name
        if not path.is_file():
            missing.append(name)
            continue
        hashes[name] = sha256_file(path)
    return hashes, missing


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    model_manifest_names = (
        args.model_manifests or DEFAULT_MODEL_MANIFESTS
    )
    prior_manifest_names = (
        args.prior_manifests or DEFAULT_PRIOR_MANIFESTS
    )

    protocol_path = rooted(args.protocol)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    frozen_input_checks = validate_frozen_inputs(protocol)
    thresholds = protocol["go_stop_gates"]["gate_2_population"]

    label_path = rooted(args.labels)
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    if not labels.get("complete"):
        raise RuntimeError("annotation metadata download is incomplete")
    source = labels.get("source", {})
    resolved_revision = source.get("resolved_repository_revision")
    post_revision = source.get("post_download_repository_revision")
    if (
        resolved_revision != EXPECTED_DATASET_REVISION
        or post_revision != EXPECTED_DATASET_REVISION
    ):
        raise RuntimeError("annotation metadata revision is not frozen")

    rows = labels.get("rows", [])
    rows_by_id = {str(row["image_id"]): row for row in rows}
    if len(rows_by_id) != len(rows):
        raise RuntimeError("duplicate official annotation image IDs")
    if any(str(row.get("split")) != "train" for row in rows):
        raise RuntimeError("non-train row found in train annotation result")

    test_path = rooted(args.bdd_oia_test)
    test_records = read_jsonl(test_path)
    model_paths = [rooted(path) for path in model_manifest_names]
    prior_paths = [rooted(path) for path in prior_manifest_names]
    model_records = [
        record for path in model_paths for record in read_jsonl(path)
    ]
    prior_records = [
        record for path in prior_paths for record in read_jsonl(path)
    ]

    model_names = manifest_names(model_records)
    model_groups = manifest_groups(model_records)
    prior_names = manifest_names(prior_records)
    prior_groups = manifest_groups(prior_records)

    keyframes = [
        record
        for record in test_records
        if is_keyframe(str(record["file_name"]))
    ]
    single_state = [
        record
        for record in keyframes
        if sole_target_state(record) is not None
    ]

    excluded_by_filename = []
    excluded_by_group = []
    eligible_after_name_group = []
    for record in single_state:
        name = str(record["file_name"])
        group = clip_group(name)
        if name in model_names or name in prior_names:
            excluded_by_filename.append(name)
            continue
        if group in model_groups or group in prior_groups:
            excluded_by_group.append(name)
            continue
        eligible_after_name_group.append(record)

    proposed_candidates = []
    no_train_annotation = []
    state_mismatch = Counter()
    for record in eligible_after_name_group:
        name = str(record["file_name"])
        image_id = Path(name).stem
        row = rows_by_id.get(image_id)
        if row is None:
            no_train_annotation.append(name)
            continue
        target_state = sole_target_state(record)
        if target_state is None:
            raise AssertionError("single-state eligibility changed")
        boxes = state_boxes(row, target_state)
        if not boxes:
            state_mismatch[target_state] += 1
            continue
        proposed_candidates.append(
            {
                "file_name": name,
                "clip_group": clip_group(name),
                "target_state": target_state,
                "official_image_id": image_id,
                "official_split": str(row["split"]),
                "official_width": int(row["width"]),
                "official_height": int(row["height"]),
                "official_state_boxes_xyxy": boxes,
                "official_state_box_count": len(boxes),
            }
        )

    image_root = rooted(args.image_root)
    names_to_hash = (
        model_names
        | prior_names
        | {str(record["file_name"]) for record in single_state}
    )
    image_hashes, missing_images = hash_named_images(
        names_to_hash, image_root
    )
    model_prior_hashes = {
        image_hashes[name]
        for name in model_names | prior_names
        if name in image_hashes
    }

    for candidate in proposed_candidates:
        candidate_hash = image_hashes.get(candidate["file_name"])
        candidate["image_sha256"] = candidate_hash
        candidate["hash_overlaps_excluded_population"] = (
            candidate_hash in model_prior_hashes
            if candidate_hash is not None
            else None
        )

    candidate_hash_counts = Counter(
        candidate["image_sha256"]
        for candidate in proposed_candidates
        if candidate["image_sha256"] is not None
    )
    hash_overlap_candidates = [
        candidate["file_name"]
        for candidate in proposed_candidates
        if candidate["hash_overlaps_excluded_population"]
    ]
    duplicate_hashes = {
        digest: count
        for digest, count in candidate_hash_counts.items()
        if count > 1
    }

    candidate_names = {
        candidate["file_name"] for candidate in proposed_candidates
    }
    candidate_groups = {
        candidate["clip_group"] for candidate in proposed_candidates
    }
    post_filename_overlap = sorted(
        candidate_names & (model_names | prior_names)
    )
    post_group_overlap = sorted(
        candidate_groups & (model_groups | prior_groups)
    )

    gate_1_passed = (
        not post_filename_overlap
        and not post_group_overlap
        and not hash_overlap_candidates
        and not duplicate_hashes
        and not missing_images
    )
    counts_by_state = Counter(
        candidate["target_state"] for candidate in proposed_candidates
    )
    gate_2_passed = (
        gate_1_passed
        and len(proposed_candidates) >= int(thresholds["minimum_total"])
        and counts_by_state["red"] >= int(thresholds["minimum_red"])
        and counts_by_state["green"] >= int(thresholds["minimum_green"])
        and len(candidate_groups)
        >= int(thresholds["minimum_independent_clip_groups"])
    )
    if not gate_1_passed:
        decision = "STOP_CEG_INDEPENDENCE"
    elif not gate_2_passed:
        decision = "STOP_CEG_POPULATION_NO_V6"
    else:
        decision = "GO_FREEZE_V5_GENERATOR_NO_MODEL_OUTPUTS"

    candidates_path = rooted(args.candidate_manifest)
    write_jsonl(candidates_path, proposed_candidates)
    candidate_manifest_hash = sha256_file(candidates_path)

    summary = {
        "protocol": {
            "path": project_relative(protocol_path),
            "sha256": sha256_file(protocol_path),
            "status": protocol["status"],
            "frozen_input_checks": frozen_input_checks,
        },
        "annotation_metadata": {
            "path": project_relative(label_path),
            "sha256": sha256_file(label_path),
            "resolved_repository_revision": resolved_revision,
            "post_download_repository_revision": post_revision,
            "requested_keyframe_ids": labels[
                "requested_keyframe_ids"
            ],
            "matched_train_rows": len(rows),
            "unmatched_keyframe_ids": len(
                labels.get("unmatched_keyframe_ids", [])
            ),
            "retained_fields_only": True,
            "image_bytes_retained": False,
            "embeddings_retained": False,
        },
        "population_flow": {
            "bdd_oia_test_records": len(test_records),
            "keyframes_only": len(keyframes),
            "single_red_or_green_rationale": len(single_state),
            "excluded_exact_filename": len(excluded_by_filename),
            "excluded_clip_group": len(excluded_by_group),
            "eligible_after_filename_group_exclusion": len(
                eligible_after_name_group
            ),
            "without_train_annotation_row": len(no_train_annotation),
            "official_state_mismatch": dict(state_mismatch),
            "official_state_matched_proposed": len(
                proposed_candidates
            ),
            "official_state_matched_red": counts_by_state["red"],
            "official_state_matched_green": counts_by_state["green"],
            "independent_clip_groups": len(candidate_groups),
        },
        "independence_gate": {
            "post_selection_filename_overlap_count": len(
                post_filename_overlap
            ),
            "post_selection_clip_group_overlap_count": len(
                post_group_overlap
            ),
            "candidate_hash_overlap_count": len(
                hash_overlap_candidates
            ),
            "within_pool_duplicate_hash_count": sum(
                count - 1 for count in duplicate_hashes.values()
            ),
            "missing_required_image_file_count": len(missing_images),
            "passed": gate_1_passed,
            "diagnostics": {
                "filename_overlaps": post_filename_overlap,
                "clip_group_overlaps": post_group_overlap,
                "hash_overlap_candidates": hash_overlap_candidates,
                "duplicate_hashes": duplicate_hashes,
                "missing_required_images": missing_images,
            },
        },
        "population_gate": {
            "minimum_total": int(thresholds["minimum_total"]),
            "minimum_red": int(thresholds["minimum_red"]),
            "minimum_green": int(thresholds["minimum_green"]),
            "minimum_independent_clip_groups": int(
                thresholds["minimum_independent_clip_groups"]
            ),
            "evaluated": gate_1_passed,
            "passed": gate_2_passed,
        },
        "candidate_manifest": {
            "path": project_relative(candidates_path),
            "sha256": candidate_manifest_hash,
            "rows": len(proposed_candidates),
            "contains_pixels": False,
            "contains_model_outputs": False,
        },
        "prohibited_actions_check": {
            "masks_generated": False,
            "model_checkpoints_opened": False,
            "logits_or_prediction_caches_read": False,
            "training_run": False,
        },
        "decision": decision,
        "next_action": (
            "Freeze the generator on the old development pool before the "
            "one-shot v5 generation; continue to prohibit model outputs."
            if gate_2_passed
            else (
                "Formally end the CEG mainline; do not lower thresholds, "
                "start v6, or substitute another dataset."
            )
        ),
    }
    output_path = rooted(args.output)
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
