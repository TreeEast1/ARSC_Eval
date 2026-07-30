"""Outcome-blind association components for Round 8 clustered inference."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import numpy as np


def build_association_components(
    clip_group_ids: np.ndarray,
    q1_source_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Build deterministic clip/image component IDs from the q=1 dyads."""

    groups = np.asarray(clip_group_ids, dtype=np.int64)
    sources = np.asarray(q1_source_indices, dtype=np.int64)
    if groups.ndim != 1 or len(groups) == 0:
        raise ValueError("clip_group_ids must be a nonempty 1-D array")
    if sources.shape != groups.shape:
        raise ValueError("q1_source_indices must align with clip_group_ids")
    if not np.array_equal(np.sort(sources), np.arange(len(groups))):
        raise ValueError("q1_source_indices must be a sample-index bijection")

    unique_groups = np.unique(groups)
    if not np.array_equal(
        unique_groups, np.arange(len(unique_groups), dtype=np.int64)
    ):
        raise ValueError("clip group IDs must be contiguous from zero")

    parent = np.arange(len(unique_groups), dtype=np.int64)
    rank = np.zeros(len(unique_groups), dtype=np.int64)

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = int(parent[node])
        return node

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if rank[left_root] < rank[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        if rank[left_root] == rank[right_root]:
            rank[left_root] += 1

    for destination, source in enumerate(sources):
        union(int(groups[destination]), int(groups[source]))

    roots = np.array([find(group) for group in unique_groups], dtype=np.int64)
    root_minimum: dict[int, int] = {}
    for group, root in enumerate(roots):
        root_minimum[root] = min(root_minimum.get(root, group), group)
    ordered_roots = sorted(root_minimum, key=root_minimum.__getitem__)
    root_to_component = {
        root: component for component, root in enumerate(ordered_roots)
    }
    component_by_clip = np.array(
        [root_to_component[int(root)] for root in roots], dtype=np.int64
    )
    component_by_image = component_by_clip[groups]
    return component_by_clip, component_by_image


def pack_members(
    component_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Pack item indices into deterministic component slices."""

    labels = np.asarray(component_ids, dtype=np.int64)
    if labels.ndim != 1 or len(labels) == 0:
        raise ValueError("component_ids must be a nonempty 1-D array")
    unique = np.unique(labels)
    if not np.array_equal(unique, np.arange(len(unique), dtype=np.int64)):
        raise ValueError("component IDs must be contiguous from zero")
    members = [
        np.flatnonzero(labels == component).astype(np.int64)
        for component in unique
    ]
    offsets = np.zeros(len(members) + 1, dtype=np.int64)
    offsets[1:] = np.cumsum([len(values) for values in members])
    flat = np.concatenate(members)
    return offsets, flat


def expand_component_draw(
    selected_components: np.ndarray,
    component_image_offsets: np.ndarray,
    component_image_indices: np.ndarray,
) -> np.ndarray:
    """Expand a component multiset to full image membership with multiplicity."""

    selected = np.asarray(selected_components, dtype=np.int64)
    offsets = np.asarray(component_image_offsets, dtype=np.int64)
    images = np.asarray(component_image_indices, dtype=np.int64)
    if selected.ndim != 1 or offsets.ndim != 1 or images.ndim != 1:
        raise ValueError("component draw arrays must be one-dimensional")
    component_count = len(offsets) - 1
    if component_count <= 0 or offsets[0] != 0 or offsets[-1] != len(images):
        raise ValueError("invalid packed component membership")
    if np.any(np.diff(offsets) <= 0):
        raise ValueError("every component must contain at least one image")
    if np.any(selected < 0) or np.any(selected >= component_count):
        raise ValueError("selected component index out of range")
    parts = [
        images[offsets[component] : offsets[component + 1]]
        for component in selected
    ]
    if not parts:
        return np.empty(0, dtype=np.int64)
    return np.concatenate(parts)


def shared_component_bootstrap_draw(
    rng: np.random.Generator,
    seed_count: int,
    component_image_offsets: np.ndarray,
    component_image_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Draw seeds and one shared association-component image multiset."""

    component_count = len(component_image_offsets) - 1
    if seed_count <= 0 or component_count <= 0:
        raise ValueError("seed_count and component_count must be positive")
    selected_seeds = rng.integers(0, seed_count, size=seed_count)
    selected_components = rng.integers(
        0, component_count, size=component_count
    )
    shared_images = expand_component_draw(
        selected_components,
        component_image_offsets,
        component_image_indices,
    )
    return selected_seeds, selected_components, shared_images


def validate_association_components(
    clip_group_ids: np.ndarray,
    source_maps: Mapping[str, np.ndarray],
    component_by_clip: np.ndarray,
    component_by_image: np.ndarray,
) -> dict[str, Any]:
    """Exact-audit the partition, closure, and restricted bijections."""

    groups = np.asarray(clip_group_ids, dtype=np.int64)
    clip_components = np.asarray(component_by_clip, dtype=np.int64)
    image_components = np.asarray(component_by_image, dtype=np.int64)
    clip_count = len(np.unique(groups))
    if clip_components.shape != (clip_count,):
        raise ValueError("component_by_clip has the wrong shape")
    if image_components.shape != groups.shape:
        raise ValueError("component_by_image has the wrong shape")
    if not np.array_equal(image_components, clip_components[groups]):
        raise ValueError("clip and image component IDs disagree")

    unique_components = np.unique(clip_components)
    if not np.array_equal(
        unique_components,
        np.arange(len(unique_components), dtype=np.int64),
    ):
        raise ValueError("component IDs must be contiguous from zero")

    clip_sizes = np.bincount(
        clip_components, minlength=len(unique_components)
    )
    image_sizes = np.bincount(
        image_components, minlength=len(unique_components)
    )
    by_map: dict[str, dict[str, Any]] = {}
    all_maps_passed = True
    for name, raw_source in source_maps.items():
        source = np.asarray(raw_source, dtype=np.int64)
        global_bijection = (
            source.shape == groups.shape
            and np.array_equal(np.sort(source), np.arange(len(groups)))
        )
        closure = bool(
            global_bijection
            and np.array_equal(image_components[source], image_components)
        )
        restricted_bijection = bool(global_bijection and closure)
        if restricted_bijection:
            for component in unique_components:
                destinations = np.flatnonzero(image_components == component)
                if not np.array_equal(
                    np.sort(source[destinations]), destinations
                ):
                    restricted_bijection = False
                    break
        passed = global_bijection and closure and restricted_bijection
        all_maps_passed = all_maps_passed and passed
        by_map[name] = {
            "global_bijection": bool(global_bijection),
            "source_closure": closure,
            "restricted_bijection": restricted_bijection,
            "passed": passed,
        }

    return {
        "component_count": int(len(unique_components)),
        "clip_count": int(clip_count),
        "image_count": int(len(groups)),
        "clip_count_histogram": {
            str(size): int(count)
            for size, count in sorted(Counter(clip_sizes.tolist()).items())
        },
        "image_count_histogram": {
            str(size): int(count)
            for size, count in sorted(Counter(image_sizes.tolist()).items())
        },
        "maximum_clips_per_component": int(clip_sizes.max()),
        "maximum_images_per_component": int(image_sizes.max()),
        "minimum_clips_per_component": int(clip_sizes.min()),
        "minimum_images_per_component": int(image_sizes.min()),
        "maps": by_map,
        "all_maps_passed": bool(all_maps_passed),
    }
