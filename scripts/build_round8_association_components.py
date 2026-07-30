"""Freeze the outcome-blind association-component partition for Round 8."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.association_components import (
    build_association_components,
    pack_members,
    validate_association_components,
)
from arsc_eval.utils import write_json


MAP_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_maps.npz"
)
MAP_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_map_manifest.json"
)
OUTPUT_NPZ = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_association_components.npz"
)
OUTPUT_JSON = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_association_component_manifest.json"
)
EXPECTED_MAP_SHA256 = (
    "8685E1A4605B5D6355A432BC6CA03CF61930BAB23D41D899478A5C1D8FC47ED1"
)
EXPECTED_MAP_MANIFEST_SHA256 = (
    "73B89C3438262BA272E0E90EDC2A6F9408B196CCBD4A30D9FA6FFFA798C273DC"
)
EXPECTED_CLIP_HASH = (
    "CBCF3E385E0FEBB22B364047BBB219CD959913F89C89663D523F6829F17DE92B"
)
EXPECTED_Q1_HASH = (
    "CEF0D9B1E82DCECC6B4D31C1664DD868E7B64FA6F065244A6539D27C1CE2D446"
)
EXPECTED_COMPONENT_COUNT = 1625
EXPECTED_CLIP_HISTOGRAM = {
    "2": 1191,
    "3": 291,
    "4": 101,
    "5": 22,
    "6": 7,
    "7": 11,
    "8": 2,
}
EXPECTED_MAXIMUM_IMAGES = 14
SOURCE_KEYS = (
    "q_000_source_indices",
    "q_025_source_indices",
    "q_050_source_indices",
    "q_075_source_indices",
    "q_100_source_indices",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(values)
    return hashlib.sha256(contiguous.tobytes()).hexdigest().upper()


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(
        sha256_file(MAP_PATH) == EXPECTED_MAP_SHA256,
        "frozen Round 8 map artifact hash mismatch",
    )
    require(
        sha256_file(MAP_MANIFEST_PATH) == EXPECTED_MAP_MANIFEST_SHA256,
        "frozen Round 8 map manifest hash mismatch",
    )
    map_manifest = json.loads(MAP_MANIFEST_PATH.read_text(encoding="utf-8"))

    with np.load(MAP_PATH, allow_pickle=False) as archive:
        available_keys = set(archive.files)
        required_keys = {"clip_group_ids", *SOURCE_KEYS}
        require(
            required_keys <= available_keys,
            "frozen map artifact is missing required arrays",
        )
        clip_group_ids = archive["clip_group_ids"].copy()
        source_maps = {key: archive[key].copy() for key in SOURCE_KEYS}

    require(
        array_sha256(clip_group_ids) == EXPECTED_CLIP_HASH,
        "clip-group array hash mismatch",
    )
    require(
        array_sha256(source_maps["q_100_source_indices"])
        == EXPECTED_Q1_HASH,
        "q=1 source-map hash mismatch",
    )
    for key, values in source_maps.items():
        manifest_item = map_manifest["map_audit"]["by_severity"][
            key.replace("_source_indices", "")
        ]
        require(
            array_sha256(values) == manifest_item["source_array_sha256"],
            f"{key} hash mismatch",
        )

    component_by_clip, component_by_image = build_association_components(
        clip_group_ids,
        source_maps["q_100_source_indices"],
    )
    component_clip_offsets, component_clip_ids = pack_members(
        component_by_clip
    )
    component_image_offsets, component_image_indices = pack_members(
        component_by_image
    )
    audit = validate_association_components(
        clip_group_ids,
        source_maps,
        component_by_clip,
        component_by_image,
    )
    require(audit["all_maps_passed"], "association-component audit failed")
    require(
        audit["component_count"] == EXPECTED_COMPONENT_COUNT,
        "unexpected association-component count",
    )
    require(
        audit["clip_count_histogram"] == EXPECTED_CLIP_HISTOGRAM,
        "unexpected component clip-count histogram",
    )
    require(
        audit["maximum_images_per_component"] == EXPECTED_MAXIMUM_IMAGES,
        "unexpected maximum component image count",
    )

    arrays: dict[str, np.ndarray] = {
        "component_id_by_clip": component_by_clip,
        "component_id_by_image": component_by_image,
        "component_clip_offsets": component_clip_offsets,
        "component_clip_ids": component_clip_ids,
        "component_image_offsets": component_image_offsets,
        "component_image_indices": component_image_indices,
    }
    np.savez_compressed(OUTPUT_NPZ, **arrays)

    core_path = (
        PROJECT_ROOT / "src" / "arsc_eval" / "association_components.py"
    )
    test_path = PROJECT_ROOT / "tests" / "test_association_components.py"
    report: dict[str, Any] = {
        "study": "Round 8 outcome-blind association components",
        "status": "FROZEN_BEFORE_METRIC_RESPONSE_OUTCOMES",
        "derivation": {
            "nodes": "3904 clip groups",
            "edges": (
                "undirected clip(i)--clip(q1_source_map[i]) for every image i"
            ),
            "connected_components": EXPECTED_COMPONENT_COUNT,
            "depends_only_on": [
                "frozen clip_group_ids",
                "frozen q=1 source-index map",
            ],
            "targets_read": False,
            "logits_probabilities_predictions_confidences_read": False,
            "metric_outcomes_read": False,
        },
        "frozen_inputs": {
            "map_artifact": {
                "path": relative(MAP_PATH),
                "sha256": sha256_file(MAP_PATH),
                "archive_keys_read": ["clip_group_ids", *SOURCE_KEYS],
            },
            "map_manifest": {
                "path": relative(MAP_MANIFEST_PATH),
                "sha256": sha256_file(MAP_MANIFEST_PATH),
            },
            "clip_group_ids_sha256": array_sha256(clip_group_ids),
            "source_map_sha256": {
                key: array_sha256(values)
                for key, values in source_maps.items()
            },
        },
        "exact_audit": audit,
        "arrays": {
            key: {
                "shape": list(values.shape),
                "dtype": str(values.dtype),
                "sha256": array_sha256(values),
            }
            for key, values in arrays.items()
        },
        "artifact": {
            "path": relative(OUTPUT_NPZ),
            "sha256": sha256_file(OUTPUT_NPZ),
            "bytes": OUTPUT_NPZ.stat().st_size,
            "contains_only_integer_partition_indices": True,
            "contains_targets_logits_probabilities_predictions_confidences": (
                False
            ),
        },
        "bootstrap_contract": {
            "unit": "association component",
            "component_count": EXPECTED_COMPONENT_COUNT,
            "one_shared_component_multiset_per_replicate": True,
            "component_draws_per_replicate": EXPECTED_COMPONENT_COUNT,
            "complete_membership_when_selected": True,
            "repeated_selection_retains_full_membership_and_multiplicity": True,
        },
        "implementation": {
            "builder": {
                "path": relative(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "core": {
                "path": relative(core_path),
                "sha256": sha256_file(core_path),
            },
            "synthetic_tests": {
                "path": relative(test_path),
                "sha256": sha256_file(test_path),
            },
        },
        "failure_policy": (
            "Any hash, partition, closure, restricted-bijection, or bootstrap "
            "contract mismatch stops Round 8 before q-response outcomes."
        ),
    }
    write_json(OUTPUT_JSON, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
