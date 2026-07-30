"""Explicit implementations of the requested ARSC metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _binary_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    true = y_true.astype(bool)
    pred = y_pred.astype(bool)
    tp = np.logical_and(true, pred).sum()
    fp = np.logical_and(~true, pred).sum()
    fn = np.logical_and(true, ~pred).sum()
    denominator = 2 * tp + fp + fn
    return float(2 * tp / denominator) if denominator else 0.0


def multilabel_f1(
    targets: np.ndarray,
    probabilities: np.ndarray,
    class_names: list[str],
    threshold: float = 0.5,
) -> dict[str, Any]:
    predictions = probabilities >= threshold
    per_class = {
        name: _binary_f1(targets[:, index], predictions[:, index])
        for index, name in enumerate(class_names)
    }
    return {
        "macro_f1": float(np.mean(list(per_class.values()))),
        "micro_f1": _binary_f1(targets.reshape(-1), predictions.reshape(-1)),
        "per_class_f1": per_class,
        "threshold": threshold,
    }


def exact_set_errors(
    targets: np.ndarray, probabilities: np.ndarray, threshold: float = 0.5
) -> np.ndarray:
    predictions = probabilities >= threshold
    return np.any(predictions != targets.astype(bool), axis=1).astype(np.float64)


def risk_coverage(
    targets: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
    ece_bins: int = 15,
) -> dict[str, Any]:
    confidence = probabilities.max(axis=1)
    errors = exact_set_errors(targets, probabilities, threshold)
    order = np.argsort(-confidence, kind="stable")
    sorted_errors = errors[order]
    count = len(sorted_errors)
    cumulative_risk = np.cumsum(sorted_errors) / np.arange(1, count + 1)
    coverage = np.arange(1, count + 1) / count
    accepted = max(1, math.ceil(0.90 * count))

    correctness = 1.0 - errors
    ece = 0.0
    bin_edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece_detail = []
    for index in range(ece_bins):
        lower, upper = bin_edges[index], bin_edges[index + 1]
        if index == 0:
            in_bin = (confidence >= lower) & (confidence <= upper)
        else:
            in_bin = (confidence > lower) & (confidence <= upper)
        bin_count = int(in_bin.sum())
        if not bin_count:
            continue
        average_confidence = float(confidence[in_bin].mean())
        average_accuracy = float(correctness[in_bin].mean())
        contribution = abs(average_accuracy - average_confidence) * (
            bin_count / count
        )
        ece += contribution
        ece_detail.append(
            {
                "lower": float(lower),
                "upper": float(upper),
                "count": bin_count,
                "mean_confidence": average_confidence,
                "accuracy": average_accuracy,
            }
        )

    return {
        "aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(cumulative_risk[accepted - 1]),
        "ece": float(ece),
        "confidence_definition": "maximum action probability",
        "error_definition": "any mismatch in the four-label action set",
        "risk_coverage_curve": {
            "coverage": coverage.tolist(),
            "risk": cumulative_risk.tolist(),
        },
        "ece_bins": ece_detail,
    }


def action_flip_rate(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: np.ndarray,
    threshold: float = 0.5,
) -> float:
    clean = clean_probabilities >= threshold
    perturbed = perturbed_probabilities >= threshold
    return float(np.any(clean != perturbed, axis=1).mean())


def rationale_jaccard(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: np.ndarray,
    threshold: float = 0.5,
) -> float:
    clean = clean_probabilities >= threshold
    perturbed = perturbed_probabilities >= threshold
    intersection = np.logical_and(clean, perturbed).sum(axis=1)
    union = np.logical_or(clean, perturbed).sum(axis=1)
    scores = np.ones(len(union), dtype=np.float64)
    non_empty = union > 0
    scores[non_empty] = intersection[non_empty] / union[non_empty]
    return float(scores.mean())
