"""Outcome-blind maps and inference helpers for Round 8.

All construction in this module depends only on canonical filenames, clip
groups, fixed salts, and explicitly supplied curves.  It does not inspect
targets, predictions, confidence values, or metric outcomes when building the
graded association maps.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def clip_group(file_name: str) -> str:
    """Collapse only the frozen BDD-OIA temporal suffixes ``_1`` and ``_3``."""

    return re.sub(r"_(?:1|3)$", "", Path(file_name).stem)


def salted_order(
    file_names: Sequence[str],
    salt: str,
) -> list[int]:
    """Return a deterministic filename-only pseudorandom order."""

    return sorted(
        range(len(file_names)),
        key=lambda index: (
            hashlib.sha256(
                f"{salt}|{file_names[index]}".encode("utf-8")
            ).hexdigest(),
            file_names[index],
            index,
        ),
    )


def _three_distinct_clip_indices(
    order: Sequence[int],
    groups: Sequence[str],
) -> tuple[int, int, int]:
    selected: list[int] = []
    selected_groups: set[str] = set()
    for index in reversed(order):
        group = groups[index]
        if group not in selected_groups:
            selected.append(index)
            selected_groups.add(group)
        if len(selected) == 3:
            return tuple(selected)  # type: ignore[return-value]
    raise ValueError("at least three distinct clip groups are required")


def build_clip_safe_cycles(
    file_names: Sequence[str],
    salt: str,
) -> tuple[list[tuple[int, ...]], dict[str, Any]]:
    """Build deterministic 2-cycles plus one final 3-cycle.

    The input length must be odd.  Pairing uses a deterministic salted order,
    removes three distinct-clip samples for the final cycle, splits the
    remaining samples in half, and chooses the first cyclic rotation of the
    second half with no same-clip pair.
    """

    names = [str(value) for value in file_names]
    if len(names) < 5 or len(names) % 2 != 1:
        raise ValueError("cycle construction requires an odd length >= 5")
    if len(set(names)) != len(names):
        raise ValueError("filenames must be unique")
    groups = [clip_group(value) for value in names]
    order = salted_order(names, salt)
    triplet = _three_distinct_clip_indices(order, groups)
    triplet_set = set(triplet)
    remaining = [index for index in order if index not in triplet_set]
    half = len(remaining) // 2
    left = remaining[:half]
    right = remaining[half:]

    selected_rotation: int | None = None
    paired_right: list[int] | None = None
    for rotation in range(half):
        candidate = right[rotation:] + right[:rotation]
        if all(
            groups[first] != groups[second]
            for first, second in zip(left, candidate)
        ):
            selected_rotation = rotation
            paired_right = candidate
            break
    if paired_right is None or selected_rotation is None:
        raise RuntimeError(
            "no clip-safe half-rotation exists; STOP without changing salt"
        )

    pairs = [
        (first, second)
        for first, second in zip(left, paired_right)
    ]
    pairs.sort(
        key=lambda pair: (
            hashlib.sha256(
                (
                    f"{salt}|cycle|"
                    + "|".join(sorted(names[index] for index in pair))
                ).encode("utf-8")
            ).hexdigest(),
            pair,
        )
    )
    cycles: list[tuple[int, ...]] = [*pairs, triplet]
    diagnostics = {
        "salt": salt,
        "pair_count": len(pairs),
        "triplet": list(triplet),
        "right_half_rotation": selected_rotation,
        "all_cycle_members_unique": (
            len({index for cycle in cycles for index in cycle})
            == len(names)
        ),
        "all_cycle_edges_cross_clip": all(
            groups[source] != groups[target]
            for cycle in cycles
            for source, target in zip(cycle, (*cycle[1:], cycle[0]))
        ),
    }
    return cycles, diagnostics


def graded_source_maps(
    sample_count: int,
    cycles: Sequence[Sequence[int]],
    severity_grid: Sequence[float],
) -> dict[float, np.ndarray]:
    """Activate a nested fraction of outcome-blind cycles at each severity."""

    if tuple(severity_grid) != (0.0, 0.25, 0.5, 0.75, 1.0):
        raise ValueError("severity grid is frozen to 0,.25,.5,.75,1")
    if not cycles or len(cycles[-1]) != 3:
        raise ValueError("the final cycle must be the odd-sample 3-cycle")
    pair_cycles = list(cycles[:-1])
    if any(len(cycle) != 2 for cycle in pair_cycles):
        raise ValueError("all non-final cycles must be 2-cycles")
    members = [index for cycle in cycles for index in cycle]
    if sorted(members) != list(range(sample_count)):
        raise ValueError("cycles must partition all canonical samples")

    result: dict[float, np.ndarray] = {}
    for severity in severity_grid:
        source = np.arange(sample_count, dtype=np.int64)
        if severity == 1.0:
            active_cycles = list(cycles)
        else:
            active_pair_count = int(
                np.floor(severity * sample_count / 2.0 + 0.5)
            )
            active_cycles = pair_cycles[:active_pair_count]
        for cycle in active_cycles:
            for current, target in zip(
                cycle, (*cycle[1:], cycle[0])
            ):
                source[current] = target
        result[float(severity)] = source
    return result


def validate_graded_maps(
    file_names: Sequence[str],
    maps: Mapping[float, np.ndarray],
) -> dict[str, Any]:
    """Return exact filename/clip-only invariants for every severity."""

    names = [str(value) for value in file_names]
    groups = [clip_group(value) for value in names]
    sample_count = len(names)
    previous_active: set[int] = set()
    by_severity: dict[str, Any] = {}
    for severity in sorted(maps):
        source = np.asarray(maps[severity], dtype=np.int64)
        active = set(np.flatnonzero(source != np.arange(sample_count)))
        by_severity[str(severity)] = {
            "bijection": bool(
                np.array_equal(np.sort(source), np.arange(sample_count))
            ),
            "active_images": len(active),
            "active_fraction": len(active) / sample_count,
            "fixed_points": int(
                np.sum(source == np.arange(sample_count))
            ),
            "active_same_filename_pairs": int(
                sum(names[index] == names[source[index]] for index in active)
            ),
            "active_same_clip_pairs": int(
                sum(groups[index] == groups[source[index]] for index in active)
            ),
            "nested_superset": previous_active.issubset(active),
        }
        previous_active = active
    return {
        "sample_count": sample_count,
        "clip_group_count": len(set(groups)),
        "by_severity": by_severity,
        "all_passed": all(
            values["bijection"]
            and values["active_same_filename_pairs"] == 0
            and values["active_same_clip_pairs"] == 0
            and values["nested_superset"]
            for values in by_severity.values()
        ),
    }


def shared_clip_bootstrap_draw(
    rng: np.random.Generator,
    seeds: Sequence[int],
    clip_to_indices: Sequence[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resample seeds and exactly one shared multiset of whole clips."""

    seed_values = np.asarray(seeds, dtype=np.int64)
    if seed_values.ndim != 1 or len(seed_values) == 0:
        raise ValueError("seeds must be a nonempty one-dimensional sequence")
    if not clip_to_indices:
        raise ValueError("at least one clip is required")
    selected_seeds = rng.choice(
        seed_values, size=len(seed_values), replace=True
    )
    selected_clips = rng.integers(
        0,
        len(clip_to_indices),
        size=len(clip_to_indices),
        dtype=np.int64,
    )
    shared_images = np.concatenate(
        [
            np.asarray(clip_to_indices[index], dtype=np.int64)
            for index in selected_clips
        ]
    )
    return selected_seeds, selected_clips, shared_images


def bottleneck_monotonic_step(
    curves: Sequence[Sequence[float]],
    direction: str,
) -> float:
    """Return the weakest adjacent step across all component curves.

    Positive values mean every adjacent step follows the expected direction.
    """

    values = np.asarray(curves, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 5:
        raise ValueError("curves must have shape (components, five severities)")
    if not np.all(np.isfinite(values)):
        raise ValueError("curves must be finite")
    if direction == "decreasing":
        steps = values[:, :-1] - values[:, 1:]
    elif direction == "increasing":
        steps = values[:, 1:] - values[:, :-1]
    else:
        raise ValueError("direction must be increasing or decreasing")
    return float(np.min(steps))
