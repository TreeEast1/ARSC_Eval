"""Training-seed heterogeneity of the ARSC profile, reported as a result.

The five-seed means in the frozen Round 5 study hide how unstable the
per-axis comparison is.  This script reports the seed-level distribution
beside the mean for every axis, so the paper can state the mean and the
spread together instead of presenting the mean alone.

The sign reversals are the point and are preserved verbatim: seed 43 reverses
the C1 stability advantage, seed 45 reverses the AURC advantage, and the
Action Macro-F1 advantage itself reverses on seeds 46 and 47.  Nothing here
tries to explain them away, and no seed is dropped or reweighted.

Everything is read from the frozen Round 5 aggregation.  For readability each
comparison is oriented so that positive means "Joint is better"; the frozen
metric key and the orientation applied to it are recorded for every row.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.paper_assets import (
    FROZEN_SEEDS,
    MODEL_JOINT,
    apply_figure_style,
    load_rq1_summary,
    provenance,
    rq1_metric_rows,
    rq1_seed_metrics,
    save_figure,
    write_csv,
    write_json,
    write_markdown_table,
)

#: Marker colour for a seed whose sign disagrees with the five-seed mean.
#: Deliberately distinct from every axis colour, including the C1 red.
REVERSAL_COLOR = "#d81b60"

#: Panels of the heterogeneity figure.
#:
#: ``orientation`` is +1 when the frozen metric already increases with a Joint
#: advantage and -1 when it decreases (AURC, UAR@90 and ECE are all
#: lower-is-better differences of the form Joint - Action-Only).
PANELS: tuple[dict[str, Any], ...] = (
    {
        "key": "delta_action_macro_f1::Joint-Action",
        "orientation": +1.0,
        "axis": "A",
        "title": "A: Action Macro-F1",
        "subtitle": "Joint - Action-Only",
        "comparison": True,
    },
    {
        "key": "delta_aurc::Joint-Action",
        "orientation": -1.0,
        "axis": "S",
        "title": "S: AURC",
        "subtitle": "Action-Only - Joint (AURC is lower-is-better)",
        "comparison": True,
    },
    {
        "key": "delta_unsafe_acceptance_rate_90::Joint-Action",
        "orientation": -1.0,
        "axis": "S",
        "title": "S: UAR@90",
        "subtitle": "Action-Only - Joint (lower-is-better)",
        "comparison": True,
    },
    {
        "key": "delta_ece_calibrated::Joint-Action",
        "orientation": -1.0,
        "axis": "S",
        "title": "S: ECE (calibrated)",
        "subtitle": "Action-Only - Joint (lower-is-better)",
        "comparison": True,
    },
    {
        "key": "advantage_action_flip_rate_mean_three::Action-Joint",
        "orientation": +1.0,
        "axis": "C1",
        "title": "C1: action-set flip rate",
        "subtitle": "Action-Only - Joint, mean of three families",
        "comparison": True,
    },
    {
        "key": f"rationale_macro_f1::{MODEL_JOINT}",
        "orientation": +1.0,
        "axis": "R",
        "title": "R: Joint rationale Macro-F1",
        "subtitle": "absolute value; Action-Only has no R axis",
        "comparison": False,
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default="outputs/paper/seed_heterogeneity.json")
    parser.add_argument("--output-csv", default="outputs/paper/seed_heterogeneity.csv")
    parser.add_argument(
        "--output-markdown", default="outputs/paper/tables/seed_heterogeneity.md"
    )
    parser.add_argument(
        "--output-figure", default="outputs/paper/figures/seed_heterogeneity"
    )
    return parser.parse_args()


def collect(
    seed_metrics: dict[int, dict[str, float]],
    metric_rows: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    records = []
    for panel in PANELS:
        key = panel["key"]
        orientation = panel["orientation"]
        values = np.array(
            [seed_metrics[seed][key] * orientation for seed in FROZEN_SEEDS]
        )
        frozen = metric_rows[key]
        mean = float(values.mean())
        ci_lower = frozen["hierarchical_ci_lower"] * orientation
        ci_upper = frozen["hierarchical_ci_upper"] * orientation
        if orientation < 0:
            ci_lower, ci_upper = ci_upper, ci_lower

        if panel["comparison"]:
            agreeing = int(np.sum(np.sign(values) == np.sign(mean)))
            reversed_seeds = [
                seed
                for seed, value in zip(FROZEN_SEEDS, values)
                if np.sign(value) != np.sign(mean)
            ]
        else:
            agreeing = len(FROZEN_SEEDS)
            reversed_seeds = []

        records.append(
            {
                "axis": panel["axis"],
                "quantity": panel["title"],
                "orientation_note": panel["subtitle"],
                "frozen_metric_key": key,
                "orientation_applied": orientation,
                "is_model_comparison": panel["comparison"],
                "mean_across_seeds": mean,
                "sd_across_seeds": float(values.std(ddof=1)),
                "min_across_seeds": float(values.min()),
                "max_across_seeds": float(values.max()),
                "range_across_seeds": float(values.max() - values.min()),
                "hierarchical_ci_lower": ci_lower,
                "hierarchical_ci_upper": ci_upper,
                "seeds_agreeing_with_mean_sign": agreeing,
                "seeds_reversing_mean_sign": reversed_seeds,
                **{
                    f"seed_{seed}": float(value)
                    for seed, value in zip(FROZEN_SEEDS, values)
                },
            }
        )
    return records


def plot(records: list[dict[str, Any]], stem: str) -> list[Path]:
    apply_figure_style()
    import matplotlib.pyplot as plt

    from arsc_eval.paper_assets import AXIS_COLORS

    figure, axes = plt.subplots(2, 3, figsize=(12.2, 6.4))
    positions = np.arange(len(FROZEN_SEEDS))

    for panel_index, record in enumerate(records):
        panel = axes[panel_index // 3][panel_index % 3]
        color = AXIS_COLORS[record["axis"]]
        values = [record[f"seed_{seed}"] for seed in FROZEN_SEEDS]
        mean = record["mean_across_seeds"]
        comparison = record["is_model_comparison"]

        if comparison:
            panel.axhspan(
                record["hierarchical_ci_lower"],
                record["hierarchical_ci_upper"],
                color=color,
                alpha=0.13,
                linewidth=0,
                zorder=1,
            )
            panel.axhline(0.0, color="#444444", linewidth=1.1, zorder=2)
        panel.axhline(
            mean,
            color=color,
            linestyle="--",
            linewidth=1.4,
            zorder=3,
        )

        reversed_seeds = set(record["seeds_reversing_mean_sign"])
        # Reversals are marked by shape as well as colour: the C1 axis colour is
        # itself a red, so colour alone would be ambiguous in that panel.
        agreeing_mask = [seed not in reversed_seeds for seed in FROZEN_SEEDS]
        for mask, marker, size, face, edge in (
            (agreeing_mask, "o", 76, color, "white"),
            ([not keep for keep in agreeing_mask], "X", 132, REVERSAL_COLOR, "black"),
        ):
            if not any(mask):
                continue
            panel.scatter(
                positions[np.array(mask)],
                np.array(values)[np.array(mask)],
                s=size,
                c=face,
                marker=marker,
                zorder=5,
                edgecolors=edge,
                linewidths=1.1,
            )
        # Label above a low-lying point and below a high-lying one so the
        # annotation never lands on the tick labels or the panel title.
        midpoint = 0.5 * (min(values) + max(values))
        for position, seed, value in zip(positions, FROZEN_SEEDS, values):
            if seed in reversed_seeds:
                below = value <= midpoint
                panel.annotate(
                    "reversed",
                    (position, value),
                    textcoords="offset points",
                    xytext=(0, 13 if below else -19),
                    ha="center",
                    va="bottom" if below else "top",
                    fontsize=7.0,
                    color=REVERSAL_COLOR,
                    fontweight="bold",
                )

        panel.set_xticks(positions)
        panel.set_xticklabels([f"s{seed}" for seed in FROZEN_SEEDS])
        panel.set_xlim(-0.55, len(FROZEN_SEEDS) - 0.45)
        title = record["quantity"]
        if comparison:
            title += f"\n{len(FROZEN_SEEDS) - len(reversed_seeds)}/{len(FROZEN_SEEDS)} seeds agree with the mean sign"
        else:
            spread = record["range_across_seeds"]
            title += f"\nacross-seed range {spread:.3f}"
        panel.set_title(title, fontsize=8.8, color=color, fontweight="bold")
        panel.set_xlabel(record["orientation_note"], fontsize=7.4)

    for row in (0, 1):
        axes[row][0].set_ylabel(
            "Joint advantage\n(positive = Joint better)", fontsize=8.2
        )
    axes[1][2].set_ylabel("Macro-F1", fontsize=8.2)

    figure.suptitle(
        "The ARSC profile has substantial training-seed heterogeneity, so "
        "means must be reported with the seed-level distribution",
        fontsize=11.5,
        fontweight="bold",
        y=0.995,
    )
    figure.text(
        0.5,
        0.945,
        "Dashed line = five-seed mean; shaded band = 95% hierarchical "
        "bootstrap CI; black-edged X marks a seed that reverses the sign of "
        "the mean",
        ha="center",
        fontsize=8.4,
        color="#444444",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.932))
    written = save_figure(figure, stem)
    plt.close(figure)
    return written


def main() -> int:
    args = parse_args()
    summary = load_rq1_summary()
    metric_rows = rq1_metric_rows(summary)
    seed_metrics = rq1_seed_metrics(summary)
    records = collect(seed_metrics, metric_rows)

    comparisons = [record for record in records if record["is_model_comparison"]]
    unanimous = [
        record
        for record in comparisons
        if record["seeds_agreeing_with_mean_sign"] == len(FROZEN_SEEDS)
    ]

    result = {
        "schema_version": "ARSC_SEED_HETEROGENEITY_V1",
        "analysis_id": "ARSC_SEED_LEVEL_PROFILE_HETEROGENEITY",
        "role": (
            "Training-seed heterogeneity reported as a result, not as noise "
            "to be averaged away."
        ),
        "frozen_inputs": {
            "seeds": list(FROZEN_SEEDS),
            "source": "outputs/validity/rq1_multiseed_summary.json",
            "archival_pilot_seed_excluded": summary["archival_pilot_seed_excluded"],
        },
        "orientation_convention": (
            "Each comparison is oriented so that positive means Joint is "
            "better. AURC, UAR@90 and ECE are lower-is-better, so the frozen "
            "Joint - Action-Only difference is negated; the frozen metric key "
            "and the orientation applied are recorded on every row."
        ),
        "records": records,
        "headline": {
            "comparison_count": len(comparisons),
            "comparisons_unanimous_across_seeds": len(unanimous),
            "no_comparison_is_unanimous": len(unanimous) == 0,
            "named_reversals": {
                record["quantity"]: record["seeds_reversing_mean_sign"]
                for record in comparisons
                if record["seeds_reversing_mean_sign"]
            },
            "joint_rationale_macro_f1_range": next(
                record["range_across_seeds"]
                for record in records
                if not record["is_model_comparison"]
            ),
        },
        "interpretation": {
            "statement": (
                "The ARSC profile shows clear training-seed heterogeneity. "
                "Every model comparison in the profile has at least one seed "
                "whose sign disagrees with the five-seed mean, so a mean "
                "alone is not an adequate summary and must always be "
                "reported together with the seed-level distribution."
            ),
            "specific_reversals": [
                "Seed 43 reverses the C1 stability advantage: Action-Only "
                "flips less often than Joint on that seed.",
                "Seed 45 reverses the AURC advantage.",
                "Seeds 46 and 47 reverse the Action Macro-F1 advantage, so "
                "the headline A comparison is 3/5 rather than 5/5.",
            ],
            "what_is_not_claimed": (
                "No attempt is made to explain the reversals, attribute them "
                "to a cause, or exclude any seed. They are reported as the "
                "observed spread of the frozen five-seed design."
            ),
        },
        "provenance": provenance(["outputs/validity/rq1_multiseed_summary.json"]),
    }

    write_json(args.output_json, result)
    write_csv(args.output_csv, records)

    markdown_rows = []
    for record in records:
        markdown_rows.append(
            [
                record["axis"],
                record["quantity"],
                *(f"{record[f'seed_{seed}']:+.6f}" for seed in FROZEN_SEEDS),
                f"{record['mean_across_seeds']:+.6f}",
                f"{record['sd_across_seeds']:.6f}",
                (
                    f"[{record['hierarchical_ci_lower']:+.6f}, "
                    f"{record['hierarchical_ci_upper']:+.6f}]"
                ),
                (
                    f"{record['seeds_agreeing_with_mean_sign']}/{len(FROZEN_SEEDS)}"
                    if record["is_model_comparison"]
                    else "n/a"
                ),
                ", ".join(str(seed) for seed in record["seeds_reversing_mean_sign"])
                or "-",
            ]
        )
    write_markdown_table(
        args.output_markdown,
        "Seed-level heterogeneity of the ARSC profile",
        [
            "Frozen Round 5 five-seed study. Each model comparison is "
            "oriented so that **positive means Joint is better**; AURC, "
            "UAR@90 and ECE are lower-is-better and are negated accordingly "
            "(the frozen metric key for every row is in "
            "`outputs/paper/seed_heterogeneity.csv`).",
            "",
            "**Every model comparison in the profile has at least one seed "
            "that reverses the sign of the five-seed mean.**",
        ],
        [
            "Axis",
            "Quantity",
            *(f"seed {seed}" for seed in FROZEN_SEEDS),
            "Mean",
            "SD",
            "95% hierarchical CI",
            "Seeds agreeing",
            "Reversed seeds",
        ],
        markdown_rows,
        notes=[
            "The confidence intervals are the frozen hierarchical bootstrap "
            "intervals (2000 replicates, seed resampling then image "
            "resampling), reoriented to match the sign convention.",
            "Seed 43 reverses C1, seed 45 reverses AURC, and seeds 46 and 47 "
            "reverse the Action Macro-F1 advantage.",
            "The Joint rationale Macro-F1 is not a model comparison because "
            "the Action-Only model has no rationale head; its across-seed "
            "range is reported instead.",
            "No seed is dropped, reweighted or explained away.",
        ],
    )

    figures = plot(records, args.output_figure)

    for record in comparisons:
        print(
            f"{record['axis']:3s} {record['quantity']:34s} "
            f"mean={record['mean_across_seeds']:+.6f} "
            f"agree={record['seeds_agreeing_with_mean_sign']}/5 "
            f"reversed={record['seeds_reversing_mean_sign']}"
        )
    print(f"comparisons unanimous across all five seeds: {len(unanimous)}")
    for path in figures:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
