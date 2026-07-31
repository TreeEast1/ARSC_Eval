"""Build the 20 outcome-blind graded maps frozen for Round 9.

The builder reads only the canonical test filename array from the frozen
seed-43 cache.  It must run before any new-map q>0 metric outcome is computed.
Every prefixed salt is retained; a failure stops the whole build.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.graded_association import (
    build_clip_safe_cycles,
    clip_group,
    graded_source_maps,
    validate_graded_maps,
)
from arsc_eval.utils import write_json


CACHE_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "rq1_seed_43"
    / "prediction_cache"
    / "rq1_lossless.npz"
)
PROTOCOL_PATH = (
    PROJECT_ROOT / "outputs" / "validity" / "round9_multimap_protocol.json"
)
OUTPUT_NPZ = (
    PROJECT_ROOT / "outputs" / "validity" / "round9_multimap_maps.npz"
)
OUTPUT_JSON = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_map_manifest.json"
)

EXPECTED_CACHE_SHA256 = (
    "0794249465A4EFEDB5177E8B74CC76C4537B4044411EE17E7BACBC66FA6E47A3"
)
EXPECTED_FILENAME_SHA256 = (
    "9D9D4E74272AB3A71390B4204CE56F1831350A29EED009111EF1AD5A29026DF6"
)
MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
SALTS = tuple(f"arsc-round9-map{index:02d}" for index in range(20))
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
EXPECTED_ACTIVE_IMAGES = (0, 1140, 2278, 3418, 4557)


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
        "Round 9 map output already exists; refusing to overwrite",
    )
    require(len(set(MAP_IDS)) == 20, "map IDs must be unique")
    require(len(set(SALTS)) == 20, "salts must be unique")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    require(
        protocol["status"]
        == "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "Round 9 protocol is not in the required preoutcome state",
    )
    require(
        tuple(protocol["map_realizations"]["map_ids"]) == MAP_IDS,
        "protocol map IDs differ from builder constants",
    )
    require(
        tuple(protocol["map_realizations"]["salts"]) == SALTS,
        "protocol salts differ from builder constants",
    )
    require(
        sha256_file(CACHE_PATH) == EXPECTED_CACHE_SHA256,
        "frozen seed-43 cache hash mismatch",
    )

    with np.load(CACHE_PATH, allow_pickle=False) as archive:
        file_names = np.asarray(archive["test_file_names"]).copy()
        archive_keys_read = ["test_file_names"]
    require(
        array_sha256(file_names) == EXPECTED_FILENAME_SHA256,
        "canonical filename-order hash mismatch",
    )
    names = [str(value) for value in file_names]
    clip_names = [clip_group(value) for value in names]
    unique_clips = sorted(set(clip_names))
    clip_to_id = {
        clip_name: index for index, clip_name in enumerate(unique_clips)
    }
    clip_group_ids = np.asarray(
        [clip_to_id[value] for value in clip_names], dtype=np.int64
    )
    sample_indices = np.arange(len(names), dtype=np.int64)

    arrays: dict[str, np.ndarray] = {
        "file_names": file_names,
        "clip_group_names": np.asarray(unique_clips),
        "clip_group_ids": clip_group_ids,
        "q_values": np.asarray(Q_VALUES, dtype=np.float64),
        "active_images": np.asarray(
            EXPECTED_ACTIVE_IMAGES, dtype=np.int64
        ),
    }
    by_map: dict[str, Any] = {}
    q1_hashes = []
    for map_id, salt in zip(MAP_IDS, SALTS):
        cycles, cycle_diagnostics = build_clip_safe_cycles(names, salt)
        maps = graded_source_maps(len(names), cycles, Q_VALUES)
        audit = validate_graded_maps(names, maps)
        source_maps = np.stack([maps[q] for q in Q_VALUES])
        observed_active = tuple(
            int(np.count_nonzero(source != sample_indices))
            for source in source_maps
        )
        require(
            audit["all_passed"],
            f"{map_id} failed the filename/clip map audit",
        )
        require(
            observed_active == EXPECTED_ACTIVE_IMAGES,
            f"{map_id} has unexpected active-image counts",
        )
        require(
            all(
                observed_active[index]
                < observed_active[index + 1]
                for index in range(len(observed_active) - 1)
            ),
            f"{map_id} active sets are not strictly nested by count",
        )
        require(
            int(np.count_nonzero(source_maps[-1] == sample_indices))
            == 0,
            f"{map_id} q=1 contains a fixed point",
        )

        pair_cycles = np.asarray(cycles[:-1], dtype=np.int64)
        triplet = np.asarray(cycles[-1], dtype=np.int64)
        arrays[f"{map_id}_pair_cycles"] = pair_cycles
        arrays[f"{map_id}_final_triplet"] = triplet
        arrays[f"{map_id}_source_maps"] = source_maps

        source_hashes = [
            array_sha256(source) for source in source_maps
        ]
        q1_hashes.append(source_hashes[-1])
        by_map[map_id] = {
            "salt": salt,
            "cycle_diagnostics": cycle_diagnostics,
            "pair_cycle_count": int(len(pair_cycles)),
            "final_triplet": triplet.tolist(),
            "source_array_key": f"{map_id}_source_maps",
            "source_array_sha256": array_sha256(source_maps),
            "source_sha256_by_q": {
                str(q): digest
                for q, digest in zip(Q_VALUES, source_hashes)
            },
            "active_images": list(observed_active),
            "audit": audit,
            "all_complete_cycles_only": True,
            "q1_fixed_points": 0,
        }

    require(
        len(set(q1_hashes)) == len(MAP_IDS),
        "the 20 q=1 source maps are not unique; STOP without replacement",
    )
    np.savez_compressed(OUTPUT_NPZ, **arrays)

    clip_size_histogram = Counter(
        Counter(clip_names).values()
    )
    core_path = (
        PROJECT_ROOT / "src" / "arsc_eval" / "graded_association.py"
    )
    test_path = PROJECT_ROOT / "tests" / "test_graded_association.py"
    manifest = {
        "study": "Round 9 outcome-blind 20-map construction",
        "status": "FROZEN_BEFORE_NEW_MAP_Q_GREATER_THAN_ZERO_OUTCOMES",
        "protocol": {
            "path": relative(PROTOCOL_PATH),
            "sha256": sha256_file(PROTOCOL_PATH),
        },
        "construction_inputs": {
            "cache_path": relative(CACHE_PATH),
            "cache_sha256": sha256_file(CACHE_PATH),
            "archive_keys_read": archive_keys_read,
            "filename_array_sha256": array_sha256(file_names),
            "targets_read": False,
            "predictions_read": False,
            "logits_or_probabilities_read": False,
            "confidence_or_errors_read": False,
            "new_map_q_greater_than_zero_metric_outcomes_read": False,
        },
        "construction": {
            "algorithm": (
                "Round 8 deterministic salted filename/clip cycle builder"
            ),
            "map_ids": list(MAP_IDS),
            "salts": list(SALTS),
            "severity_grid": list(Q_VALUES),
            "expected_active_images": list(EXPECTED_ACTIVE_IMAGES),
            "salt_replacement_allowed": False,
            "all_salts_unique": len(set(SALTS)) == 20,
            "all_q1_source_maps_unique": len(set(q1_hashes)) == 20,
            "depends_only_on": [
                "canonical filename strings",
                "clip groups derived by removing terminal _1 or _3",
                "prefixed fixed salt",
                "frozen q grid",
            ],
        },
        "clip_population": {
            "sample_count": len(names),
            "clip_groups": len(unique_clips),
            "size_histogram": {
                str(size): count
                for size, count in sorted(clip_size_histogram.items())
            },
            "clip_group_ids_sha256": array_sha256(clip_group_ids),
        },
        "maps": by_map,
        "artifact": {
            "path": relative(OUTPUT_NPZ),
            "sha256": sha256_file(OUTPUT_NPZ),
            "bytes": OUTPUT_NPZ.stat().st_size,
            "array_count": len(arrays),
            "array_keys": sorted(arrays),
            "contains_targets_predictions_logits_probabilities_confidence_errors_or_metric_outcomes": (
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
            "Any salt, hash, uniqueness, cycle, nesting, bijection, "
            "same-file, same-clip, or q1 fixed-point failure stops all of "
            "Round 9; do not drop or replace a prefixed salt."
        ),
    }
    write_json(OUTPUT_JSON, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "maps": len(MAP_IDS),
                "all_q1_source_maps_unique": len(set(q1_hashes)) == 20,
                "artifact": manifest["artifact"],
                "manifest": relative(OUTPUT_JSON),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
