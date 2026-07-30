"""Frozen clean A/R/S/C1 metrics for the BDD-OIA paired-seed study."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.internal_validity import (
    PERTURBATIONS,
    action_flip_samples,
    rationale_jaccard_samples,
    selective_metrics,
    sigmoid,
)
from arsc_eval.metrics import multilabel_f1


MODEL_ACTION = "Action-Only"
MODEL_JOINT = "Joint Action-Rationale"


def rationale_jaccard_components(
    clean: np.ndarray,
    perturbed: np.ndarray,
    threshold: float,
    indices: np.ndarray | None = None,
) -> dict[str, float]:
    clean_sets = np.asarray(clean) >= threshold
    perturbed_sets = np.asarray(perturbed) >= threshold
    if indices is not None:
        clean_sets = clean_sets[indices]
        perturbed_sets = perturbed_sets[indices]
    union = np.logical_or(clean_sets, perturbed_sets).sum(axis=1)
    scores = rationale_jaccard_samples(
        clean_sets.astype(np.float64),
        perturbed_sets.astype(np.float64),
        0.5,
    )
    nonempty = union > 0
    return {
        "unconditional": float(scores.mean()),
        "empty_empty_fraction": float(np.mean(~nonempty)),
        "union_nonempty_conditional": (
            float(scores[nonempty].mean()) if np.any(nonempty) else 1.0
        ),
    }


def prepare_rq1_arrays(
    cache: Mapping[str, np.ndarray],
    action_temperature: float,
    joint_temperature: float,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {
        "action_targets": np.asarray(cache["test_action_targets"]),
        "rationale_targets": np.asarray(cache["test_rationale_targets"]),
        "raw_clean": {
            MODEL_ACTION: sigmoid(cache["test_clean_action_logits"]),
            MODEL_JOINT: sigmoid(cache["test_clean_joint_action_logits"]),
        },
        "calibrated_clean": {
            MODEL_ACTION: sigmoid(
                cache["test_clean_action_logits"], action_temperature
            ),
            MODEL_JOINT: sigmoid(
                cache["test_clean_joint_action_logits"], joint_temperature
            ),
        },
        "raw_perturbed": {},
        "rationale_clean": sigmoid(
            cache["test_clean_joint_rationale_logits"]
        ),
        "rationale_perturbed": {},
    }
    for kind in PERTURBATIONS:
        prepared["raw_perturbed"][kind] = {
            MODEL_ACTION: sigmoid(
                cache[f"test_{kind}_action_logits"]
            ),
            MODEL_JOINT: sigmoid(
                cache[f"test_{kind}_joint_action_logits"]
            ),
        }
        prepared["rationale_perturbed"][kind] = sigmoid(
            cache[f"test_{kind}_joint_rationale_logits"]
        )
    return prepared


def rq1_metric_estimates(
    prepared: Mapping[str, Any],
    threshold: float = 0.5,
    indices: np.ndarray | None = None,
) -> dict[str, float]:
    def take(values: np.ndarray) -> np.ndarray:
        return values if indices is None else values[indices]

    action_targets = take(prepared["action_targets"])
    rationale_targets = take(prepared["rationale_targets"])
    result: dict[str, float] = {}
    for model in (MODEL_ACTION, MODEL_JOINT):
        raw = take(prepared["raw_clean"][model])
        calibrated = take(prepared["calibrated_clean"][model])
        action = multilabel_f1(
            action_targets, raw, ACTION_NAMES, threshold
        )
        result[f"action_macro_f1::{model}"] = action["macro_f1"]
        result[f"action_micro_f1::{model}"] = action["micro_f1"]
        raw_safety = selective_metrics(action_targets, raw, threshold)
        calibrated_safety = selective_metrics(
            action_targets, calibrated, threshold
        )
        result[f"aurc::{model}"] = calibrated_safety["aurc"]
        result[f"unsafe_acceptance_rate_90::{model}"] = (
            calibrated_safety["unsafe_acceptance_rate_90"]
        )
        result[f"ece_calibrated::{model}"] = calibrated_safety["ece"]
        result[f"ece_uncalibrated::{model}"] = raw_safety["ece"]

    rationale = multilabel_f1(
        rationale_targets,
        take(prepared["rationale_clean"]),
        RATIONALE_NAMES,
        threshold,
    )
    result[f"rationale_macro_f1::{MODEL_JOINT}"] = rationale["macro_f1"]
    result[f"rationale_micro_f1::{MODEL_JOINT}"] = rationale["micro_f1"]

    for kind in PERTURBATIONS:
        for model in (MODEL_ACTION, MODEL_JOINT):
            flips = action_flip_samples(
                prepared["raw_clean"][model],
                prepared["raw_perturbed"][kind][model],
                threshold,
            )
            result[f"action_flip_rate_{kind}::{model}"] = float(
                take(flips).mean()
            )
        components = rationale_jaccard_components(
            prepared["rationale_clean"],
            prepared["rationale_perturbed"][kind],
            threshold,
            indices,
        )
        for name, value in components.items():
            result[
                f"rationale_jaccard_{kind}_{name}::{MODEL_JOINT}"
            ] = value

    for model in (MODEL_ACTION, MODEL_JOINT):
        per_image = np.mean(
            [
                action_flip_samples(
                    prepared["raw_clean"][model],
                    prepared["raw_perturbed"][kind][model],
                    threshold,
                )
                for kind in PERTURBATIONS
            ],
            axis=0,
        )
        result[f"action_flip_rate_mean_three::{model}"] = float(
            take(per_image).mean()
        )
    result[f"rationale_jaccard_mean_three::{MODEL_JOINT}"] = float(
        np.mean(
            [
                result[
                    f"rationale_jaccard_{kind}_unconditional::"
                    f"{MODEL_JOINT}"
                ]
                for kind in PERTURBATIONS
            ]
        )
    )

    result["delta_action_macro_f1::Joint-Action"] = (
        result[f"action_macro_f1::{MODEL_JOINT}"]
        - result[f"action_macro_f1::{MODEL_ACTION}"]
    )
    for metric in (
        "aurc",
        "unsafe_acceptance_rate_90",
        "ece_calibrated",
        "ece_uncalibrated",
    ):
        result[f"delta_{metric}::Joint-Action"] = (
            result[f"{metric}::{MODEL_JOINT}"]
            - result[f"{metric}::{MODEL_ACTION}"]
        )
    for kind in (*PERTURBATIONS, "mean_three"):
        metric = f"action_flip_rate_{kind}"
        result[f"advantage_{metric}::Action-Joint"] = (
            result[f"{metric}::{MODEL_ACTION}"]
            - result[f"{metric}::{MODEL_JOINT}"]
        )
    return result
