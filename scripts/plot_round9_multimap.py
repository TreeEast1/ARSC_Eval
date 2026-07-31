"""Plot the frozen Round 9 20-map graded-response curves.

The figure is descriptive. Thin lines are map-specific five-seed means and
bold lines are grand means across all 20 maps and five seeds. The
preregistered hierarchical intervals apply to each axis bottleneck statistic,
not to individual q points, so no pointwise bands are drawn.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDITY_DIR = PROJECT_ROOT / "outputs" / "validity"
RESULT_PATH = VALIDITY_DIR / "round9_multimap_results.json"
PRIMITIVE_PATH = VALIDITY_DIR / "round9_multimap_primitives.npz"
PNG_PATH = VALIDITY_DIR / "round9_multimap_curves.png"
SVG_PATH = VALIDITY_DIR / "round9_multimap_curves.svg"
Q_VALUES = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing PNG/SVG outputs",
    )
    return parser.parse_args()


def load_result() -> dict[str, Any]:
    with RESULT_PATH.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def draw_component(
    axis: plt.Axes,
    curves: np.ndarray,
    component: int,
    label: str,
    color: str,
    marker: str,
) -> None:
    map_means = curves[:, :, component, :].mean(axis=1)
    for values in map_means:
        axis.plot(
            Q_VALUES,
            values,
            color=color,
            linewidth=0.8,
            alpha=0.13,
        )
    axis.plot(
        Q_VALUES,
        map_means.mean(axis=0),
        color=color,
        linewidth=2.6,
        marker=marker,
        markersize=5.5,
        label=label,
    )


def format_axis(
    axis: plt.Axes,
    title: str,
    ylabel: str,
) -> None:
    axis.set_title(title, loc="left", fontweight="bold", fontsize=12)
    axis.set_xlabel("Association destruction q")
    axis.set_ylabel(ylabel)
    axis.set_xticks(Q_VALUES)
    axis.set_xticklabels(["0", ".25", ".50", ".75", "1"])
    axis.grid(True, color="#D9DEE7", linewidth=0.7, alpha=0.8)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def main() -> int:
    args = parse_args()
    if not args.force:
        existing = [path for path in (PNG_PATH, SVG_PATH) if path.exists()]
        if existing:
            raise RuntimeError(
                f"plot output already exists; pass --force: {existing}"
            )
    result = load_result()
    with np.load(PRIMITIVE_PATH, allow_pickle=False) as archive:
        curves = {
            axis: archive[f"{axis}_primary_curves"].copy()
            for axis in ("A", "R", "S", "C1")
        }

    figure, axes = plt.subplots(2, 2, figsize=(12.8, 9.3))
    figure.patch.set_facecolor("#F8FAFD")
    for axis in axes.flat:
        axis.set_facecolor("#FFFFFF")

    draw_component(
        axes[0, 0],
        curves["A"],
        0,
        "Action-Only Macro-F1",
        "#1769AA",
        "o",
    )
    draw_component(
        axes[0, 0],
        curves["A"],
        1,
        "Joint Macro-F1",
        "#D1495B",
        "s",
    )
    format_axis(
        axes[0, 0],
        "A  Action accuracy (expected decrease)",
        "Macro-F1",
    )
    axes[0, 0].legend(frameon=False, fontsize=9)

    draw_component(
        axes[0, 1],
        curves["R"],
        0,
        "Joint 21-label Macro-F1",
        "#6A4C93",
        "D",
    )
    format_axis(
        axes[0, 1],
        "R  Rationale quality (expected decrease)",
        "Macro-F1",
    )
    axes[0, 1].legend(frameon=False, fontsize=9)

    draw_component(
        axes[1, 0],
        curves["S"],
        0,
        "Action-Only tie-averaged AURC",
        "#1769AA",
        "o",
    )
    draw_component(
        axes[1, 0],
        curves["S"],
        1,
        "Joint tie-averaged AURC",
        "#D1495B",
        "s",
    )
    format_axis(
        axes[1, 0],
        "S  Selective risk ordering (expected increase)",
        "AURC (lower is better)",
    )
    axes[1, 0].legend(frameon=False, fontsize=9)

    draw_component(
        axes[1, 1],
        curves["C1"],
        0,
        "Action-Only action flip",
        "#1769AA",
        "o",
    )
    draw_component(
        axes[1, 1],
        curves["C1"],
        1,
        "Joint action flip",
        "#D1495B",
        "s",
    )
    draw_component(
        axes[1, 1],
        curves["C1"],
        2,
        "Joint rationale Jaccard",
        "#2A9D8F",
        "^",
    )
    format_axis(
        axes[1, 1],
        "C1  Sample correspondence response",
        "Flip rate / Jaccard",
    )
    axes[1, 1].legend(frameon=False, fontsize=8.5)

    summaries = result["axis_summaries"]
    bottleneck_items = [
        (
            f"{axis}: mean {summaries[axis]['grand_mean']:.4f}, "
            f"95% CI [{summaries[axis]['bootstrap_interval'][0]:.4f}, "
            f"{summaries[axis]['bootstrap_interval'][1]:.4f}], "
            f"{summaries[axis]['positive_map_count']}/20 maps"
        )
        for axis in ("A", "R", "S", "C1")
    ]
    figure.suptitle(
        "BDD-OIA Round 9: 20-map graded association-response robustness",
        x=0.06,
        y=0.985,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.945,
        (
            "Thin lines: map-specific five-seed means. Bold lines: means "
            "across 20 maps x 5 seeds. Every axis is positive on 20/20 maps."
        ),
        ha="left",
        fontsize=9.5,
        color="#343A40",
    )
    figure.text(
        0.06,
        0.043,
        " | ".join(bottleneck_items[:2]),
        ha="left",
        fontsize=8.4,
        color="#343A40",
    )
    figure.text(
        0.06,
        0.027,
        " | ".join(bottleneck_items[2:]),
        ha="left",
        fontsize=8.4,
        color="#343A40",
    )
    figure.text(
        0.06,
        0.009,
        (
            "Hierarchical map x seed x component intervals apply to the "
            "weakest adjacent-step bottleneck, not to individual q points."
        ),
        ha="left",
        fontsize=8.3,
        color="#5C6770",
    )
    figure.tight_layout(rect=(0.04, 0.085, 0.98, 0.92))
    figure.savefig(PNG_PATH, dpi=180, facecolor=figure.get_facecolor())
    figure.savefig(SVG_PATH, facecolor=figure.get_facecolor())
    plt.close(figure)
    print(
        json.dumps(
            {
                "png": str(PNG_PATH.relative_to(PROJECT_ROOT)),
                "svg": str(SVG_PATH.relative_to(PROJECT_ROOT)),
                "descriptive_only": True,
                "pointwise_confidence_bands_drawn": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
