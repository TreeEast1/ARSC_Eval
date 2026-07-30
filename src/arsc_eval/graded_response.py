"""Pure NumPy helpers for the preregistered Round 8 graded-response study."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from arsc_eval.internal_validity import (
    action_flip_samples,
    macro_f1,
    rationale_jaccard_samples,
)
from arsc_eval.metric_validity import binary_auroc


Q_COUNT = 5
MODEL_KEYS = ("action_only", "joint")
PERTURBATION_KEYS = ("brightness", "blur", "noise")
AXIS_DIRECTIONS = {
    "A": ("decreasing", "decreasing"),
    "R": ("decreasing",),
    "S": ("increasing", "increasing"),
    "C1": ("increasing", "increasing", "decreasing"),
}


def stable_aurc(
    errors: np.ndarray,
    confidence: np.ndarray,
) -> float:
    """AURC with the repository's historical canonical stable-tie rule."""

    error_values = np.asarray(errors, dtype=np.float64)
    score_values = np.asarray(confidence, dtype=np.float64)
    _validate_safety_arrays(error_values, score_values)
    order = np.argsort(-score_values, kind="stable")
    cumulative = np.cumsum(error_values[order]) / np.arange(
        1, len(error_values) + 1
    )
    return float(cumulative.mean())


def tie_averaged_aurc(
    errors: np.ndarray,
    confidence: np.ndarray,
) -> float:
    """Exact expected AURC over all orderings within confidence ties."""

    error_values = np.asarray(errors, dtype=np.float64)
    score_values = np.asarray(confidence, dtype=np.float64)
    _validate_safety_arrays(error_values, score_values)
    order = np.argsort(-score_values, kind="stable")
    sorted_scores = score_values[order]
    sorted_errors = error_values[order]
    cumulative_errors = 0.0
    total_expected_risk = 0.0
    start = 0
    while start < len(order):
        stop = start + 1
        while (
            stop < len(order)
            and sorted_scores[stop] == sorted_scores[start]
        ):
            stop += 1
        block_size = stop - start
        block_errors = float(sorted_errors[start:stop].sum())
        expected_error_per_position = block_errors / block_size
        positions = np.arange(start + 1, stop + 1, dtype=np.float64)
        within_block = np.arange(1, block_size + 1, dtype=np.float64)
        expected_cumulative = (
            cumulative_errors
            + within_block * expected_error_per_position
        )
        total_expected_risk += float(
            np.sum(expected_cumulative / positions)
        )
        cumulative_errors += block_errors
        start = stop
    return total_expected_risk / len(order)


def confidence_diagnostics(
    errors: np.ndarray,
    confidence: np.ndarray,
    ece_bins: int = 15,
) -> dict[str, float | None]:
    """Return stable-tie S diagnostics for fixed errors and confidence."""

    error_values = np.asarray(errors, dtype=np.float64)
    score_values = np.asarray(confidence, dtype=np.float64)
    _validate_safety_arrays(error_values, score_values)
    if np.any((score_values < 0.0) | (score_values > 1.0)):
        raise ValueError("confidence must be within [0, 1]")
    if ece_bins <= 0:
        raise ValueError("ece_bins must be positive")

    order = np.argsort(-score_values, kind="stable")
    cumulative_risk = np.cumsum(error_values[order]) / np.arange(
        1, len(error_values) + 1
    )
    accepted = max(1, int(math.ceil(0.90 * len(error_values))))
    correctness = 1.0 - error_values
    edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece = 0.0
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if index == 0:
            in_bin = (score_values >= lower) & (score_values <= upper)
        else:
            in_bin = (score_values > lower) & (score_values <= upper)
        count = int(in_bin.sum())
        if count:
            ece += (
                abs(
                    float(correctness[in_bin].mean())
                    - float(score_values[in_bin].mean())
                )
                * count
                / len(error_values)
            )
    tenth = max(1, len(error_values) // 10)
    return {
        "tie_averaged_aurc": tie_averaged_aurc(
            error_values, score_values
        ),
        "canonical_stable_aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(
            cumulative_risk[accepted - 1]
        ),
        "correctness_auroc": binary_auroc(correctness, score_values),
        "ece": float(ece),
        "exact_set_error_rate": float(error_values.mean()),
        "highest_confidence_decile_error_rate": float(
            error_values[order[:tenth]].mean()
        ),
        "lowest_confidence_decile_error_rate": float(
            error_values[order[-tenth:]].mean()
        ),
    }


def _validate_safety_arrays(
    errors: np.ndarray,
    confidence: np.ndarray,
) -> None:
    if (
        errors.ndim != 1
        or confidence.shape != errors.shape
        or len(errors) == 0
    ):
        raise ValueError(
            "errors and confidence must be nonempty aligned 1-D arrays"
        )
    if not np.all(np.isfinite(errors)) or not np.all(
        np.isfinite(confidence)
    ):
        raise ValueError("errors and confidence must be finite")
    if not np.all(np.isin(errors, (0.0, 1.0))):
        raise ValueError("errors must be binary")


def bottleneck_statistic(
    curves: Sequence[Sequence[float]],
    directions: Sequence[str],
) -> float:
    """Return the weakest expected-direction adjacent step across curves."""

    values = np.asarray(curves, dtype=np.float64)
    if (
        values.ndim != 2
        or values.shape[1] != Q_COUNT
        or len(directions) != values.shape[0]
    ):
        raise ValueError(
            "curves must have five q values and one direction per curve"
        )
    steps = []
    for curve, direction in zip(values, directions):
        if direction == "decreasing":
            steps.append(curve[:-1] - curve[1:])
        elif direction == "increasing":
            steps.append(curve[1:] - curve[:-1])
        else:
            raise ValueError(
                "directions must be increasing or decreasing"
            )
    return float(np.min(np.concatenate(steps)))


def mean_curves_have_no_reversal(
    curves_by_seed: Sequence[Sequence[Sequence[float]]],
    directions: Sequence[str],
    tolerance: float = 0.0,
) -> bool:
    """Check every component of the across-seed mean curve."""

    values = np.asarray(curves_by_seed, dtype=np.float64)
    if values.ndim != 3 or values.shape[2] != Q_COUNT:
        raise ValueError(
            "curves_by_seed must have shape (seeds, components, five q)"
        )
    mean_curves = values.mean(axis=0)
    if len(directions) != len(mean_curves):
        raise ValueError("directions must align with components")
    for curve, direction in zip(mean_curves, directions):
        differences = np.diff(curve)
        if direction == "decreasing" and np.any(
            differences > tolerance
        ):
            return False
        if direction == "increasing" and np.any(
            differences < -tolerance
        ):
            return False
        if direction not in ("decreasing", "increasing"):
            raise ValueError(
                "directions must be increasing or decreasing"
            )
    return True


def graded_axis_curves(
    prepared: Mapping[str, Any],
    source_maps: np.ndarray,
    indices: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Compute the four frozen primary-axis component curves for one seed."""

    maps = np.asarray(source_maps, dtype=np.int64)
    action_targets = np.asarray(prepared["action_targets"])
    rationale_targets = np.asarray(prepared["rationale_targets"])
    sample_count = len(action_targets)
    if (
        action_targets.ndim != 2
        or rationale_targets.ndim != 2
        or len(rationale_targets) != sample_count
        or maps.shape != (Q_COUNT, sample_count)
    ):
        raise ValueError("prepared targets and five source maps must align")
    selected = (
        np.arange(sample_count, dtype=np.int64)
        if indices is None
        else np.asarray(indices, dtype=np.int64)
    )
    if selected.ndim != 1 or len(selected) == 0:
        raise ValueError("indices must be a nonempty one-dimensional array")
    if np.any(selected < 0) or np.any(selected >= sample_count):
        raise ValueError("indices contain an out-of-range sample")

    action_curves = []
    safety_curves = []
    for model in MODEL_KEYS:
        action_predictions = np.asarray(
            prepared["action_predictions"][model]
        )
        errors = np.asarray(prepared["exact_set_errors"][model])
        confidence = np.asarray(prepared["confidence"][model])
        if (
            action_predictions.shape != action_targets.shape
            or errors.shape != (sample_count,)
            or confidence.shape != (sample_count,)
        ):
            raise ValueError(f"prepared arrays do not align for {model}")
        action_curves.append(
            [
                macro_f1(
                    action_targets[source[selected]],
                    action_predictions[selected],
                    0.5,
                )
                for source in maps
            ]
        )
        safety_curves.append(
            [
                tie_averaged_aurc(
                    errors[selected], confidence[source[selected]]
                )
                for source in maps
            ]
        )

    rationale_predictions = np.asarray(
        prepared["rationale_predictions"]
    )
    if rationale_predictions.shape != rationale_targets.shape:
        raise ValueError("rationale predictions do not align")
    rationale_curve = [
        macro_f1(
            rationale_targets[source[selected]],
            rationale_predictions[selected],
            0.5,
        )
        for source in maps
    ]

    action_c1_curves = []
    for model in MODEL_KEYS:
        clean = np.asarray(prepared["action_predictions"][model])
        perturbed = prepared["action_perturbed_predictions"]
        by_q = []
        for source in maps:
            per_perturbation = []
            for perturbation in PERTURBATION_KEYS:
                values = np.asarray(perturbed[perturbation][model])
                if values.shape != clean.shape:
                    raise ValueError(
                        f"{perturbation}/{model} action arrays do not align"
                    )
                per_perturbation.append(
                    action_flip_samples(
                        clean[selected],
                        values[source[selected]],
                        0.5,
                    )
                )
            by_q.append(float(np.mean(per_perturbation, axis=0).mean()))
        action_c1_curves.append(by_q)

    rationale_clean = rationale_predictions
    rationale_perturbed = prepared["rationale_perturbed_predictions"]
    rationale_c1_curve = []
    for source in maps:
        per_perturbation = []
        for perturbation in PERTURBATION_KEYS:
            values = np.asarray(rationale_perturbed[perturbation])
            if values.shape != rationale_clean.shape:
                raise ValueError(
                    f"{perturbation} rationale arrays do not align"
                )
            per_perturbation.append(
                rationale_jaccard_samples(
                    rationale_clean[selected],
                    values[source[selected]],
                    0.5,
                )
            )
        rationale_c1_curve.append(
            float(np.mean(per_perturbation, axis=0).mean())
        )

    return {
        "A": np.asarray(action_curves, dtype=np.float64),
        "R": np.asarray([rationale_curve], dtype=np.float64),
        "S": np.asarray(safety_curves, dtype=np.float64),
        "C1": np.asarray(
            [*action_c1_curves, rationale_c1_curve],
            dtype=np.float64,
        ),
    }


def axis_bottlenecks(
    curves: Mapping[str, np.ndarray],
) -> dict[str, float]:
    """Compute one preregistered minimum adjacent-step statistic per axis."""

    if set(curves) != set(AXIS_DIRECTIONS):
        raise ValueError("curves must contain exactly A, R, S, and C1")
    return {
        axis: bottleneck_statistic(curves[axis], AXIS_DIRECTIONS[axis])
        for axis in AXIS_DIRECTIONS
    }


def mean_selected_seed_bottlenecks(
    curves_by_seed: Sequence[Mapping[str, np.ndarray]],
    selected_seed_indices: np.ndarray,
) -> dict[str, float]:
    """Take each selected seed's bottleneck before averaging across seeds."""

    selected = np.asarray(selected_seed_indices, dtype=np.int64)
    if selected.ndim != 1 or len(selected) == 0:
        raise ValueError("selected_seed_indices must be nonempty and 1-D")
    if np.any(selected < 0) or np.any(selected >= len(curves_by_seed)):
        raise ValueError("selected seed index out of range")
    per_seed = [axis_bottlenecks(curves_by_seed[index]) for index in selected]
    return {
        axis: float(np.mean([values[axis] for values in per_seed]))
        for axis in AXIS_DIRECTIONS
    }


def mean_curve_checks(
    curves_by_seed: Sequence[Mapping[str, np.ndarray]],
) -> dict[str, bool]:
    """Check every component of each five-seed mean curve for reversals."""

    if not curves_by_seed:
        raise ValueError("curves_by_seed must be nonempty")
    return {
        axis: mean_curves_have_no_reversal(
            [curves[axis] for curves in curves_by_seed],
            AXIS_DIRECTIONS[axis],
        )
        for axis in AXIS_DIRECTIONS
    }
