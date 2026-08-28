"""Per-class coverage diagnosis for the ARSC rationale axis (R).

A single R Macro-F1 of 0.274 is not interpretable on its own.  This script
decomposes it into the 21 per-class F1 scores, their support in the frozen
BDD-OIA test split, and their spread across the five frozen training seeds,
so the reader can see *where* the aggregate comes from.

Nothing is retrained.  No rationale loss is added, no class weight is tuned.
The script reads the frozen Round 5 per-seed logit caches and per-seed metric
records only.

Claim boundary: this measures **rationale-label recovery coverage**.  It says
nothing about whether the model reasons, and a class with F1 = 0 is not
evidence that the model "explained itself incorrectly" -- it is evidence that
the label is not recovered at the frozen 0.5 threshold.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import RATIONALE_NAMES
from arsc_eval.internal_validity import sigmoid
from arsc_eval.paper_assets import (
    FROZEN_SEEDS,
    FROZEN_THRESHOLD,
    MODEL_JOINT,
    apply_figure_style,
    load_rq1_summary,
    load_seed_cache,
    provenance,
    rq1_metric_rows,
    save_figure,
    write_csv,
    write_json,
    write_markdown_table,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default="outputs/paper/rationale_coverage.json")
    parser.add_argument("--output-csv", default="outputs/paper/rationale_coverage.csv")
    parser.add_argument(
        "--output-markdown", default="outputs/paper/tables/rationale_coverage.md"
    )
    parser.add_argument(
        "--output-figure", default="outputs/paper/figures/rationale_coverage"
    )
    return parser.parse_args()


def binary_counts(
    targets: np.ndarray, predictions: np.ndarray
) -> dict[str, float]:
    """True/false positive and negative counts plus precision, recall and F1."""

    true = targets.astype(bool)
    pred = predictions.astype(bool)
    tp = int(np.logical_and(true, pred).sum())
    fp = int(np.logical_and(~true, pred).sum())
    fn = int(np.logical_and(true, ~pred).sum())
    denominator = 2 * tp + fp + fn
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "predicted_positive": tp + fp,
        "precision": float(tp / (tp + fp)) if (tp + fp) else 0.0,
        "recall": float(tp / (tp + fn)) if (tp + fn) else 0.0,
        "f1": float(2 * tp / denominator) if denominator else 0.0,
    }


def collect() -> dict[str, Any]:
    per_seed: dict[int, dict[str, dict[str, float]]] = {}
    support: dict[str, int] | None = None
    sample_count = 0

    for seed in FROZEN_SEEDS:
        cache = load_seed_cache(seed)
        targets = np.asarray(cache["test_rationale_targets"])
        # Rationale heads are read at the frozen threshold without temperature
        # scaling, matching arsc_eval.rq1.prepare_rq1_arrays.
        probabilities = sigmoid(cache["test_clean_joint_rationale_logits"])
        predictions = probabilities >= FROZEN_THRESHOLD
        sample_count = int(len(targets))

        seed_support = {
            name: int(targets[:, index].sum())
            for index, name in enumerate(RATIONALE_NAMES)
        }
        if support is None:
            support = seed_support
        elif support != seed_support:
            raise RuntimeError(
                "rationale support differs across seeds; the frozen test "
                "split is supposed to be identical for every seed"
            )
        per_seed[seed] = {
            name: binary_counts(targets[:, index], predictions[:, index])
            for index, name in enumerate(RATIONALE_NAMES)
        }

    assert support is not None
    return {
        "per_seed": per_seed,
        "support": support,
        "sample_count": sample_count,
    }


def summarise(collected: dict[str, Any]) -> list[dict[str, Any]]:
    per_seed = collected["per_seed"]
    support = collected["support"]
    sample_count = collected["sample_count"]

    rows = []
    for index, name in enumerate(RATIONALE_NAMES):
        f1_values = [per_seed[seed][name]["f1"] for seed in FROZEN_SEEDS]
        precision = [per_seed[seed][name]["precision"] for seed in FROZEN_SEEDS]
        recall = [per_seed[seed][name]["recall"] for seed in FROZEN_SEEDS]
        predicted = [
            per_seed[seed][name]["predicted_positive"] for seed in FROZEN_SEEDS
        ]
        zero_seed_count = sum(1 for value in f1_values if value == 0.0)
        never_predicted = sum(1 for value in predicted if value == 0)
        rows.append(
            {
                "class_index": index,
                "class_name": name,
                "support": support[name],
                "support_rate": support[name] / sample_count,
                "f1_mean": float(np.mean(f1_values)),
                "f1_sd": float(np.std(f1_values, ddof=1)),
                "f1_min": float(np.min(f1_values)),
                "f1_max": float(np.max(f1_values)),
                "precision_mean": float(np.mean(precision)),
                "recall_mean": float(np.mean(recall)),
                "predicted_positive_mean": float(np.mean(predicted)),
                "seeds_with_zero_f1": zero_seed_count,
                "seeds_never_predicting_class": never_predicted,
                "zero_in_all_seeds": bool(zero_seed_count == len(FROZEN_SEEDS)),
                **{
                    f"f1_seed_{seed}": per_seed[seed][name]["f1"]
                    for seed in FROZEN_SEEDS
                },
            }
        )
    return rows


#: Rationale classes that come in a left/right pair.  BDD-OIA annotates the
#: two sides with separate labels, which makes the prevalence asymmetry
#: between them directly measurable.
LATERAL_PAIRS = (
    ("left_lane", "right_lane"),
    ("no_left_lane", "no_right_lane"),
    ("left_follow", "right_follow"),
    ("left_green_light", "right_green_light"),
    ("left_obstacle", "right_obstacle"),
    ("left_solid_line", "right_solid_line"),
)


def lateral_asymmetry(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Left vs right recovery for the six paired rationale classes."""

    by_name = {row["class_name"]: row for row in rows}
    pairs = []
    for left_name, right_name in LATERAL_PAIRS:
        left_row, right_row = by_name[left_name], by_name[right_name]
        pairs.append(
            {
                "left_class": left_name,
                "right_class": right_name,
                "left_support": left_row["support"],
                "right_support": right_row["support"],
                "support_ratio_right_over_left": (
                    right_row["support"] / left_row["support"]
                    if left_row["support"]
                    else float("inf")
                ),
                "left_f1_mean": left_row["f1_mean"],
                "right_f1_mean": right_row["f1_mean"],
                "f1_gap_right_minus_left": (
                    right_row["f1_mean"] - left_row["f1_mean"]
                ),
                "left_zero_in_all_seeds": left_row["zero_in_all_seeds"],
            }
        )
    return pairs


def plot(rows: list[dict[str, Any]], collected: dict[str, Any], stem: str) -> list[Path]:
    apply_figure_style()
    import matplotlib.pyplot as plt

    order = sorted(rows, key=lambda row: row["f1_mean"])
    positions = np.arange(len(order))

    figure, (left, right) = plt.subplots(
        1,
        2,
        figsize=(11.6, 6.4),
        gridspec_kw={"width_ratios": [1.85, 1.0]},
    )

    dead_color, live_color = "#b03030", "#4c78a8"
    colors = [
        dead_color if row["zero_in_all_seeds"] else live_color for row in order
    ]
    left.barh(
        positions,
        [row["f1_mean"] for row in order],
        color=colors,
        alpha=0.85,
        height=0.66,
        zorder=2,
    )
    for position, row in zip(positions, order):
        values = [row[f"f1_seed_{seed}"] for seed in FROZEN_SEEDS]
        left.scatter(
            values,
            np.full(len(values), position),
            s=13,
            color="#22303f",
            zorder=4,
            alpha=0.85,
            linewidths=0,
        )

    dead_rows = [row for row in order if row["zero_in_all_seeds"]]
    if dead_rows:
        top = max(
            position
            for position, row in zip(positions, order)
            if row["zero_in_all_seeds"]
        )
        left.annotate(
            f"never predicted in any seed\n(support {min(r['support'] for r in dead_rows)}"
            f"-{max(r['support'] for r in dead_rows)} of {collected['sample_count']})",
            xy=(0.005, top),
            xytext=(0.17, top - 0.15),
            fontsize=7.6,
            color=dead_color,
            va="center",
            arrowprops={
                "arrowstyle": "->",
                "color": dead_color,
                "linewidth": 1.0,
            },
        )

    macro = float(np.mean([row["f1_mean"] for row in rows]))
    left.axvline(
        macro,
        color="#111111",
        linestyle="--",
        linewidth=1.3,
        zorder=5,
        label=f"R Macro-F1 = {macro:.3f}",
    )
    left.set_yticks(positions)
    left.set_yticklabels([row["class_name"] for row in order])
    for tick, row in zip(left.get_yticklabels(), order):
        if row["zero_in_all_seeds"]:
            tick.set_color(dead_color)
            tick.set_fontweight("bold")
    left.set_xlabel(
        "Per-class rationale F1 (bar = 5-seed mean, dot = individual seed)"
    )
    left.set_xlim(0.0, 0.85)
    left.set_title(
        "(a) A single R Macro-F1 hides which classes are recovered",
        loc="left",
        fontweight="bold",
    )
    left.legend(loc="lower right")

    pairs = lateral_asymmetry(rows)
    pair_positions = np.arange(len(pairs))
    for position, pair in zip(pair_positions, pairs):
        right.plot(
            [pair["left_f1_mean"], pair["right_f1_mean"]],
            [position, position],
            color="#9aa5b1",
            linewidth=1.6,
            zorder=1,
        )
    right.scatter(
        [pair["left_f1_mean"] for pair in pairs],
        pair_positions,
        s=52,
        color=dead_color,
        zorder=3,
        label="left-side class",
        linewidths=0,
    )
    right.scatter(
        [pair["right_f1_mean"] for pair in pairs],
        pair_positions,
        s=52,
        color=live_color,
        zorder=3,
        label="right-side class",
        linewidths=0,
    )
    for position, pair in zip(pair_positions, pairs):
        right.annotate(
            f"x{pair['support_ratio_right_over_left']:.0f} support",
            xy=(
                (pair["left_f1_mean"] + pair["right_f1_mean"]) / 2.0,
                position,
            ),
            textcoords="offset points",
            xytext=(0, 7),
            ha="center",
            fontsize=6.8,
            color="#5a6470",
        )
    right.set_yticks(pair_positions)
    right.set_yticklabels(
        [
            f"{pair['left_class'].replace('left_', '').replace('no_', 'no ')}"
            for pair in pairs
        ]
    )
    right.set_xlim(-0.03, 0.72)
    right.set_xlabel("5-seed mean F1")
    right.set_title(
        "(b) Recovery collapses on the rarer left-side label of each pair",
        loc="left",
        fontweight="bold",
    )
    right.set_ylim(-0.6, len(pairs) - 0.15)
    right.legend(loc="lower right", ncol=2)

    figure.suptitle(
        "Rationale-label recovery coverage is incomplete and highly "
        f"class-dependent: {len(dead_rows)} of {len(rows)} classes score "
        "F1 = 0 in all five seeds",
        fontsize=11,
        fontweight="bold",
        y=0.985,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    written = save_figure(figure, stem)
    plt.close(figure)
    return written


def main() -> int:
    args = parse_args()
    collected = collect()
    rows = summarise(collected)

    summary = load_rq1_summary()
    metrics = rq1_metric_rows(summary)
    macro_row = metrics[f"rationale_macro_f1::{MODEL_JOINT}"]
    micro_row = metrics[f"rationale_micro_f1::{MODEL_JOINT}"]

    computed_macro = float(np.mean([row["f1_mean"] for row in rows]))
    if abs(computed_macro - macro_row["mean_across_seeds"]) > 1e-9:
        raise RuntimeError(
            "recomputed rationale Macro-F1 does not match the frozen summary: "
            f"{computed_macro} vs {macro_row['mean_across_seeds']}"
        )

    dead = [row for row in rows if row["zero_in_all_seeds"]]
    weak = [
        row
        for row in rows
        if not row["zero_in_all_seeds"] and row["f1_mean"] < 0.05
    ]

    result = {
        "schema_version": "ARSC_RATIONALE_COVERAGE_V1",
        "analysis_id": "ARSC_R_AXIS_PER_CLASS_COVERAGE",
        "axis": "R (Rationale-label Performance)",
        "operationalisation": "21-class rationale Macro/Micro-F1 at threshold 0.5",
        "frozen_inputs": {
            "seeds": list(FROZEN_SEEDS),
            "threshold": FROZEN_THRESHOLD,
            "sample_count": collected["sample_count"],
            "model": MODEL_JOINT,
            "note": (
                "Only the Joint model has rationale heads; the Action-Only "
                "model has no R axis by construction."
            ),
        },
        "aggregate": {
            "macro_f1_mean_across_seeds": macro_row["mean_across_seeds"],
            "macro_f1_hierarchical_ci": [
                macro_row["hierarchical_ci_lower"],
                macro_row["hierarchical_ci_upper"],
            ],
            "micro_f1_mean_across_seeds": micro_row["mean_across_seeds"],
            "micro_f1_hierarchical_ci": [
                micro_row["hierarchical_ci_lower"],
                micro_row["hierarchical_ci_upper"],
            ],
            "macro_minus_micro": (
                macro_row["mean_across_seeds"] - micro_row["mean_across_seeds"]
            ),
            "macro_micro_gap_reading": (
                "Micro-F1 is dominated by the high-support classes that the "
                "model does recover, so it stays near 0.50 while Macro-F1 "
                "falls to 0.27. The gap is the coverage hole."
            ),
        },
        "coverage": {
            "class_count": len(rows),
            "classes_with_zero_f1_in_all_seeds": [
                row["class_name"] for row in dead
            ],
            "zero_class_count": len(dead),
            "classes_below_0_05_mean_f1_but_not_always_zero": [
                row["class_name"] for row in weak
            ],
            "classes_never_predicted_in_any_seed": [
                row["class_name"]
                for row in rows
                if row["seeds_never_predicting_class"] == len(FROZEN_SEEDS)
            ],
            "zero_class_support_range": [
                min(row["support"] for row in dead),
                max(row["support"] for row in dead),
            ],
            "zero_classes_are_the_rarest_classes": bool(
                {row["class_name"] for row in dead}
                == {
                    row["class_name"]
                    for row in sorted(rows, key=lambda item: item["support"])[
                        : len(dead)
                    ]
                }
            ),
            "reading": (
                "The six classes with F1 = 0 in every seed are exactly the "
                "six rarest classes, and the model never emits them in any "
                "seed. The coverage hole is therefore an absence of "
                "predictions, not a set of wrong predictions."
            ),
        },
        "lateral_asymmetry": {
            "description": (
                "BDD-OIA annotates left-side and right-side rationales with "
                "separate labels. Every one of the six left/right pairs is "
                "strongly asymmetric in both prevalence and recovery."
            ),
            "pairs": lateral_asymmetry(rows),
            "reading": (
                "The rationale vocabulary the model actually recovers is "
                "missing the left-turn justification set. A single R "
                "Macro-F1 cannot express this."
            ),
        },
        "per_class": rows,
        "reproduction_check": {
            "recomputed_macro_f1": computed_macro,
            "frozen_macro_f1": macro_row["mean_across_seeds"],
            "matches": True,
        },
        "provenance": provenance(
            [
                *(
                    f"outputs/validity/rq1_seed_{seed}/prediction_cache/rq1_lossless.npz"
                    for seed in FROZEN_SEEDS
                ),
                "outputs/validity/rq1_multiseed_summary.json",
            ]
        ),
        "claim_boundary": (
            "Rationale-label recovery coverage is incomplete and highly "
            "class-dependent. This is not a statement about reasoning "
            "faithfulness and not a statement that the model's explanations "
            "are wrong."
        ),
    }

    write_json(args.output_json, result)
    write_csv(args.output_csv, rows)

    markdown_rows = []
    for row in sorted(rows, key=lambda item: item["f1_mean"]):
        markdown_rows.append(
            [
                row["class_name"],
                row["support"],
                f"{row['support_rate']:.4f}",
                f"{row['f1_mean']:.4f}",
                f"{row['f1_sd']:.4f}",
                f"{row['f1_min']:.4f}-{row['f1_max']:.4f}",
                f"{row['precision_mean']:.4f}",
                f"{row['recall_mean']:.4f}",
                f"{row['predicted_positive_mean']:.1f}",
                "ZERO" if row["zero_in_all_seeds"] else "",
            ]
        )
    write_markdown_table(
        args.output_markdown,
        "R axis: per-class rationale-label coverage",
        [
            f"Frozen Round 5 study, seeds {', '.join(str(s) for s in FROZEN_SEEDS)}, "
            f"threshold {FROZEN_THRESHOLD}, "
            f"n = {collected['sample_count']} test images, Joint model only.",
            "",
            f"R Macro-F1 = {macro_row['mean_across_seeds']:.6f} "
            f"(95% hierarchical CI "
            f"[{macro_row['hierarchical_ci_lower']:.6f}, "
            f"{macro_row['hierarchical_ci_upper']:.6f}]); "
            f"R Micro-F1 = {micro_row['mean_across_seeds']:.6f} "
            f"(95% hierarchical CI "
            f"[{micro_row['hierarchical_ci_lower']:.6f}, "
            f"{micro_row['hierarchical_ci_upper']:.6f}]).",
            "",
            f"**{len(dead)} of {len(rows)} classes score F1 = 0 in all five "
            "seeds** and are marked ZERO. Rows are sorted by 5-seed mean F1.",
        ],
        [
            "Rationale class",
            "Support",
            "Support rate",
            "Mean F1",
            "SD",
            "Min-Max",
            "Mean precision",
            "Mean recall",
            "Mean predicted positives",
            "Flag",
        ],
        markdown_rows,
        notes=[
            "Support is identical across seeds because the frozen test split "
            "is shared; the script asserts this.",
            "A class flagged ZERO is a rationale-label recovery hole at the "
            "frozen threshold. It is not evidence about reasoning quality.",
            "The ZERO classes have a mean predicted-positive count of 0 in "
            "every seed: the model never emits these labels at all, so the "
            "hole is missing predictions rather than wrong predictions.",
            "The ZERO classes are exactly the six rarest classes "
            f"(support {min(row['support'] for row in dead)}-"
            f"{max(row['support'] for row in dead)} of "
            f"{collected['sample_count']}), so prevalence explains much of "
            "the pattern; the point of the table is that the aggregate "
            "Macro-F1 does not reveal it.",
            "All six left/right rationale pairs are asymmetric: the rarer "
            "left-side label is recovered far worse than its right-side "
            "counterpart (see the lateral_asymmetry block of the JSON).",
            "The Macro/Micro gap "
            f"({macro_row['mean_across_seeds']:.4f} vs "
            f"{micro_row['mean_across_seeds']:.4f}) is what a single Macro "
            "number hides: Micro is carried by the recovered high-support "
            "classes.",
        ],
    )

    figures = plot(rows, collected, args.output_figure)

    print(f"R Macro-F1 {macro_row['mean_across_seeds']:.6f} / Micro-F1 "
          f"{micro_row['mean_across_seeds']:.6f}")
    print(f"zero-in-all-seeds classes ({len(dead)}): "
          f"{[row['class_name'] for row in dead]}")
    print(f"near-zero but not always zero ({len(weak)}): "
          f"{[row['class_name'] for row in weak]}")
    for path in figures:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
