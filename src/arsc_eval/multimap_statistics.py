"""Component-aggregated statistics for the frozen Round 9 bootstrap."""

from __future__ import annotations

from typing import Any

import numpy as np

from arsc_eval.graded_response import (
    MODEL_KEYS,
    PERTURBATION_KEYS,
)
from arsc_eval.internal_validity import rationale_jaccard_samples


Q_COUNT = 5


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


def confidence_group_ids(
    confidence: np.ndarray,
) -> tuple[np.ndarray, int]:
    """Assign confidence-tie groups in descending-confidence order."""

    values = np.asarray(confidence, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("confidence must be a nonempty 1-D array")
    _, ascending = np.unique(values, return_inverse=True)
    count = int(ascending.max()) + 1
    return (count - 1 - ascending).astype(np.int32), count


def harmonic_numbers(maximum: int) -> np.ndarray:
    if maximum <= 0:
        raise ValueError("maximum must be positive")
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
    """Exact tie-averaged AURC for integer-weighted observations."""

    error_values = np.asarray(errors, dtype=np.int64)
    groups = np.asarray(group_ids, dtype=np.int64)
    weights = np.asarray(image_weights, dtype=np.int64)
    if (
        error_values.ndim != 1
        or groups.shape != error_values.shape
        or weights.shape != error_values.shape
        or group_count <= 0
        or np.any(weights < 0)
        or not np.all(np.isin(error_values, (0, 1)))
    ):
        raise ValueError("invalid grouped AURC arrays")
    counts = np.bincount(
        groups, weights=weights, minlength=group_count
    )
    error_counts = np.bincount(
        groups,
        weights=weights * error_values,
        minlength=group_count,
    )
    active = counts > 0
    counts = counts[active]
    error_counts = error_counts[active]
    if not len(counts):
        raise ValueError("at least one observation must have positive weight")
    integer_counts = counts.astype(np.int64)
    starts = np.cumsum(integer_counts) - integer_counts
    stops = starts + integer_counts
    if int(stops[-1]) >= len(harmonic):
        raise ValueError("harmonic array is too short")
    harmonic_span = harmonic[stops] - harmonic[starts]
    prior_errors = np.cumsum(error_counts) - error_counts
    contribution = (
        prior_errors * harmonic_span
        + (error_counts / counts)
        * (counts - starts * harmonic_span)
    )
    return float(contribution.sum() / stops[-1])


def component_sums(
    values: np.ndarray,
    offsets: np.ndarray,
    flat_images: np.ndarray,
) -> np.ndarray:
    ordered = np.asarray(values)[np.asarray(flat_images, dtype=np.int64)]
    return np.add.reduceat(
        ordered, np.asarray(offsets, dtype=np.int64)[:-1], axis=0
    )


def prepare_component_statistics(
    primitive: dict[str, Any],
    source_maps: np.ndarray,
    component_image_offsets: np.ndarray,
    component_image_indices: np.ndarray,
    component_id_by_image: np.ndarray,
) -> dict[str, Any]:
    """Precompute per-component sufficient statistics for one map/seed."""

    maps = np.asarray(source_maps, dtype=np.int64)
    offsets = np.asarray(component_image_offsets, dtype=np.int64)
    flat = np.asarray(component_image_indices, dtype=np.int64)
    component_ids = np.asarray(component_id_by_image, dtype=np.int64)
    action_targets = np.asarray(primitive["action_targets"], dtype=bool)
    rationale_targets = np.asarray(
        primitive["rationale_targets"], dtype=bool
    )
    sample_count = len(action_targets)
    if (
        maps.shape != (Q_COUNT, sample_count)
        or rationale_targets.shape[0] != sample_count
        or component_ids.shape != (sample_count,)
        or offsets.ndim != 1
        or offsets[0] != 0
        or offsets[-1] != sample_count
        or flat.shape != (sample_count,)
    ):
        raise ValueError("map, target, and component arrays do not align")
    component_count = len(offsets) - 1
    if component_count <= 0:
        raise ValueError("at least one component is required")

    result: dict[str, Any] = {
        "A": {},
        "R": [],
        "S": {},
        "C1": {},
        "component_sizes": np.diff(offsets).astype(np.int64),
        "component_id_by_image": component_ids,
    }
    for model in MODEL_KEYS:
        prediction = np.asarray(
            primitive["action_predictions"][model], dtype=bool
        )
        errors = np.asarray(
            primitive["exact_set_errors"][model], dtype=np.int64
        )
        confidence = np.asarray(
            primitive["confidence"][model], dtype=np.float64
        )
        result["A"][model] = []
        result["S"][model] = []
        result["C1"][model] = []
        for source in maps:
            target = action_targets[source]
            counts = tuple(
                component_sums(part, offsets, flat).astype(np.uint16)
                for part in (
                    np.logical_and(target, prediction),
                    np.logical_and(~target, prediction),
                    np.logical_and(target, ~prediction),
                )
            )
            result["A"][model].append(counts)
            groups, group_count = confidence_group_ids(confidence[source])
            result["S"][model].append(
                {
                    "errors": errors,
                    "group_ids": groups,
                    "group_count": group_count,
                }
            )
            per_perturbation = []
            for perturbation in PERTURBATION_KEYS:
                perturbed = np.asarray(
                    primitive["action_perturbed_predictions"][
                        perturbation
                    ][model],
                    dtype=bool,
                )[source]
                flips = np.any(prediction != perturbed, axis=1)
                per_perturbation.append(
                    component_sums(flips, offsets, flat).astype(
                        np.uint16
                    )
                )
            result["C1"][model].append(per_perturbation)

    rationale_prediction = np.asarray(
        primitive["rationale_predictions"], dtype=bool
    )
    result["C1"]["rationale"] = []
    for source in maps:
        target = rationale_targets[source]
        result["R"].append(
            tuple(
                component_sums(part, offsets, flat).astype(np.uint16)
                for part in (
                    np.logical_and(target, rationale_prediction),
                    np.logical_and(~target, rationale_prediction),
                    np.logical_and(target, ~rationale_prediction),
                )
            )
        )
        per_perturbation = []
        for perturbation in PERTURBATION_KEYS:
            perturbed = np.asarray(
                primitive["rationale_perturbed_predictions"][perturbation],
                dtype=bool,
            )[source]
            samples = rationale_jaccard_samples(
                rationale_prediction, perturbed, 0.5
            )
            per_perturbation.append(
                component_sums(samples, offsets, flat).astype(np.float64)
            )
        result["C1"]["rationale"].append(per_perturbation)
    return result


def curves_from_component_counts(
    prepared: dict[str, Any],
    component_counts: np.ndarray,
    harmonic: np.ndarray,
) -> dict[str, np.ndarray]:
    """Evaluate all four axes for one complete-component multiset."""

    counts = np.asarray(component_counts, dtype=np.int64)
    component_sizes = np.asarray(
        prepared["component_sizes"], dtype=np.int64
    )
    if (
        counts.shape != component_sizes.shape
        or np.any(counts < 0)
        or int(counts.sum()) <= 0
    ):
        raise ValueError("component counts must be nonnegative and nonempty")
    sample_total = int(counts @ component_sizes)
    image_weights = counts[
        np.asarray(prepared["component_id_by_image"], dtype=np.int64)
    ]

    action_curves = []
    safety_curves = []
    for model in MODEL_KEYS:
        action = []
        safety = []
        for q_index in range(Q_COUNT):
            tp_component, fp_component, fn_component = prepared["A"][
                model
            ][q_index]
            tp = counts @ tp_component
            fp = counts @ fp_component
            fn = counts @ fn_component
            action.append(float(f1_from_counts(tp, fp, fn).mean()))
            safety_data = prepared["S"][model][q_index]
            safety.append(
                grouped_tie_averaged_aurc(
                    safety_data["errors"],
                    safety_data["group_ids"],
                    safety_data["group_count"],
                    image_weights,
                    harmonic,
                )
            )
        action_curves.append(action)
        safety_curves.append(safety)

    rationale_curve = []
    for q_index in range(Q_COUNT):
        tp_component, fp_component, fn_component = prepared["R"][q_index]
        tp = counts @ tp_component
        fp = counts @ fp_component
        fn = counts @ fn_component
        rationale_curve.append(float(f1_from_counts(tp, fp, fn).mean()))

    c1_curves = []
    for component_name in (*MODEL_KEYS, "rationale"):
        curve = []
        for q_index in range(Q_COUNT):
            per_perturbation = [
                float(counts @ values) / sample_total
                for values in prepared["C1"][component_name][q_index]
            ]
            curve.append(float(np.mean(per_perturbation)))
        c1_curves.append(curve)
    return {
        "A": np.asarray(action_curves, dtype=np.float64),
        "R": np.asarray([rationale_curve], dtype=np.float64),
        "S": np.asarray(safety_curves, dtype=np.float64),
        "C1": np.asarray(c1_curves, dtype=np.float64),
    }
