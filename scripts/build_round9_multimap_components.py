"""Build one outcome-blind association-component partition per Round 9 map."""

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


PROTOCOL_PATH = (
    PROJECT_ROOT / "outputs" / "validity" / "round9_multimap_protocol.json"
)
MAP_PATH = (
    PROJECT_ROOT / "outputs" / "validity" / "round9_multimap_maps.npz"
)
MAP_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_map_manifest.json"
)
OUTPUT_NPZ = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_components.npz"
)
OUTPUT_JSON = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_component_manifest.json"
)

MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
SAMPLE_COUNT = 4557
CLIP_COUNT = 3904


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).tobytes()
    ).hexdigest().upper()


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    require(
        not OUTPUT_NPZ.exists() and not OUTPUT_JSON.exists(),
        "Round 9 component output already exists; refusing to overwrite",
    )
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    map_manifest = json.loads(
        MAP_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    require(
        protocol["status"]
        == "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "Round 9 protocol is not in its preoutcome state",
    )
    require(
        map_manifest["status"]
        == "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "Round 9 map manifest is not in its preoutcome state",
    )
    require(
        map_manifest["protocol"]["sha256"]
        == sha256_file(PROTOCOL_PATH),
        "map manifest does not bind the current protocol",
    )
    require(
        map_manifest["artifact"]["sha256"] == sha256_file(MAP_PATH),
        "map artifact hash does not match its manifest",
    )

    with np.load(MAP_PATH, allow_pickle=False) as archive:
        available = set(archive.files)
        required = {"clip_group_ids"} | {
            f"{map_id}_source_maps" for map_id in MAP_IDS
        }
        require(
            required <= available,
            "Round 9 map artifact is missing required arrays",
        )
        clip_group_ids = archive["clip_group_ids"].copy()
        source_maps_by_id = {
            map_id: archive[f"{map_id}_source_maps"].copy()
            for map_id in MAP_IDS
        }
        archive_keys_read = [
            "clip_group_ids",
            *[f"{map_id}_source_maps" for map_id in MAP_IDS],
        ]

    require(
        clip_group_ids.shape == (SAMPLE_COUNT,),
        "clip-group array has the wrong shape",
    )
    require(
        len(np.unique(clip_group_ids)) == CLIP_COUNT,
        "clip-group array has the wrong population",
    )

    arrays: dict[str, np.ndarray] = {}
    by_map: dict[str, Any] = {}
    component_partition_hashes = []
    for map_id in MAP_IDS:
        source_maps = source_maps_by_id[map_id]
        require(
            source_maps.shape == (len(Q_VALUES), SAMPLE_COUNT),
            f"{map_id} source maps have the wrong shape",
        )
        component_by_clip, component_by_image = (
            build_association_components(
                clip_group_ids, source_maps[-1]
            )
        )
        component_clip_offsets, component_clip_ids = pack_members(
            component_by_clip
        )
        component_image_offsets, component_image_indices = pack_members(
            component_by_image
        )
        source_mapping = {
            f"q_{int(round(q * 100)):03d}": source_maps[index]
            for index, q in enumerate(Q_VALUES)
        }
        audit = validate_association_components(
            clip_group_ids,
            source_mapping,
            component_by_clip,
            component_by_image,
        )
        require(
            audit["all_maps_passed"],
            f"{map_id} component closure/restricted-bijection audit failed",
        )
        require(
            audit["minimum_clips_per_component"] >= 2,
            f"{map_id} contains a singleton clip component",
        )
        require(
            audit["minimum_images_per_component"] >= 2,
            f"{map_id} contains a singleton image component",
        )

        map_arrays = {
            "component_id_by_clip": component_by_clip,
            "component_id_by_image": component_by_image,
            "component_clip_offsets": component_clip_offsets,
            "component_clip_ids": component_clip_ids,
            "component_image_offsets": component_image_offsets,
            "component_image_indices": component_image_indices,
        }
        for name, values in map_arrays.items():
            arrays[f"{map_id}_{name}"] = values
        partition_hash = array_sha256(component_by_image)
        component_partition_hashes.append(partition_hash)
        by_map[map_id] = {
            "source_maps_sha256": array_sha256(source_maps),
            "component_count": audit["component_count"],
            "partition_sha256": partition_hash,
            "exact_audit": audit,
            "arrays": {
                name: {
                    "key": f"{map_id}_{name}",
                    "shape": list(values.shape),
                    "dtype": str(values.dtype),
                    "sha256": array_sha256(values),
                }
                for name, values in map_arrays.items()
            },
            "bootstrap_contract": {
                "unit": "association component",
                "component_draws_per_occurrence": audit[
                    "component_count"
                ],
                "complete_membership_when_selected": True,
                "repeated_selection_retains_membership_and_multiplicity": (
                    True
                ),
            },
        }

    np.savez_compressed(OUTPUT_NPZ, **arrays)
    core_path = (
        PROJECT_ROOT / "src" / "arsc_eval" / "association_components.py"
    )
    test_path = PROJECT_ROOT / "tests" / "test_association_components.py"
    counts = [
        by_map[map_id]["component_count"] for map_id in MAP_IDS
    ]
    report: dict[str, Any] = {
        "study": "Round 9 per-map outcome-blind association components",
        "status": "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "derivation": {
            "for_each_map": (
                "connected components of clip(i)--clip(q1_source[i])"
            ),
            "map_count": len(MAP_IDS),
            "targets_predictions_logits_probabilities_confidences_errors_or_metric_outcomes_read": (
                False
            ),
            "new_map_q_greater_than_zero_metric_outcomes_read": False,
            "all_component_partitions_unique": (
                len(set(component_partition_hashes)) == len(MAP_IDS)
            ),
        },
        "frozen_inputs": {
            "protocol": {
                "path": relative(PROTOCOL_PATH),
                "sha256": sha256_file(PROTOCOL_PATH),
            },
            "map_artifact": {
                "path": relative(MAP_PATH),
                "sha256": sha256_file(MAP_PATH),
                "archive_keys_read": archive_keys_read,
            },
            "map_manifest": {
                "path": relative(MAP_MANIFEST_PATH),
                "sha256": sha256_file(MAP_MANIFEST_PATH),
            },
            "clip_group_ids_sha256": array_sha256(clip_group_ids),
        },
        "component_count_summary": {
            "minimum": int(min(counts)),
            "maximum": int(max(counts)),
            "mean": float(np.mean(counts)),
            "by_map": {
                map_id: by_map[map_id]["component_count"]
                for map_id in MAP_IDS
            },
        },
        "maps": by_map,
        "artifact": {
            "path": relative(OUTPUT_NPZ),
            "sha256": sha256_file(OUTPUT_NPZ),
            "bytes": OUTPUT_NPZ.stat().st_size,
            "array_count": len(arrays),
            "array_keys": sorted(arrays),
            "contains_only_integer_partition_indices": True,
            "contains_targets_predictions_logits_probabilities_confidences_errors_or_metric_outcomes": (
                False
            ),
        },
        "implementation": {
            "builder": {
                "path": relative(Path(__file__).resolve()),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "Round8_core_reused_without_change": {
                "path": relative(core_path),
                "sha256": sha256_file(core_path),
            },
            "existing_synthetic_tests": {
                "path": relative(test_path),
                "sha256": sha256_file(test_path),
            },
        },
        "failure_policy": (
            "Any map-specific hash, partition, closure, restricted "
            "bijection, or bootstrap-membership failure stops Round 9; "
            "do not drop or replace the map/salt."
        ),
    }
    write_json(OUTPUT_JSON, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "component_count_summary": report[
                    "component_count_summary"
                ],
                "artifact": report["artifact"],
                "manifest": relative(OUTPUT_JSON),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
