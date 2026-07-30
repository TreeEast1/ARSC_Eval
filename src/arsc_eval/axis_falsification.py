"""Pure NumPy controls for the frozen ARSC-axis falsification suite.

The functions in this module do not perform model inference, training, data
selection, or artifact I/O.  They implement only the transformations frozen in
``outputs/validity/arsc_axis_falsification_protocol.json`` so they can be
validated on synthetic arrays before any real intervention outcome is read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from arsc_eval.internal_validity import (
    action_flip_samples,
    rationale_jaccard_samples,
)
from arsc_eval.metric_validity import selective_metrics_from_confidence
from arsc_eval.metrics import exact_set_errors, multilabel_f1


def array_sha256(values: np.ndarray) -> str:
    """Hash the lossless contiguous bytes of an array."""

    contiguous = np.ascontiguousarray(np.asarray(values))
    return hashlib.sha256(contiguous.tobytes()).hexdigest().upper()


def cyclic_source_indices(length: int, offset: int) -> np.ndarray:
    """Return ``source[i] = (i + offset) mod length``."""

    if length <= 1:
        raise ValueError("a cyclic derangement requires at least two rows")
    normalized = int(offset) % length
    if normalized == 0:
        raise ValueError("offset must produce a non-identity mapping")
    return (np.arange(length, dtype=np.int64) + normalized) % length


def shifted_column_sources(width: int, shift: int) -> np.ndarray:
    """Return a no-fixed-point cyclic source-column map."""

    return cyclic_source_indices(width, shift)


def intervene_targets(
    targets: np.ndarray,
    row_sources: np.ndarray | None = None,
    column_sources: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the frozen source-row and source-column maps to targets."""

    values = np.asarray(targets)
    if values.ndim != 2:
        raise ValueError("targets must be a 2-D array")
    result = values
    if row_sources is not None:
        rows = np.asarray(row_sources, dtype=np.int64)
        if rows.shape != (len(values),):
            raise ValueError("row source map must align with targets")
        if np.any((rows < 0) | (rows >= len(values))):
            raise ValueError("row source map contains an invalid index")
        result = result[rows]
    if column_sources is not None:
        columns = np.asarray(column_sources, dtype=np.int64)
        if columns.shape != (values.shape[1],):
            raise ValueError("column source map must align with targets")
        if np.any((columns < 0) | (columns >= values.shape[1])):
            raise ValueError("column source map contains an invalid index")
        result = result[:, columns]
    return np.asarray(result)


def f1_control_estimates(
    targets: np.ndarray,
    probabilities: np.ndarray,
    class_names: Sequence[str],
    row_sources: np.ndarray,
    column_sources: np.ndarray,
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[str, dict[str, Any]]:
    """Compute perfect, original, and three frozen target controls."""

    values = np.asarray(targets)
    scores = np.asarray(probabilities)
    if values.ndim != 2 or scores.shape != values.shape:
        raise ValueError("targets and probabilities must be aligned 2-D arrays")
    if len(class_names) != values.shape[1]:
        raise ValueError("class names must align with target columns")

    controls = {
        "perfect": (values, values),
        "original": (values, scores),
        "row_destroyed": (
            intervene_targets(values, row_sources=row_sources),
            scores,
        ),
        "class_destroyed": (
            intervene_targets(values, column_sources=column_sources),
            scores,
        ),
        "row_and_class_destroyed": (
            intervene_targets(
                values,
                row_sources=row_sources,
                column_sources=column_sources,
            ),
            scores,
        ),
    }
    if indices is not None:
        selected = np.asarray(indices, dtype=np.int64)
        controls = {
            name: (control_targets[selected], control_scores[selected])
            for name, (control_targets, control_scores) in controls.items()
        }
    result: dict[str, dict[str, Any]] = {}
    for name, (control_targets, control_scores) in controls.items():
        estimates = multilabel_f1(
            control_targets,
            control_scores,
            list(class_names),
            threshold,
        )
        predictions = control_scores >= threshold
        estimates["target_positive_count"] = {
            class_name: int(control_targets[:, column].astype(bool).sum())
            for column, class_name in enumerate(class_names)
        }
        estimates["predicted_positive_count"] = {
            class_name: int(predictions[:, column].sum())
            for column, class_name in enumerate(class_names)
        }
        result[name] = estimates
    return result


def fixed_random_scores(sample_count: int, seed: int) -> np.ndarray:
    """Create unique scores whose descending order is one frozen permutation."""

    if sample_count <= 1:
        raise ValueError("random ordering requires at least two samples")
    order = np.random.default_rng(seed).permutation(sample_count)
    descending = np.linspace(1.0, 0.0, sample_count, dtype=np.float64)
    scores = np.empty(sample_count, dtype=np.float64)
    scores[order] = descending
    return scores


def crossed_bootstrap_draw(
    rng: np.random.Generator,
    seeds: Sequence[int],
    sample_count: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw seeds and one shared canonical-image multiset."""

    seed_values = np.asarray(seeds, dtype=np.int64)
    if seed_values.ndim != 1 or len(seed_values) == 0:
        raise ValueError("seeds must be a nonempty one-dimensional sequence")
    if sample_count <= 0:
        raise ValueError("sample count must be positive")
    selected_seeds = rng.choice(
        seed_values, size=len(seed_values), replace=True
    )
    shared_images = rng.integers(
        0, sample_count, size=sample_count, dtype=np.int64
    )
    return selected_seeds, shared_images


def confidence_control_scores(
    targets: np.ndarray,
    probabilities: np.ndarray,
    random_scores: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Return fixed oracle/original/random/adversarial confidence scores."""

    values = np.asarray(probabilities)
    random_values = np.asarray(random_scores, dtype=np.float64)
    if values.ndim != 2 or random_values.shape != (len(values),):
        raise ValueError("probabilities and random scores must align")
    if np.any((random_values < 0.0) | (random_values > 1.0)):
        raise ValueError("random scores must be within [0, 1]")
    errors = exact_set_errors(targets, values, threshold)
    correct = errors == 0.0
    oracle = np.where(
        correct,
        0.75 + 0.25 * random_values,
        0.25 * random_values,
    )
    adversarial = np.where(
        ~correct,
        0.75 + 0.25 * random_values,
        0.25 * random_values,
    )
    return errors, {
        "oracle": oracle,
        "original": values.max(axis=1),
        "random": random_values.copy(),
        "adversarial": adversarial,
    }


def safety_control_estimates(
    targets: np.ndarray,
    probabilities: np.ndarray,
    random_scores: np.ndarray,
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[str, dict[str, Any]]:
    """Evaluate selective metrics without changing predictions or errors."""

    errors, controls = confidence_control_scores(
        targets, probabilities, random_scores, threshold
    )
    values = np.asarray(probabilities)
    selected_targets = np.asarray(targets)
    if indices is not None:
        selected = np.asarray(indices, dtype=np.int64)
        selected_targets = selected_targets[selected]
        values = values[selected]
        errors = errors[selected]
        controls = {
            name: scores[selected] for name, scores in controls.items()
        }
    result: dict[str, dict[str, Any]] = {}
    for name, confidence in controls.items():
        estimates = selective_metrics_from_confidence(
            selected_targets,
            values,
            confidence,
            threshold,
        )
        estimates.pop("risk_curve")
        result[name] = estimates
    prediction_hash = array_sha256(values >= threshold)
    error_hash = array_sha256(errors)
    for estimates in result.values():
        estimates["prediction_sha256"] = prediction_hash
        estimates["exact_set_error_sha256"] = error_hash
    return result


def action_pairing_estimates(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: Mapping[str, np.ndarray],
    wrong_sources: np.ndarray,
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute identity, correct, and frozen-wrong action flip controls."""

    clean = np.asarray(clean_probabilities)
    sources = np.asarray(wrong_sources, dtype=np.int64)
    if clean.ndim != 2 or sources.shape != (len(clean),):
        raise ValueError("clean probabilities and wrong map must align")
    selected = (
        np.arange(len(clean), dtype=np.int64)
        if indices is None
        else np.asarray(indices, dtype=np.int64)
    )
    clean_selected = clean[selected]
    identity = action_flip_samples(
        clean_selected, clean_selected, threshold
    )
    controls: dict[str, dict[str, float]] = {
        "identity": {"self": float(identity.mean())},
        "correct": {},
        "wrong": {},
    }
    for name, perturbed_values in perturbed_probabilities.items():
        perturbed = np.asarray(perturbed_values)
        if perturbed.shape != clean.shape:
            raise ValueError(f"perturbation {name!r} does not align")
        correct = action_flip_samples(
            clean_selected, perturbed[selected], threshold
        )
        wrong = action_flip_samples(
            clean_selected, perturbed[sources[selected]], threshold
        )
        controls["correct"][name] = float(correct.mean())
        controls["wrong"][name] = float(wrong.mean())
    perturbation_names = tuple(perturbed_probabilities)
    controls["correct"]["mean_three"] = float(
        np.mean(
            [
                controls["correct"][name]
                for name in perturbation_names
            ]
        )
    )
    controls["wrong"]["mean_three"] = float(
        np.mean(
            [controls["wrong"][name] for name in perturbation_names]
        )
    )
    controls["primary_contrast"] = (
        controls["wrong"]["mean_three"]
        - controls["correct"]["mean_three"]
    )
    return controls


def rationale_pairing_estimates(
    clean_probabilities: np.ndarray,
    perturbed_probabilities: Mapping[str, np.ndarray],
    wrong_sources: np.ndarray,
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[str, Any]:
    """Compute identity, correct, and frozen-wrong rationale Jaccard controls."""

    clean = np.asarray(clean_probabilities)
    sources = np.asarray(wrong_sources, dtype=np.int64)
    if clean.ndim != 2 or sources.shape != (len(clean),):
        raise ValueError("clean probabilities and wrong map must align")
    selected = (
        np.arange(len(clean), dtype=np.int64)
        if indices is None
        else np.asarray(indices, dtype=np.int64)
    )
    clean_selected = clean[selected]
    identity = rationale_jaccard_samples(
        clean_selected, clean_selected, threshold
    )
    controls: dict[str, dict[str, float]] = {
        "identity": {"self": float(identity.mean())},
        "correct": {},
        "wrong": {},
    }
    for name, perturbed_values in perturbed_probabilities.items():
        perturbed = np.asarray(perturbed_values)
        if perturbed.shape != clean.shape:
            raise ValueError(f"perturbation {name!r} does not align")
        correct = rationale_jaccard_samples(
            clean_selected, perturbed[selected], threshold
        )
        wrong = rationale_jaccard_samples(
            clean_selected, perturbed[sources[selected]], threshold
        )
        controls["correct"][name] = float(correct.mean())
        controls["wrong"][name] = float(wrong.mean())
    perturbation_names = tuple(perturbed_probabilities)
    controls["correct"]["mean_three"] = float(
        np.mean(
            [
                controls["correct"][name]
                for name in perturbation_names
            ]
        )
    )
    controls["wrong"]["mean_three"] = float(
        np.mean(
            [controls["wrong"][name] for name in perturbation_names]
        )
    )
    controls["primary_contrast"] = (
        controls["correct"]["mean_three"]
        - controls["wrong"]["mean_three"]
    )
    return controls
