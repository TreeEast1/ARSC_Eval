"""Run offline falsification and sensitivity checks for the four ARSC axes.

The analysis consumes the frozen v2 per-sample prediction cache.  Alternative
thresholds and confidence definitions are explicitly exploratory and never
replace the preregistered threshold=0.5 / maximum-probability primary result.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.internal_validity import (
    PERTURBATIONS,
    action_flip_samples,
    causal_gap_samples,
    rationale_jaccard_samples,
    sigmoid,
)
from arsc_eval.metric_validity import (
    CONFIDENCE_DEFINITIONS,
    compare_risk_curves,
    confidence_scores,
    selective_metrics_from_confidence,
)
from arsc_eval.metrics import multilabel_f1
from arsc_eval.utils import json_safe, write_json


MODEL_SPECS = (
    ("Action-Only", "action", 1.0),
    ("Joint Action-Rationale", "joint_action", 1.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache",
        default="outputs/validity/prediction_cache/internal_validity_v2.npz",
    )
    parser.add_argument(
        "--calibration",
        default="outputs/calibration.json",
    )
    parser.add_argument(
        "--output-json",
        default="outputs/validity/metric_validity_sensitivity.json",
    )
    parser.add_argument(
        "--output-csv",
        default="outputs/validity/metric_validity_thresholds.csv",
    )
    parser.add_argument(
        "--thresholds",
        default="0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70",
    )
    parser.add_argument("--random-seed", type=int, default=20260731)
    return parser.parse_args()


def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_temperature(path: Path) -> float:
    return float(json.loads(path.read_text(encoding="utf-8"))["temperature"])


def probability_bundle(
    cache: np.lib.npyio.NpzFile,
    temperature: float,
) -> dict[str, dict[str, Any]]:
    bundle: dict[str, dict[str, Any]] = {}
    for model, stem, model_temperature in (
        *MODEL_SPECS,
        ("Joint-Calibrated", "joint_action", temperature),
    ):
        bundle[model] = {
            "clean": sigmoid(
                cache[f"test_clean_{stem}_logits"], model_temperature
            ),
            "perturbed": {
                kind: sigmoid(
                    cache[f"test_{kind}_{stem}_logits"],
                    model_temperature,
                )
                for kind in PERTURBATIONS
            },
        }
    joint_rationale = {
        "clean": sigmoid(cache["test_clean_joint_rationale_logits"]),
        "perturbed": {
            kind: sigmoid(
                cache[f"test_{kind}_joint_rationale_logits"]
            )
            for kind in PERTURBATIONS
        },
    }
    bundle["Joint Action-Rationale"]["rationale"] = joint_rationale
    bundle["Joint-Calibrated"]["rationale"] = joint_rationale
    return bundle


def threshold_rows(
    probabilities: dict[str, dict[str, Any]],
    action_targets: np.ndarray,
    rationale_targets: np.ndarray,
    thresholds: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        for model, values in probabilities.items():
            clean = values["clean"]
            primary_confidence = confidence_scores(
                clean, threshold, "maximum_action_probability"
            )
            safety = selective_metrics_from_confidence(
                action_targets,
                clean,
                primary_confidence,
                threshold,
            )
            flips = [
                float(
                    action_flip_samples(
                        clean,
                        values["perturbed"][kind],
                        threshold,
                    ).mean()
                )
                for kind in PERTURBATIONS
            ]
            rationale_jaccard = None
            if "rationale" in values:
                rationale_jaccard = float(
                    np.mean(
                        [
                            rationale_jaccard_samples(
                                values["rationale"]["clean"],
                                values["rationale"]["perturbed"][kind],
                                threshold,
                            ).mean()
                            for kind in PERTURBATIONS
                        ]
                    )
                )
            action_f1 = multilabel_f1(
                action_targets, clean, ACTION_NAMES, threshold
            )
            rationale_f1 = None
            if "rationale" in values:
                rationale_f1 = multilabel_f1(
                    rationale_targets,
                    values["rationale"]["clean"],
                    RATIONALE_NAMES,
                    threshold,
                )["macro_f1"]
            rows.append(
                {
                    "threshold": threshold,
                    "model": model,
                    "action_macro_f1": action_f1["macro_f1"],
                    "rationale_macro_f1": rationale_f1,
                    "aurc": safety["aurc"],
                    "unsafe_acceptance_rate_90": safety[
                        "unsafe_acceptance_rate_90"
                    ],
                    "ece": safety["ece"],
                    "exact_set_error_rate": safety[
                        "exact_set_error_rate"
                    ],
                    "mean_action_flip_rate": float(np.mean(flips)),
                    "mean_rationale_jaccard": rationale_jaccard,
                }
            )
    return rows


def contrast_stability(
    rows: list[dict[str, Any]],
    thresholds: list[float],
) -> dict[str, Any]:
    by_key = {
        (float(row["threshold"]), str(row["model"])): row for row in rows
    }
    metrics = (
        "action_macro_f1",
        "aurc",
        "unsafe_acceptance_rate_90",
        "ece",
        "mean_action_flip_rate",
    )
    result: dict[str, Any] = {}
    for metric in metrics:
        values = []
        for threshold in thresholds:
            joint = by_key[(threshold, "Joint Action-Rationale")][metric]
            action = by_key[(threshold, "Action-Only")][metric]
            values.append(float(joint) - float(action))
        nonzero_signs = np.sign(values)
        nonzero_signs = nonzero_signs[nonzero_signs != 0]
        reversals = (
            int(np.sum(nonzero_signs[1:] != nonzero_signs[:-1]))
            if len(nonzero_signs) > 1
            else 0
        )
        result[metric] = {
            "direction": "Joint - Action-Only",
            "values": [
                {"threshold": t, "contrast": value}
                for t, value in zip(thresholds, values)
            ],
            "minimum": float(min(values)),
            "maximum": float(max(values)),
            "sign_reversals": reversals,
            "same_direction_all_thresholds": bool(
                np.all(np.asarray(values) >= 0)
                or np.all(np.asarray(values) <= 0)
            ),
        }
    return result


def confidence_sensitivity(
    probabilities: dict[str, dict[str, Any]],
    targets: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    by_definition: dict[str, Any] = {}
    for definition in CONFIDENCE_DEFINITIONS:
        models: dict[str, Any] = {}
        curves: dict[str, np.ndarray] = {}
        for model, values in probabilities.items():
            scores = confidence_scores(
                values["clean"], threshold, definition
            )
            metrics = selective_metrics_from_confidence(
                targets, values["clean"], scores, threshold
            )
            curves[model] = metrics.pop("risk_curve")
            models[model] = metrics
        by_definition[definition] = {
            "models": models,
            "joint_vs_action_risk_curve": compare_risk_curves(
                curves["Joint Action-Rationale"],
                curves["Action-Only"],
            ),
            "joint_minus_action": {
                metric: (
                    models["Joint Action-Rationale"][metric]
                    - models["Action-Only"][metric]
                )
                for metric in (
                    "aurc",
                    "unsafe_acceptance_rate_90",
                    "ece",
                    "correctness_auroc",
                )
            },
        }
    return by_definition


def sanity_checks(
    cache: np.lib.npyio.NpzFile,
    probabilities: dict[str, dict[str, Any]],
    seed: int,
) -> dict[str, Any]:
    synthetic_targets = np.eye(len(ACTION_NAMES), dtype=np.float64)
    perfect = multilabel_f1(
        synthetic_targets,
        synthetic_targets,
        ACTION_NAMES,
        0.5,
    )
    all_zero = multilabel_f1(
        synthetic_targets,
        np.zeros_like(synthetic_targets),
        ACTION_NAMES,
        0.5,
    )
    all_one = multilabel_f1(
        synthetic_targets,
        np.ones_like(synthetic_targets),
        ACTION_NAMES,
        0.5,
    )
    joint = probabilities["Joint Action-Rationale"]
    identity_flip = {
        model: float(
            action_flip_samples(values["clean"], values["clean"], 0.5).mean()
        )
        for model, values in probabilities.items()
    }
    identity_jaccard = float(
        rationale_jaccard_samples(
            joint["rationale"]["clean"],
            joint["rationale"]["clean"],
            0.5,
        ).mean()
    )

    mask_targets = np.asarray(cache["mask_action_targets"])
    action_mask = np.asarray(cache["mask_action_dimension_mask"]).astype(bool)
    clean = sigmoid(cache["mask_clean_joint_action_logits"])
    critical = sigmoid(cache["mask_critical_joint_action_logits"])
    control = sigmoid(cache["mask_noncritical_joint_action_logits"])
    ceg = causal_gap_samples(
        mask_targets, clean, critical, control, action_mask
    )["causal_evidence_gap"]
    swapped = causal_gap_samples(
        mask_targets, clean, control, critical, action_mask
    )["causal_evidence_gap"]

    errors = (
        np.any(
            (joint["clean"] >= 0.5)
            != np.asarray(cache["test_action_targets"]).astype(bool),
            axis=1,
        )
        .astype(np.float64)
    )
    rng = np.random.default_rng(seed)
    random_confidence = rng.random(len(errors))
    constant_confidence = np.full(len(errors), 0.5)
    random_safety = selective_metrics_from_confidence(
        cache["test_action_targets"],
        joint["clean"],
        random_confidence,
        0.5,
    )
    constant_safety = selective_metrics_from_confidence(
        cache["test_action_targets"],
        joint["clean"],
        constant_confidence,
        0.5,
    )
    random_safety.pop("risk_curve")
    constant_safety.pop("risk_curve")

    rationale_targets = np.asarray(cache["test_rationale_targets"])
    rationale_probabilities = joint["rationale"]["clean"]
    observed_rationale = multilabel_f1(
        rationale_targets,
        rationale_probabilities,
        RATIONALE_NAMES,
        0.5,
    )
    permutation = rng.permutation(len(rationale_targets))
    permuted_rationale = multilabel_f1(
        rationale_targets[permutation],
        rationale_probabilities,
        RATIONALE_NAMES,
        0.5,
    )
    clean_rationale_sets = rationale_probabilities >= 0.5
    rationale_unions = clean_rationale_sets.sum(axis=1)

    return {
        "perfect_action_prediction": {
            "macro_f1": perfect["macro_f1"],
            "micro_f1": perfect["micro_f1"],
            "passed": bool(
                perfect["macro_f1"] == 1.0
                and perfect["micro_f1"] == 1.0
            ),
        },
        "action_boundary_predictions": {
            "all_zero_macro_f1": all_zero["macro_f1"],
            "all_zero_micro_f1": all_zero["micro_f1"],
            "all_one_macro_f1": all_one["macro_f1"],
            "all_one_micro_f1": all_one["micro_f1"],
            "definition": (
                "A class with no true or predicted positives receives F1=0."
            ),
        },
        "rationale_label_permutation": {
            "seed": seed,
            "observed_macro_f1": observed_rationale["macro_f1"],
            "permuted_macro_f1": permuted_rationale["macro_f1"],
            "observed_micro_f1": observed_rationale["micro_f1"],
            "permuted_micro_f1": permuted_rationale["micro_f1"],
            "macro_f1_decreased": bool(
                permuted_rationale["macro_f1"]
                < observed_rationale["macro_f1"]
            ),
            "predicted_empty_set_fraction": float(
                np.mean(rationale_unions == 0)
            ),
        },
        "identity_transform": {
            "action_flip_rate": identity_flip,
            "joint_rationale_jaccard": identity_jaccard,
            "passed": bool(
                all(value == 0.0 for value in identity_flip.values())
                and identity_jaccard == 1.0
            ),
        },
        "ceg_critical_control_swap": {
            "original_mean": float(ceg.mean()),
            "swapped_mean": float(swapped.mean()),
            "maximum_pairwise_sum_residual": float(
                np.max(np.abs(ceg + swapped))
            ),
            "passed": bool(np.allclose(ceg, -swapped)),
            "development_only_due_to_v2_mask_audit_failure": True,
        },
        "confidence_references": {
            "random_ordering": random_safety,
            "constant_stable_ordering": constant_safety,
            "overall_error_rate": float(errors.mean()),
        },
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    thresholds = [float(value) for value in args.thresholds.split(",")]
    if 0.5 not in thresholds:
        raise ValueError("threshold grid must include preregistered 0.5")
    cache_path = rooted(args.cache)
    with np.load(cache_path, allow_pickle=False) as cache:
        temperature = load_temperature(rooted(args.calibration))
        probabilities = probability_bundle(cache, temperature)
        action_targets = np.asarray(cache["test_action_targets"])
        rationale_targets = np.asarray(cache["test_rationale_targets"])
        rows = threshold_rows(
            probabilities,
            action_targets,
            rationale_targets,
            thresholds,
        )
        result = {
            "analysis_status": "exploratory_metric_falsification",
            "primary_definition_unchanged": {
                "threshold": 0.5,
                "confidence": "maximum_action_probability",
            },
            "cache": str(cache_path.relative_to(PROJECT_ROOT)),
            "samples": int(len(action_targets)),
            "threshold_grid": thresholds,
            "threshold_contrast_stability": contrast_stability(
                rows, thresholds
            ),
            "confidence_definition_sensitivity_at_threshold_0_5": (
                confidence_sensitivity(
                    probabilities, action_targets, 0.5
                )
            ),
            "sanity_checks": sanity_checks(
                cache, probabilities, args.random_seed
            ),
            "interpretation_guardrails": [
                "Alternative thresholds and confidence definitions are "
                "exploratory and do not replace the preregistered primary "
                "metrics.",
                "Joint-Calibrated is a monotone transform of the Joint "
                "checkpoint, not an independently trained model.",
                "The CEG swap check tests algebraic implementation only; v2 "
                "mask effects remain invalid for confirmatory inference.",
            ],
        }
    write_json(rooted(args.output_json), json_safe(result))
    write_rows(rooted(args.output_csv), rows)
    print(json.dumps(json_safe(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
