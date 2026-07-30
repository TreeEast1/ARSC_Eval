"""Independently reproduce the frozen Round 8 graded-response outputs.

This verifier deliberately imports no ``arsc_eval`` implementation code.  It
reconstructs the four primary curves from the saved primitive arrays using a
different computation path:

* A/R: component-aggregated TP/FP/FN counts;
* S: confidence-group aggregation with an exact harmonic tie formula;
* C1: component-aggregated per-image flip/Jaccard events.

The full mode also redraws the frozen seed/component bootstrap and saves every
replicate.  ``--points-only`` performs all hash, invariant, and point checks
without writing an audit artifact.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDITY_DIR = PROJECT_ROOT / "outputs" / "validity"
RESULT_PATH = VALIDITY_DIR / "round8_graded_response_results.json"
PRIMITIVES_PATH = VALIDITY_DIR / "round8_graded_response_primitives.npz"
AUDIT_PATH = (
    VALIDITY_DIR / "round8_graded_response_independent_audit.json"
)
DRAW_PATH = (
    VALIDITY_DIR
    / "round8_graded_response_independent_bootstrap_draws.npz"
)

SEEDS = (43, 44, 45, 46, 47)
MODELS = ("action_only", "joint")
PERTURBATIONS = ("brightness", "blur", "noise")
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
AXIS_DIRECTIONS = {
    "A": ("decreasing", "decreasing"),
    "R": ("decreasing",),
    "S": ("increasing", "increasing"),
    "C1": ("increasing", "increasing", "decreasing"),
}
ACTION_NAMES = ("Forward", "Stop", "Left", "Right")
RATIONALE_NAMES = (
    "green_light",
    "follow",
    "road_clear",
    "red_light",
    "traffic_sign",
    "car",
    "person",
    "rider",
    "other_obstacle",
    "left_lane",
    "left_green_light",
    "left_follow",
    "no_left_lane",
    "left_obstacle",
    "left_solid_line",
    "right_lane",
    "right_green_light",
    "right_follow",
    "no_right_lane",
    "right_obstacle",
    "right_solid_line",
)
MEAN_CURVE_NAMES = {
    "A": (
        "Action-Only Macro-F1",
        "Joint Action-Rationale Macro-F1",
    ),
    "R": ("Joint Action-Rationale 21-label Macro-F1",),
    "S": (
        "Action-Only tie-averaged AURC",
        "Joint Action-Rationale tie-averaged AURC",
    ),
    "C1": (
        "Action-Only mean-three action flip",
        "Joint Action-Rationale mean-three action flip",
        "Joint Action-Rationale mean-three rationale Jaccard",
    ),
}

REPLICATES = 2000
BOOTSTRAP_SEED = 20260803
SAMPLE_COUNT = 4557
COMPONENT_COUNT = 1625
FLOAT_TOLERANCE = 5e-13

EXPECTED_HASHES = {
    "outputs/validity/round8_graded_response_results.json": (
        "4CD0FCD16ED4A3BAE1D378FD10B3A44705F2433FDF3C3E15A26FBCE303AF6FD3"
    ),
    "outputs/validity/round8_graded_response_point_estimates.csv": (
        "CDCBE0BAA0DD949B9F18F2545C76C4BC98328B3F48D301D018CF09D1B2AB7620"
    ),
    "outputs/validity/round8_graded_response_bootstrap.csv": (
        "A4042CEBB040CBC744BAF3D2BF6081CEC76AABA64C1F0962C0C15465A3276C41"
    ),
    "outputs/validity/round8_graded_response_primitives.npz": (
        "6E51FB8842C6A6510364415C9D2D19C2307363024C34C8C7DE00DB57DCC7160C"
    ),
    "outputs/validity/round8_graded_response_formal_tmux.log": (
        "B09902A81C392F4FDBDEEF44A56DF93DEF15636480A6CCFB959785D9F2816351"
    ),
    "outputs/validity/round8_graded_response_protocol.json": (
        "B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357"
    ),
    "outputs/validity/round8_graded_response_protocol_amendment01.json": (
        "D15E6F93FFEF686172F3887BAB609E6DA724ECE975BB125485A717688A020C8A"
    ),
    "outputs/research_review_memo_round8_preregister.md": (
        "83C13D1112ABAF9CBA6504E26BBB0BDBBDD99C5D7A45DB27A840D0A695B65BF2"
    ),
    "outputs/research_review_memo_round8_amendment01.md": (
        "CBF47293F5D983772C305B53E7C1DACD056D1609C7BA4F0A3B284BFAEEC9B66A"
    ),
    "outputs/research_review_memo_round8_attempt01_failure.md": (
        "9E051D174D3DC4117C6F4F9005EE03791CF297E0E5495E0C38953D6BA3ED54B8"
    ),
    "outputs/validity/round8_graded_association_maps.npz": (
        "8685E1A4605B5D6355A432BC6CA03CF61930BAB23D41D899478A5C1D8FC47ED1"
    ),
    "outputs/validity/round8_graded_association_map_manifest.json": (
        "73B89C3438262BA272E0E90EDC2A6F9408B196CCBD4A30D9FA6FFFA798C273DC"
    ),
    "outputs/validity/round8_association_components.npz": (
        "F1DF45A526EEBE02C2CDA6EA2FB1FE8B034A3FDD3B1582B3598B602916CDD0E8"
    ),
    "outputs/validity/round8_association_component_manifest.json": (
        "7E5EA6AB9E83A0CCE03FDBBBAC274AB01D1B7773CA43833348C77ED71127653F"
    ),
    "outputs/validity/round8_graded_response_preflight.json": (
        "595D9E0A68124ADE294B90AD3891365C569AEE367CD576AC9C97F2D647CFBA0F"
    ),
    "outputs/validity/round8_graded_response_run_manifest.json": (
        "85DC92712634C56B856409E3A58105205ABCCA504238A8B74EA3EC1F1F334ACD"
    ),
    "outputs/validity/round8_graded_response_formal_attempt01_failed.log": (
        "E3D3D58FF47663F7031AA85963D3AA81702BA4CA21F35C60DA77DEEA10E95296"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--points-only",
        action="store_true",
        help="run hashes, invariants, and point reproduction only",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing independent audit/draw artifact",
    )
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


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def append_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> None:
    checks.append(
        {"name": name, "passed": bool(passed), "detail": detail}
    )


def max_abs_difference(left: Any, right: Any) -> float:
    left_values = np.asarray(left, dtype=np.float64)
    right_values = np.asarray(right, dtype=np.float64)
    if left_values.shape != right_values.shape:
        return math.inf
    if not left_values.size:
        return 0.0
    return float(np.max(np.abs(left_values - right_values)))


def f1_from_counts(
    true_positive: np.ndarray,
    false_positive: np.ndarray,
    false_negative: np.ndarray,
) -> np.ndarray:
    denominator = (
        2.0 * true_positive + false_positive + false_negative
    )
    return np.divide(
        2.0 * true_positive,
        denominator,
        out=np.zeros_like(denominator, dtype=np.float64),
        where=denominator != 0,
    )


def multilabel_detail(
    targets: np.ndarray,
    predictions: np.ndarray,
) -> dict[str, Any]:
    true = np.asarray(targets, dtype=bool)
    pred = np.asarray(predictions, dtype=bool)
    tp = np.logical_and(true, pred).sum(axis=0, dtype=np.int64)
    fp = np.logical_and(~true, pred).sum(axis=0, dtype=np.int64)
    fn = np.logical_and(true, ~pred).sum(axis=0, dtype=np.int64)
    per_class = f1_from_counts(tp, fp, fn)
    flat_tp = int(tp.sum())
    flat_fp = int(fp.sum())
    flat_fn = int(fn.sum())
    micro = f1_from_counts(
        np.asarray([flat_tp], dtype=np.float64),
        np.asarray([flat_fp], dtype=np.float64),
        np.asarray([flat_fn], dtype=np.float64),
    )[0]
    return {
        "macro_f1": float(per_class.mean()),
        "micro_f1": float(micro),
        "per_class_f1": per_class,
    }


def confidence_group_ids(
    confidence: np.ndarray,
) -> tuple[np.ndarray, int]:
    _, ascending_ids = np.unique(
        np.asarray(confidence, dtype=np.float64),
        return_inverse=True,
    )
    count = int(ascending_ids.max()) + 1
    return (count - 1 - ascending_ids).astype(np.int32), count


def harmonic_numbers(maximum: int) -> np.ndarray:
    values = np.zeros(maximum + 1, dtype=np.float64)
    values[1:] = np.cumsum(
        1.0 / np.arange(1, maximum + 1, dtype=np.float64)
    )
    return values


def grouped_tie_averaged_aurc(
    errors: np.ndarray,
    group_ids: np.ndarray,
    group_count: int,
    image_weights: np.ndarray,
    harmonic: np.ndarray,
) -> float:
    """Expected AURC over ties, evaluated from group sufficient statistics."""

    weights = np.asarray(image_weights, dtype=np.int64)
    counts = np.bincount(
        group_ids, weights=weights, minlength=group_count
    )
    error_counts = np.bincount(
        group_ids,
        weights=weights * np.asarray(errors, dtype=np.int64),
        minlength=group_count,
    )
    active = counts > 0
    counts = counts[active]
    error_counts = error_counts[active]
    integer_counts = counts.astype(np.int64)
    starts = np.cumsum(integer_counts) - integer_counts
    stops = starts + integer_counts
    harmonic_span = harmonic[stops] - harmonic[starts]
    prior_errors = np.cumsum(error_counts) - error_counts
    contribution = (
        prior_errors * harmonic_span
        + (error_counts / counts)
        * (counts - starts * harmonic_span)
    )
    return float(contribution.sum() / stops[-1])


def direct_tie_averaged_aurc(
    errors: np.ndarray,
    confidence: np.ndarray,
) -> float:
    groups, count = confidence_group_ids(confidence)
    harmonic = harmonic_numbers(len(errors))
    return grouped_tie_averaged_aurc(
        errors,
        groups,
        count,
        np.ones(len(errors), dtype=np.int64),
        harmonic,
    )


def stable_aurc_detail(
    errors: np.ndarray,
    confidence: np.ndarray,
) -> dict[str, Any]:
    error_values = np.asarray(errors, dtype=np.float64)
    score_values = np.asarray(confidence, dtype=np.float64)
    order = np.argsort(-score_values, kind="stable")
    risk = np.cumsum(error_values[order]) / np.arange(
        1, len(errors) + 1
    )
    accepted = max(1, int(math.ceil(0.90 * len(errors))))
    correctness = 1.0 - error_values
    edges = np.linspace(0.0, 1.0, 16)
    ece = 0.0
    for index, (lower, upper) in enumerate(
        zip(edges[:-1], edges[1:])
    ):
        if index == 0:
            selected = (score_values >= lower) & (
                score_values <= upper
            )
        else:
            selected = (score_values > lower) & (
                score_values <= upper
            )
        count = int(selected.sum())
        if count:
            ece += (
                abs(
                    float(correctness[selected].mean())
                    - float(score_values[selected].mean())
                )
                * count
                / len(errors)
            )
    tenth = max(1, len(errors) // 10)
    return {
        "tie_averaged_aurc": direct_tie_averaged_aurc(
            error_values, score_values
        ),
        "canonical_stable_aurc": float(risk.mean()),
        "unsafe_acceptance_rate_90": float(risk[accepted - 1]),
        "correctness_auroc": binary_auroc(
            correctness.astype(bool), score_values
        ),
        "ece": float(ece),
        "exact_set_error_rate": float(error_values.mean()),
        "highest_confidence_decile_error_rate": float(
            error_values[order[:tenth]].mean()
        ),
        "lowest_confidence_decile_error_rate": float(
            error_values[order[-tenth:]].mean()
        ),
    }


def binary_auroc(
    labels: np.ndarray,
    scores: np.ndarray,
) -> float | None:
    targets = np.asarray(labels, dtype=bool)
    values = np.asarray(scores, dtype=np.float64)
    positives = int(targets.sum())
    negatives = int((~targets).sum())
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        stop = start + 1
        while (
            stop < len(values)
            and sorted_values[stop] == sorted_values[start]
        ):
            stop += 1
        ranks[order[start:stop]] = 0.5 * (start + 1 + stop)
        start = stop
    rank_sum = float(ranks[targets].sum())
    return (
        rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def jaccard_samples(
    clean: np.ndarray,
    perturbed: np.ndarray,
) -> np.ndarray:
    left = np.asarray(clean, dtype=bool)
    right = np.asarray(perturbed, dtype=bool)
    intersection = np.logical_and(left, right).sum(axis=1)
    union = np.logical_or(left, right).sum(axis=1)
    values = np.ones(len(union), dtype=np.float64)
    nonempty = union > 0
    values[nonempty] = intersection[nonempty] / union[nonempty]
    return values


def component_sums(
    values: np.ndarray,
    offsets: np.ndarray,
    flat_images: np.ndarray,
) -> np.ndarray:
    ordered = np.asarray(values)[flat_images]
    return np.add.reduceat(ordered, offsets[:-1], axis=0)


def bottleneck(
    curves: np.ndarray,
    directions: tuple[str, ...],
) -> float:
    steps: list[np.ndarray] = []
    for curve, direction in zip(curves, directions):
        if direction == "decreasing":
            steps.append(curve[:-1] - curve[1:])
        else:
            steps.append(curve[1:] - curve[:-1])
    return float(np.min(np.concatenate(steps)))


def axis_bottlenecks(
    curves: dict[str, np.ndarray],
) -> dict[str, float]:
    return {
        axis: bottleneck(curves[axis], AXIS_DIRECTIONS[axis])
        for axis in AXIS_DIRECTIONS
    }


def build_independent_primitives(
    arrays: dict[str, np.ndarray],
) -> dict[str, Any]:
    targets_a = arrays["action_targets"].astype(bool)
    targets_r = arrays["rationale_targets"].astype(bool)
    source_maps = arrays["source_maps"]
    offsets = arrays["component_image_offsets"]
    flat = arrays["component_image_indices"]
    component_id = arrays["component_id_by_image"]

    prepared: dict[str, Any] = {}
    for seed in SEEDS:
        by_seed: dict[str, Any] = {
            "A": {},
            "R": [],
            "S": {},
            "C1": {},
        }
        for model in MODELS:
            prediction = arrays[
                f"seed_{seed}_{model}_action_predictions"
            ].astype(bool)
            by_seed["A"][model] = []
            by_seed["S"][model] = []
            by_seed["C1"][model] = []
            for q_index, source in enumerate(source_maps):
                target = targets_a[source]
                tp = np.logical_and(target, prediction)
                fp = np.logical_and(~target, prediction)
                fn = np.logical_and(target, ~prediction)
                by_seed["A"][model].append(
                    tuple(
                        component_sums(part, offsets, flat)
                        for part in (tp, fp, fn)
                    )
                )
                confidence = arrays[
                    f"seed_{seed}_{model}_confidence"
                ][source]
                group_ids, group_count = confidence_group_ids(
                    confidence
                )
                by_seed["S"][model].append(
                    {
                        "group_ids": group_ids,
                        "group_count": group_count,
                        "errors": arrays[
                            f"seed_{seed}_{model}_exact_set_errors"
                        ].astype(np.int64),
                    }
                )

                per_perturbation = []
                for perturbation in PERTURBATIONS:
                    perturbed = arrays[
                        f"seed_{seed}_{model}_{perturbation}"
                        "_action_predictions"
                    ][source].astype(bool)
                    sample_values = np.any(
                        prediction != perturbed, axis=1
                    ).astype(np.float64)
                    per_perturbation.append(
                        component_sums(sample_values, offsets, flat)
                    )
                by_seed["C1"][model].append(per_perturbation)

        rationale_prediction = arrays[
            f"seed_{seed}_joint_rationale_predictions"
        ].astype(bool)
        by_seed["C1"]["rationale"] = []
        for source in source_maps:
            target = targets_r[source]
            tp = np.logical_and(target, rationale_prediction)
            fp = np.logical_and(~target, rationale_prediction)
            fn = np.logical_and(target, ~rationale_prediction)
            by_seed["R"].append(
                tuple(
                    component_sums(part, offsets, flat)
                    for part in (tp, fp, fn)
                )
            )
            per_perturbation = []
            for perturbation in PERTURBATIONS:
                perturbed = arrays[
                    f"seed_{seed}_joint_{perturbation}"
                    "_rationale_predictions"
                ][source].astype(bool)
                values = jaccard_samples(
                    rationale_prediction, perturbed
                )
                per_perturbation.append(
                    component_sums(values, offsets, flat)
                )
            by_seed["C1"]["rationale"].append(per_perturbation)
        prepared[str(seed)] = by_seed
    return {
        "by_seed": prepared,
        "component_sizes": np.diff(offsets),
        "component_id_by_image": component_id,
    }


def curves_from_component_draw(
    prepared: dict[str, Any],
    seed: int,
    component_counts: np.ndarray,
    harmonic: np.ndarray,
) -> dict[str, np.ndarray]:
    data = prepared["by_seed"][str(seed)]
    component_sizes = prepared["component_sizes"]
    sample_total = int(component_counts @ component_sizes)
    image_weights = component_counts[
        prepared["component_id_by_image"]
    ]

    action_curves = []
    safety_curves = []
    for model in MODELS:
        action = []
        safety = []
        for q_index in range(len(Q_VALUES)):
            tp_comp, fp_comp, fn_comp = data["A"][model][q_index]
            tp = component_counts @ tp_comp
            fp = component_counts @ fp_comp
            fn = component_counts @ fn_comp
            action.append(float(f1_from_counts(tp, fp, fn).mean()))
            s_data = data["S"][model][q_index]
            safety.append(
                grouped_tie_averaged_aurc(
                    s_data["errors"],
                    s_data["group_ids"],
                    s_data["group_count"],
                    image_weights,
                    harmonic,
                )
            )
        action_curves.append(action)
        safety_curves.append(safety)

    rationale_curve = []
    for q_index in range(len(Q_VALUES)):
        tp_comp, fp_comp, fn_comp = data["R"][q_index]
        tp = component_counts @ tp_comp
        fp = component_counts @ fp_comp
        fn = component_counts @ fn_comp
        rationale_curve.append(
            float(f1_from_counts(tp, fp, fn).mean())
        )

    c1_curves = []
    for component_name in (*MODELS, "rationale"):
        curve = []
        for q_index in range(len(Q_VALUES)):
            per_perturbation = [
                float(component_counts @ component_values)
                / sample_total
                for component_values in data["C1"][component_name][
                    q_index
                ]
            ]
            curve.append(float(np.mean(per_perturbation)))
        c1_curves.append(curve)
    return {
        "A": np.asarray(action_curves, dtype=np.float64),
        "R": np.asarray([rationale_curve], dtype=np.float64),
        "S": np.asarray(safety_curves, dtype=np.float64),
        "C1": np.asarray(c1_curves, dtype=np.float64),
    }


def verify_artifact_hashes(
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    observed = {}
    for relative, expected in EXPECTED_HASHES.items():
        path = PROJECT_ROOT / relative
        digest = sha256_file(path) if path.exists() else None
        observed[relative] = {
            "expected": expected,
            "observed": digest,
            "passed": digest == expected,
        }
    append_check(
        checks,
        "all_frozen_artifact_hashes",
        all(item["passed"] for item in observed.values()),
        {
            "artifact_count": len(observed),
            "failed": [
                path
                for path, item in observed.items()
                if not item["passed"]
            ],
        },
    )
    return observed


def verify_array_invariants(
    arrays: dict[str, np.ndarray],
    result: dict[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    source_maps = arrays["source_maps"]
    offsets = arrays["component_image_offsets"]
    flat = arrays["component_image_indices"]
    component_id = arrays["component_id_by_image"]
    expected_indices = np.arange(SAMPLE_COUNT, dtype=np.int64)
    reconstructed = np.empty(SAMPLE_COUNT, dtype=np.int64)
    for component in range(COMPONENT_COUNT):
        reconstructed[
            flat[offsets[component] : offsets[component + 1]]
        ] = component

    invariants = {
        "array_count": len(arrays),
        "sample_count": len(arrays["file_names"]),
        "source_map_shape": list(source_maps.shape),
        "all_source_maps_bijections": bool(
            all(
                np.array_equal(np.sort(source), expected_indices)
                for source in source_maps
            )
        ),
        "packed_offsets_valid": bool(
            offsets.shape == (COMPONENT_COUNT + 1,)
            and offsets[0] == 0
            and offsets[-1] == SAMPLE_COUNT
            and np.all(np.diff(offsets) > 0)
        ),
        "packed_images_bijection": bool(
            np.array_equal(np.sort(flat), expected_indices)
        ),
        "component_ids_reconstructed": bool(
            np.array_equal(reconstructed, component_id)
        ),
        "all_maps_component_closed": bool(
            all(
                np.array_equal(component_id[source], component_id)
                for source in source_maps
            )
        ),
        "component_count": int(len(offsets) - 1),
        "component_size_min": int(np.diff(offsets).min()),
        "component_size_max": int(np.diff(offsets).max()),
    }
    error_mismatches = {}
    targets = arrays["action_targets"].astype(bool)
    for seed in SEEDS:
        for model in MODELS:
            prediction = arrays[
                f"seed_{seed}_{model}_action_predictions"
            ].astype(bool)
            derived = np.any(prediction != targets, axis=1).astype(
                np.uint8
            )
            stored = arrays[
                f"seed_{seed}_{model}_exact_set_errors"
            ]
            if not np.array_equal(derived, stored):
                error_mismatches[f"{seed}/{model}"] = int(
                    np.count_nonzero(derived != stored)
                )
    invariants["exact_set_error_mismatches"] = error_mismatches
    invariants["result_parameters_match"] = bool(
        result["frozen_parameters"]["seeds"] == list(SEEDS)
        and result["frozen_parameters"]["q_values"] == list(Q_VALUES)
        and result["frozen_parameters"]["sample_count"] == SAMPLE_COUNT
        and result["frozen_parameters"]["bootstrap"]["components"]
        == COMPONENT_COUNT
        and result["frozen_parameters"]["bootstrap"]["replicates"]
        == REPLICATES
        and result["frozen_parameters"]["bootstrap"]["seed"]
        == BOOTSTRAP_SEED
    )
    passed = (
        invariants["array_count"] == 87
        and invariants["sample_count"] == SAMPLE_COUNT
        and invariants["source_map_shape"] == [5, SAMPLE_COUNT]
        and invariants["all_source_maps_bijections"]
        and invariants["packed_offsets_valid"]
        and invariants["packed_images_bijection"]
        and invariants["component_ids_reconstructed"]
        and invariants["all_maps_component_closed"]
        and invariants["component_count"] == COMPONENT_COUNT
        and invariants["component_size_max"] == 14
        and not error_mismatches
        and invariants["result_parameters_match"]
    )
    append_check(
        checks, "primitive_and_component_invariants", passed, invariants
    )
    return invariants


def verify_point_results(
    arrays: dict[str, np.ndarray],
    prepared: dict[str, Any],
    result: dict[str, Any],
    harmonic: np.ndarray,
    checks: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, np.ndarray]], dict[str, Any]]:
    all_components_once = np.ones(COMPONENT_COUNT, dtype=np.int64)
    curves_by_seed: dict[int, dict[str, np.ndarray]] = {}
    curve_differences: dict[str, Any] = {}
    detail_differences: dict[str, Any] = {}
    maximum_curve_difference = 0.0
    maximum_detail_difference = 0.0
    source_maps = arrays["source_maps"]
    action_targets = arrays["action_targets"]
    rationale_targets = arrays["rationale_targets"]

    for seed in SEEDS:
        curves = curves_from_component_draw(
            prepared, seed, all_components_once, harmonic
        )
        curves_by_seed[seed] = curves
        formal = result["point_estimates_by_seed"][str(seed)]
        curve_differences[str(seed)] = {}
        detail_differences[str(seed)] = {}
        for axis in AXIS_DIRECTIONS:
            difference = max_abs_difference(
                curves[axis], formal["primary_curves"][axis]
            )
            curve_differences[str(seed)][axis] = difference
            maximum_curve_difference = max(
                maximum_curve_difference, difference
            )

        per_seed_details = []
        for q_index, source in enumerate(source_maps):
            for model_index, model in enumerate(MODELS):
                action_prediction = arrays[
                    f"seed_{seed}_{model}_action_predictions"
                ]
                observed = multilabel_detail(
                    action_targets[source], action_prediction
                )
                expected = formal["A"][model][q_index]
                values = [
                    abs(observed["macro_f1"] - expected["macro_f1"]),
                    abs(observed["micro_f1"] - expected["micro_f1"]),
                    max_abs_difference(
                        observed["per_class_f1"],
                        [
                            expected["per_class_f1"][name]
                            for name in ACTION_NAMES
                        ],
                    ),
                ]
                per_seed_details.extend(values)

                confidence = arrays[
                    f"seed_{seed}_{model}_confidence"
                ][source]
                errors = arrays[
                    f"seed_{seed}_{model}_exact_set_errors"
                ]
                observed_s = stable_aurc_detail(errors, confidence)
                expected_s = formal["S"][model][q_index]
                for metric, value in observed_s.items():
                    expected_value = expected_s[metric]
                    if value is None or expected_value is None:
                        per_seed_details.append(
                            0.0 if value == expected_value else math.inf
                        )
                    else:
                        per_seed_details.append(
                            abs(value - expected_value)
                        )

                c1_expected = formal["C1"]["action"][model][q_index]
                c1_values = []
                clean = action_prediction.astype(bool)
                for perturbation in PERTURBATIONS:
                    perturbed = arrays[
                        f"seed_{seed}_{model}_{perturbation}"
                        "_action_predictions"
                    ][source].astype(bool)
                    estimate = float(
                        np.any(clean != perturbed, axis=1).mean()
                    )
                    c1_values.append(estimate)
                    per_seed_details.append(
                        abs(estimate - c1_expected[perturbation])
                    )
                per_seed_details.append(
                    abs(
                        float(np.mean(c1_values))
                        - c1_expected["mean_three"]
                    )
                )

            observed_r = multilabel_detail(
                rationale_targets[source],
                arrays[f"seed_{seed}_joint_rationale_predictions"],
            )
            expected_r = formal["R"]["joint"][q_index]
            per_seed_details.extend(
                [
                    abs(observed_r["macro_f1"] - expected_r["macro_f1"]),
                    abs(observed_r["micro_f1"] - expected_r["micro_f1"]),
                    max_abs_difference(
                        observed_r["per_class_f1"],
                        [
                            expected_r["per_class_f1"][name]
                            for name in RATIONALE_NAMES
                        ],
                    ),
                ]
            )

            rationale_expected = formal["C1"]["rationale"]["joint"][
                q_index
            ]
            rationale_clean = arrays[
                f"seed_{seed}_joint_rationale_predictions"
            ]
            rationale_values = []
            for perturbation in PERTURBATIONS:
                perturbed = arrays[
                    f"seed_{seed}_joint_{perturbation}"
                    "_rationale_predictions"
                ][source]
                estimate = float(
                    jaccard_samples(
                        rationale_clean, perturbed
                    ).mean()
                )
                rationale_values.append(estimate)
                per_seed_details.append(
                    abs(estimate - rationale_expected[perturbation])
                )
            per_seed_details.append(
                abs(
                    float(np.mean(rationale_values))
                    - rationale_expected["mean_three"]
                )
            )
        seed_detail_max = float(max(per_seed_details))
        detail_differences[str(seed)] = seed_detail_max
        maximum_detail_difference = max(
            maximum_detail_difference, seed_detail_max
        )

    raw_bottlenecks = {
        str(seed): axis_bottlenecks(curves_by_seed[seed])
        for seed in SEEDS
    }
    bottleneck_difference = 0.0
    for axis in AXIS_DIRECTIONS:
        expected = result["bootstrap_summary"][axis]["raw_by_seed"]
        observed = {
            str(seed): raw_bottlenecks[str(seed)][axis]
            for seed in SEEDS
        }
        bottleneck_difference = max(
            bottleneck_difference,
            max_abs_difference(
                list(observed.values()), list(expected.values())
            ),
        )

    mean_curve_differences = {}
    no_reversal = {}
    for axis, names in MEAN_CURVE_NAMES.items():
        values = np.stack(
            [curves_by_seed[seed][axis] for seed in SEEDS]
        )
        mean_curve_differences[axis] = {}
        no_reversal[axis] = True
        for index, (name, direction) in enumerate(
            zip(names, AXIS_DIRECTIONS[axis])
        ):
            observed_mean = values[:, index, :].mean(axis=0)
            observed_sd = values[:, index, :].std(axis=0, ddof=1)
            expected = result["mean_component_curves"][axis][name]
            mean_difference = max_abs_difference(
                observed_mean, expected["mean"]
            )
            sd_difference = max_abs_difference(
                observed_sd, expected["sd"]
            )
            mean_curve_differences[axis][name] = {
                "mean_max_abs_difference": mean_difference,
                "sd_max_abs_difference": sd_difference,
            }
            differences = np.diff(observed_mean)
            if direction == "decreasing":
                no_reversal[axis] = bool(
                    no_reversal[axis]
                    and np.all(differences <= 0.0)
                )
            else:
                no_reversal[axis] = bool(
                    no_reversal[axis]
                    and np.all(differences >= 0.0)
                )
    mean_curve_max = max(
        item[key]
        for by_axis in mean_curve_differences.values()
        for item in by_axis.values()
        for key in (
            "mean_max_abs_difference",
            "sd_max_abs_difference",
        )
    )
    point_audit = {
        "maximum_primary_curve_abs_difference": maximum_curve_difference,
        "maximum_full_point_detail_abs_difference": (
            maximum_detail_difference
        ),
        "maximum_raw_bottleneck_abs_difference": bottleneck_difference,
        "maximum_mean_curve_or_sd_abs_difference": mean_curve_max,
        "primary_curve_differences_by_seed": curve_differences,
        "full_point_detail_differences_by_seed": detail_differences,
        "mean_curve_differences": mean_curve_differences,
        "mean_curves_no_reversal": no_reversal,
        "raw_bottlenecks": raw_bottlenecks,
    }
    passed = bool(
        maximum_curve_difference <= FLOAT_TOLERANCE
        and maximum_detail_difference <= FLOAT_TOLERANCE
        and bottleneck_difference <= FLOAT_TOLERANCE
        and mean_curve_max <= FLOAT_TOLERANCE
        and all(no_reversal.values())
    )
    append_check(
        checks,
        "independent_point_curve_detail_and_bottleneck_reproduction",
        passed,
        {
            "tolerance": FLOAT_TOLERANCE,
            "maximum_primary_curve_abs_difference": (
                maximum_curve_difference
            ),
            "maximum_full_point_detail_abs_difference": (
                maximum_detail_difference
            ),
            "maximum_raw_bottleneck_abs_difference": (
                bottleneck_difference
            ),
            "maximum_mean_curve_or_sd_abs_difference": mean_curve_max,
            "mean_curves_no_reversal": no_reversal,
        },
    )
    return curves_by_seed, point_audit


def verify_csv_shapes(checks: list[dict[str, Any]]) -> dict[str, Any]:
    point_path = (
        VALIDITY_DIR / "round8_graded_response_point_estimates.csv"
    )
    bootstrap_path = (
        VALIDITY_DIR / "round8_graded_response_bootstrap.csv"
    )
    with point_path.open("r", encoding="utf-8", newline="") as stream:
        point_rows = list(csv.DictReader(stream))
    with bootstrap_path.open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        bootstrap_rows = list(csv.DictReader(stream))
    detail = {
        "point_row_count": len(point_rows),
        "point_expected_row_count": 1575,
        "bootstrap_row_count": len(bootstrap_rows),
        "bootstrap_axes": [row["axis"] for row in bootstrap_rows],
    }
    append_check(
        checks,
        "published_csv_structure",
        (
            len(point_rows) == 1575
            and len(bootstrap_rows) == 4
            and detail["bootstrap_axes"] == ["A", "R", "S", "C1"]
        ),
        detail,
    )
    return detail


def run_bootstrap(
    prepared: dict[str, Any],
    result: dict[str, Any],
    harmonic: np.ndarray,
    checks: list[dict[str, Any]],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = {
        axis: np.empty(REPLICATES, dtype=np.float64)
        for axis in AXIS_DIRECTIONS
    }
    image_counts = np.empty(REPLICATES, dtype=np.int64)
    seed_digest = hashlib.sha256()
    component_digest = hashlib.sha256()
    first_draw = None
    last_draw = None
    component_sizes = prepared["component_sizes"]

    for replicate in range(REPLICATES):
        selected_seeds = rng.integers(0, len(SEEDS), size=len(SEEDS))
        selected_components = rng.integers(
            0, COMPONENT_COUNT, size=COMPONENT_COUNT
        )
        seed_digest.update(
            selected_seeds.astype("<i8", copy=False).tobytes()
        )
        component_digest.update(
            selected_components.astype("<i8", copy=False).tobytes()
        )
        component_counts = np.bincount(
            selected_components, minlength=COMPONENT_COUNT
        ).astype(np.int64)
        image_counts[replicate] = int(
            component_counts @ component_sizes
        )
        per_seed = {}
        for position in np.unique(selected_seeds):
            curves = curves_from_component_draw(
                prepared,
                SEEDS[int(position)],
                component_counts,
                harmonic,
            )
            per_seed[int(position)] = axis_bottlenecks(curves)
        for axis in AXIS_DIRECTIONS:
            draws[axis][replicate] = float(
                np.mean(
                    [
                        per_seed[int(position)][axis]
                        for position in selected_seeds
                    ]
                )
            )
        draw_detail = {
            "replicate": replicate,
            "selected_seed_positions": selected_seeds.tolist(),
            "selected_seed_values": [
                SEEDS[int(position)] for position in selected_seeds
            ],
            "selected_component_sha256": hashlib.sha256(
                selected_components.astype(
                    "<i8", copy=False
                ).tobytes()
            )
            .hexdigest()
            .upper(),
            "expanded_image_count": int(image_counts[replicate]),
        }
        if replicate == 0:
            first_draw = draw_detail
        if replicate == REPLICATES - 1:
            last_draw = draw_detail
        if (replicate + 1) % 100 == 0:
            print(
                json.dumps(
                    {
                        "independent_bootstrap_completed": replicate + 1,
                        "total": REPLICATES,
                        "expanded_images": int(
                            image_counts[replicate]
                        ),
                    }
                ),
                flush=True,
            )

    comparisons = {}
    maximum_difference = 0.0
    for axis in AXIS_DIRECTIONS:
        observed_ci = np.quantile(draws[axis], [0.025, 0.975])
        expected = result["bootstrap_summary"][axis]
        raw = np.asarray(
            list(expected["raw_by_seed"].values()), dtype=np.float64
        )
        observed = {
            "mean_across_seeds": float(raw.mean()),
            "sd_across_seeds": float(raw.std(ddof=1)),
            "positive_seed_count": int(np.sum(raw > 0.0)),
            "association_component_bootstrap_ci": observed_ci.tolist(),
            "ci_lower_positive": bool(observed_ci[0] > 0.0),
        }
        differences = {
            "mean": abs(
                observed["mean_across_seeds"]
                - expected["mean_across_seeds"]
            ),
            "sd": abs(
                observed["sd_across_seeds"]
                - expected["sd_across_seeds"]
            ),
            "ci": max_abs_difference(
                observed_ci,
                expected["association_component_bootstrap_ci"],
            ),
        }
        maximum_difference = max(
            maximum_difference, *differences.values()
        )
        comparisons[axis] = {
            "observed": observed,
            "expected": {
                "mean_across_seeds": expected["mean_across_seeds"],
                "sd_across_seeds": expected["sd_across_seeds"],
                "positive_seed_count": expected["positive_seed_count"],
                "association_component_bootstrap_ci": expected[
                    "association_component_bootstrap_ci"
                ],
            },
            "absolute_differences": differences,
            "draw_sha256": array_sha256(draws[axis]),
        }

    diagnostics = result["bootstrap_summary"]["_bootstrap_diagnostics"]
    image_differences = {
        "min": abs(int(image_counts.min()) - diagnostics[
            "replicate_image_count_min"
        ]),
        "max": abs(int(image_counts.max()) - diagnostics[
            "replicate_image_count_max"
        ]),
        "mean": abs(
            float(image_counts.mean())
            - diagnostics["replicate_image_count_mean"]
        ),
    }
    passed = bool(
        maximum_difference <= FLOAT_TOLERANCE
        and max(image_differences.values()) <= FLOAT_TOLERANCE
        and all(
            comparison["observed"]["positive_seed_count"]
            == comparison["expected"]["positive_seed_count"]
            and comparison["observed"]["ci_lower_positive"]
            for comparison in comparisons.values()
        )
    )
    bootstrap_audit = {
        "replicates": REPLICATES,
        "rng_seed": BOOTSTRAP_SEED,
        "statistic_order": (
            "per selected seed: minimum expected-direction adjacent "
            "step; then mean over five selected seed positions"
        ),
        "shared_cluster_draw": True,
        "seed_draw_stream_sha256": seed_digest.hexdigest().upper(),
        "component_draw_stream_sha256": (
            component_digest.hexdigest().upper()
        ),
        "first_draw": first_draw,
        "last_draw": last_draw,
        "comparisons": comparisons,
        "maximum_summary_abs_difference": maximum_difference,
        "image_count": {
            "min": int(image_counts.min()),
            "max": int(image_counts.max()),
            "mean": float(image_counts.mean()),
            "array_sha256": array_sha256(image_counts),
            "absolute_differences": image_differences,
        },
    }
    append_check(
        checks,
        "independent_exact_rng_cluster_bootstrap_reproduction",
        passed,
        {
            "tolerance": FLOAT_TOLERANCE,
            "maximum_summary_abs_difference": maximum_difference,
            "image_count_absolute_differences": image_differences,
            "all_ci_lower_bounds_positive": all(
                comparison["observed"]["ci_lower_positive"]
                for comparison in comparisons.values()
            ),
        },
    )
    draws["_image_counts"] = image_counts
    return draws, bootstrap_audit


def main() -> int:
    args = parse_args()
    if not args.points_only and not args.force:
        existing = [path for path in (AUDIT_PATH, DRAW_PATH) if path.exists()]
        if existing:
            raise RuntimeError(
                "independent output already exists; pass --force only "
                f"after preserving it: {existing}"
            )

    checks: list[dict[str, Any]] = []
    artifact_hashes = verify_artifact_hashes(checks)
    result = load_json(RESULT_PATH)
    with np.load(PRIMITIVES_PATH, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}

    invariant_audit = verify_array_invariants(arrays, result, checks)
    csv_audit = verify_csv_shapes(checks)
    prepared = build_independent_primitives(arrays)
    maximum_bootstrap_images = COMPONENT_COUNT * int(
        prepared["component_sizes"].max()
    )
    harmonic = harmonic_numbers(maximum_bootstrap_images)

    synthetic_errors = np.asarray([0, 1, 1], dtype=np.int64)
    synthetic_confidence = np.asarray([0.9, 0.9, 0.2])
    synthetic_expected = np.mean(
        [
            np.mean(np.cumsum(synthetic_errors[order]) / [1, 2, 3])
            for order in (
                np.asarray([0, 1, 2]),
                np.asarray([1, 0, 2]),
            )
        ]
    )
    synthetic_observed = direct_tie_averaged_aurc(
        synthetic_errors, synthetic_confidence
    )
    append_check(
        checks,
        "independent_tie_formula_synthetic",
        abs(synthetic_observed - synthetic_expected)
        <= FLOAT_TOLERANCE,
        {
            "observed": synthetic_observed,
            "brute_force_expected": float(synthetic_expected),
        },
    )

    _, point_audit = verify_point_results(
        arrays, prepared, result, harmonic, checks
    )
    if args.points_only:
        passed = all(check["passed"] for check in checks)
        print(
            json.dumps(
                {
                    "status": "POINTS_ONLY_PASS" if passed else "STOP",
                    "checks_passed": int(
                        sum(check["passed"] for check in checks)
                    ),
                    "checks_total": len(checks),
                    "failed": [
                        check["name"]
                        for check in checks
                        if not check["passed"]
                    ],
                    "point_max_difference": point_audit[
                        "maximum_full_point_detail_abs_difference"
                    ],
                },
                indent=2,
            )
        )
        return 0 if passed else 1

    draws, bootstrap_audit = run_bootstrap(
        prepared, result, harmonic, checks
    )
    np.savez_compressed(DRAW_PATH, **draws)
    draw_artifact = {
        "path": str(DRAW_PATH.relative_to(PROJECT_ROOT)).replace(
            "\\", "/"
        ),
        "sha256": sha256_file(DRAW_PATH),
        "bytes": DRAW_PATH.stat().st_size,
        "arrays": {
            key: {
                "shape": list(value.shape),
                "dtype": str(value.dtype),
                "array_sha256": array_sha256(value),
            }
            for key, value in draws.items()
        },
    }

    gates = {
        axis: bool(
            bootstrap_audit["comparisons"][axis]["observed"][
                "mean_across_seeds"
            ]
            > 0.0
            and bootstrap_audit["comparisons"][axis]["observed"][
                "positive_seed_count"
            ]
            >= 4
            and bootstrap_audit["comparisons"][axis]["observed"][
                "ci_lower_positive"
            ]
            and point_audit["mean_curves_no_reversal"][axis]
        )
        for axis in AXIS_DIRECTIONS
    }
    decisions_match = bool(
        gates == result["decisions"]["axis_gates"]
        and all(gates.values())
        == result["decisions"]["full_Round8_measurement_pass"]
    )
    append_check(
        checks,
        "independent_gate_decisions",
        decisions_match,
        {
            "independent_axis_gates": gates,
            "formal_axis_gates": result["decisions"]["axis_gates"],
            "independent_full_pass": all(gates.values()),
            "formal_full_pass": result["decisions"][
                "full_Round8_measurement_pass"
            ],
        },
    )

    status = "PASS" if all(check["passed"] for check in checks) else "STOP"
    audit = {
        "study": "Round 8 independent graded-response reproduction",
        "status": status,
        "independence": {
            "imports_arsc_eval_source": False,
            "formal_analysis_script_imported": False,
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
            "bootstrap_draws_recreated_from_seed": True,
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
        "frozen_artifact_hashes": artifact_hashes,
        "primitive_invariants": invariant_audit,
        "csv_structure": csv_audit,
        "point_reproduction": point_audit,
        "bootstrap_reproduction": bootstrap_audit,
        "bootstrap_draw_artifact": draw_artifact,
        "independent_decisions": {
            "axis_gates": gates,
            "full_Round8_measurement_pass": bool(all(gates.values())),
            "matches_formal_result": decisions_match,
        },
        "claim_boundary": (
            "PASS verifies computational reproduction of the frozen "
            "BDD-OIA Round 8 estimands and gates. It does not add "
            "construct, external, causal, grounding, or real-safety "
            "validity."
        ),
    }
    write_json(AUDIT_PATH, audit)
    print(
        json.dumps(
            {
                "status": status,
                "checks": audit["summary"],
                "axis_gates": gates,
                "audit": str(AUDIT_PATH.relative_to(PROJECT_ROOT)),
                "audit_sha256": sha256_file(AUDIT_PATH),
                "draws": draw_artifact,
            },
            indent=2,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
