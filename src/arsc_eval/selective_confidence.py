"""Confidence constructions for the selective-risk (S) construct audit.

The frozen ARSC selective-risk axis pairs an *exact-set* error definition
(``any of the four thresholded action bits is wrong``) with a *single-bit*
confidence score (``max_i p_i``).  This module exposes that frozen baseline
alongside two pre-registered alternatives so the mismatch can be measured
instead of argued about.

Nothing here replaces the frozen primary result.  ``S0`` reproduces the
published operationalisation bit-for-bit; ``S1`` and ``S2`` exist only to
answer whether the Joint vs Action-Only ordering survives a change of
confidence construction.

Definitions (all evaluated on the same calibrated probabilities and the same
0.5 decision threshold as the frozen protocol):

``S0`` maximum positive-class probability
    ``conf = max_i p_i`` -- the frozen baseline.

``S1`` exact-set probability proxy
    ``conf = prod_i q_i`` with ``q_i = p_i`` when action bit ``i`` is
    predicted positive and ``q_i = 1 - p_i`` otherwise.  Under an
    independence assumption across the four action heads this is an estimate
    of ``P(the entire predicted action set is correct)``, i.e. it is
    semantically matched to the exact-set error definition.  Evaluated in
    log-space.

``S2`` weakest-bit certainty
    ``conf = min_i max(p_i, 1 - p_i)`` -- the certainty of the least certain
    bit in the predicted action set.

The decision threshold is 0.5 and temperature scaling uses a positive scalar,
so the predicted action set -- and therefore the exact-set error vector -- is
identical for all three constructions.  Only the ranking of samples changes.
"""

from __future__ import annotations

from typing import Any

import numpy as np


CONFIDENCE_IDS = ("S0", "S1", "S2")

CONFIDENCE_LABELS = {
    "S0": "S0 max positive probability (frozen primary)",
    "S1": "S1 exact-set probability proxy",
    "S2": "S2 weakest-bit certainty",
}

CONFIDENCE_FORMULAS = {
    "S0": "conf = max_i p_i",
    "S1": "conf = prod_i q_i, q_i = p_i if bit_i predicted else 1 - p_i",
    "S2": "conf = min_i max(p_i, 1 - p_i)",
}

CONFIDENCE_ROLES = {
    "S0": "frozen_primary",
    "S1": "construct_audit_alternative",
    "S2": "construct_audit_alternative",
}

#: Smallest probability admitted before taking a logarithm in ``S1``.
_LOG_FLOOR = 1e-300


def exact_set_error_vector(
    targets: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
) -> np.ndarray:
    """Per-sample exact-set error: 1.0 if any action bit is wrong."""

    targets = np.asarray(targets).astype(bool)
    probabilities = np.asarray(probabilities)
    if targets.ndim != 2 or probabilities.shape != targets.shape:
        raise ValueError("targets and probabilities must have equal 2-D shapes")
    predicted = probabilities >= threshold
    return np.any(predicted != targets, axis=1).astype(np.float64)


def confidence_s0(probabilities: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Frozen baseline: maximum positive-class probability."""

    del threshold  # the frozen baseline ignores the predicted set
    return np.asarray(probabilities, dtype=np.float64).max(axis=1)


def confidence_s1(probabilities: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Exact-set probability proxy, evaluated in log-space."""

    probabilities = np.asarray(probabilities, dtype=np.float64)
    predicted = probabilities >= threshold
    matched = np.where(predicted, probabilities, 1.0 - probabilities)
    log_confidence = np.log(np.clip(matched, _LOG_FLOOR, 1.0)).sum(axis=1)
    return np.exp(log_confidence)


def confidence_s2(probabilities: np.ndarray, threshold: float = 0.5) -> np.ndarray:
    """Certainty of the least certain bit in the predicted action set."""

    del threshold  # max(p, 1 - p) is threshold-symmetric at 0.5
    probabilities = np.asarray(probabilities, dtype=np.float64)
    return np.maximum(probabilities, 1.0 - probabilities).min(axis=1)


CONFIDENCE_FUNCTIONS = {
    "S0": confidence_s0,
    "S1": confidence_s1,
    "S2": confidence_s2,
}


def confidence_scores(
    construction: str,
    probabilities: np.ndarray,
    threshold: float = 0.5,
) -> np.ndarray:
    """Dispatch to one of the three pre-registered confidence constructions."""

    if construction not in CONFIDENCE_FUNCTIONS:
        raise ValueError(
            f"unknown confidence construction {construction!r}; "
            f"the audit is frozen to {CONFIDENCE_IDS}"
        )
    return CONFIDENCE_FUNCTIONS[construction](probabilities, threshold)


def expected_calibration_error(
    confidence: np.ndarray,
    errors: np.ndarray,
    ece_bins: int = 15,
) -> float:
    """Equal-width binned ECE against exact-set correctness.

    Binning matches ``arsc_eval.internal_validity.selective_metrics``: the
    first bin is closed on both sides, every later bin is left-open.
    """

    confidence = np.asarray(confidence, dtype=np.float64)
    correctness = 1.0 - np.asarray(errors, dtype=np.float64)
    count = len(confidence)
    edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece = 0.0
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if index == 0:
            in_bin = (confidence >= lower) & (confidence <= upper)
        else:
            in_bin = (confidence > lower) & (confidence <= upper)
        bin_count = int(in_bin.sum())
        if bin_count:
            ece += (
                abs(
                    float(correctness[in_bin].mean())
                    - float(confidence[in_bin].mean())
                )
                * bin_count
                / count
            )
    return float(ece)


def selective_metrics_from_confidence(
    errors: np.ndarray,
    confidence: np.ndarray,
    ece_bins: int = 15,
    coverage: float = 0.90,
) -> dict[str, float]:
    """AURC, UAR@coverage and ECE for a given error/confidence pair.

    Uses the frozen conventions: descending confidence with a stable sort,
    cumulative risk averaged over every coverage level for AURC, and the
    ``ceil(coverage * n)``-th accepted sample for the unsafe acceptance rate.
    """

    errors = np.asarray(errors, dtype=np.float64)
    confidence = np.asarray(confidence, dtype=np.float64)
    if errors.shape != confidence.shape or errors.ndim != 1:
        raise ValueError("errors and confidence must be aligned 1-D arrays")
    if not len(errors):
        raise ValueError("selective metrics require at least one sample")

    order = np.argsort(-confidence, kind="stable")
    cumulative_risk = np.cumsum(errors[order]) / np.arange(1, len(errors) + 1)
    accepted = max(1, int(np.ceil(coverage * len(errors))))
    return {
        "aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(cumulative_risk[accepted - 1]),
        "ece": float(expected_calibration_error(confidence, errors, ece_bins)),
    }


def audit_selective_metrics(
    targets: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
    ece_bins: int = 15,
) -> dict[str, Any]:
    """Evaluate all three confidence constructions on one model/seed."""

    errors = exact_set_error_vector(targets, probabilities, threshold)
    result: dict[str, Any] = {
        "exact_set_error_rate": float(errors.mean()),
        "sample_count": int(len(errors)),
    }
    for construction in CONFIDENCE_IDS:
        confidence = confidence_scores(construction, probabilities, threshold)
        metrics = selective_metrics_from_confidence(errors, confidence, ece_bins)
        result[construction] = {
            **metrics,
            "mean_confidence": float(confidence.mean()),
            "min_confidence": float(confidence.min()),
            "max_confidence": float(confidence.max()),
            "formula": CONFIDENCE_FORMULAS[construction],
            "role": CONFIDENCE_ROLES[construction],
        }
    return result
