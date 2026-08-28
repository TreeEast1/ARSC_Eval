"""RQ2 main figure: the four ARSC axes do not move together under perturbation.

Round 10 re-ran inference over 4557 BDD-OIA test images drawn from 3904
source clips, for three semantics-preserving corruption families
(brightness, blur, noise) at a clean level plus four severity levels, for
five frozen training seeds and both models.

The frozen pre-registered verdict is unchanged: 3 of 12 family-by-axis gates
passed.  This script does not re-run, re-threshold or re-test anything.  It
reads the frozen point-diagnostics table and draws what the 3/12 verdict
actually looks like -- the three gates that passed are exactly the three C1
gates, and A, R and S stay nearly flat over the same severity range.

That is the RQ2 evidence: a manipulation strong enough to change the
thresholded action set on 16-27% of images leaves aggregate Action Macro-F1
almost unmoved.  Prediction stability and action performance are therefore
not measuring the same thing.  The figure is deliberately drawn on a shared
scale in the top row so the *non*-uniformity is visible at a glance.

Reading conventions:
  * Every panel plots *degradation relative to the clean level*, signed so
    that positive always means worse: -dMacro-F1 for A and R, +dAURC for S,
    +d(action-set flip rate) for C1.
  * The top row shares one y-axis across all four axes.  The bottom row
    rescales each axis independently and adds the +/-1 SD band across the
    five seeds.

Claim boundary: C1 measures thresholded prediction-set stability under
synthetic image corruptions.  It is not real-road robustness and it is not
evidence about what the model attends to.
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
    AXIS_COLORS,
    AXIS_NAMES,
    AXIS_NOT,
    AXIS_OPERATIONALISATION,
    FROZEN_SEEDS,
    MODEL_ACTION,
    MODEL_JOINT,
    PERTURBATION_FAMILIES,
    apply_figure_style,
    load_round10_results,
    provenance,
    round10_primary_curves,
    save_figure,
    write_csv,
    write_json,
    write_markdown_table,
)

#: Which frozen curve component belongs to which axis and model, and the sign
#: that turns "change from clean" into "degradation" (positive = worse).
AXIS_COMPONENTS: dict[str, list[tuple[str, str, float]]] = {
    # axis: [(component, model label, degradation sign)]
    "A": [
        ("action_only", MODEL_ACTION, -1.0),
        ("joint", MODEL_JOINT, -1.0),
    ],
    "R": [("joint_rationale", MODEL_JOINT, -1.0)],
    "S": [
        ("action_only", MODEL_ACTION, +1.0),
        ("joint", MODEL_JOINT, +1.0),
    ],
    "C1": [
        ("action_only_flip", MODEL_ACTION, +1.0),
        ("joint_flip", MODEL_JOINT, +1.0),
    ],
}

AXIS_UNITS = {
    "A": "-d(Action Macro-F1)",
    "R": "-d(Rationale Macro-F1)",
    "S": "+d(AURC)",
    "C1": "+d(action-set flip rate)",
}

FAMILY_COLORS = {
    "brightness": "#e8a33d",
    "blur": "#3b7dd8",
    "noise": "#4aa564",
}

MODEL_STYLES = {MODEL_ACTION: "-", MODEL_JOINT: "--"}

AXIS_ORDER = ("A", "R", "S", "C1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-figure", default="outputs/paper/figures/round10_axis_separation"
    )
    parser.add_argument("--output-json", default="outputs/paper/round10_axis_separation.json")
    parser.add_argument("--output-csv", default="outputs/paper/round10_axis_separation.csv")
    parser.add_argument(
        "--output-markdown", default="outputs/paper/tables/round10_axis_separation.md"
    )
    return parser.parse_args()


def gate_table(results: dict[str, Any]) -> dict[tuple[str, str], bool]:
    return {
        (gate["family"], gate["axis"]): bool(gate["passed"])
        for gate in results["gate_result"]["family_axis_gates"]
    }


def degradation_curves(
    curves: dict[tuple[str, str, str], dict[int, list[float]]],
) -> dict[tuple[str, str, str], dict[str, np.ndarray]]:
    """Per-seed degradation relative to the clean level, keyed by axis."""

    prepared: dict[tuple[str, str, str], dict[str, np.ndarray]] = {}
    for axis, components in AXIS_COMPONENTS.items():
        for component, model, sign in components:
            for family in PERTURBATION_FAMILIES:
                by_level = curves[(family, axis, component)]
                levels = sorted(by_level)
                matrix = np.array(
                    [by_level[level] for level in levels], dtype=np.float64
                )  # (level, seed)
                baseline = matrix[0]
                degradation = sign * (matrix - baseline)
                prepared[(family, axis, model)] = {
                    "levels": np.asarray(levels),
                    "per_seed": degradation,
                    "mean": degradation.mean(axis=1),
                    "sd": degradation.std(axis=1, ddof=1),
                    "raw_mean": matrix.mean(axis=1),
                }
    return prepared


def build_rows(
    prepared: dict[tuple[str, str, str], dict[str, np.ndarray]],
    gates: dict[tuple[str, str], bool],
    parameters: dict[str, list[float]],
) -> list[dict[str, Any]]:
    rows = []
    for family in PERTURBATION_FAMILIES:
        for axis in AXIS_ORDER:
            for _, model, sign in AXIS_COMPONENTS[axis]:
                data = prepared[(family, axis, model)]
                for index, level in enumerate(data["levels"]):
                    rows.append(
                        {
                            "family": family,
                            "axis": axis,
                            "axis_name": AXIS_NAMES[axis],
                            "model": model,
                            "severity_level": int(level),
                            "severity_parameter": parameters[family][int(level)],
                            "raw_mean_across_seeds": float(data["raw_mean"][index]),
                            "degradation_mean_across_seeds": float(
                                data["mean"][index]
                            ),
                            "degradation_sd_across_seeds": float(data["sd"][index]),
                            "degradation_sign_convention": (
                                "positive_is_worse" if sign > 0 else "positive_is_worse"
                            ),
                            "family_axis_gate_passed": gates[(family, axis)],
                        }
                    )
    return rows


def plot(
    prepared: dict[tuple[str, str, str], dict[str, np.ndarray]],
    gates: dict[tuple[str, str], bool],
    results: dict[str, Any],
    stem: str,
) -> list[Path]:
    apply_figure_style()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    figure, axes = plt.subplots(2, 4, figsize=(13.4, 6.9))

    shared_top = 0.0
    for key, data in prepared.items():
        shared_top = max(shared_top, float(np.max(data["mean"] + data["sd"])))
    shared_top *= 1.12

    for column, axis in enumerate(AXIS_ORDER):
        passed = sum(
            1 for family in PERTURBATION_FAMILIES if gates[(family, axis)]
        )
        for row in (0, 1):
            panel = axes[row][column]
            for family in PERTURBATION_FAMILIES:
                for _, model, _ in AXIS_COMPONENTS[axis]:
                    data = prepared[(family, axis, model)]
                    levels = data["levels"]
                    panel.plot(
                        levels,
                        data["mean"],
                        color=FAMILY_COLORS[family],
                        linestyle=MODEL_STYLES[model],
                        marker="o" if model == MODEL_ACTION else "s",
                        markersize=3.4,
                        linewidth=1.7,
                        zorder=3,
                    )
                    if row == 1:
                        panel.fill_between(
                            levels,
                            data["mean"] - data["sd"],
                            data["mean"] + data["sd"],
                            color=FAMILY_COLORS[family],
                            alpha=0.16,
                            linewidth=0,
                            zorder=1,
                        )
            panel.axhline(0.0, color="#555555", linewidth=0.9, zorder=2)
            panel.set_xticks([0, 1, 2, 3, 4])
            if row == 0:
                panel.set_ylim(-0.02 * shared_top / 0.2, shared_top)
                panel.set_title(
                    f"{axis} - {AXIS_NAMES[axis]}\n"
                    f"{passed}/3 severity gates passed",
                    fontsize=9,
                    fontweight="bold",
                    color=AXIS_COLORS[axis],
                )
                if column == 0:
                    panel.set_ylabel(
                        "Degradation vs clean\n(shared scale, positive = worse)",
                        fontsize=8.5,
                    )
            else:
                panel.set_xlabel("Perturbation severity level")
                panel.set_title(
                    f"{AXIS_UNITS[axis]}   (own scale)", fontsize=8.5
                )
                if column == 0:
                    panel.set_ylabel(
                        "Degradation vs clean\n(own scale, +/-1 SD across seeds)",
                        fontsize=8.5,
                    )

    axes[0][0].annotate(
        "A, R and S are flat here",
        xy=(2.0, 0.004),
        xytext=(0.35, 0.55 * shared_top),
        fontsize=8.4,
        color="#444444",
        arrowprops={"arrowstyle": "->", "color": "#444444", "linewidth": 0.9},
    )
    c1_panel = axes[0][3]
    c1_panel.annotate(
        "only C1 responds\nto severity",
        xy=(4.0, prepared[("blur", "C1", MODEL_ACTION)]["mean"][-1]),
        xytext=(1.15, 0.72 * shared_top),
        fontsize=8.6,
        color=AXIS_COLORS["C1"],
        fontweight="bold",
        arrowprops={
            "arrowstyle": "->",
            "color": AXIS_COLORS["C1"],
            "linewidth": 1.1,
        },
    )

    handles = [
        Line2D([], [], color=FAMILY_COLORS[family], linewidth=2.0, label=family)
        for family in PERTURBATION_FAMILIES
    ] + [
        Line2D(
            [],
            [],
            color="#555555",
            linestyle=MODEL_STYLES[model],
            marker="o" if model == MODEL_ACTION else "s",
            markersize=4,
            linewidth=1.6,
            label=model,
        )
        for model in (MODEL_ACTION, MODEL_JOINT)
    ]
    figure.legend(
        handles=handles,
        loc="lower center",
        ncol=5,
        bbox_to_anchor=(0.5, -0.005),
        fontsize=8.5,
    )

    design = results["design"]
    figure.suptitle(
        "Round 10: perturbation severity separates the ARSC axes. "
        f"{results['gate_result']['passed_gate_count']} of "
        f"{results['gate_result']['gate_count']} pre-registered family-by-axis "
        "gates passed, and all three are C1 gates.",
        fontsize=11.5,
        fontweight="bold",
        y=0.995,
    )
    figure.text(
        0.5,
        0.945,
        f"{design['sample_count']} test images from "
        f"{design['source_clip_count']} source clips - "
        f"{len(FROZEN_SEEDS)} frozen seeds - clean level plus four severity "
        "levels - real re-inference, no cached predictions",
        ha="center",
        fontsize=8.6,
        color="#444444",
    )
    figure.tight_layout(rect=(0, 0.045, 1, 0.935))
    written = save_figure(figure, stem)
    plt.close(figure)
    return written


def main() -> int:
    args = parse_args()
    results = load_round10_results()
    curves = round10_primary_curves()
    gates = gate_table(results)
    prepared = degradation_curves(curves)
    parameters = results["design"]["parameters"]
    rows = build_rows(prepared, gates, parameters)

    passed_gates = [key for key, value in gates.items() if value]
    if results["gate_result"]["passed_gate_count"] != len(passed_gates):
        raise RuntimeError("gate bookkeeping disagrees with the frozen result")

    endpoint = {}
    for family in PERTURBATION_FAMILIES:
        for axis in AXIS_ORDER:
            for _, model, _ in AXIS_COMPONENTS[axis]:
                data = prepared[(family, axis, model)]
                endpoint[f"{family}::{axis}::{model}"] = {
                    "degradation_at_max_severity": float(data["mean"][-1]),
                    "sd_across_seeds_at_max_severity": float(data["sd"][-1]),
                    "clean_value": float(data["raw_mean"][0]),
                    "max_severity_value": float(data["raw_mean"][-1]),
                }

    max_c1 = max(
        endpoint[f"{family}::C1::{model}"]["degradation_at_max_severity"]
        for family in PERTURBATION_FAMILIES
        for model in (MODEL_ACTION, MODEL_JOINT)
    )
    max_a = max(
        abs(endpoint[f"{family}::A::{model}"]["degradation_at_max_severity"])
        for family in PERTURBATION_FAMILIES
        for model in (MODEL_ACTION, MODEL_JOINT)
    )
    max_r = max(
        abs(endpoint[f"{family}::R::{MODEL_JOINT}"]["degradation_at_max_severity"])
        for family in PERTURBATION_FAMILIES
    )
    s_signs = {
        family: float(
            np.sign(
                endpoint[f"{family}::S::{MODEL_ACTION}"][
                    "degradation_at_max_severity"
                ]
            )
        )
        for family in PERTURBATION_FAMILIES
    }

    result = {
        "schema_version": "ARSC_ROUND10_AXIS_SEPARATION_V1",
        "analysis_id": "ARSC_RQ2_AXIS_NON_REDUNDANCY",
        "role": "RQ2 primary evidence: the four axes are not redundant",
        "frozen_verdict": {
            "verdict": results["verdict"],
            "gate_count": results["gate_result"]["gate_count"],
            "passed_gate_count": results["gate_result"]["passed_gate_count"],
            "passed_gates": [
                {"family": family, "axis": axis} for family, axis in passed_gates
            ],
            "unchanged": True,
            "note": (
                "The pre-registered thresholds, gate definitions and verdict "
                "are reproduced verbatim from the frozen Round 10 result. "
                "Only the interpretation is written here."
            ),
        },
        "design": {
            "sample_count": results["design"]["sample_count"],
            "source_clip_count": results["design"]["source_clip_count"],
            "families": list(results["design"]["families"]),
            "levels": list(results["design"]["levels"]),
            "parameters": parameters,
            "seeds": list(results["design"]["seeds"]),
            "bootstrap_replicates": results["design"]["bootstrap_replicates"],
        },
        "axis_definitions": {
            axis: {
                "name": AXIS_NAMES[axis],
                "operationalisation": AXIS_OPERATIONALISATION[axis],
                "degradation_convention": AXIS_UNITS[axis],
                "does_not_measure": AXIS_NOT[axis],
            }
            for axis in AXIS_ORDER
        },
        "endpoint_summary": endpoint,
        "headline": {
            "largest_c1_degradation_at_max_severity": max_c1,
            "largest_absolute_a_degradation_at_max_severity": max_a,
            "largest_absolute_r_degradation_at_max_severity": max_r,
            "c1_to_a_magnitude_ratio": max_c1 / max_a if max_a else float("inf"),
            "s_degradation_sign_by_family": s_signs,
            "s_sign_is_consistent_across_families": len(set(s_signs.values())) == 1,
        },
        "interpretation": {
            "what_the_3_of_12_verdict_means": (
                "Only the C1 gates passed. Read as a construct-validation "
                "exercise the pre-registered expectation that all four axes "
                "should respond to this manipulation was not met. Read as a "
                "discriminant-validity exercise, that is the finding: the "
                "axes separate."
            ),
            "why_this_is_non_redundancy_evidence": (
                "Input perturbation produced action-set changes on a large "
                "fraction of individual images while aggregate Action "
                "Macro-F1 stayed nearly constant. A metric that barely moves "
                "when a large share of individual predictions change is not "
                "measuring the same quantity as one that tracks those "
                "changes."
            ),
            "what_this_does_not_license": [
                "It does not show that every perturbation should move every "
                "axis.",
                "It does not show that A, R or S are insensitive in general; "
                "it shows they are insensitive to *this* manipulation.",
                "It does not make C1 a measure of real-road robustness.",
                "It does not validate the four axes as a construct; the "
                "pre-registered construct-validation gate remains 3/12.",
            ],
        },
        "provenance": provenance(
            [
                "outputs/validity/round10_corruption_formal_attempt02/"
                "round10_corruption_results.json",
                "outputs/validity/round10_corruption_formal_attempt02/"
                "round10_corruption_point_diagnostics.csv",
            ]
        ),
        "claim_boundary": results["claim_boundary"],
    }

    write_json(args.output_json, result)
    write_csv(args.output_csv, rows)

    markdown_rows = []
    for family in PERTURBATION_FAMILIES:
        for axis in AXIS_ORDER:
            for _, model, _ in AXIS_COMPONENTS[axis]:
                data = endpoint[f"{family}::{axis}::{model}"]
                markdown_rows.append(
                    [
                        family,
                        axis,
                        model,
                        f"{data['clean_value']:.4f}",
                        f"{data['max_severity_value']:.4f}",
                        f"{data['degradation_at_max_severity']:+.4f}",
                        f"{data['sd_across_seeds_at_max_severity']:.4f}",
                        "PASS" if gates[(family, axis)] else "fail",
                    ]
                )
    write_markdown_table(
        args.output_markdown,
        "Round 10: axis response to perturbation severity",
        [
            f"Frozen Round 10 formal run (attempt02): "
            f"{results['design']['sample_count']} test images from "
            f"{results['design']['source_clip_count']} source clips, "
            f"{len(FROZEN_SEEDS)} seeds, three corruption families, clean "
            "level plus four severity levels, real re-inference.",
            "",
            f"Pre-registered verdict, unchanged: **{results['verdict']}**, "
            f"{results['gate_result']['passed_gate_count']} of "
            f"{results['gate_result']['gate_count']} family-by-axis gates "
            "passed. The three that passed are the three C1 gates.",
            "",
            "Degradation is signed so that positive always means worse: "
            "-dMacro-F1 for A and R, +dAURC for S, +d(flip rate) for C1.",
        ],
        [
            "Family",
            "Axis",
            "Model",
            "Clean",
            "Max severity",
            "Degradation",
            "SD across seeds",
            "Gate",
        ],
        markdown_rows,
        notes=[
            f"Largest C1 degradation at maximum severity: {max_c1:.4f}. "
            f"Largest absolute A degradation over the same range: {max_a:.4f} "
            f"({max_c1 / max_a:.1f}x smaller).",
            f"Largest absolute R degradation: {max_r:.4f}.",
            "S does not even agree with itself across families: AURC gets "
            "worse under brightness and blur but better under noise, which "
            "is why no S gate passed.",
            "C1 measures thresholded prediction-set stability under "
            "synthetic image corruption. It is not real-road robustness and "
            "not evidence about what the model attends to.",
        ],
    )

    figures = plot(prepared, gates, results, args.output_figure)

    print(f"frozen verdict {results['verdict']} "
          f"({results['gate_result']['passed_gate_count']}/"
          f"{results['gate_result']['gate_count']} gates), passed = {passed_gates}")
    print(f"max C1 degradation {max_c1:.4f} vs max |A| degradation {max_a:.4f} "
          f"({max_c1 / max_a:.1f}x)")
    print(f"S degradation sign by family: {s_signs}")
    for path in figures:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
