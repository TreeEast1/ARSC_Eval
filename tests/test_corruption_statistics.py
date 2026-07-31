from __future__ import annotations

import copy

import numpy as np
import pytest

from arsc_eval.corruption_statistics import (
    AXIS_DIRECTIONS,
    ENDPOINT_COMPONENTS,
    PRACTICAL_THRESHOLDS,
    all_family_curves_from_clip_counts,
    bottleneck,
    endpoint_effects,
    family_axis_bottlenecks,
    f1_from_counts,
    harmonic_numbers,
    mean_curve_no_reversal,
    practical_endpoint_pass,
    prepare_seed_clip_statistics,
    quantile_diagnostic,
    run_shared_bootstrap,
    source_clip_membership,
    weighted_tie_averaged_aurc,
    confidence_group_ids,
)
from arsc_eval.graded_response import tie_averaged_aurc


def synthetic_prepared(offset: float = 0.0) -> dict:
    action_targets = np.asarray(
        [
            [1, 0, 0, 0],
            [1, 0, 1, 0],
            [0, 1, 0, 0],
            [1, 0, 0, 1],
            [0, 1, 0, 0],
            [1, 0, 1, 0],
        ],
        dtype=np.float32,
    )
    rationale_targets = np.zeros((6, 21), dtype=np.float32)
    rationale_targets[:, 0] = action_targets[:, 0]
    rationale_targets[:, 1] = action_targets[:, 1]
    base_action = np.where(action_targets > 0.5, 2.0, -2.0) + offset
    base_rationale = np.where(
        rationale_targets > 0.5,
        2.0,
        -2.0,
    ) + offset
    action_only = np.empty((3, 5, 6, 4), dtype=np.float32)
    joint_action = np.empty_like(action_only)
    joint_rationale = np.empty((3, 5, 6, 21), dtype=np.float32)
    for family in range(3):
        for level in range(5):
            action_only[family, level] = base_action
            joint_action[family, level] = base_action
            joint_rationale[family, level] = base_rationale
    clip_ids, _, _ = source_clip_membership(
        (
            "a_1.jpg",
            "a_3.jpg",
            "b.jpg",
            "c_1.jpg",
            "c_3.jpg",
            "d.jpg",
        )
    )
    return prepare_seed_clip_statistics(
        action_targets,
        rationale_targets,
        action_only,
        joint_action,
        joint_rationale,
        1.25,
        0.75,
        clip_ids,
        4,
    )


def test_source_clip_membership_preserves_first_occurrence() -> None:
    ids, keys, sizes = source_clip_membership(
        ("z_3.jpg", "a.jpg", "z_1.jpg", "b_1.jpg", "b_3.jpg")
    )
    assert keys == ("z", "a", "b")
    assert ids.tolist() == [0, 1, 0, 2, 2]
    assert sizes.tolist() == [2, 1, 2]


def test_f1_zero_denominator_and_exact_counts() -> None:
    observed = f1_from_counts(
        np.asarray([0, 2]),
        np.asarray([0, 1]),
        np.asarray([0, 1]),
    )
    assert observed[0] == 0.0
    assert observed[1] == pytest.approx(4.0 / 6.0)
    with pytest.raises(ValueError, match="finite"):
        f1_from_counts(
            np.asarray([np.nan]),
            np.asarray([0.0]),
            np.asarray([0.0]),
        )


def test_weighted_tie_aurc_matches_explicit_duplicate_expansion() -> None:
    errors = np.asarray([0, 1, 1, 0], dtype=np.uint8)
    confidence = np.asarray([0.9, 0.9, 0.4, 0.1])
    weights = np.asarray([2, 3, 1, 0], dtype=np.int64)
    groups, count = confidence_group_ids(confidence)
    observed = weighted_tie_averaged_aurc(
        errors,
        groups,
        count,
        weights,
        harmonic_numbers(int(weights.sum())),
    )
    expanded_errors = np.repeat(errors, weights)
    expanded_confidence = np.repeat(confidence, weights)
    expected = tie_averaged_aurc(
        expanded_errors,
        expanded_confidence,
    )
    assert observed == pytest.approx(expected, abs=1e-15)


def test_prepared_identity_and_weighted_curves() -> None:
    prepared = synthetic_prepared()
    assert np.all(prepared["C1_action_clip_sums"][:, 0] == 0)
    counts = np.asarray([2, 0, 1, 3], dtype=np.int64)
    curves = all_family_curves_from_clip_counts(
        prepared,
        counts,
        harmonic_numbers(12),
    )
    assert curves["A"].shape == (3, 2, 5)
    assert curves["R"].shape == (3, 1, 5)
    assert curves["S"].shape == (3, 2, 5)
    assert curves["C1"].shape == (3, 3, 5)
    assert np.all(curves["A"] == 1.0)
    assert np.all(curves["R"][:, :, :] == pytest.approx(2.0 / 21.0))
    assert np.all(curves["C1"][:, 0:2] == 0.0)
    assert np.all(curves["C1"][:, 2] == 1.0)
    assert np.all(family_axis_bottlenecks(curves) == 0.0)
    assert np.all(endpoint_effects(curves) == 0.0)


def test_bottleneck_endpoint_and_practical_equality_rules() -> None:
    curves = {
        "A": np.tile(
            np.asarray([[0.9, 0.8, 0.7, 0.6, 0.5]])[None, :, :],
            (3, 2, 1),
        ),
        "R": np.tile(
            np.asarray([[0.7, 0.6, 0.5, 0.4, 0.3]])[None, :, :],
            (3, 1, 1),
        ),
        "S": np.tile(
            np.asarray([[0.1, 0.2, 0.3, 0.4, 0.5]])[None, :, :],
            (3, 2, 1),
        ),
        "C1": np.tile(
            np.asarray(
                [
                    [0.0, 0.1, 0.2, 0.3, 0.4],
                    [0.0, 0.1, 0.2, 0.3, 0.4],
                    [1.0, 0.9, 0.8, 0.7, 0.6],
                ]
            )[None, :, :],
            (3, 1, 1),
        ),
    }
    observed = family_axis_bottlenecks(curves)
    assert np.all(observed > 0.0)
    effects = endpoint_effects(curves)
    assert effects.shape == (3, len(ENDPOINT_COMPONENTS))
    equality = np.asarray(
        [
            [PRACTICAL_THRESHOLDS[name] for name in ENDPOINT_COMPONENTS]
        ]
        * 3,
        dtype=np.float64,
    )
    assert practical_endpoint_pass(equality).all()
    equality[0, 0] = np.nextafter(equality[0, 0], -np.inf)
    assert not practical_endpoint_pass(equality)[0, 0]
    assert bottleneck(curves["C1"][0], AXIS_DIRECTIONS["C1"]) > 0


def test_mean_curve_ties_pass_and_reversal_fails() -> None:
    seeds = np.ones((5, 2, 5), dtype=np.float64)
    assert mean_curve_no_reversal(seeds, ("decreasing", "decreasing"))
    reversed_values = seeds.copy()
    reversed_values[:, 0, 4] = 2.0
    assert not mean_curve_no_reversal(
        reversed_values,
        ("decreasing", "decreasing"),
    )


def test_quantile_is_linear_hash_bound_and_rejects_nonfinite() -> None:
    values = np.asarray([0.0, 10.0, 20.0, 30.0])
    observed = quantile_diagnostic(values, 0.25)
    assert observed["numpy_method"] == "linear"
    assert observed["unrounded_result"] == 7.5
    assert len(observed["input_array_sha256"]) == 64
    with pytest.raises(ValueError, match="finite"):
        quantile_diagnostic(np.asarray([0.0, np.nan]), 0.5)


def test_shared_bootstrap_is_deterministic_and_freezes_rng_call_order() -> None:
    prepared = synthetic_prepared()
    seeds = [copy.deepcopy(prepared) for _ in range(5)]
    first = run_shared_bootstrap(seeds, replicates=3, seed=20260810)
    second = run_shared_bootstrap(seeds, replicates=3, seed=20260810)
    for key in first:
        assert np.array_equal(first[key], second[key])
    assert first["family_axis_gate_draws"].shape == (3, 12)
    assert first["endpoint_draws"].shape == (3, 24)
    assert first["seed_position_draws"].shape == (3, 5)
    assert first["clip_position_draws"].shape == (3, 4)
    rng = np.random.default_rng(20260810)
    expected_seeds = rng.integers(0, 5, size=5)
    expected_clips = rng.integers(0, 4, size=4)
    assert np.array_equal(first["seed_position_draws"][0], expected_seeds)
    assert np.array_equal(first["clip_position_draws"][0], expected_clips)
