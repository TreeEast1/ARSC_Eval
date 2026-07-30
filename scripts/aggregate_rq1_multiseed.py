"""Aggregate the five frozen BDD-OIA paired seeds with hierarchical bootstrap."""

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

from arsc_eval.internal_validity import percentile_interval
from arsc_eval.rq1 import prepare_rq1_arrays, rq1_metric_estimates
from arsc_eval.utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="43,44,45,46,47")
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260731)
    parser.add_argument(
        "--output-json",
        default="outputs/validity/rq1_multiseed_summary.json",
    )
    parser.add_argument(
        "--output-seed-csv",
        default="outputs/validity/rq1_multiseed_seed_metrics.csv",
    )
    parser.add_argument(
        "--output-summary-csv",
        default="outputs/validity/rq1_multiseed_metric_summary.csv",
    )
    return parser.parse_args()


def rooted(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def calibration_temperature(path: Path, model_type: str) -> float:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["model_type"] != model_type:
        raise RuntimeError(f"wrong model calibration at {path}")
    return float(result["temperature"])


def load_seed(seed: int) -> tuple[dict[str, Any], dict[str, float]]:
    output_dir = (
        PROJECT_ROOT / "outputs" / "validity" / f"rq1_seed_{seed}"
    )
    cache_path = output_dir / "prediction_cache" / "rq1_lossless.npz"
    with np.load(cache_path, allow_pickle=False) as archive:
        cache = {key: np.asarray(archive[key]) for key in archive.files}
    action_temperature = calibration_temperature(
        output_dir / "calibration_action_only.json", "action_only"
    )
    joint_temperature = calibration_temperature(
        output_dir / "calibration_joint.json", "joint"
    )
    prepared = prepare_rq1_arrays(
        cache, action_temperature, joint_temperature
    )
    point = rq1_metric_estimates(prepared, 0.5)
    return prepared, point


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    seeds = [int(value) for value in args.seeds.split(",")]
    if seeds != [43, 44, 45, 46, 47]:
        raise ValueError("primary seed list is frozen to 43,44,45,46,47")
    prepared_by_seed = {}
    points_by_seed = {}
    for seed in seeds:
        prepared, point = load_seed(seed)
        prepared_by_seed[seed] = prepared
        points_by_seed[seed] = point
    metric_names = sorted(points_by_seed[seeds[0]])
    if any(
        sorted(points_by_seed[seed]) != metric_names for seed in seeds
    ):
        raise RuntimeError("metric keys differ across seeds")

    seed_rows = []
    for seed in seeds:
        for metric in metric_names:
            seed_rows.append(
                {
                    "seed": seed,
                    "metric": metric,
                    "estimate": points_by_seed[seed][metric],
                }
            )

    mean_estimates = {
        metric: float(
            np.mean(
                [points_by_seed[seed][metric] for seed in seeds]
            )
        )
        for metric in metric_names
    }
    sd_estimates = {
        metric: float(
            np.std(
                [points_by_seed[seed][metric] for seed in seeds],
                ddof=1,
            )
        )
        for metric in metric_names
    }

    rng = np.random.default_rng(args.bootstrap_seed)
    draws = {
        metric: np.empty(args.replicates, dtype=np.float64)
        for metric in metric_names
    }
    for replicate in range(args.replicates):
        selected_seeds = rng.choice(seeds, size=len(seeds), replace=True)
        current = {metric: [] for metric in metric_names}
        for seed in selected_seeds:
            prepared = prepared_by_seed[int(seed)]
            sample_count = len(prepared["action_targets"])
            indices = rng.integers(0, sample_count, size=sample_count)
            estimates = rq1_metric_estimates(prepared, 0.5, indices)
            for metric, value in estimates.items():
                current[metric].append(value)
        for metric in metric_names:
            draws[metric][replicate] = float(np.mean(current[metric]))

    summary_rows = []
    for metric in metric_names:
        lower, upper = percentile_interval(draws[metric], 0.95)
        summary_rows.append(
            {
                "metric": metric,
                "mean_across_seeds": mean_estimates[metric],
                "sd_across_seeds": sd_estimates[metric],
                "hierarchical_ci_lower": lower,
                "hierarchical_ci_upper": upper,
            }
        )

    equivalence_metric = "delta_action_macro_f1::Joint-Action"
    equivalence_row = next(
        row for row in summary_rows if row["metric"] == equivalence_metric
    )
    action_equivalence = bool(
        equivalence_row["hierarchical_ci_lower"] >= -0.03
        and equivalence_row["hierarchical_ci_upper"] <= 0.03
    )
    flip_metric = (
        "advantage_action_flip_rate_mean_three::Action-Joint"
    )
    flip_values = [
        points_by_seed[seed][flip_metric] for seed in seeds
    ]
    perturbation_means = {
        kind: mean_estimates[
            f"advantage_action_flip_rate_{kind}::Action-Joint"
        ]
        for kind in ("brightness", "blur", "noise")
    }
    flip_support = bool(
        mean_estimates[flip_metric] >= 0.01
        and sum(value > 0.0 for value in flip_values) >= 4
        and all(value >= -0.01 for value in perturbation_means.values())
    )

    per_class = {"action": {}, "rationale": {}}
    for seed in seeds:
        result_path = (
            PROJECT_ROOT
            / "outputs"
            / "validity"
            / f"rq1_seed_{seed}"
            / "rq1_metrics.json"
        )
        result = json.loads(result_path.read_text(encoding="utf-8"))
        for model, values in result["per_class_action_f1"].items():
            per_class["action"].setdefault(model, {})
            for class_name, value in values.items():
                per_class["action"][model].setdefault(
                    class_name, []
                ).append(float(value))
        for class_name, value in result[
            "per_class_rationale_f1"
        ].items():
            per_class["rationale"].setdefault(class_name, []).append(
                float(value)
            )
    per_class_summary = {"action": {}, "rationale": {}}
    for model, classes in per_class["action"].items():
        per_class_summary["action"][model] = {
            class_name: {
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)),
                "raw_by_seed": dict(zip(map(str, seeds), values)),
            }
            for class_name, values in classes.items()
        }
    per_class_summary["rationale"] = {
        class_name: {
            "mean": float(np.mean(values)),
            "sd": float(np.std(values, ddof=1)),
            "raw_by_seed": dict(zip(map(str, seeds), values)),
        }
        for class_name, values in per_class["rationale"].items()
    }

    result = {
        "study": "BDD-OIA five-new-paired-seed RQ1 replication",
        "primary_seeds": seeds,
        "archival_pilot_seed_excluded": 42,
        "bootstrap": {
            "method": (
                "hierarchical paired bootstrap: resample training seeds, "
                "then images within each selected seed; model and "
                "perturbation pairing preserved"
            ),
            "replicates": args.replicates,
            "seed": args.bootstrap_seed,
            "confidence_level": 0.95,
        },
        "metric_summary": summary_rows,
        "raw_seed_metrics": {
            str(seed): points_by_seed[seed] for seed in seeds
        },
        "per_class_f1": per_class_summary,
        "decisions": {
            "action_equivalence": {
                "margin": [-0.03, 0.03],
                "mean_delta_joint_minus_action": mean_estimates[
                    equivalence_metric
                ],
                "hierarchical_ci": [
                    equivalence_row["hierarchical_ci_lower"],
                    equivalence_row["hierarchical_ci_upper"],
                ],
                "passed": action_equivalence,
            },
            "rq2_light_perturbation_subbranch": {
                "mean_flip_advantage_action_minus_joint": (
                    mean_estimates[flip_metric]
                ),
                "raw_by_seed": dict(zip(map(str, seeds), flip_values)),
                "positive_seed_count": sum(
                    value > 0.0 for value in flip_values
                ),
                "per_perturbation_mean_advantage": perturbation_means,
                "criteria": {
                    "mean_at_least": 0.01,
                    "minimum_positive_seeds": 4,
                    "no_perturbation_mean_below": -0.01,
                },
                "supported": flip_support,
            },
            "rq2_ceg": {
                "status": "unanswered",
                "reason": "v4 mask measurement gate failed",
            },
        },
        "interpretation": {
            "safety_and_consistency_attribution_allowed": action_equivalence,
            "if_false": (
                "S/C1 differences are descriptive accompanying differences "
                "and cannot be attributed to rationale supervision."
            ),
        },
    }
    write_json(rooted(args.output_json), result)
    write_csv(
        rooted(args.output_seed_csv),
        seed_rows,
        ["seed", "metric", "estimate"],
    )
    write_csv(
        rooted(args.output_summary_csv),
        summary_rows,
        [
            "metric",
            "mean_across_seeds",
            "sd_across_seeds",
            "hierarchical_ci_lower",
            "hierarchical_ci_upper",
        ],
    )
    print(json.dumps(result["decisions"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
