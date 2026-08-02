"""Compact Phase-1 Round 12 existing-outputs core tests.

These drive :mod:`arsc_eval.round12_existing_outputs` with **formal axes**
(5 seeds x 3 families x 5 levels x 2 models) but a **2-clip** synthetic input
so every computation stays small and hand-checkable.  Coverage:

* a hand-constructed valid D_C1 point estimate flowing through the full
  ``round12_statistics`` entry point;
* duplicate bootstrap draws, tie-averaged AURC, and zero-F1 handling;
* metadata / clean-baseline / clip-map / draw-shape / expanded-image-count
  validation failures;
* rejection of forbidden aggregate / derived (curve) keys;
* optional ``expected_replicates`` enforcement;
* gate verdict equality for PASS / PARTIAL / FAIL.
"""

from __future__ import annotations

import numpy as np
import pytest

from arsc_eval.corruption_statistics import (
    f1_from_counts,
    harmonic_numbers,
    weighted_tie_averaged_aurc,
)
from arsc_eval.round12_existing_outputs import (
    FAMILIES,
    LEVELS,
    MODELS,
    assess_gate,
    bootstrap_lower_bounds,
    point_statistics,
    round12_statistics,
    validate_raw_inputs,
)

SEEDS = (43, 44, 45, 46, 47)
N_SEED, N_FAMILY, N_LEVEL, N_MODEL = 5, 3, 5, 2
CLIP_SIZES = np.asarray([2, 1], dtype=np.int64)
N_IMAGES = int(CLIP_SIZES.sum())  # 3
CLIP_ID_BY_IMAGE = np.asarray([0, 0, 1], dtype=np.int64)


def tile_level0(arr: np.ndarray) -> np.ndarray:
    """Force exact level-0 (clean) bit-for-bit equality across the three
    family copies by broadcasting family 0's clean slice onto the others."""
    base = arr[:, 0:1, 0, ...]
    arr[:, :, 0, ...] = base
    return arr


def make_inputs(
    *,
    d_c1: float = 0.0,
    clip_sizes: np.ndarray = CLIP_SIZES,
    clip_sizes_override: np.ndarray | None = None,
    clip_id_by_image: np.ndarray = CLIP_ID_BY_IMAGE,
    families: tuple = FAMILIES,
    levels: tuple = LEVELS,
    models: tuple = MODELS,
) -> dict[str, np.ndarray]:
    """Build a structurally valid formal-axis, 2-clip raw-input bundle.

    When ``d_c1`` is nonzero, the nonzero-level C1 action sums are scaled so
    the grand D_C1 point estimate equals ``d_c1`` (see "valid hand D_C1" test).
    """
    sizes = clip_sizes if clip_sizes_override is None else clip_sizes_override
    clip = int(len(sizes))
    n = int(len(clip_id_by_image))

    def _arr(*shape: int, dtype=np.int64) -> np.ndarray:
        return np.zeros(shape, dtype=dtype)

    A = np.zeros((N_SEED, N_FAMILY, N_LEVEL, N_MODEL, clip, 4), dtype=np.int64)
    R = np.zeros((N_SEED, N_FAMILY, N_LEVEL, clip, 21), dtype=np.int64)
    C1 = np.zeros((N_SEED, N_FAMILY, N_LEVEL, N_MODEL, clip), dtype=np.int64)
    errors = np.zeros((N_SEED, N_FAMILY, N_LEVEL, N_MODEL, n), dtype=np.int64)
    group_ids = np.zeros_like(errors)
    confidence = np.zeros((N_SEED, N_FAMILY, N_LEVEL, N_MODEL, n), dtype=np.float64)
    action_pred = np.zeros((N_SEED, N_FAMILY, N_LEVEL, N_MODEL, n, 4), dtype=np.int64)
    rationale_pred = np.zeros((N_SEED, N_FAMILY, N_LEVEL, n, 21), dtype=np.int64)

    if d_c1:
        # action_only (model 0) clip sums [2,1] -> C1 rate 1.0 with weight-ones,
        # joint (model 1) sums 0 -> rate 0, so D_C1 cell = 1.0 for every
        # nonzero level and family.  Level-0 stays zero (clean baseline equal).
        C1[:, :, 1:, 0, :] = np.asarray(
            [[2, 1]], dtype=np.int64
        )

    inputs: dict[str, np.ndarray] = {
        "seeds": np.asarray(SEEDS, dtype=np.int64),
        "families": np.asarray(list(families), dtype=object),
        "levels": np.asarray(list(levels), dtype=np.int64),
        "models": np.asarray(list(models), dtype=object),
        "A_tp": tile_level0(A),
        "A_fp": tile_level0(A.copy()),
        "A_fn": tile_level0(A.copy()),
        "R_tp": tile_level0(R),
        "R_fp": tile_level0(R.copy()),
        "R_fn": tile_level0(R.copy()),
        "C1_action_clip_sums": tile_level0(C1),
        "errors": tile_level0(errors),
        "group_ids": tile_level0(group_ids),
        "group_counts": tile_level0(np.ones((N_SEED, N_FAMILY, N_LEVEL, N_MODEL), dtype=np.int64)),
        "confidence": tile_level0(confidence),
        "action_predictions": tile_level0(action_pred),
        "rationale_predictions": tile_level0(rationale_pred),
        "clip_id_by_image": clip_id_by_image.astype(np.int64),
        "clip_sizes": sizes.astype(np.int64),
    }
    return inputs


def sample_draws(
    *,
    replicates: int = 1,
    clip_draw: np.ndarray | None = None,
    seed_draw: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Default single-replicate draws selecting every clip once."""
    if clip_draw is None:
        clip_draw = np.zeros((replicates, len(CLIP_SIZES)), dtype=np.int64)
        for i in range(replicates):
            clip_draw[i] = np.arange(len(CLIP_SIZES))
    if seed_draw is None:
        seed_draw = np.zeros((replicates, N_SEED), dtype=np.int64)
    counts = np.array(
        [
            int(
                np.dot(
                    np.bincount(row.astype(np.int64), minlength=len(CLIP_SIZES)),
                    CLIP_SIZES,
                )
            )
            for row in clip_draw
        ],
        dtype=np.int64,
    )
    return seed_draw, clip_draw, counts


# ---------------------------------------------------------------------------
# Valid hand D_C1 through the full entry point
# ---------------------------------------------------------------------------


def test_valid_hand_d_c1_and_point_statistics() -> None:
    inputs = make_inputs(d_c1=1.0)
    validated = validate_raw_inputs(inputs)

    point = point_statistics(validated)
    # action C1 rate 1.0, joint 0.0 across all 12 nonzero cells -> D_C1 = 1.0.
    assert point["point_estimates"]["D_C1"] == pytest.approx(1.0, abs=1e-9)
    assert point["point_estimates"]["D_A"] == pytest.approx(0.0, abs=1e-9)
    assert point["point_estimates"]["D_R"] == pytest.approx(0.0, abs=1e-9)
    assert point["point_estimates"]["D_S"] == pytest.approx(0.0, abs=1e-9)
    assert np.all(np.asarray(point["per_seed_D_C1"]) == pytest.approx(1.0))
    assert np.all(np.asarray(point["per_family_D_C1"]) == pytest.approx(1.0))


def test_round12_statistics_full_entry_point_is_pass() -> None:
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    result = round12_statistics(
        inputs,
        seed_draw,
        clip_draw,
        expanded_image_counts=expanded,
    )
    assert result["point_estimates"]["D_C1"] == pytest.approx(1.0, abs=1e-9)
    assert result["lower_bounds"]["D_C1"] == pytest.approx(1.0, abs=1e-9)
    assert result["gates"]["verdict"] == "PASS"
    assert {"D_A", "D_R", "D_S", "D_C1"} == set(result["bootstrap_draws"])


# ---------------------------------------------------------------------------
# Duplicate draws / tie AURC / zero F1
# ---------------------------------------------------------------------------


def test_duplicate_bootstrap_draws_give_identical_replicate_rows() -> None:
    inputs = make_inputs(d_c1=1.0)
    # Two identical replicates both select every clip once and the same seed 0.
    seed_draw = np.zeros((2, N_SEED), dtype=np.int64)
    clip_draw = np.tile(np.arange(len(CLIP_SIZES)), (2, 1))
    expanded = np.array([3, 3], dtype=np.int64)

    validated = validate_raw_inputs(inputs)
    boot = bootstrap_lower_bounds(
        validated, seed_draw, clip_draw, expanded_image_counts=expanded
    )
    draws = boot["bootstrap_draws"]
    for axis in ("D_A", "D_R", "D_S", "D_C1"):
        assert draws[axis][0] == pytest.approx(draws[axis][1], abs=1e-12)


def test_tie_averaged_aurc_hand_value() -> None:
    # Three images with a 2-way tied confidence group: all share the same group
    # id (a full tie), errors [0,0,1].  Tie-averaged AURC equals the ordinary
    # micro-AUC over the single tied group: exactly 1/3.
    harmonic = harmonic_numbers(3)
    value = weighted_tie_averaged_aurc(
        np.asarray([0, 0, 1], dtype=np.int64),
        np.asarray([0, 0, 0], dtype=np.int64),
        1,
        np.ones(3, dtype=np.int64),
        harmonic,
    )
    assert value == pytest.approx(1.0 / 3.0, abs=1e-12)
    assert np.isfinite(value)


def test_zero_f1_returns_zero_without_division_error() -> None:
    result = f1_from_counts(
        np.array([0], dtype=np.float64),
        np.array([0], dtype=np.float64),
        np.array([0], dtype=np.float64),
    )
    assert np.all(result == 0.0)
    assert np.all(np.isfinite(result))

    # Full data with all-zero A/R counts yields finite D_A / D_R / D_S.
    inputs = make_inputs(d_c1=0.0)
    validated = validate_raw_inputs(inputs)
    point = point_statistics(validated)
    for axis in ("D_A", "D_R", "D_S"):
        assert np.isfinite(point["point_estimates"][axis])


# ---------------------------------------------------------------------------
# Metadata / clean / map / draw / expanded validation failures
# ---------------------------------------------------------------------------


def test_wrong_metadata_families_rejected() -> None:
    inputs = make_inputs()
    inputs["families"] = np.asarray(["brightness", "blur", "xxxx"], dtype=object)
    with pytest.raises(ValueError, match="families metadata"):
        validate_raw_inputs(inputs)


def test_wrong_metadata_levels_rejected() -> None:
    inputs = make_inputs()
    inputs["levels"] = np.asarray([0, 1, 2, 3, 99], dtype=np.int64)
    with pytest.raises(ValueError, match="levels metadata"):
        validate_raw_inputs(inputs)


def test_wrong_metadata_models_rejected() -> None:
    inputs = make_inputs()
    inputs["models"] = np.asarray(["action_only", "joint_oops"], dtype=object)
    with pytest.raises(ValueError, match="models metadata"):
        validate_raw_inputs(inputs)


def test_clean_baseline_violation_rejected() -> None:
    inputs = make_inputs()
    # Break level-0 equality across families on the C1 action sums.
    inputs["C1_action_clip_sums"][0, 1, 0, 0, 0] = 5
    with pytest.raises(ValueError, match="level-0 clean equality"):
        validate_raw_inputs(inputs)


@pytest.mark.parametrize(
    "key,index",
    [
        ("confidence", (0, 1, 0, 0, 0)),
        ("action_predictions", (0, 1, 0, 0, 0, 0)),
        ("rationale_predictions", (0, 1, 0, 0, 0)),
        ("A_tp", (0, 1, 0, 0, 0, 0)),
    ],
)
def test_level0_family_mismatch_rejected(key: str, index: tuple) -> None:
    # Breaking level-0 (clean) equality across family copies of any raw input
    # with a family axis must raise, not pass.
    inputs = make_inputs()
    inputs[key][index] = 1
    with pytest.raises(ValueError, match="level-0 clean equality"):
        validate_raw_inputs(inputs)


def test_clip_map_disagrees_with_clip_sizes_rejected() -> None:
    inputs = make_inputs()
    inputs["clip_id_by_image"] = np.asarray([0, 0, 0], dtype=np.int64)  # 3 -> clip 0
    with pytest.raises(ValueError, match="clip_id_by_image"):
        validate_raw_inputs(inputs)


def test_draw_shape_must_be_exact_2d_replicates_clip_count() -> None:
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    # clip_draws with the wrong column count (1 instead of clip_count=2).
    bad_clip_draw = np.zeros((1, 1), dtype=np.int64)
    with pytest.raises(ValueError, match="exactly 2D"):
        bootstrap_lower_bounds(
            validate_raw_inputs(inputs),
            seed_draw,
            bad_clip_draw,
            expanded_image_counts=expanded,
        )


def test_1d_draws_rejected_before_shape_indexing() -> None:
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    # A 1-D seed-position draw must be rejected with the 2D shape message
    # (never an IndexError from shape[1]).
    for bad_seed in (
        np.zeros(1, dtype=np.int64),
        np.zeros((1, 1, 1), dtype=np.int64),
    ):
        with pytest.raises(ValueError, match="exactly 2D"):
            bootstrap_lower_bounds(
                validate_raw_inputs(inputs),
                bad_seed,
                clip_draw,
                expanded_image_counts=expanded,
            )
    # A 1-D clip-position draw must likewise be rejected up front.
    for bad_clip in (
        np.zeros(1, dtype=np.int64),
        np.zeros((1, 1, 1), dtype=np.int64),
    ):
        with pytest.raises(ValueError, match="exactly 2D"):
            bootstrap_lower_bounds(
                validate_raw_inputs(inputs),
                seed_draw,
                bad_clip,
                expanded_image_counts=expanded,
            )


def test_seed_draw_with_seed_index_5_rejected() -> None:
    # SEED_COUNT = 5, so a valid seed position is 0..4; index 5 is out of range.
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    bad_seed = np.asarray([[5] * N_SEED], dtype=np.int64)
    with pytest.raises(ValueError, match="out of bounds"):
        bootstrap_lower_bounds(
            validate_raw_inputs(inputs),
            bad_seed,
            clip_draw,
            expanded_image_counts=expanded,
        )


def test_clip_draw_with_clip_index_equal_to_clip_count_rejected() -> None:
    # Valid clip positions are 0..clip_count-1; clip_count itself is out of
    # range (here clip_count = 2).
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    bad_clip = np.asarray([[0, len(CLIP_SIZES)]], dtype=np.int64)
    with pytest.raises(ValueError, match="out-of-range clip"):
        bootstrap_lower_bounds(
            validate_raw_inputs(inputs),
            seed_draw,
            bad_clip,
            expanded_image_counts=expanded,
        )


def test_expanded_image_count_mismatch_rejected() -> None:
    inputs = make_inputs(d_c1=1.0)
    seed_draw, clip_draw, expanded = sample_draws()
    bad_expanded = expanded.copy()
    bad_expanded[0] += 1
    with pytest.raises(ValueError, match="expanded_image_counts row mismatch"):
        bootstrap_lower_bounds(
            validate_raw_inputs(inputs),
            seed_draw,
            clip_draw,
            expanded_image_counts=bad_expanded,
        )


# ---------------------------------------------------------------------------
# Rejection of forbidden aggregate / derived (curve) keys
# ---------------------------------------------------------------------------


def test_curve_extra_keys_rejected() -> None:
    inputs = make_inputs()
    inputs["curve_A"] = np.zeros((N_SEED, N_FAMILY, N_MODEL, N_LEVEL))
    with pytest.raises(ValueError, match="forbidden aggregate"):
        validate_raw_inputs(inputs)


def test_round12_statistics_rejects_aggregate_keys() -> None:
    inputs = make_inputs(d_c1=1.0)
    inputs["endpoint_effects"] = np.zeros(3)
    seed_draw, clip_draw, expanded = sample_draws()
    with pytest.raises(ValueError, match="forbidden aggregate"):
        round12_statistics(
            inputs,
            seed_draw,
            clip_draw,
            expanded_image_counts=expanded,
        )


# ---------------------------------------------------------------------------
# Replicate enforcement
# ---------------------------------------------------------------------------


def test_expected_replicates_enforced() -> None:
    inputs = make_inputs(d_c1=1.0)
    # Two replicates.
    seed_draw = np.zeros((2, N_SEED), dtype=np.int64)
    clip_draw = np.tile(np.arange(len(CLIP_SIZES)), (2, 1))
    expanded = np.array([3, 3], dtype=np.int64)

    with pytest.raises(ValueError, match="must be exactly 5000"):
        round12_statistics(
            inputs,
            seed_draw,
            clip_draw,
            expanded_image_counts=expanded,
            expected_replicates=5000,
        )

    # Correct expected replicate count is accepted.
    result = round12_statistics(
        inputs,
        seed_draw,
        clip_draw,
        expanded_image_counts=expanded,
        expected_replicates=2,
    )
    assert result["gates"]["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# Gate verdict equality: PASS / PARTIAL / FAIL
# ---------------------------------------------------------------------------


def _gate_kwargs(**overrides: float) -> dict[str, float]:
    base: dict[str, float] = {
        "d_c1_point": 0.05,
        "d_c1_lower": 0.01,
        "per_seed_dc1": np.asarray([0.02, 0.03, 0.01, 0.04, 0.02]),
        "per_family_dc1": np.asarray([0.01, 0.02, 0.03]),
        "d_a_lower": 0.001,
        "d_r_lower": 0.001,
        "d_s_lower": 0.001,
    }
    for key, value in overrides.items():
        base[key] = value
    return base


def test_gate_pass() -> None:
    result = assess_gate(**_gate_kwargs())
    assert result["verdict"] == "PASS"
    assert result["c1_pass"] is True
    assert result["ars_pass"] is True


def test_gate_partial_when_ars_fail() -> None:
    result = assess_gate(**_gate_kwargs(d_a_lower=-0.02))
    assert result["verdict"] == "PARTIAL"
    assert result["c1_pass"] is True
    assert result["ars_pass"] is False


def test_gate_fail_when_c1_fails() -> None:
    result = assess_gate(**_gate_kwargs(d_c1_point=0.0))
    assert result["verdict"] == "FAIL"
    assert result["c1_pass"] is False


def test_gate_fail_when_seed_count_below_threshold() -> None:
    per_seed = np.asarray([0.01, 0.0, 0.0, 0.0, 0.0])  # only 1 of 5 > 0
    result = assess_gate(**_gate_kwargs(per_seed_dc1=per_seed))
    assert result["verdict"] == "FAIL"
    assert result["c1_pass"] is False


def test_gate_thresholds_point_minimum_pass() -> None:
    # D_C1 grand point estimate == 0.01 satisfies the non-strict >= 0.01 gate.
    result = assess_gate(**_gate_kwargs(d_c1_point=0.01))
    assert result["verdict"] == "PASS"
    assert result["checks"]["D_C1 point >= 0.01"] is True


def test_gate_thresholds_lower_zero_fails_strict() -> None:
    # D_C1 q=0.0125 lower bound == 0.0 fails the strict > 0.0 gate.
    result = assess_gate(**_gate_kwargs(d_c1_lower=0.0))
    assert result["verdict"] == "FAIL"
    assert result["checks"]["D_C1 q=0.0125 lower bound > 0.0"] is False
    assert result["c1_pass"] is False


def test_gate_thresholds_family_floor_inclusive_pass() -> None:
    # Each family D_C1 == -0.01 still satisfies the non-strict >= -0.01 gate.
    per_family = np.asarray([-0.01, -0.01, -0.01])
    result = assess_gate(**_gate_kwargs(per_family_dc1=per_family))
    assert result["verdict"] == "PASS"
    assert result["checks"]["each family D_C1 >= -0.01"] is True


def test_gate_thresholds_ars_floor_strict_fails() -> None:
    # Each D_A / D_R / D_S lower bound == -0.01 fails the strict > -0.01 gate.
    result = assess_gate(
        **_gate_kwargs(d_a_lower=-0.01, d_r_lower=-0.01, d_s_lower=-0.01)
    )
    assert result["ars_pass"] is False
    assert result["verdict"] == "PARTIAL"
    assert result["checks"]["D_A q=0.0125 lower bound > -0.01"] is False
    assert result["checks"]["D_R q=0.0125 lower bound > -0.01"] is False
    assert result["checks"]["D_S q=0.0125 lower bound > -0.01"] is False


def test_gate_thresholds_four_positive_seeds_pass() -> None:
    # Exactly 4 of 5 seeds > 0 satisfies the >= 4 gate.
    per_seed = np.asarray([0.01, 0.0, 0.01, 0.01, 0.01])
    result = assess_gate(**_gate_kwargs(per_seed_dc1=per_seed))
    assert result["verdict"] == "PASS"
    assert result["checks"][">= 4 of 5 seed-specific D_C1 > 0.0"] is True
    assert result["c1_pass"] is True


def test_gate_thresholds_three_positive_seeds_fail() -> None:
    # Exactly 3 of 5 seeds > 0 fails the >= 4 gate.
    per_seed = np.asarray([0.01, 0.0, 0.01, 0.0, 0.01])
    result = assess_gate(**_gate_kwargs(per_seed_dc1=per_seed))
    assert result["verdict"] == "FAIL"
    assert result["checks"][">= 4 of 5 seed-specific D_C1 > 0.0"] is False
    assert result["c1_pass"] is False


# ---------------------------------------------------------------------------
# Metadata labels match the frozen protocol
# ---------------------------------------------------------------------------


def test_metadata_constants_match_frozen_protocol() -> None:
    assert FAMILIES == ("brightness", "blur", "noise")
    assert LEVELS == (0, 1, 2, 3, 4)
    assert MODELS == ("action_only", "joint")
    assert list(SEEDS) == [43, 44, 45, 46, 47]
