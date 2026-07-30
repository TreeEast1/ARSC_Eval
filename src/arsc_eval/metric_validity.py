"""Utilities for falsification and sensitivity checks of ARSC metrics.

These functions do not redefine the preregistered metrics.  They expose
alternative confidence summaries and small diagnostic statistics so the
primary results can be checked for construction-driven conclusions.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from arsc_eval.metrics import exact_set_errors


CONFIDENCE_DEFINITIONS = (
    "maximum_action_probability",
    "minimum_predicted_state_probability",
    "mean_predicted_state_probability",
    "one_minus_mean_binary_entropy",
)


def predicted_state_probabilities(
    probabilities: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Return confidence assigned to each thresholded binary label state."""

    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("probabilities must be a 2-D array")
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between zero and one")
    if np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("probabilities must be within [0, 1]")
    return np.where(values >= threshold, values, 1.0 - values)


def confidence_scores(
    probabilities: np.ndarray,
    threshold: float,
    definition: str,
) -> np.ndarray:
    """Compute a scalar confidence score for each multi-label sample."""

    values = np.asarray(probabilities, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("probabilities must be a 2-D array")
    if definition == "maximum_action_probability":
        return values.max(axis=1)

    state = predicted_state_probabilities(values, threshold)
    if definition == "minimum_predicted_state_probability":
        return state.min(axis=1)
    if definition == "mean_predicted_state_probability":
        return state.mean(axis=1)
    if definition == "one_minus_mean_binary_entropy":
        clipped = np.clip(values, 1e-12, 1.0 - 1e-12)
        entropy = -(
            clipped * np.log2(clipped)
            + (1.0 - clipped) * np.log2(1.0 - clipped)
        )
        return 1.0 - entropy.mean(axis=1)
    raise ValueError(f"unknown confidence definition: {definition}")


def binary_auroc(targets: np.ndarray, scores: np.ndarray) -> float | None:
    """AUROC with average ranks for ties and no third-party dependency."""

    labels = np.asarray(targets).astype(bool)
    values = np.asarray(scores, dtype=np.float64)
    if labels.ndim != 1 or values.shape != labels.shape:
        raise ValueError("targets and scores must be aligned 1-D arrays")
    positives = int(labels.sum())
    negatives = int((~labels).sum())
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
    positive_rank_sum = float(ranks[labels].sum())
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def selective_metrics_from_confidence(
    targets: np.ndarray,
    probabilities: np.ndarray,
    confidence: np.ndarray,
    threshold: float,
    ece_bins: int = 15,
) -> dict[str, Any]:
    """Compute selective metrics for an explicitly supplied ordering score."""

    values = np.asarray(probabilities)
    scores = np.asarray(confidence, dtype=np.float64)
    if values.ndim != 2 or scores.shape != (len(values),):
        raise ValueError("probabilities and confidence must align")
    if np.any((scores < 0.0) | (scores > 1.0)):
        raise ValueError("confidence must be within [0, 1]")

    errors = exact_set_errors(targets, values, threshold)
    order = np.argsort(-scores, kind="stable")
    cumulative_risk = np.cumsum(errors[order]) / np.arange(
        1, len(errors) + 1
    )
    accepted = max(1, int(math.ceil(0.90 * len(errors))))
    correctness = 1.0 - errors

    edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece = 0.0
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if index == 0:
            in_bin = (scores >= lower) & (scores <= upper)
        else:
            in_bin = (scores > lower) & (scores <= upper)
        count = int(in_bin.sum())
        if count:
            ece += (
                abs(
                    float(correctness[in_bin].mean())
                    - float(scores[in_bin].mean())
                )
                * count
                / len(errors)
            )

    tenth = max(1, len(errors) // 10)
    return {
        "aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(
            cumulative_risk[accepted - 1]
        ),
        "ece": float(ece),
        "exact_set_error_rate": float(errors.mean()),
        "correctness_auroc": binary_auroc(correctness, scores),
        "highest_confidence_decile_error_rate": float(
            errors[order[:tenth]].mean()
        ),
        "lowest_confidence_decile_error_rate": float(
            errors[order[-tenth:]].mean()
        ),
        "risk_curve": cumulative_risk,
    }


def compare_risk_curves(
    first: np.ndarray,
    second: np.ndarray,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    """Describe dominance and crossings between aligned risk curves."""

    left = np.asarray(first, dtype=np.float64)
    right = np.asarray(second, dtype=np.float64)
    if left.ndim != 1 or left.shape != right.shape or len(left) == 0:
        raise ValueError("risk curves must be nonempty aligned 1-D arrays")
    difference = left - right
    signs = np.zeros(len(difference), dtype=np.int8)
    signs[difference > tolerance] = 1
    signs[difference < -tolerance] = -1
    nonzero = signs[signs != 0]
    crossings = (
        int(np.sum(nonzero[1:] != nonzero[:-1]))
        if len(nonzero) > 1
        else 0
    )
    return {
        "first_lower_fraction": float(np.mean(signs < 0)),
        "second_lower_fraction": float(np.mean(signs > 0)),
        "tie_fraction": float(np.mean(signs == 0)),
        "strict_first_dominance": bool(np.all(signs <= 0)),
        "strict_second_dominance": bool(np.all(signs >= 0)),
        "direction_crossings": crossings,
        "maximum_absolute_risk_gap": float(np.max(np.abs(difference))),
    }
