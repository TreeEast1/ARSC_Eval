"""Build the outcome-blind graded association maps for Round 8."""

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
OUTPUT_NPZ = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_maps.npz"
)
OUTPUT_JSON = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_map_manifest.json"
)
EXPECTED_CACHE_SHA256 = (
    "0794249465A4EFEDB5177E8B74CC76C4537B4044411EE17E7BACBC66FA6E47A3"
)
EXPECTED_FILENAME_SHA256 = (
    "9D9D4E74272AB3A71390B4204CE56F1831350A29EED009111EF1AD5A29026DF6"
)
SALT = "ARSC_ROUND8_GRADED_ASSOCIATION_V1"
SEVERITY_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
EXPECTED_ACTIVE_IMAGES = {
    0.0: 0,
    0.25: 1140,
    0.5: 2278,
    0.75: 3418,
    1.0: 4557,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).tobytes()
    ).hexdigest().upper()


def severity_key(value: float) -> str:
    return f"q_{int(round(value * 100)):03d}"


def main() -> int:
    if OUTPUT_NPZ.exists() or OUTPUT_JSON.exists():
        raise RuntimeError(
            "Round 8 map artifact already exists; do not overwrite"
        )
    cache_hash = sha256_file(CACHE_PATH)
    if cache_hash != EXPECTED_CACHE_SHA256:
        raise RuntimeError("seed-43 frozen cache hash mismatch")
    with np.load(CACHE_PATH, allow_pickle=False) as archive:
        file_names = np.asarray(archive["test_file_names"]).copy()
        keys_read = ["test_file_names"]
    if array_sha256(file_names) != EXPECTED_FILENAME_SHA256:
        raise RuntimeError("canonical filename-order hash mismatch")
    names = file_names.tolist()
    groups = [clip_group(value) for value in names]
    unique_groups = sorted(set(groups))
    group_to_id = {
        group: index for index, group in enumerate(unique_groups)
    }
    group_ids = np.asarray(
        [group_to_id[group] for group in groups], dtype=np.int64
    )

    cycles, cycle_diagnostics = build_clip_safe_cycles(names, SALT)
    maps = graded_source_maps(
        len(names), cycles, SEVERITY_GRID
    )
    audit = validate_graded_maps(names, maps)
    observed_active = {
        severity: int(
            np.sum(source != np.arange(len(names), dtype=np.int64))
        )
        for severity, source in maps.items()
    }
    if observed_active != EXPECTED_ACTIVE_IMAGES:
        raise RuntimeError(
            f"unexpected active-image counts: {observed_active}"
        )
    if not audit["all_passed"]:
        raise RuntimeError("graded map invariant audit failed")

    pair_cycles = np.asarray(cycles[:-1], dtype=np.int64)
    triplet = np.asarray(cycles[-1], dtype=np.int64)
    arrays: dict[str, np.ndarray] = {
        "file_names": file_names,
        "clip_group_names": np.asarray(unique_groups),
        "clip_group_ids": group_ids,
        "pair_cycles_in_activation_order": pair_cycles,
        "final_triplet_cycle": triplet,
    }
    for severity, source in maps.items():
        arrays[f"{severity_key(severity)}_source_indices"] = source
    np.savez_compressed(OUTPUT_NPZ, **arrays)

    group_sizes = Counter(groups)
    size_histogram = Counter(group_sizes.values())
    by_severity: dict[str, Any] = {}
    for severity, source in maps.items():
        key = severity_key(severity)
        values = audit["by_severity"][str(severity)]
        by_severity[key] = {
            "nominal_q": severity,
            "source_array_key": f"{key}_source_indices",
            "source_array_sha256": array_sha256(source),
            "active_images": values["active_images"],
            "active_fraction": values["active_fraction"],
            "fixed_points": values["fixed_points"],
            "bijection": values["bijection"],
            "active_same_filename_pairs": values[
                "active_same_filename_pairs"
            ],
            "active_same_clip_pairs": values[
                "active_same_clip_pairs"
            ],
            "nested_superset": values["nested_superset"],
        }
    core_path = (
        PROJECT_ROOT / "src" / "arsc_eval" / "graded_association.py"
    )
    test_path = (
        PROJECT_ROOT / "tests" / "test_graded_association.py"
    )
    manifest = {
        "study": "Round 8 outcome-blind graded association maps",
        "status": "FROZEN_BEFORE_METRIC_RESPONSE_OUTCOMES",
        "construction_inputs": {
            "cache_path": CACHE_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "cache_sha256": cache_hash,
            "archive_keys_read": keys_read,
            "filename_array_sha256": array_sha256(file_names),
            "targets_read": False,
            "logits_or_probabilities_read": False,
            "prior_metric_results_read": False,
        },
        "construction": {
            "salt": SALT,
            "depends_only_on": [
                "canonical filename strings",
                "clip groups derived by removing terminal _1 or _3",
                "fixed salt",
                "frozen severity grid"
            ],
            "sample_count": len(names),
            "severity_grid": list(SEVERITY_GRID),
            "cycle_diagnostics": cycle_diagnostics,
            "pair_cycles": int(len(pair_cycles)),
            "final_triplet_cycle": triplet.tolist(),
            "all_cycles_activated_only_at_q1": True,
        },
        "clip_population": {
            "clip_groups": len(unique_groups),
            "size_histogram": {
                str(size): count
                for size, count in sorted(size_histogram.items())
            },
            "images_in_non_singleton_groups": int(
                sum(
                    size * count
                    for size, count in size_histogram.items()
                    if size > 1
                )
            ),
            "maximum_group_size": max(group_sizes.values()),
            "clip_group_ids_sha256": array_sha256(group_ids),
        },
        "map_audit": {
            "all_passed": audit["all_passed"],
            "by_severity": by_severity,
            "prevalence_preservation_reason": (
                "Every q-specific source array is a global bijection and "
                "identity outside a nested union of complete cycles."
            ),
        },
        "artifact": {
            "path": OUTPUT_NPZ.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": sha256_file(OUTPUT_NPZ),
            "bytes": OUTPUT_NPZ.stat().st_size,
            "array_keys": sorted(arrays),
            "contains_targets": False,
            "contains_logits_probabilities_or_metric_outcomes": False,
        },
        "implementation": {
            "builder": {
                "path": Path(__file__).resolve().relative_to(
                    PROJECT_ROOT
                ).as_posix(),
                "sha256": sha256_file(Path(__file__).resolve()),
            },
            "core": {
                "path": core_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(core_path),
            },
            "synthetic_tests": {
                "path": test_path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(test_path),
            },
        },
        "failure_policy": (
            "Any later hash or invariant mismatch stops Round 8; do not "
            "change the salt, cycle order, grid, or maps."
        ),
    }
    write_json(OUTPUT_JSON, manifest)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "clip_population": manifest["clip_population"],
                "map_audit": manifest["map_audit"],
                "artifact": manifest["artifact"],
                "manifest": OUTPUT_JSON.relative_to(
                    PROJECT_ROOT
                ).as_posix(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
