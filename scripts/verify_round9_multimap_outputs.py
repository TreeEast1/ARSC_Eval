"""Independently reproduce all frozen Round 9 point and bootstrap outputs.

This verifier deliberately imports neither the Round 9 formal analysis script
nor any ``arsc_eval`` implementation module.  It extends the already
independent Round 8 sufficient-statistic implementation to every one of the 20
prefixed maps, then recreates the exact frozen map/seed/component RNG stream.

The audit checks:

* hashes and schemas of every formal result artifact;
* all primary and diagnostic point arrays for 20 maps x 5 seeds x 5 q values;
* all 400 map-by-seed bottlenecks and all reported grand curves;
* every selection, expanded-image count, and four-axis value in all 2,000
  hierarchical bootstrap replicates;
* all four preregistered gate decisions and their claim boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np

from verify_round8_graded_response_outputs import (
    ACTION_NAMES,
    AXIS_DIRECTIONS,
    MODELS,
    PERTURBATIONS,
    Q_VALUES,
    RATIONALE_NAMES,
    array_sha256,
    axis_bottlenecks,
    build_independent_primitives,
    curves_from_component_draw,
    harmonic_numbers,
    jaccard_samples,
    max_abs_difference,
    multilabel_detail,
    sha256_file,
    stable_aurc_detail,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDITY_DIR = PROJECT_ROOT / "outputs" / "validity"
ROUND8_PRIMITIVES_PATH = (
    VALIDITY_DIR / "round8_graded_response_primitives.npz"
)
MAP_PATH = VALIDITY_DIR / "round9_multimap_maps.npz"
COMPONENT_PATH = VALIDITY_DIR / "round9_multimap_components.npz"
FORMAL_PRIMITIVES_PATH = (
    VALIDITY_DIR / "round9_multimap_primitives.npz"
)
FORMAL_DRAWS_PATH = (
    VALIDITY_DIR / "round9_multimap_bootstrap_draws.npz"
)
RESULT_PATH = VALIDITY_DIR / "round9_multimap_results.json"
POINT_CSV_PATH = (
    VALIDITY_DIR / "round9_multimap_point_diagnostics.csv"
)
BOOTSTRAP_CSV_PATH = (
    VALIDITY_DIR / "round9_multimap_bootstrap_summary.csv"
)
AUDIT_PATH = (
    VALIDITY_DIR / "round9_multimap_independent_audit.json"
)
INDEPENDENT_DRAWS_PATH = (
    VALIDITY_DIR / "round9_multimap_independent_bootstrap_draws.npz"
)

MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
SEEDS = (43, 44, 45, 46, 47)
AXES = ("A", "R", "S", "C1")
AXIS_INDEX = {axis: index for index, axis in enumerate(AXES)}
REPLICATES = 2000
BOOTSTRAP_SEED = 20260809
COMPONENT_COUNT = 1625
SAMPLE_COUNT = 4557
FLOAT_TOLERANCE = 5e-13
RESULT_SHA256 = (
    "667C34891BADF1861757877DDE263A218652AA60B4B00E58E03421F7CE162735"
)

EXPECTED_FORMAL_PRIMITIVE_KEYS = {
    "map_ids",
    "seeds",
    "q_values",
    "axis_names",
    "A_micro_f1",
    "A_per_class_f1",
    "A_target_positive_count",
    "A_predicted_positive_count",
    "R_micro_f1",
    "R_per_class_f1",
    "R_target_positive_count",
    "R_predicted_positive_count",
    "S_diagnostics",
    "S_diagnostic_names",
    "C1_action_per_perturbation",
    "C1_rationale_per_perturbation",
    "perturbation_names",
    "action_class_names",
    "rationale_class_names",
    "A_primary_curves",
    "R_primary_curves",
    "S_primary_curves",
    "C1_primary_curves",
    "map_seed_axis_bottlenecks",
    "map_mean_axis_bottlenecks",
    "input_round8_primitives_sha256",
}
EXPECTED_DRAW_KEYS = {
    "A",
    "R",
    "S",
    "C1",
    "selected_map_positions",
    "selected_seed_positions",
    "expanded_image_counts",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--points-only",
        action="store_true",
        help="reproduce all point arrays but skip the 2,000 bootstrap draws",
    )
    return parser.parse_args()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    staging = path.with_name(path.name + ".tmp")
    require(not staging.exists(), f"staging output already exists: {staging}")
    with staging.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    os.replace(staging, path)


def write_npz_atomic(
    path: Path, arrays: dict[str, np.ndarray]
) -> None:
    staging = path.with_name(path.name + ".tmp")
    require(not staging.exists(), f"staging output already exists: {staging}")
    with staging.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(staging, path)


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> None:
    checks.append(
        {"name": name, "passed": bool(passed), "detail": detail}
    )


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key].copy() for key in archive.files}


def verify_hashes(
    result: dict[str, Any], checks: list[dict[str, Any]]
) -> dict[str, str]:
    observed: dict[str, str] = {}
    result_hash = sha256_file(RESULT_PATH)
    observed[str(RESULT_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/")] = (
        result_hash
    )
    add_check(
        checks,
        "formal_completion_result_hash",
        result_hash == RESULT_SHA256,
        {"expected": RESULT_SHA256, "observed": result_hash},
    )

    comparisons: dict[str, Any] = {}
    for relative_path, metadata in result["artifacts"].items():
        path = PROJECT_ROOT / relative_path
        digest = sha256_file(path)
        observed[relative_path] = digest
        comparisons[relative_path] = {
            "expected_sha256": metadata["sha256"],
            "observed_sha256": digest,
            "expected_bytes": int(metadata["bytes"]),
            "observed_bytes": path.stat().st_size,
        }
    add_check(
        checks,
        "formal_artifact_hashes_and_sizes",
        all(
            item["expected_sha256"] == item["observed_sha256"]
            and item["expected_bytes"] == item["observed_bytes"]
            for item in comparisons.values()
        ),
        comparisons,
    )

    provenance: dict[str, Any] = {}
    for name, metadata in result["provenance"].items():
        path = PROJECT_ROOT / metadata["path"]
        digest = sha256_file(path)
        observed[metadata["path"]] = digest
        provenance[name] = {
            "path": metadata["path"],
            "expected_sha256": metadata["sha256"],
            "observed_sha256": digest,
        }
    add_check(
        checks,
        "frozen_provenance_hashes",
        all(
            item["expected_sha256"] == item["observed_sha256"]
            for item in provenance.values()
        ),
        provenance,
    )
    return observed


def verify_schemas(
    raw: dict[str, np.ndarray],
    maps: dict[str, np.ndarray],
    components: dict[str, np.ndarray],
    formal: dict[str, np.ndarray],
    formal_draws: dict[str, np.ndarray],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_component_keys = {
        f"{map_id}_{suffix}"
        for map_id in MAP_IDS
        for suffix in (
            "component_id_by_clip",
            "component_id_by_image",
            "component_clip_offsets",
            "component_clip_ids",
            "component_image_offsets",
            "component_image_indices",
        )
    }
    expected_map_keys = {
        "file_names",
        "q_values",
        "active_images",
        "clip_group_names",
        "clip_group_ids",
    } | {
        f"{map_id}_{suffix}"
        for map_id in MAP_IDS
        for suffix in ("source_maps", "pair_cycles", "final_triplet")
    }
    component_counts = [
        len(components[f"{map_id}_component_image_offsets"]) - 1
        for map_id in MAP_IDS
    ]
    map_partition_checks = {
        map_id: bool(
            np.array_equal(
                np.sort(components[f"{map_id}_component_image_indices"]),
                np.arange(SAMPLE_COUNT, dtype=np.int64),
            )
            and np.array_equal(
                np.bincount(
                    components[f"{map_id}_component_id_by_image"],
                    minlength=COMPONENT_COUNT,
                ),
                np.diff(
                    components[f"{map_id}_component_image_offsets"]
                ),
            )
        )
        for map_id in MAP_IDS
    }
    detail = {
        "formal_primitive_key_count": len(formal),
        "formal_draw_key_count": len(formal_draws),
        "map_key_count": len(maps),
        "component_key_count": len(components),
        "component_counts_by_map": component_counts,
        "map_partitions_valid": map_partition_checks,
    }
    passed = bool(
        set(formal) == EXPECTED_FORMAL_PRIMITIVE_KEYS
        and set(formal_draws) == EXPECTED_DRAW_KEYS
        and set(maps) == expected_map_keys
        and set(components) == expected_component_keys
        and component_counts == [COMPONENT_COUNT] * len(MAP_IDS)
        and all(map_partition_checks.values())
        and np.array_equal(raw["file_names"], maps["file_names"])
        and np.array_equal(formal["map_ids"], np.asarray(MAP_IDS))
        and np.array_equal(formal["seeds"], np.asarray(SEEDS))
        and np.array_equal(formal["q_values"], np.asarray(Q_VALUES))
        and np.array_equal(formal["axis_names"], np.asarray(AXES))
    )
    add_check(checks, "exact_schemas_and_component_partitions", passed, detail)
    return detail


def map_input(
    raw: dict[str, np.ndarray],
    maps: dict[str, np.ndarray],
    components: dict[str, np.ndarray],
    map_id: str,
) -> dict[str, np.ndarray]:
    values = dict(raw)
    values["source_maps"] = maps[f"{map_id}_source_maps"]
    values["component_image_offsets"] = components[
        f"{map_id}_component_image_offsets"
    ]
    values["component_image_indices"] = components[
        f"{map_id}_component_image_indices"
    ]
    values["component_id_by_image"] = components[
        f"{map_id}_component_id_by_image"
    ]
    return values


def independently_prepare_maps(
    raw: dict[str, np.ndarray],
    maps: dict[str, np.ndarray],
    components: dict[str, np.ndarray],
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for map_index, map_id in enumerate(MAP_IDS):
        prepared.append(
            build_independent_primitives(
                map_input(raw, maps, components, map_id)
            )
        )
        print(
            json.dumps(
                {
                    "independent_map_precompute_completed": map_id,
                    "maps_completed": map_index + 1,
                    "maps_total": len(MAP_IDS),
                }
            ),
            flush=True,
        )
    return prepared


def independent_diagnostic_arrays(
    raw: dict[str, np.ndarray],
    maps: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    prefix = (len(MAP_IDS), len(SEEDS))
    output = {
        "A_micro_f1": np.empty((*prefix, 2, 5)),
        "A_per_class_f1": np.empty((*prefix, 2, 5, 4)),
        "A_target_positive_count": np.empty(
            (*prefix, 2, 5, 4), dtype=np.int64
        ),
        "A_predicted_positive_count": np.empty(
            (*prefix, 2, 5, 4), dtype=np.int64
        ),
        "R_micro_f1": np.empty((*prefix, 5)),
        "R_per_class_f1": np.empty((*prefix, 5, 21)),
        "R_target_positive_count": np.empty(
            (*prefix, 5, 21), dtype=np.int64
        ),
        "R_predicted_positive_count": np.empty(
            (*prefix, 5, 21), dtype=np.int64
        ),
        "S_diagnostics": np.empty((*prefix, 2, 5, 8)),
        "C1_action_per_perturbation": np.empty(
            (*prefix, 2, 5, 3)
        ),
        "C1_rationale_per_perturbation": np.empty(
            (*prefix, 5, 3)
        ),
    }
    targets_a = raw["action_targets"].astype(bool)
    targets_r = raw["rationale_targets"].astype(bool)
    diagnostic_names = (
        "tie_averaged_aurc",
        "canonical_stable_aurc",
        "unsafe_acceptance_rate_90",
        "correctness_auroc",
        "ece",
        "exact_set_error_rate",
        "highest_confidence_decile_error_rate",
        "lowest_confidence_decile_error_rate",
    )
    for map_index, map_id in enumerate(MAP_IDS):
        source_maps = maps[f"{map_id}_source_maps"]
        for seed_index, seed in enumerate(SEEDS):
            rationale_prediction = raw[
                f"seed_{seed}_joint_rationale_predictions"
            ].astype(bool)
            for q_index, source in enumerate(source_maps):
                for model_index, model in enumerate(MODELS):
                    prediction = raw[
                        f"seed_{seed}_{model}_action_predictions"
                    ].astype(bool)
                    action_detail = multilabel_detail(
                        targets_a[source], prediction
                    )
                    output["A_micro_f1"][
                        map_index, seed_index, model_index, q_index
                    ] = action_detail["micro_f1"]
                    output["A_per_class_f1"][
                        map_index, seed_index, model_index, q_index
                    ] = action_detail["per_class_f1"]
                    output["A_target_positive_count"][
                        map_index, seed_index, model_index, q_index
                    ] = targets_a[source].sum(axis=0)
                    output["A_predicted_positive_count"][
                        map_index, seed_index, model_index, q_index
                    ] = prediction.sum(axis=0)

                    safety = stable_aurc_detail(
                        raw[
                            f"seed_{seed}_{model}_exact_set_errors"
                        ],
                        raw[f"seed_{seed}_{model}_confidence"][source],
                    )
                    output["S_diagnostics"][
                        map_index, seed_index, model_index, q_index
                    ] = [
                        np.nan if safety[name] is None else safety[name]
                        for name in diagnostic_names
                    ]
                    for perturbation_index, perturbation in enumerate(
                        PERTURBATIONS
                    ):
                        perturbed = raw[
                            f"seed_{seed}_{model}_{perturbation}"
                            "_action_predictions"
                        ][source].astype(bool)
                        output["C1_action_per_perturbation"][
                            map_index,
                            seed_index,
                            model_index,
                            q_index,
                            perturbation_index,
                        ] = np.any(
                            prediction != perturbed, axis=1
                        ).mean()

                rationale_detail = multilabel_detail(
                    targets_r[source], rationale_prediction
                )
                output["R_micro_f1"][
                    map_index, seed_index, q_index
                ] = rationale_detail["micro_f1"]
                output["R_per_class_f1"][
                    map_index, seed_index, q_index
                ] = rationale_detail["per_class_f1"]
                output["R_target_positive_count"][
                    map_index, seed_index, q_index
                ] = targets_r[source].sum(axis=0)
                output["R_predicted_positive_count"][
                    map_index, seed_index, q_index
                ] = rationale_prediction.sum(axis=0)
                for perturbation_index, perturbation in enumerate(
                    PERTURBATIONS
                ):
                    perturbed = raw[
                        f"seed_{seed}_joint_{perturbation}"
                        "_rationale_predictions"
                    ][source].astype(bool)
                    output["C1_rationale_per_perturbation"][
                        map_index,
                        seed_index,
                        q_index,
                        perturbation_index,
                    ] = jaccard_samples(
                        rationale_prediction, perturbed
                    ).mean()
    return output


def reproduce_points(
    prepared: list[dict[str, Any]],
    formal: dict[str, np.ndarray],
    result: dict[str, Any],
    raw: dict[str, np.ndarray],
    maps: dict[str, np.ndarray],
    checks: list[dict[str, Any]],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    maximum_images = max(
        COMPONENT_COUNT * int(item["component_sizes"].max())
        for item in prepared
    )
    harmonic = harmonic_numbers(maximum_images)
    curves = {
        axis: np.empty_like(formal[f"{axis}_primary_curves"])
        for axis in AXES
    }
    bottlenecks = np.empty((20, 5, 4), dtype=np.float64)
    full_counts = np.ones(COMPONENT_COUNT, dtype=np.int64)
    for map_index, item in enumerate(prepared):
        for seed_index, seed in enumerate(SEEDS):
            observed = curves_from_component_draw(
                item, seed, full_counts, harmonic
            )
            for axis in AXES:
                curves[axis][map_index, seed_index] = observed[axis]
            values = axis_bottlenecks(observed)
            for axis in AXES:
                bottlenecks[
                    map_index, seed_index, AXIS_INDEX[axis]
                ] = values[axis]

    primary_differences = {
        axis: max_abs_difference(
            curves[axis], formal[f"{axis}_primary_curves"]
        )
        for axis in AXES
    }
    bottleneck_differences = {
        "map_seed": max_abs_difference(
            bottlenecks, formal["map_seed_axis_bottlenecks"]
        ),
        "map_mean": max_abs_difference(
            bottlenecks.mean(axis=1),
            formal["map_mean_axis_bottlenecks"],
        ),
    }
    grand_curve_differences: dict[str, dict[str, float | bool]] = {}
    no_reversal: dict[str, bool] = {}
    for axis in AXES:
        mean = curves[axis].mean(axis=(0, 1))
        sd = curves[axis].reshape(
            -1, curves[axis].shape[2], curves[axis].shape[3]
        ).std(axis=0, ddof=1)
        differences = np.diff(mean, axis=1)
        no_reversal[axis] = all(
            bool(np.all(step <= 0.0))
            if direction == "decreasing"
            else bool(np.all(step >= 0.0))
            for step, direction in zip(
                differences, AXIS_DIRECTIONS[axis]
            )
        )
        grand_curve_differences[axis] = {
            "mean": max_abs_difference(
                mean,
                result["axis_summaries"][axis][
                    "grand_mean_component_curves"
                ],
            ),
            "sd": max_abs_difference(
                sd,
                result["axis_summaries"][axis][
                    "grand_sd_component_curves"
                ],
            ),
            "no_reversal": no_reversal[axis],
        }

    diagnostic_arrays = independent_diagnostic_arrays(raw, maps)
    diagnostic_differences = {
        key: max_abs_difference(values, formal[key])
        for key, values in diagnostic_arrays.items()
    }
    maximum_difference = max(
        *primary_differences.values(),
        *bottleneck_differences.values(),
        *diagnostic_differences.values(),
        *[
            float(value)
            for by_axis in grand_curve_differences.values()
            for key, value in by_axis.items()
            if key != "no_reversal"
        ],
    )
    detail = {
        "tolerance": FLOAT_TOLERANCE,
        "maximum_abs_difference": maximum_difference,
        "primary_curve_max_abs_difference": primary_differences,
        "diagnostic_array_max_abs_difference": diagnostic_differences,
        "bottleneck_max_abs_difference": bottleneck_differences,
        "grand_curve_max_abs_difference": grand_curve_differences,
        "mean_curves_no_reversal": no_reversal,
    }
    add_check(
        checks,
        "independent_all_point_diagnostic_and_bottleneck_reproduction",
        maximum_difference <= FLOAT_TOLERANCE
        and all(no_reversal.values()),
        detail,
    )
    return curves, detail


def verify_csvs(
    formal: dict[str, np.ndarray], checks: list[dict[str, Any]]
) -> dict[str, Any]:
    with POINT_CSV_PATH.open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        point_fields = reader.fieldnames
        point_count = sum(1 for _ in reader)
    with BOOTSTRAP_CSV_PATH.open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        bootstrap_fields = reader.fieldnames
        bootstrap_rows = list(reader)
    detail = {
        "point_rows": point_count,
        "point_fields": point_fields,
        "bootstrap_rows": len(bootstrap_rows),
        "bootstrap_fields": bootstrap_fields,
        "bootstrap_axes": [row["axis"] for row in bootstrap_rows],
        "reported_s_diagnostic_names": formal[
            "S_diagnostic_names"
        ].tolist(),
    }
    passed = bool(
        point_count == 60500
        and len(bootstrap_rows) == 4
        and detail["bootstrap_axes"] == list(AXES)
    )
    add_check(checks, "published_csv_structure", passed, detail)
    return detail


def reproduce_bootstrap(
    prepared: list[dict[str, Any]],
    formal_draws: dict[str, np.ndarray],
    result: dict[str, Any],
    point_curves: dict[str, np.ndarray],
    checks: list[dict[str, Any]],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    independent = {
        axis: np.empty(REPLICATES, dtype=np.float64)
        for axis in AXES
    }
    selected_maps_all = np.empty((REPLICATES, 20), dtype=np.int16)
    selected_seeds_all = np.empty((REPLICATES, 5), dtype=np.int8)
    image_counts = np.empty((REPLICATES, 20), dtype=np.int32)
    maximum_images = max(
        COMPONENT_COUNT * int(item["component_sizes"].max())
        for item in prepared
    )
    harmonic = harmonic_numbers(maximum_images)
    map_digest = hashlib.sha256()
    seed_digest = hashlib.sha256()
    component_digest = hashlib.sha256()
    first_draw = None
    last_draw = None

    for replicate in range(REPLICATES):
        selected_maps = rng.integers(0, 20, size=20)
        selected_seeds = rng.integers(0, 5, size=5)
        selected_maps_all[replicate] = selected_maps
        selected_seeds_all[replicate] = selected_seeds
        map_digest.update(
            selected_maps.astype("<i8", copy=False).tobytes()
        )
        seed_digest.update(
            selected_seeds.astype("<i8", copy=False).tobytes()
        )
        occurrence_values: list[dict[str, float]] = []
        occurrence_hashes: list[str] = []
        for occurrence, map_position in enumerate(selected_maps):
            selected_components = rng.integers(
                0, COMPONENT_COUNT, size=COMPONENT_COUNT
            )
            component_bytes = selected_components.astype(
                "<i8", copy=False
            ).tobytes()
            component_digest.update(component_bytes)
            occurrence_hashes.append(
                hashlib.sha256(component_bytes).hexdigest().upper()
            )
            component_counts = np.bincount(
                selected_components, minlength=COMPONENT_COUNT
            ).astype(np.int64)
            item = prepared[int(map_position)]
            image_counts[replicate, occurrence] = int(
                component_counts @ item["component_sizes"]
            )
            per_seed: dict[int, dict[str, float]] = {}
            for seed_position in np.unique(selected_seeds):
                curves = curves_from_component_draw(
                    item,
                    SEEDS[int(seed_position)],
                    component_counts,
                    harmonic,
                )
                per_seed[int(seed_position)] = axis_bottlenecks(curves)
            occurrence_values.append(
                {
                    axis: float(
                        np.mean(
                            [
                                per_seed[int(seed_position)][axis]
                                for seed_position in selected_seeds
                            ]
                        )
                    )
                    for axis in AXES
                }
            )
        for axis in AXES:
            independent[axis][replicate] = float(
                np.mean(
                    [value[axis] for value in occurrence_values]
                )
            )
        draw_detail = {
            "replicate": replicate,
            "selected_map_positions": selected_maps.tolist(),
            "selected_seed_positions": selected_seeds.tolist(),
            "component_draw_sha256_by_occurrence": occurrence_hashes,
            "expanded_image_count_by_occurrence": (
                image_counts[replicate].tolist()
            ),
        }
        if replicate == 0:
            first_draw = draw_detail
        if replicate == REPLICATES - 1:
            last_draw = draw_detail
        if (replicate + 1) % 25 == 0:
            print(
                json.dumps(
                    {
                        "independent_hierarchical_bootstrap_completed": (
                            replicate + 1
                        ),
                        "bootstrap_total": REPLICATES,
                    }
                ),
                flush=True,
            )

    independent.update(
        {
            "selected_map_positions": selected_maps_all,
            "selected_seed_positions": selected_seeds_all,
            "expanded_image_counts": image_counts,
        }
    )
    stream_hashes = {
        "map": map_digest.hexdigest().upper(),
        "seed": seed_digest.hexdigest().upper(),
        "component": component_digest.hexdigest().upper(),
    }
    expected_stream_hashes = {
        "map": result["hierarchical_bootstrap"][
            "map_draw_stream_sha256"
        ],
        "seed": result["hierarchical_bootstrap"][
            "seed_draw_stream_sha256"
        ],
        "component": result["hierarchical_bootstrap"][
            "component_draw_stream_sha256"
        ],
    }
    array_differences = {
        key: max_abs_difference(independent[key], formal_draws[key])
        for key in EXPECTED_DRAW_KEYS
    }
    exact_selection_matches = {
        key: bool(np.array_equal(independent[key], formal_draws[key]))
        for key in (
            "selected_map_positions",
            "selected_seed_positions",
            "expanded_image_counts",
        )
    }
    axis_summary: dict[str, Any] = {}
    for axis in AXES:
        interval = np.quantile(
            independent[axis], [0.025, 0.975], method="linear"
        )
        map_means = np.asarray(
            formal_draws[axis], dtype=np.float64
        )
        del map_means
        point_map_means = np.asarray(
            [
                axis_bottlenecks(
                    {
                        candidate: point_curves[candidate][
                            map_index, seed_index
                        ]
                        for candidate in AXES
                    }
                )[axis]
                for map_index in range(20)
                for seed_index in range(5)
            ],
            dtype=np.float64,
        ).reshape(20, 5).mean(axis=1)
        axis_summary[axis] = {
            "draw_max_abs_difference": array_differences[axis],
            "interval": interval.tolist(),
            "formal_interval": result["axis_summaries"][axis][
                "bootstrap_interval"
            ],
            "interval_max_abs_difference": max_abs_difference(
                interval,
                result["axis_summaries"][axis][
                    "bootstrap_interval"
                ],
            ),
            "map_mean": float(point_map_means.mean()),
            "positive_map_count": int(np.sum(point_map_means > 0.0)),
            "draw_array_sha256": array_sha256(independent[axis]),
            "formal_draw_array_sha256": result["axis_summaries"][axis][
                "bootstrap_draw_sha256"
            ],
        }

    diagnostics = result["hierarchical_bootstrap"]
    image_summary = {
        "minimum": int(image_counts.min()),
        "maximum": int(image_counts.max()),
        "mean": float(image_counts.mean()),
    }
    image_summary_differences = {
        key: abs(image_summary[key] - diagnostics[
            "expanded_image_count"
        ][key])
        for key in image_summary
    }
    first_last_match = bool(
        first_draw == diagnostics["first_draw"]
        and last_draw == diagnostics["last_draw"]
    )
    maximum_numeric_difference = max(
        *array_differences.values(),
        *[
            value["interval_max_abs_difference"]
            for value in axis_summary.values()
        ],
        *image_summary_differences.values(),
    )
    detail = {
        "tolerance": FLOAT_TOLERANCE,
        "maximum_numeric_abs_difference": maximum_numeric_difference,
        "array_max_abs_differences": array_differences,
        "exact_selection_and_image_count_matches": (
            exact_selection_matches
        ),
        "stream_hashes": stream_hashes,
        "expected_stream_hashes": expected_stream_hashes,
        "first_and_last_draw_exact_match": first_last_match,
        "axis_summary": axis_summary,
        "expanded_image_count": image_summary,
        "expanded_image_count_abs_differences": (
            image_summary_differences
        ),
    }
    passed = bool(
        maximum_numeric_difference <= FLOAT_TOLERANCE
        and all(exact_selection_matches.values())
        and stream_hashes == expected_stream_hashes
        and first_last_match
        and all(
            item["draw_array_sha256"]
            == item["formal_draw_array_sha256"]
            for item in axis_summary.values()
        )
    )
    add_check(
        checks,
        "independent_all_2000_hierarchical_draw_reproduction",
        passed,
        detail,
    )
    return independent, detail


def independent_gates(
    point_detail: dict[str, Any],
    bootstrap_detail: dict[str, Any],
    result: dict[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, bool]:
    gates = {
        axis: bool(
            bootstrap_detail["axis_summary"][axis][
                "positive_map_count"
            ]
            >= 18
            and bootstrap_detail["axis_summary"][axis]["map_mean"] > 0.0
            and bootstrap_detail["axis_summary"][axis]["interval"][0]
            > 0.0
            and point_detail["mean_curves_no_reversal"][axis]
        )
        for axis in AXES
    }
    matches = bool(
        gates == result["decisions"]["axis_gates"]
        and all(gates.values())
        == result["decisions"]["full_Round9_measurement_pass"]
    )
    add_check(
        checks,
        "independent_preregistered_gate_decisions",
        matches,
        {
            "independent_axis_gates": gates,
            "formal_axis_gates": result["decisions"]["axis_gates"],
            "independent_full_pass": all(gates.values()),
            "formal_full_pass": result["decisions"][
                "full_Round9_measurement_pass"
            ],
        },
    )
    return gates


def main() -> int:
    args = parse_args()
    if not args.points_only:
        require(
            not AUDIT_PATH.exists()
            and not INDEPENDENT_DRAWS_PATH.exists(),
            "independent final output already exists; preserve it and "
            "change the attempt name before any rerun",
        )
    result = read_json(RESULT_PATH)
    require(
        result["status"] == "ROUND9_FULL_PASS"
        and result["completed_formal_attempt"] == "attempt01",
        "formal completion marker is not the frozen successful attempt",
    )
    checks: list[dict[str, Any]] = []
    frozen_hashes = verify_hashes(result, checks)
    raw = load_npz(ROUND8_PRIMITIVES_PATH)
    maps = load_npz(MAP_PATH)
    components = load_npz(COMPONENT_PATH)
    formal = load_npz(FORMAL_PRIMITIVES_PATH)
    formal_draws = load_npz(FORMAL_DRAWS_PATH)
    schema = verify_schemas(
        raw, maps, components, formal, formal_draws, checks
    )
    prepared = independently_prepare_maps(raw, maps, components)
    point_curves, point_detail = reproduce_points(
        prepared, formal, result, raw, maps, checks
    )
    csv_detail = verify_csvs(formal, checks)

    if args.points_only:
        passed = all(check["passed"] for check in checks)
        print(
            json.dumps(
                {
                    "status": (
                        "POINTS_ONLY_PASS" if passed else "POINTS_ONLY_STOP"
                    ),
                    "checks_passed": sum(
                        check["passed"] for check in checks
                    ),
                    "checks_total": len(checks),
                    "failed": [
                        check["name"]
                        for check in checks
                        if not check["passed"]
                    ],
                    "maximum_point_abs_difference": point_detail[
                        "maximum_abs_difference"
                    ],
                },
                indent=2,
            )
        )
        return 0 if passed else 1

    independent_draws, bootstrap_detail = reproduce_bootstrap(
        prepared, formal_draws, result, point_curves, checks
    )
    gates = independent_gates(
        point_detail, bootstrap_detail, result, checks
    )
    write_npz_atomic(INDEPENDENT_DRAWS_PATH, independent_draws)
    independent_draw_metadata = {
        "path": str(
            INDEPENDENT_DRAWS_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "sha256": sha256_file(INDEPENDENT_DRAWS_PATH),
        "bytes": INDEPENDENT_DRAWS_PATH.stat().st_size,
        "arrays": {
            key: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "array_sha256": array_sha256(value),
            }
            for key, value in independent_draws.items()
        },
    }
    status = "PASS" if all(check["passed"] for check in checks) else "STOP"
    audit = {
        "study": "Round 9 independent 20-map reproduction",
        "status": status,
        "formal_result_sha256": RESULT_SHA256,
        "independence": {
            "imports_round9_formal_analysis": False,
            "imports_arsc_eval_source": False,
            "independent_base": (
                "Round 8 raw-array sufficient-statistic verifier"
            ),
            "different_computation_path": {
                "A_R": "component-aggregated TP/FP/FN counts",
                "S": (
                    "confidence-group sufficient statistics with exact "
                    "harmonic tie expectation"
                ),
                "C1": (
                    "component-aggregated per-image flip/Jaccard events"
                ),
            },
            "all_rng_draws_recreated_from_seed": True,
        },
        "checks": checks,
        "summary": {
            "passed": int(sum(check["passed"] for check in checks)),
            "total": len(checks),
            "failed": [
                check["name"]
                for check in checks
                if not check["passed"]
            ],
        },
        "frozen_artifact_hashes": frozen_hashes,
        "schema_and_partition_audit": schema,
        "csv_structure": csv_detail,
        "point_reproduction": point_detail,
        "bootstrap_reproduction": bootstrap_detail,
        "independent_bootstrap_draw_artifact": (
            independent_draw_metadata
        ),
        "independent_decisions": {
            "axis_gates": gates,
            "full_Round9_measurement_pass": bool(all(gates.values())),
            "matches_formal_result": bool(
                gates == result["decisions"]["axis_gates"]
            ),
        },
        "claim_boundary": (
            "PASS verifies computational reproduction of the frozen "
            "BDD-OIA Round 9 conditional estimands and gates. It does "
            "not add external, construct, causal, grounding, calibration, "
            "or real-safety validity, and the 20 maps are not 20 datasets."
        ),
    }
    write_json_atomic(AUDIT_PATH, audit)
    print(
        json.dumps(
            {
                "status": status,
                "checks": audit["summary"],
                "axis_gates": gates,
                "audit": str(AUDIT_PATH.relative_to(PROJECT_ROOT)).replace(
                    "\\", "/"
                ),
                "audit_sha256": sha256_file(AUDIT_PATH),
                "independent_draws": independent_draw_metadata,
            },
            indent=2,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
