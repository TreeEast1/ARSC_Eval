"""Paired, sample-level internal-validity analysis for ARSC-Eval.

This module intentionally contains only NumPy/statistical code.  Model
inference and artifact I/O live in ``scripts/analyze_internal_validity.py`` so
the estimands can be unit-tested without importing PyTorch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np


MODEL_ACTION = "Action-Only"
MODEL_JOINT = "Joint Action-Rationale"
MODEL_CALIBRATED = "Joint-Calibrated"
MODEL_ORDER = (MODEL_ACTION, MODEL_JOINT, MODEL_CALIBRATED)
PERTURBATIONS = ("brightness", "blur", "noise")

MetricKey = tuple[str, str, str, str]

PREFERRED_DIRECTION = {
    "action_macro_f1": "higher",
    "rationale_macro_f1": "higher",
    "aurc": "lower",
    "unsafe_acceptance_rate_90": "lower",
    "ece": "lower",
    "action_flip_rate": "lower",
    "rationale_jaccard": "higher",
    # Positive CEG means the positive ground-truth action probability is more
    # sensitive to the critical mask than to the matched noncritical mask.
    # It is evidence of selectivity, not automatically evidence of quality.
    "causal_evidence_gap": "context_dependent",
    "mean_delta_critical": "context_dependent",
    "mean_delta_noncritical": "context_dependent",
}


def sigmoid(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Numerically stable sigmoid with a positive scalar temperature."""

    if temperature <= 0:
        raise ValueError("temperature must be positive")
    scaled = np.clip(np.asarray(logits, dtype=np.float64) / temperature, -50, 50)
    return 1.0 / (1.0 + np.exp(-scaled))


def _binary_f1(targets: np.ndarray, predictions: np.ndarray) -> float:
    targets_bool = np.asarray(targets).astype(bool)
    predictions_bool = np.asarray(predictions).astype(bool)
    true_positive = np.logical_and(targets_bool, predictions_bool).sum()
    false_positive = np.logical_and(~targets_bool, predictions_bool).sum()
    false_negative = np.logical_and(targets_bool, ~predictions_bool).sum()
    denominator = 2 * true_positive + false_positive + false_negative
    return float(2 * true_positive / denominator) if denominator else 0.0


def macro_f1(
    targets: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> float:
    """Macro average of one-vs-rest binary F1 across output dimensions."""

    predictions = np.asarray(probabilities) >= threshold
    targets = np.asarray(targets)
    if targets.ndim != 2 or predictions.shape != targets.shape:
        raise ValueError("targets and probabilities must have equal 2-D shapes")
    return float(
        np.mean(
            [
                _binary_f1(targets[:, column], predictions[:, column])
                for column in range(targets.shape[1])
            ]
        )
    )


def selective_metrics(
    targets: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    ece_bins: int = 15,
) -> dict[str, float]:
    """Return scalar versions of the primary risk-coverage metrics."""

    targets = np.asarray(targets).astype(bool)
    probabilities = np.asarray(probabilities)
    if targets.ndim != 2 or probabilities.shape != targets.shape:
        raise ValueError("targets and probabilities must have equal 2-D shapes")
    if not len(targets):
        raise ValueError("selective metrics require at least one sample")

    predicted = probabilities >= threshold
    errors = np.any(predicted != targets, axis=1).astype(np.float64)
    confidence = probabilities.max(axis=1)
    order = np.argsort(-confidence, kind="stable")
    cumulative_risk = np.cumsum(errors[order]) / np.arange(1, len(errors) + 1)
    accepted = max(1, int(np.ceil(0.90 * len(errors))))

    correctness = 1.0 - errors
    ece = 0.0
    edges = np.linspace(0.0, 1.0, ece_bins + 1)
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if index == 0:
            in_bin = (confidence >= lower) & (confidence <= upper)
        else:
            in_bin = (confidence > lower) & (confidence <= upper)
        count = int(in_bin.sum())
        if count:
            ece += (
                abs(
                    float(correctness[in_bin].mean())
                    - float(confidence[in_bin].mean())
                )
                * count
                / len(errors)
            )

    return {
        "aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(cumulative_risk[accepted - 1]),
        "ece": float(ece),
    }


def correct_action_probability(
    targets: np.ndarray,
    probabilities: np.ndarray,
) -> np.ndarray:
    """Mean probability assigned to each sample's positive action labels."""

    targets = np.asarray(targets)
    probabilities = np.asarray(probabilities)
    positive = targets > 0.5
    counts = positive.sum(axis=1)
    if targets.ndim != 2 or probabilities.shape != targets.shape:
        raise ValueError("targets and probabilities must have equal 2-D shapes")
    if np.any(counts == 0):
        raise ValueError("causal-evidence input has an empty action label")
    return (probabilities * positive).sum(axis=1) / counts


def correct_action_state_probability(
    targets: np.ndarray,
    probabilities: np.ndarray,
    action_dimension_mask: np.ndarray,
) -> np.ndarray:
    """Probability assigned to the annotated state of rationale-bound actions.

    Unlike ``correct_action_probability``, this handles both positive and
    negative ground-truth action states.  This matters for rationales such as
    ``no_left_lane``, which are associated with the Left decision dimension
    even when the annotated Left action is zero.
    """

    targets = np.asarray(targets)
    probabilities = np.asarray(probabilities)
    selected = np.asarray(action_dimension_mask).astype(bool)
    if (
        targets.ndim != 2
        or probabilities.shape != targets.shape
        or selected.shape != targets.shape
    ):
        raise ValueError(
            "targets, probabilities, and action mask must align in 2-D"
        )
    counts = selected.sum(axis=1)
    if np.any(counts == 0):
        raise ValueError("each mask sample must bind at least one action")
    correct_state = np.where(targets > 0.5, probabilities, 1.0 - probabilities)
    return (correct_state * selected).sum(axis=1) / counts


def causal_gap_samples(
    targets: np.ndarray,
    clean_probabilities: np.ndarray,
    critical_probabilities: np.ndarray,
    noncritical_probabilities: np.ndarray,
    action_dimension_mask: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Return the per-sample components of the Causal Evidence Gap.

    For the existing estimand,

    ``(clean - critical) - (clean - noncritical)``

    the clean term cancels exactly.  It is retained in this implementation to
    expose both component drops and to audit the intended definition.
    """

    probability = (
        correct_action_probability
        if action_dimension_mask is None
        else lambda current_targets, current_probabilities: (
            correct_action_state_probability(
                current_targets,
                current_probabilities,
                action_dimension_mask,
            )
        )
    )
    clean = probability(targets, clean_probabilities)
    critical = probability(targets, critical_probabilities)
    noncritical = probability(targets, noncritical_probabilities)
    delta_critical = clean - critical
    delta_noncritical = clean - noncritical
    return {
        "mean_delta_critical": delta_critical,
        "mean_delta_noncritical": delta_noncritical,
        "causal_evidence_gap": delta_critical - delta_noncritical,
    }


def action_flip_samples(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: np.ndarray,
    threshold: float,
) -> np.ndarray:
    clean = np.asarray(clean_probabilities) >= threshold
    perturbed = np.asarray(perturbed_probabilities) >= threshold
    if clean.shape != perturbed.shape:
        raise ValueError("clean and perturbed action arrays must align")
    return np.any(clean != perturbed, axis=1).astype(np.float64)


def rationale_jaccard_samples(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: np.ndarray,
    threshold: float,
) -> np.ndarray:
    clean = np.asarray(clean_probabilities) >= threshold
    perturbed = np.asarray(perturbed_probabilities) >= threshold
    if clean.shape != perturbed.shape:
        raise ValueError("clean and perturbed rationale arrays must align")
    intersection = np.logical_and(clean, perturbed).sum(axis=1)
    union = np.logical_or(clean, perturbed).sum(axis=1)
    scores = np.ones(len(union), dtype=np.float64)
    nonempty = union > 0
    scores[nonempty] = intersection[nonempty] / union[nonempty]
    return scores


def prepare_probabilities(
    cache: Mapping[str, np.ndarray],
    temperature: float,
    threshold: float,
) -> dict[str, Any]:
    """Convert a validated logit cache into reusable analysis arrays."""

    prepared: dict[str, Any] = {
        "test_targets": np.asarray(cache["test_action_targets"]),
        "test_rationale_targets": np.asarray(
            cache["test_rationale_targets"]
        ),
        "mask_targets": np.asarray(cache["mask_action_targets"]),
        "clean_action": {
            MODEL_ACTION: sigmoid(cache["test_clean_action_logits"]),
            MODEL_JOINT: sigmoid(cache["test_clean_joint_action_logits"]),
            MODEL_CALIBRATED: sigmoid(
                cache["test_clean_joint_action_logits"], temperature
            ),
        },
        "clean_rationale": {
            MODEL_JOINT: sigmoid(
                cache["test_clean_joint_rationale_logits"]
            ),
            # Calibration changes action logits only.
            MODEL_CALIBRATED: sigmoid(
                cache["test_clean_joint_rationale_logits"]
            ),
        },
        "perturbed_action": {},
        "perturbed_rationale": {},
        "mask_clean": {},
        "mask_critical": {},
        "mask_noncritical": {},
    }
    if "mask_action_dimension_mask" in cache:
        prepared["mask_action_dimension_mask"] = np.asarray(
            cache["mask_action_dimension_mask"]
        ).astype(bool)
    for perturbation in PERTURBATIONS:
        prepared["perturbed_action"][perturbation] = {
            MODEL_ACTION: sigmoid(
                cache[f"test_{perturbation}_action_logits"]
            ),
            MODEL_JOINT: sigmoid(
                cache[f"test_{perturbation}_joint_action_logits"]
            ),
            MODEL_CALIBRATED: sigmoid(
                cache[f"test_{perturbation}_joint_action_logits"],
                temperature,
            ),
        }
        rationale = sigmoid(
            cache[f"test_{perturbation}_joint_rationale_logits"]
        )
        prepared["perturbed_rationale"][perturbation] = {
            MODEL_JOINT: rationale,
            MODEL_CALIBRATED: rationale,
        }

    for model, cache_stem, model_temperature in (
        (MODEL_ACTION, "action", 1.0),
        (MODEL_JOINT, "joint_action", 1.0),
        (MODEL_CALIBRATED, "joint_action", temperature),
    ):
        prepared["mask_clean"][model] = sigmoid(
            cache[f"mask_clean_{cache_stem}_logits"], model_temperature
        )
        prepared["mask_critical"][model] = sigmoid(
            cache[f"mask_critical_{cache_stem}_logits"], model_temperature
        )
        prepared["mask_noncritical"][model] = sigmoid(
            cache[f"mask_noncritical_{cache_stem}_logits"],
            model_temperature,
        )

    prepared["flip_samples"] = {}
    prepared["jaccard_samples"] = {}
    for perturbation in PERTURBATIONS:
        prepared["flip_samples"][perturbation] = {
            model: action_flip_samples(
                prepared["clean_action"][model],
                prepared["perturbed_action"][perturbation][model],
                threshold,
            )
            for model in MODEL_ORDER
        }
        prepared["jaccard_samples"][perturbation] = {
            model: rationale_jaccard_samples(
                prepared["clean_rationale"][model],
                prepared["perturbed_rationale"][perturbation][model],
                threshold,
            )
            for model in (MODEL_JOINT, MODEL_CALIBRATED)
        }
    return prepared


def test_metric_estimates(
    prepared: Mapping[str, Any],
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[MetricKey, float]:
    """Compute clean and perturbation metrics on one paired resample."""

    def take(array: np.ndarray) -> np.ndarray:
        return array if indices is None else array[indices]

    estimates: dict[MetricKey, float] = {}
    action_targets = take(prepared["test_targets"])
    for model in MODEL_ORDER:
        probabilities = take(prepared["clean_action"][model])
        estimates[("clean", "official_test", "action_macro_f1", model)] = (
            macro_f1(action_targets, probabilities, threshold)
        )
        selective = selective_metrics(
            action_targets, probabilities, threshold
        )
        for metric, value in selective.items():
            estimates[("clean", "official_test", metric, model)] = value

    rationale_targets = take(prepared["test_rationale_targets"])
    for model in (MODEL_JOINT, MODEL_CALIBRATED):
        estimates[
            ("clean", "official_test", "rationale_macro_f1", model)
        ] = macro_f1(
            rationale_targets,
            take(prepared["clean_rationale"][model]),
            threshold,
        )

    for perturbation in PERTURBATIONS:
        for model in MODEL_ORDER:
            estimates[
                (
                    "consistency",
                    perturbation,
                    "action_flip_rate",
                    model,
                )
            ] = float(take(prepared["flip_samples"][perturbation][model]).mean())
        for model in (MODEL_JOINT, MODEL_CALIBRATED):
            estimates[
                (
                    "consistency",
                    perturbation,
                    "rationale_jaccard",
                    model,
                )
            ] = float(
                take(prepared["jaccard_samples"][perturbation][model]).mean()
            )

    for model in MODEL_ORDER:
        per_sample_mean = np.mean(
            [
                prepared["flip_samples"][perturbation][model]
                for perturbation in PERTURBATIONS
            ],
            axis=0,
        )
        estimates[
            ("consistency", "mean_three", "action_flip_rate", model)
        ] = float(take(per_sample_mean).mean())
    for model in (MODEL_JOINT, MODEL_CALIBRATED):
        per_sample_mean = np.mean(
            [
                prepared["jaccard_samples"][perturbation][model]
                for perturbation in PERTURBATIONS
            ],
            axis=0,
        )
        estimates[
            ("consistency", "mean_three", "rationale_jaccard", model)
        ] = float(take(per_sample_mean).mean())
    return estimates


def mask_metric_estimates(
    prepared: Mapping[str, Any],
    indices: np.ndarray | None = None,
    condition: str = "detector_subset",
) -> dict[MetricKey, float]:
    """Compute direct CEG and its components on one paired mask resample."""

    def take(array: np.ndarray) -> np.ndarray:
        return array if indices is None else array[indices]

    targets = take(prepared["mask_targets"])
    action_dimension_mask = (
        take(prepared["mask_action_dimension_mask"])
        if "mask_action_dimension_mask" in prepared
        else None
    )
    estimates: dict[MetricKey, float] = {}
    # Temperature scaling is a monotone post-processing of the same Joint
    # checkpoint, not a separate evidence-use model. Keep the direct RQ2
    # comparison to the two independently trained systems.
    for model in (MODEL_ACTION, MODEL_JOINT):
        components = causal_gap_samples(
            targets,
            take(prepared["mask_clean"][model]),
            take(prepared["mask_critical"][model]),
            take(prepared["mask_noncritical"][model]),
            action_dimension_mask,
        )
        for metric, samples in components.items():
            estimates[("critical_masks", condition, metric, model)] = (
                float(samples.mean())
            )
    return estimates


def paired_bootstrap(
    compute: Callable[[np.ndarray | None], dict[MetricKey, float]],
    sample_count: int,
    replicates: int,
    rng: np.random.Generator,
) -> tuple[dict[MetricKey, float], dict[MetricKey, np.ndarray]]:
    """Paired nonparametric bootstrap using one index draw for every model."""

    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    estimates = compute(None)
    draws = {
        key: np.empty(replicates, dtype=np.float64) for key in estimates
    }
    expected_keys = set(estimates)
    for replicate in range(replicates):
        indices = rng.integers(0, sample_count, size=sample_count)
        current = compute(indices)
        if set(current) != expected_keys:
            raise RuntimeError("metric keys changed across bootstrap replicates")
        for key, value in current.items():
            draws[key][replicate] = value
    return estimates, draws


def percentile_interval(
    values: np.ndarray,
    confidence_level: float,
) -> tuple[float, float]:
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")
    alpha = (1.0 - confidence_level) / 2.0
    lower, upper = np.quantile(values, [alpha, 1.0 - alpha])
    return float(lower), float(upper)


def _comparison_pairs(models: list[str]) -> list[tuple[str, str]]:
    available = set(models)
    candidates = (
        (MODEL_JOINT, MODEL_ACTION),
        (MODEL_CALIBRATED, MODEL_ACTION),
        (MODEL_CALIBRATED, MODEL_JOINT),
    )
    return [
        (model, reference)
        for model, reference in candidates
        if model in available and reference in available
    ]


def summarize_families(
    estimates: Mapping[MetricKey, float],
    draws: Mapping[MetricKey, np.ndarray],
    sample_sizes: Mapping[tuple[str, str], int],
    confidence_level: float,
) -> list[dict[str, Any]]:
    """Group estimates and paired contrasts into JSON-friendly families."""

    grouped: dict[tuple[str, str, str], list[MetricKey]] = defaultdict(list)
    for key in estimates:
        grouped[key[:3]].append(key)

    families: list[dict[str, Any]] = []
    for group_key in sorted(grouped):
        cohort, condition, metric = group_key
        keys = grouped[group_key]
        by_model = {key[3]: key for key in keys}
        models = [model for model in MODEL_ORDER if model in by_model]
        model_estimates = []
        for model in models:
            key = by_model[model]
            lower, upper = percentile_interval(
                draws[key], confidence_level
            )
            model_estimates.append(
                {
                    "model": model,
                    "estimate": float(estimates[key]),
                    "ci_lower": lower,
                    "ci_upper": upper,
                }
            )

        contrasts = []
        for model, reference in _comparison_pairs(models):
            model_key = by_model[model]
            reference_key = by_model[reference]
            contrast_draws = draws[model_key] - draws[reference_key]
            lower, upper = percentile_interval(
                contrast_draws, confidence_level
            )
            contrasts.append(
                {
                    "model": model,
                    "reference_model": reference,
                    "direction": f"{model} - {reference}",
                    "estimate": float(
                        estimates[model_key] - estimates[reference_key]
                    ),
                    "ci_lower": lower,
                    "ci_upper": upper,
                    "bootstrap_probability_gt_zero": float(
                        np.mean(contrast_draws > 0)
                    ),
                    "bootstrap_probability_lt_zero": float(
                        np.mean(contrast_draws < 0)
                    ),
                }
            )

        families.append(
            {
                "cohort": cohort,
                "condition": condition,
                "metric": metric,
                "preferred_direction": PREFERRED_DIRECTION.get(
                    metric, "unspecified"
                ),
                "samples": int(sample_sizes[(cohort, condition)]),
                "model_estimates": model_estimates,
                "paired_contrasts": contrasts,
            }
        )
    return families
