"""Construct audit of the ARSC selective-risk (S) operationalisation.

The frozen S axis scores every test image with ``max_i p_i`` but declares an
error whenever *any* of the four thresholded action bits is wrong.  This
script measures whether the published Joint vs Action-Only S conclusion
depends on that mismatch, by recomputing AURC, UAR@90 and ECE under three
pre-registered confidence constructions (see
``arsc_eval.selective_confidence``).

Nothing is retrained and nothing is re-tuned.  The script reads the frozen
Round 5 per-seed logit caches and the frozen temperature-scaling results, and
reuses the frozen decision threshold (0.5), seed list (43-47), test split,
calibration protocol and hierarchical bootstrap settings.

``S0`` is and remains the primary result.  ``S1``/``S2`` are reported only as
a sensitivity analysis; the script deliberately offers no mechanism to
promote an alternative construction to primary.

Self-verification: because ``S0`` reuses the frozen protocol exactly -- and
because the bootstrap RNG is advanced in the same order as
``scripts/aggregate_rq1_multiseed.py`` -- the recomputed ``S0`` point
estimates and confidence intervals must match
``outputs/validity/rq1_multiseed_summary.json``.  The script asserts this and
fails loudly otherwise.
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

from arsc_eval.internal_validity import percentile_interval, sigmoid
from arsc_eval.paper_assets import write_json
from arsc_eval.selective_confidence import (
    CONFIDENCE_FORMULAS,
    CONFIDENCE_IDS,
    CONFIDENCE_LABELS,
    CONFIDENCE_ROLES,
    confidence_scores,
    exact_set_error_vector,
    selective_metrics_from_confidence,
)

FROZEN_SEEDS = (43, 44, 45, 46, 47)
FROZEN_THRESHOLD = 0.5
FROZEN_REPLICATES = 2000
FROZEN_BOOTSTRAP_SEED = 20260731
FROZEN_ECE_BINS = 15

MODEL_ACTION = "Action-Only"
MODEL_JOINT = "Joint Action-Rationale"
MODELS = (MODEL_ACTION, MODEL_JOINT)

METRICS = ("aurc", "unsafe_acceptance_rate_90", "ece")

#: Frozen summary keys that the recomputed S0 numbers must reproduce.
FROZEN_S0_EQUIVALENTS = {
    "aurc": "aurc",
    "unsafe_acceptance_rate_90": "unsafe_acceptance_rate_90",
    "ece": "ece_calibrated",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="43,44,45,46,47")
    parser.add_argument("--replicates", type=int, default=FROZEN_REPLICATES)
    parser.add_argument(
        "--bootstrap-seed", type=int, default=FROZEN_BOOTSTRAP_SEED
    )
    parser.add_argument(
        "--output-json",
        default="outputs/paper/s_confidence_audit.json",
    )
    parser.add_argument(
        "--output-csv",
        default="outputs/paper/s_confidence_audit.csv",
    )
    parser.add_argument(
        "--output-seed-csv",
        default="outputs/paper/s_confidence_audit_seed_level.csv",
    )
    parser.add_argument(
        "--verification-tolerance", type=float, default=1e-9
    )
    return parser.parse_args()


def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def calibration_temperature(path: Path, model_type: str) -> float:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["model_type"] != model_type:
        raise RuntimeError(f"wrong model calibration at {path}")
    return float(payload["temperature"])


def load_seed_primitives(seed: int) -> dict[str, Any]:
    """Per-sample errors and confidences for one frozen seed.

    Because the exact-set error and every confidence score are per-sample
    quantities, the bootstrap only has to index into these vectors.  This is
    numerically identical to recomputing from resampled probability matrices,
    which is what the frozen aggregation script does.
    """

    output_dir = PROJECT_ROOT / "outputs" / "validity" / f"rq1_seed_{seed}"
    cache_path = output_dir / "prediction_cache" / "rq1_lossless.npz"
    with np.load(cache_path, allow_pickle=False) as archive:
        cache = {key: np.asarray(archive[key]) for key in archive.files}

    temperatures = {
        MODEL_ACTION: calibration_temperature(
            output_dir / "calibration_action_only.json", "action_only"
        ),
        MODEL_JOINT: calibration_temperature(
            output_dir / "calibration_joint.json", "joint"
        ),
    }
    logit_keys = {
        MODEL_ACTION: "test_clean_action_logits",
        MODEL_JOINT: "test_clean_joint_action_logits",
    }

    targets = np.asarray(cache["test_action_targets"])
    primitives: dict[str, Any] = {
        "sample_count": int(len(targets)),
        "temperatures": temperatures,
        "errors": {},
        "confidence": {},
    }
    for model in MODELS:
        calibrated = sigmoid(cache[logit_keys[model]], temperatures[model])
        errors = exact_set_error_vector(targets, calibrated, FROZEN_THRESHOLD)
        primitives["errors"][model] = errors
        primitives["confidence"][model] = {
            construction: confidence_scores(
                construction, calibrated, FROZEN_THRESHOLD
            )
            for construction in CONFIDENCE_IDS
        }
    return primitives


def estimate(
    primitives: dict[str, Any], indices: np.ndarray | None = None
) -> dict[str, float]:
    """All audited metrics for one seed, optionally on a bootstrap resample."""

    result: dict[str, float] = {}
    for model in MODELS:
        errors = primitives["errors"][model]
        errors = errors if indices is None else errors[indices]
        for construction in CONFIDENCE_IDS:
            confidence = primitives["confidence"][model][construction]
            confidence = confidence if indices is None else confidence[indices]
            metrics = selective_metrics_from_confidence(
                errors, confidence, FROZEN_ECE_BINS
            )
            for metric in METRICS:
                result[f"{construction}::{metric}::{model}"] = metrics[metric]
    for construction in CONFIDENCE_IDS:
        for metric in METRICS:
            result[f"{construction}::{metric}::delta_joint_minus_action"] = (
                result[f"{construction}::{metric}::{MODEL_JOINT}"]
                - result[f"{construction}::{metric}::{MODEL_ACTION}"]
            )
    return result


def load_frozen_reference() -> dict[str, dict[str, float]]:
    path = (
        PROJECT_ROOT / "outputs" / "validity" / "rq1_multiseed_summary.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {row["metric"]: row for row in payload["metric_summary"]}


def verify_against_frozen(
    summary: dict[str, dict[str, float]],
    tolerance: float,
) -> list[dict[str, Any]]:
    """Assert the recomputed S0 numbers match the published frozen result."""

    reference = load_frozen_reference()
    checks: list[dict[str, Any]] = []
    for metric, frozen_metric in FROZEN_S0_EQUIVALENTS.items():
        for model in MODELS:
            audited = summary[f"S0::{metric}::{model}"]
            frozen = reference[f"{frozen_metric}::{model}"]
            for field in (
                "mean_across_seeds",
                "hierarchical_ci_lower",
                "hierarchical_ci_upper",
            ):
                difference = abs(audited[field] - frozen[field])
                checks.append(
                    {
                        "frozen_metric": f"{frozen_metric}::{model}",
                        "audited_metric": f"S0::{metric}::{model}",
                        "field": field,
                        "frozen_value": frozen[field],
                        "audited_value": audited[field],
                        "absolute_difference": difference,
                        "within_tolerance": bool(difference <= tolerance),
                    }
                )
    failures = [check for check in checks if not check["within_tolerance"]]
    if failures:
        raise RuntimeError(
            "S0 reproduction check failed against the frozen summary: "
            + json.dumps(failures[:4], indent=2)
        )
    return checks


def interpret(summary: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Answer the three audit questions from the computed numbers only."""

    def direction(row: dict[str, float]) -> str:
        if row["hierarchical_ci_upper"] < 0.0:
            return "joint_better"
        if row["hierarchical_ci_lower"] > 0.0:
            return "joint_worse"
        return "inconclusive"

    # Every audited S metric is oriented "lower is better".
    directions = {
        construction: {
            metric: direction(
                summary[f"{construction}::{metric}::delta_joint_minus_action"]
            )
            for metric in METRICS
        }
        for construction in CONFIDENCE_IDS
    }

    per_metric_stable = {
        metric: len(
            {directions[construction][metric] for construction in CONFIDENCE_IDS}
        )
        == 1
        for metric in METRICS
    }
    per_construction_agreement = {
        construction: len(set(directions[construction].values())) == 1
        for construction in CONFIDENCE_IDS
    }

    mean_confidence = {
        construction: {
            model: summary[f"{construction}::aurc::{model}"][
                "mean_confidence_across_seeds"
            ]
            for model in MODELS
        }
        for construction in CONFIDENCE_IDS
    }
    mean_error_rate = summary["__exact_set_error_rate__"]

    return {
        "q1_does_the_S_conclusion_depend_on_the_confidence_definition": {
            "per_metric_direction_by_construction": directions,
            "direction_is_stable_across_constructions": per_metric_stable,
            "answer": (
                "no_all_three_metrics_stable"
                if all(per_metric_stable.values())
                else "yes_at_least_one_metric_changes_verdict"
            ),
        },
        "q2_do_aurc_uar90_and_ece_still_disagree": {
            "all_three_metrics_agree_within_construction": (
                per_construction_agreement
            ),
            "answer": (
                "metrics_disagree_under_at_least_one_construction"
                if not all(per_construction_agreement.values())
                else "metrics_agree_under_every_construction"
            ),
        },
        "q3_is_max_p_semantically_mismatched_with_exact_set_correctness": {
            "mean_exact_set_error_rate_by_model": mean_error_rate,
            "mean_confidence_by_construction_and_model": mean_confidence,
            "note": (
                "Compare each mean confidence against the corresponding "
                "empirical exact-set accuracy (1 - error rate).  A "
                "construction whose mean confidence sits far above the "
                "exact-set accuracy is scoring a different event than the "
                "one the error definition counts."
            ),
        },
    }


def main() -> int:
    args = parse_args()
    seeds = [int(value) for value in args.seeds.split(",")]
    if tuple(seeds) != FROZEN_SEEDS:
        raise ValueError(
            f"the S audit is frozen to seeds {FROZEN_SEEDS}; refusing to run"
        )

    primitives_by_seed = {seed: load_seed_primitives(seed) for seed in seeds}
    sample_counts = {
        seed: primitives_by_seed[seed]["sample_count"] for seed in seeds
    }
    points_by_seed = {
        seed: estimate(primitives_by_seed[seed]) for seed in seeds
    }
    metric_names = sorted(points_by_seed[seeds[0]])

    # Hierarchical bootstrap, advancing the RNG in exactly the order used by
    # scripts/aggregate_rq1_multiseed.py so that S0 reproduces the frozen CI.
    rng = np.random.default_rng(args.bootstrap_seed)
    draws = {
        metric: np.empty(args.replicates, dtype=np.float64)
        for metric in metric_names
    }
    for replicate in range(args.replicates):
        selected_seeds = rng.choice(seeds, size=len(seeds), replace=True)
        current: dict[str, list[float]] = {
            metric: [] for metric in metric_names
        }
        for seed in selected_seeds:
            seed = int(seed)
            indices = rng.integers(0, sample_counts[seed], size=sample_counts[seed])
            for metric, value in estimate(primitives_by_seed[seed], indices).items():
                current[metric].append(value)
        for metric in metric_names:
            draws[metric][replicate] = float(np.mean(current[metric]))

    summary: dict[str, Any] = {}
    for metric in metric_names:
        values = [points_by_seed[seed][metric] for seed in seeds]
        lower, upper = percentile_interval(draws[metric], 0.95)
        summary[metric] = {
            "mean_across_seeds": float(np.mean(values)),
            "sd_across_seeds": float(np.std(values, ddof=1)),
            "hierarchical_ci_lower": lower,
            "hierarchical_ci_upper": upper,
            "by_seed": {str(seed): points_by_seed[seed][metric] for seed in seeds},
        }

    # Descriptive confidence-distribution statistics, attached to the AURC row
    # of each construction so the interpretation block can reach them.
    for construction in CONFIDENCE_IDS:
        for model in MODELS:
            per_seed_mean = [
                float(
                    primitives_by_seed[seed]["confidence"][model][
                        construction
                    ].mean()
                )
                for seed in seeds
            ]
            summary[f"{construction}::aurc::{model}"][
                "mean_confidence_across_seeds"
            ] = float(np.mean(per_seed_mean))
    summary["__exact_set_error_rate__"] = {
        model: float(
            np.mean(
                [
                    float(primitives_by_seed[seed]["errors"][model].mean())
                    for seed in seeds
                ]
            )
        )
        for model in MODELS
    }

    verification = verify_against_frozen(summary, args.verification_tolerance)
    interpretation = interpret(summary)

    result = {
        "schema_version": "ARSC_S_CONFIDENCE_CONSTRUCT_AUDIT_V1",
        "analysis_id": "ARSC_S_CONFIDENCE_CONSTRUCT_AUDIT",
        "status": (
            "Sensitivity / construct audit of the selective-risk "
            "operationalisation. NOT a replacement primary result."
        ),
        "primary_result_remains": (
            "S0 (conf = max_i p_i) as published in "
            "outputs/validity/rq1_multiseed_summary.json"
        ),
        "frozen_inputs": {
            "seeds": seeds,
            "threshold": FROZEN_THRESHOLD,
            "test_split": "BDD-OIA official test, 4557 valid four-action images",
            "calibration": "scalar temperature scaling fitted on official validation",
            "temperatures_by_seed": {
                str(seed): primitives_by_seed[seed]["temperatures"]
                for seed in seeds
            },
            "sample_counts_by_seed": {
                str(seed): sample_counts[seed] for seed in seeds
            },
            "error_definition": (
                "exact-set error: any of the four thresholded action bits wrong"
            ),
            "ece_bins": FROZEN_ECE_BINS,
        },
        "bootstrap": {
            "method": (
                "hierarchical paired bootstrap: resample training seeds, then "
                "images within each selected seed; model pairing preserved"
            ),
            "replicates": args.replicates,
            "seed": args.bootstrap_seed,
            "confidence_level": 0.95,
            "rng_stream_matches_frozen_rq1_aggregation": True,
        },
        "confidence_constructions": {
            construction: {
                "label": CONFIDENCE_LABELS[construction],
                "formula": CONFIDENCE_FORMULAS[construction],
                "role": CONFIDENCE_ROLES[construction],
            }
            for construction in CONFIDENCE_IDS
        },
        "s0_reproduction_check": {
            "reference": "outputs/validity/rq1_multiseed_summary.json",
            "tolerance": args.verification_tolerance,
            "all_checks_passed": True,
            "checks": verification,
        },
        "summary": summary,
        "interpretation": interpretation,
        "claim_boundary": (
            "This audit varies only the confidence construction used to rank "
            "test images for selective prediction. It does not measure "
            "safety, does not license calling any construction correct, and "
            "does not change the frozen primary S result."
        ),
    }

    output_json = rooted(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_json, result)

    rows = []
    for construction in CONFIDENCE_IDS:
        for metric in METRICS:
            for column in (*MODELS, "delta_joint_minus_action"):
                key = f"{construction}::{metric}::{column}"
                row = summary[key]
                rows.append(
                    {
                        "confidence_construction": construction,
                        "confidence_role": CONFIDENCE_ROLES[construction],
                        "metric": metric,
                        "quantity": column,
                        "mean_across_seeds": row["mean_across_seeds"],
                        "sd_across_seeds": row["sd_across_seeds"],
                        "hierarchical_ci_lower": row["hierarchical_ci_lower"],
                        "hierarchical_ci_upper": row["hierarchical_ci_upper"],
                    }
                )
    output_csv = rooted(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    seed_rows = []
    for construction in CONFIDENCE_IDS:
        for metric in METRICS:
            for column in (*MODELS, "delta_joint_minus_action"):
                key = f"{construction}::{metric}::{column}"
                for seed in seeds:
                    seed_rows.append(
                        {
                            "confidence_construction": construction,
                            "metric": metric,
                            "quantity": column,
                            "seed": seed,
                            "estimate": summary[key]["by_seed"][str(seed)],
                        }
                    )
    output_seed_csv = rooted(args.output_seed_csv)
    with output_seed_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(seed_rows[0]))
        writer.writeheader()
        writer.writerows(seed_rows)

    print(json.dumps(interpretation, indent=2))
    print(f"\nwrote {output_json}")
    print(f"wrote {output_csv}")
    print(f"wrote {output_seed_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
