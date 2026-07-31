"""Pure NumPy helpers for the preregistered Round 9 map hierarchy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


AXES = ("A", "R", "S", "C1")
Q_COUNT = 5


def validate_multimap_stack(
    source_maps: np.ndarray,
    expected_active_images: Sequence[int],
) -> dict[str, Any]:
    """Validate structural invariants for a stack of graded source maps."""

    values = np.asarray(source_maps, dtype=np.int64)
    expected = np.asarray(expected_active_images, dtype=np.int64)
    if values.ndim != 3 or values.shape[1] != Q_COUNT:
        raise ValueError(
            "source_maps must have shape (maps, five q values, images)"
        )
    if expected.shape != (Q_COUNT,):
        raise ValueError("expected_active_images must have five values")
    map_count, _, sample_count = values.shape
    identity = np.arange(sample_count, dtype=np.int64)
    by_map = []
    q1_hashable = []
    for map_index in range(map_count):
        maps = values[map_index]
        active_sets = [
            set(np.flatnonzero(source != identity)) for source in maps
        ]
        active_counts = np.asarray(
            [len(active) for active in active_sets], dtype=np.int64
        )
        bijections = [
            bool(np.array_equal(np.sort(source), identity))
            for source in maps
        ]
        nested = all(
            active_sets[index] < active_sets[index + 1]
            for index in range(Q_COUNT - 1)
        )
        q1_hashable.append(maps[-1].tobytes())
        by_map.append(
            {
                "map_index": map_index,
                "bijections": bijections,
                "active_images": active_counts.tolist(),
                "active_counts_match": bool(
                    np.array_equal(active_counts, expected)
                ),
                "strictly_nested": bool(nested),
                "q0_identity": bool(np.array_equal(maps[0], identity)),
                "q1_fixed_points": int(np.sum(maps[-1] == identity)),
            }
        )
    all_q1_unique = len(set(q1_hashable)) == map_count
    return {
        "map_count": map_count,
        "sample_count": sample_count,
        "all_q1_unique": all_q1_unique,
        "by_map": by_map,
        "all_passed": bool(
            all(
                all(item["bijections"])
                and item["active_counts_match"]
                and item["strictly_nested"]
                and item["q0_identity"]
                and item["q1_fixed_points"] == 0
                for item in by_map
            )
            and all_q1_unique
        ),
    }


def hierarchical_multimap_draw(
    rng: np.random.Generator,
    map_count: int,
    seed_count: int,
    component_counts: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Draw maps, one shared seed vector, and per-occurrence components."""

    counts = np.asarray(component_counts, dtype=np.int64)
    if (
        map_count <= 0
        or seed_count <= 0
        or counts.shape != (map_count,)
        or np.any(counts <= 0)
    ):
        raise ValueError("map, seed, and component counts must be positive")
    selected_maps = rng.integers(0, map_count, size=map_count)
    selected_seeds = rng.integers(0, seed_count, size=seed_count)
    selected_components = [
        rng.integers(
            0,
            int(counts[map_index]),
            size=int(counts[map_index]),
        )
        for map_index in selected_maps
    ]
    return selected_maps, selected_seeds, selected_components


def bottleneck_from_curves(
    curves: np.ndarray,
    directions: Sequence[str],
) -> float:
    """Take the weakest expected-direction adjacent step."""

    values = np.asarray(curves, dtype=np.float64)
    if (
        values.ndim != 2
        or values.shape[1] != Q_COUNT
        or len(directions) != values.shape[0]
    ):
        raise ValueError(
            "curves must be components by five q values with directions"
        )
    steps = []
    for curve, direction in zip(values, directions):
        if direction == "decreasing":
            steps.append(curve[:-1] - curve[1:])
        elif direction == "increasing":
            steps.append(curve[1:] - curve[:-1])
        else:
            raise ValueError(
                "direction must be increasing or decreasing"
            )
    return float(np.min(np.concatenate(steps)))


def average_occurrence_seed_bottlenecks(
    values_by_occurrence: Sequence[Mapping[int, Mapping[str, float]]],
    selected_seed_positions: np.ndarray,
) -> dict[str, float]:
    """Average per-map-occurrence, per-seed bottlenecks in frozen order."""

    selected = np.asarray(selected_seed_positions, dtype=np.int64)
    if selected.ndim != 1 or len(selected) == 0:
        raise ValueError("selected_seed_positions must be nonempty and 1-D")
    if not values_by_occurrence:
        raise ValueError("at least one map occurrence is required")
    occurrence_means = []
    for occurrence in values_by_occurrence:
        if not set(occurrence) >= set(selected.tolist()):
            raise ValueError(
                "every occurrence must contain every selected seed position"
            )
        occurrence_means.append(
            {
                axis: float(
                    np.mean(
                        [
                            occurrence[int(seed_position)][axis]
                            for seed_position in selected
                        ]
                    )
                )
                for axis in AXES
            }
        )
    return {
        axis: float(
            np.mean([values[axis] for values in occurrence_means])
        )
        for axis in AXES
    }


def grand_mean_curve_has_no_reversal(
    curves_by_map_seed: np.ndarray,
    directions: Sequence[str],
    tolerance: float = 0.0,
) -> bool:
    """Check a map-by-seed grand mean component curve."""

    values = np.asarray(curves_by_map_seed, dtype=np.float64)
    if values.ndim != 4 or values.shape[-1] != Q_COUNT:
        raise ValueError(
            "curves must have shape (maps, seeds, components, five q)"
        )
    mean_curves = values.mean(axis=(0, 1))
    if len(directions) != len(mean_curves):
        raise ValueError("directions do not align with components")
    for curve, direction in zip(mean_curves, directions):
        differences = np.diff(curve)
        if direction == "decreasing":
            if np.any(differences > tolerance):
                return False
        elif direction == "increasing":
            if np.any(differences < -tolerance):
                return False
        else:
            raise ValueError(
                "direction must be increasing or decreasing"
            )
    return True


def round9_axis_gate(
    map_mean_bottlenecks: Sequence[float],
    bootstrap_interval: Sequence[float],
    grand_mean_no_reversal: bool,
    minimum_positive_maps: int = 18,
) -> dict[str, Any]:
    """Apply the frozen Round 9 per-axis intersection gate."""

    raw = np.asarray(map_mean_bottlenecks, dtype=np.float64)
    interval = np.asarray(bootstrap_interval, dtype=np.float64)
    if raw.shape != (20,) or interval.shape != (2,):
        raise ValueError("Round 9 requires 20 maps and a two-sided CI")
    if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(interval)):
        raise ValueError("gate inputs must be finite")
    positive_maps = int(np.sum(raw > 0.0))
    subgates = {
        "at_least_18_of_20_positive_maps": (
            positive_maps >= minimum_positive_maps
        ),
        "grand_mean_positive": bool(raw.mean() > 0.0),
        "hierarchical_ci_lower_positive": bool(interval[0] > 0.0),
        "grand_mean_component_curves_no_reversal": bool(
            grand_mean_no_reversal
        ),
    }
    return {
        "map_count": len(raw),
        "positive_map_count": positive_maps,
        "grand_mean": float(raw.mean()),
        "bootstrap_interval": interval.tolist(),
        "subgates": subgates,
        "passed": bool(all(subgates.values())),
    }
