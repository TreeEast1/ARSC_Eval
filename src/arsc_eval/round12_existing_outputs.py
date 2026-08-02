"""Pure Round 12 existing-outputs statistics core (Phase 1).

This module intentionally has NO file transaction, runner, or formal NPZ
reader/writer.  It accepts *already-loaded in-memory* raw arrays (the five
seeds' clip-level sufficient statistics plus the source-clip mapping) and the
saved bootstrap seed-position / clip-position draw rows, then recomputes every
per-cell ``A``/``R``/``S``/``C1`` metric from the raw inputs using the three
canonical helpers ``f1_from_counts``, ``harmonic_numbers`` and
``weighted_tie_averaged_aurc`` from :mod:`arsc_eval.corruption_statistics`.

It never accepts or reads ``curve_*``, ``endpoint_*``, ``family_axis_*`` or any
aggregate / derived outcome array (e.g. ``endpoint_effects``,
``family_axis_bottlenecks``, ``safety_diagnostics``, resolved F1 tables).  The
output is a pure ``dict`` of scalars/arrays plus the component bootstrap draw
arrays only; nothing is written anywhere.

Protocol facts frozen in
``outputs/validity/round12_existing_outputs_frozen_protocol.json``:

* 12 cells = 3 families x nonzero levels (1, 2, 3, 4); equal cell weighting.
* ``D_A``/``D_R``/``D_S``/``D_C1`` follow the frozen ``effect_definitions``.
* bootstrap: single shared seed-position and clip-position draw per replicate;
  metrics are recomputed from the expanded clip sample (never from aggregate
  cell means).  ``clip_position_draws`` must be exactly 2D ``(replicates,
  clip_count)`` and ``round12_statistics`` *requires* the caller-supplied
  ``expanded_image_counts`` (validated exactly against the clip draws), with an
  optional ``expected_replicates`` gate passed through to the bootstrap.
* exact ``families`` / ``levels`` / ``models`` metadata must be supplied and
  must equal the frozen values below, alongside the frozen ``seeds``.
* q = 0.0125 linear float64 lower bounds; PASS / PARTIAL / FAIL gates with the
  frozen (non-)strict comparison wording.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from arsc_eval.corruption_statistics import (
    f1_from_counts,
    harmonic_numbers,
    weighted_tie_averaged_aurc,
)

FAMILIES = ("brightness", "blur", "noise")
LEVELS = (0, 1, 2, 3, 4)
NONZERO_LEVELS = (1, 2, 3, 4)
MODELS = ("action_only", "joint")

# Frozen numeric policy (raw float64, no rounding in gates).
LOWER_QUANTILE = 0.0125
PRACTICAL_MARGIN = 0.01
C1_POINT_MINIMUM = 0.01
C1_LOWER_STRICT_POSITIVE = 0.0
C1_FAMILY_GUARDRAIL_FLOOR = -0.01
C1_MINIMUM_POSITIVE_SEEDS = 4
AR_S_NON_INFERIORITY_FLOOR = -0.01

SEED_COUNT = 5
FAMILY_COUNT = 3
LEVEL_COUNT = 5
MODEL_COUNT = 2

# The only raw inputs this core is allowed to consume.  Anything else is a
# forbidden aggregate / derived / outcome array.
REQUIRED_INPUT_KEYS = (
    "seeds",
    "families",
    "levels",
    "models",
    "A_tp",
    "A_fp",
    "A_fn",
    "R_tp",
    "R_fp",
    "R_fn",
    "C1_action_clip_sums",
    "errors",
    "group_ids",
    "group_counts",
    "clip_id_by_image",
    "clip_sizes",
    # Validation-only (never consumed by metric recomputation): the raw
    # confidence scores and clip-level hard predictions must match the frozen
    # protocol's shapes, dtypes, binary/finite/range policy, and exact clean
    # baseline (level-0) equality across the three family copies.
    "confidence",
    "action_predictions",
    "rationale_predictions",
)

# Frozen axis sizes / labels.
A_CLASS_COUNT = 4  # action classes, independent of the rationale vocabulary.
R_CLASS_COUNT = 21  # rationale classes, independent of the action vocabulary.
EXPECTED_SEEDS = (43, 44, 45, 46, 47)

D_AXES = ("D_A", "D_R", "D_S", "D_C1")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


# ---------------------------------------------------------------------------
# Input validation (metadata / order / shape / range / finite / binary /
# level-0 clean equality; forbidden aggregate rejection).
# ---------------------------------------------------------------------------


def validate_raw_input_keys(inputs: Mapping[str, Any]) -> None:
    """Reject missing raw inputs and any forbidden aggregate/derived key."""
    provided = set(inputs)
    required = set(REQUIRED_INPUT_KEYS)
    missing = required - provided
    if missing:
        raise ValueError(
            "missing required raw inputs: " + ", ".join(sorted(missing))
        )
    extra = provided - required
    if extra:
        raise ValueError(
            "forbidden aggregate/derived argument(s): "
            + ", ".join(sorted(extra))
        )


def _as_float_array(values: np.ndarray, name: str) -> np.ndarray:
    array = np.asarray(values)
    require(array.dtype.fields is None, f"{name} must be numeric")
    require(np.all(np.isfinite(array)), f"{name} is nonfinite")
    return array


def _check_level0_family_equality(name: str, array: np.ndarray) -> None:
    """A clean baseline counts exactly once: all families' level-0 (clean)
    copies of a raw input must be bit-for-bit identical per seed."""
    base = array[:, 0, 0]
    for family in range(1, FAMILY_COUNT):
        require(
            np.array_equal(array[:, family, 0], base),
            f"level-0 clean equality across families FAILED for {name} "
            f"(family {family}); ROUND12_INCONCLUSIVE_STOP",
        )


def validate_raw_inputs(inputs: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Raise unless every raw input is structurally sound.

    Also cross-checks ``clip_id_by_image`` against ``clip_sizes`` and enforces
    http exact, bit-for-bit level-0 (clean baseline) equality across the three
    family copies for *every* raw input that carries a family axis.
    """
    validate_raw_input_keys(inputs)

    seeds = np.asarray(inputs["seeds"])
    require(seeds.ndim == 1 and len(seeds) == SEED_COUNT, "seeds must have length 5")
    require(np.all(np.isfinite(seeds.astype(np.float64))), "seeds must be finite")
    require(
        tuple(int(s) for s in seeds) == EXPECTED_SEEDS,
        "seeds must be exactly 43,44,45,46,47",
    )

    families = np.asarray(inputs["families"])
    levels = np.asarray(inputs["levels"])
    models = np.asarray(inputs["models"])
    require(
        families.ndim == 1 and list(families.astype(str)) == list(FAMILIES),
        f"families metadata must be exactly {list(FAMILIES)}",
    )
    require(
        levels.ndim == 1 and [int(x) for x in levels] == list(LEVELS),
        f"levels metadata must be exactly {list(LEVELS)}",
    )
    require(
        models.ndim == 1 and list(models.astype(str)) == list(MODELS),
        f"models metadata must be exactly {list(MODELS)}",
    )

    A_tp = np.asarray(inputs["A_tp"])
    A_fp = np.asarray(inputs["A_fp"])
    A_fn = np.asarray(inputs["A_fn"])
    R_tp = np.asarray(inputs["R_tp"])
    R_fp = np.asarray(inputs["R_fp"])
    R_fn = np.asarray(inputs["R_fn"])
    C1 = np.asarray(inputs["C1_action_clip_sums"])
    errors = np.asarray(inputs["errors"])
    group_ids = np.asarray(inputs["group_ids"])
    group_counts = np.asarray(inputs["group_counts"])
    clip_id_by_image = np.asarray(inputs["clip_id_by_image"])
    clip_sizes = np.asarray(inputs["clip_sizes"])
    confidence = np.asarray(inputs["confidence"])
    action_predictions = np.asarray(inputs["action_predictions"])
    rationale_predictions = np.asarray(inputs["rationale_predictions"])

    require(
        A_tp.shape == A_fp.shape == A_fn.shape
        and A_tp.ndim == 6
        and A_tp.shape[:3] == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT)
        and A_tp.shape[3] == MODEL_COUNT,
        "A_tp/A_fp/A_fn must be (5,3,5,2,clip,K)",
    )
    require(
        A_tp.shape[5] == A_CLASS_COUNT,
        f"A action class count must be exactly {A_CLASS_COUNT}",
    )
    require(
        R_tp.shape == R_fp.shape == R_fn.shape
        and R_tp.ndim == 5
        and R_tp.shape[:3] == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT),
        "R_tp/R_fp/R_fn must be (5,3,5,clip,L)",
    )
    require(
        R_tp.shape[4] == R_CLASS_COUNT,
        f"R rationale class count must be exactly {R_CLASS_COUNT}",
    )
    require(
        C1.ndim == 5
        and C1.shape[:3] == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT)
        and C1.shape[3] == MODEL_COUNT
        and C1.shape[4] == A_tp.shape[4],
        "C1_action_clip_sums must be (5,3,5,2,clip)",
    )
    require(
        errors.shape == group_ids.shape
        and errors.ndim == 5
        and errors.shape[:3] == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT)
        and errors.shape[3] == MODEL_COUNT
        and errors.shape[4] == len(clip_id_by_image),
        "errors/group_ids must be (5,3,5,2,n) aligned with clip_id_by_image",
    )
    require(
        group_counts.shape == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT, MODEL_COUNT),
        "group_counts must be (5,3,5,2)",
    )
    require(
        clip_id_by_image.ndim == 1
        and len(clip_id_by_image) > 0,
        "clip_id_by_image must be a nonempty 1-D image->clip map",
    )
    require(
        clip_sizes.ndim == 1
        and A_tp.shape[4] == clip_sizes.shape[0]
        and np.all(clip_sizes > 0),
        "clip_sizes must be positive and aligned to the clip axis",
    )
    clip_count = int(clip_sizes.shape[0])

    # Assert the shared clip axis is consistent across all raw inputs.  The A
    # action and R rationale class vocabularies are validated independently
    # (4 vs 21) and are NOT required to be equal.
    require(
        R_tp.shape[3] == clip_count,
        "R_* clip axis must match clip_sizes length",
    )

    # Finite / integral-count / range checks on the clip-level sufficient stats.
    for name, arr in (
        ("A_tp", A_tp),
        ("A_fp", A_fp),
        ("A_fn", A_fn),
        ("R_tp", R_tp),
        ("R_fp", R_fp),
        ("R_fn", R_fn),
        ("C1_action_clip_sums", C1),
    ):
        values = _as_float_array(arr, name)
        require(np.all(values >= 0.0), f"{name} counts must be nonnegative")
        require(
            np.all(values == values.astype(np.int64)),
            f"{name} counts must be integral",
        )

    # Errors must be binary; confidence-group ids must be within bounds.
    require(
        np.all(np.isin(errors, (0, 1))),
        "errors must be binary (0/1)",
    )
    require(np.all(group_counts > 0), "group_counts must be positive")
    require(
        np.all((group_ids >= 0) & (group_ids < group_counts[..., None])),
        "group_ids must lie within group_counts",
    )

    # Validation-only raw arrays: confidence scores and hard predictions must be
    # structurally sound (formal-compatible shapes, finite/range for confidence,
    # binary for predictions).  They are never consumed downstream.
    require(
        confidence.ndim == 5
        and confidence.shape[:4]
        == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT, MODEL_COUNT)
        and confidence.shape[4] == len(clip_id_by_image),
        "confidence must be (5,3,5,2,n) aligned with clip_id_by_image",
    )
    require(np.all(np.isfinite(confidence)), "confidence is nonfinite")
    require(
        np.all((confidence >= 0.0) & (confidence <= 1.0)),
        "confidence must lie in [0,1]",
    )
    require(
        action_predictions.ndim == 6
        and action_predictions.shape[:4]
        == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT, MODEL_COUNT)
        and action_predictions.shape[4] == len(clip_id_by_image)
        and action_predictions.shape[5] == A_CLASS_COUNT,
        "action_predictions must be (5,3,5,2,n,4)",
    )
    require(
        np.all(np.isin(action_predictions, (0, 1))),
        "action_predictions must be binary (0/1)",
    )
    require(
        rationale_predictions.ndim == 5
        and rationale_predictions.shape[:3]
        == (SEED_COUNT, FAMILY_COUNT, LEVEL_COUNT)
        and rationale_predictions.shape[3] == len(clip_id_by_image)
        and rationale_predictions.shape[4] == R_CLASS_COUNT,
        "rationale_predictions must be (5,3,5,n,21)",
    )
    require(
        np.all(np.isin(rationale_predictions, (0, 1))),
        "rationale_predictions must be binary (0/1)",
    )

    # Source-clip mapping must match clip sizes exactly.
    require(
        np.all(clip_id_by_image >= 0) and np.all(clip_id_by_image < clip_count),
        "clip_id_by_image references a clip outside the clip axis",
    )
    observed_sizes = np.bincount(
        clip_id_by_image.astype(np.int64),
        minlength=clip_count,
    )
    require(
        np.array_equal(observed_sizes, clip_sizes),
        "clip_id_by_image image counts disagree with clip_sizes",
    )

    # Exact level-0 (clean) equality across family copies for every raw input
    # that has a family axis.
    for name, arr in (
        ("A_tp", A_tp),
        ("A_fp", A_fp),
        ("A_fn", A_fn),
        ("R_tp", R_tp),
        ("R_fp", R_fp),
        ("R_fn", R_fn),
        ("C1_action_clip_sums", C1),
        ("errors", errors),
        ("group_ids", group_ids),
        ("group_counts", group_counts),
        ("confidence", confidence),
        ("action_predictions", action_predictions),
        ("rationale_predictions", rationale_predictions),
    ):
        _check_level0_family_equality(name, arr)

    return {
        "seeds": seeds.astype(np.int64),
        "families": np.asarray(list(FAMILIES), dtype=object),
        "levels": np.asarray(list(LEVELS), dtype=np.int64),
        "models": np.asarray(list(MODELS), dtype=object),
        "A_tp": A_tp,
        "A_fp": A_fp,
        "A_fn": A_fn,
        "R_tp": R_tp,
        "R_fp": R_fp,
        "R_fn": R_fn,
        "C1_action_clip_sums": C1,
        "errors": errors,
        "group_ids": group_ids,
        "group_counts": group_counts,
        "clip_id_by_image": clip_id_by_image.astype(np.int64),
        "clip_sizes": clip_sizes.astype(np.int64),
        "confidence": confidence,
        "action_predictions": action_predictions,
        "rationale_predictions": rationale_predictions,
        "clip_count": clip_count,
    }


# ---------------------------------------------------------------------------
# Metric recomputation from raw clip-level sufficient statistics.
# ---------------------------------------------------------------------------


def recompute_seed_metrics(
    inputs: Mapping[str, np.ndarray],
    seed_index: int,
    clip_weights: np.ndarray,
    harmonic: np.ndarray,
) -> dict[str, np.ndarray]:
    """Recompute the four per-cell metrics for one seed using the canonical
    helpers on the *expanded* clip sample (never averaged cell means).

    Returns
    -------
    dict with ``A`` ``(3,2,5)`` macro-F1, ``R`` ``(3,1,5)`` macro-F1,
    ``S`` ``(3,2,5)`` tie-averaged AURC, and ``C1`` ``(3,2,5)`` action-flip
    rate.  The C1 ``model`` axis holds ``action_only`` (0) and ``joint`` (1).
    """
    weights = np.asarray(clip_weights, dtype=np.int64)
    require(weights.ndim == 1 and len(weights) == inputs["clip_count"], "bad clip weights")
    clip_sizes = inputs["clip_sizes"].astype(np.float64)
    sample_total = float(np.dot(weights.astype(np.float64), clip_sizes))
    require(sample_total > 0.0, "empty expanded image sample")

    A_tp = inputs["A_tp"][seed_index].astype(np.float64)
    A_fp = inputs["A_fp"][seed_index].astype(np.float64)
    A_fn = inputs["A_fn"][seed_index].astype(np.float64)
    R_tp = inputs["R_tp"][seed_index].astype(np.float64)
    R_fp = inputs["R_fp"][seed_index].astype(np.float64)
    R_fn = inputs["R_fn"][seed_index].astype(np.float64)
    C1 = inputs["C1_action_clip_sums"][seed_index].astype(np.float64)
    image_weights = weights[inputs["clip_id_by_image"]]

    A = np.empty((FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), dtype=np.float64)
    R = np.empty((FAMILY_COUNT, 1, LEVEL_COUNT), dtype=np.float64)
    S = np.empty((FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), dtype=np.float64)
    C1rate = np.empty((FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), dtype=np.float64)

    for family in range(FAMILY_COUNT):
        for level in range(LEVEL_COUNT):
            for model in range(MODEL_COUNT):
                a_tp = np.einsum("cm,c->m", A_tp[family, level, model], weights)
                a_fp = np.einsum("cm,c->m", A_fp[family, level, model], weights)
                a_fn = np.einsum("cm,c->m", A_fn[family, level, model], weights)
                A[family, model, level] = float(f1_from_counts(a_tp, a_fp, a_fn).mean())
                S[family, model, level] = weighted_tie_averaged_aurc(
                    inputs["errors"][seed_index, family, level, model],
                    inputs["group_ids"][seed_index, family, level, model],
                    int(
                        inputs["group_counts"][seed_index, family, level, model]
                    ),
                    image_weights,
                    harmonic,
                )
                C1rate[family, model, level] = (
                    float(np.dot(C1[family, level, model], weights)) / sample_total
                )
            r_tp = np.einsum("cl,c->l", R_tp[family, level], weights)
            r_fp = np.einsum("cl,c->l", R_fp[family, level], weights)
            r_fn = np.einsum("cl,c->l", R_fn[family, level], weights)
            R[family, 0, level] = float(f1_from_counts(r_tp, r_fp, r_fn).mean())

    return {"A": A, "R": R, "S": S, "C1": C1rate}


def seed_d_cells(curves: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Compute the exact 12-cell (family, nonzero-level) D arrays for a seed.

    The ``C1`` curve's model axis carries action_only (0) and joint (1).
    """
    A = np.asarray(curves["A"], dtype=np.float64)
    R = np.asarray(curves["R"], dtype=np.float64)
    S = np.asarray(curves["S"], dtype=np.float64)
    C1 = np.asarray(curves["C1"], dtype=np.float64)
    require(A.shape == (FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), "bad A curve")
    require(R.shape == (FAMILY_COUNT, 1, LEVEL_COUNT), "bad R curve")
    require(S.shape == (FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), "bad S curve")
    require(C1.shape == (FAMILY_COUNT, MODEL_COUNT, LEVEL_COUNT), "bad C1 curve")

    base_slice = slice(0, 1)
    da = (A[:, 1, 1:] - A[:, 1, base_slice]) - (A[:, 0, 1:] - A[:, 0, base_slice])
    dr = R[:, 0, 1:] - R[:, 0, base_slice]
    ds = (S[:, 0, 1:] - S[:, 0, base_slice]) - (S[:, 1, 1:] - S[:, 1, base_slice])
    dc1 = C1[:, 0, 1:] - C1[:, 1, 1:]
    return {"D_A": da, "D_R": dr, "D_S": ds, "D_C1": dc1}


def seed_d_scores(d_cells: Mapping[str, np.ndarray]) -> dict[str, float]:
    """Equal-weight mean over the 12 cells for one seed."""
    require(set(d_cells) == set(D_AXES), "D cells must contain four axes")
    return {axis: float(np.asarray(d_cells[axis]).mean()) for axis in D_AXES}


def _validate_draws(seed_draws: np.ndarray, clip_draws: np.ndarray, clip_count: int) -> int:
    seed_values = np.asarray(seed_draws)
    clip_values = np.asarray(clip_draws)
    require(
        seed_values.ndim == 2,
        "seed-position draws must be exactly 2D (replicates, 5)",
    )
    require(
        clip_values.ndim == 2,
        "clip-position draws must be exactly 2D (replicates, clip_count)",
    )
    require(
        seed_values.shape[0] == clip_values.shape[0],
        "seed/clip draws must align row-wise",
    )
    require(seed_values.shape[1] == SEED_COUNT, "seed draw must pick five seeds")
    require(
        clip_values.shape[1] == clip_count,
        "clip-position draws must be exactly 2D (replicates, clip_count)",
    )
    require(
        seed_values.shape[0] > 0,
        "seed/clip draw rows must be nonempty",
    )
    require(
        np.all((seed_values >= 0) & (seed_values < SEED_COUNT)),
        "seed-position draw out of bounds",
    )
    require(
        np.all((clip_values >= 0) & (clip_values < clip_count)),
        "clip-position draw references an out-of-range clip",
    )
    replicates = int(seed_values.shape[0])
    require(
        np.all(seed_values == seed_values.astype(np.int64)),
        "seed-position draws must be integral",
    )
    require(
        np.all(clip_values == clip_values.astype(np.int64)),
        "clip-position draws must be integral",
    )
    return replicates


# ---------------------------------------------------------------------------
# Point estimates, seed/family guardrails, bootstrap lower bounds, gates.
# ---------------------------------------------------------------------------


def point_statistics(
    inputs: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Point estimates of D_A/D_R/D_S/D_C1, per-seed and per-family D_C1."""
    clip_count = inputs["clip_count"]
    # Full-sample point estimate: every source clip selected exactly once.
    clip_weights = np.ones(clip_count, dtype=np.int64)
    maximum_expanded = clip_count * int(inputs["clip_sizes"].max())
    harmonic = harmonic_numbers(maximum_expanded)

    per_seed_scores: dict[str, np.ndarray] = {axis: np.empty(SEED_COUNT) for axis in D_AXES}
    d_c1_cells_stack = np.empty((SEED_COUNT, FAMILY_COUNT, len(NONZERO_LEVELS)))
    for seed_index in range(SEED_COUNT):
        curves = recompute_seed_metrics(inputs, seed_index, clip_weights, harmonic)
        cells = seed_d_cells(curves)
        scores = seed_d_scores(cells)
        for axis in D_AXES:
            per_seed_scores[axis][seed_index] = scores[axis]
        d_c1_cells_stack[seed_index] = cells["D_C1"]

    point = {axis: float(per_seed_scores[axis].mean()) for axis in D_AXES}
    per_seed_dc1 = per_seed_scores["D_C1"].copy()
    # Per-family D_C1 = mean over the four nonzero levels and the five seeds.
    per_family_dc1 = np.asarray(
        [float(d_c1_cells_stack[:, family, :].mean()) for family in range(FAMILY_COUNT)]
    )
    return {
        "point_estimates": point,
        "per_seed_D_C1": per_seed_dc1,
        "per_family_D_C1": per_family_dc1,
        "_d_c1_point_cells": d_c1_cells_stack,
    }


def _validate_expanded_image_counts(
    expanded_image_counts: np.ndarray | None,
    clip_draws: np.ndarray,
    clip_sizes: np.ndarray,
    replicates: int,
    expected_replicates: int | None,
) -> np.ndarray | None:
    """Validate optional ``expanded_image_counts`` against the clip draws.

    When provided it must (a) align row-for-row with the bootstrap
    ``clip_position_draws`` / ``seed_position_draws`` (length == replicates),
    (b) be integral, nonnegative and finite, and (c) exactly equal, for every
    replicate, the expanded image count
    ``dot(bincount(clip_draw[row]), clip_sizes)``.  An optional expected
    replicate count (formal run uses 5000) is enforced when supplied.
    """
    if expanded_image_counts is None:
        return None
    values = np.asarray(expanded_image_counts)
    require(
        values.ndim == 1 and len(values) == replicates,
        "expanded_image_counts must be a length-replicates 1-D array aligned "
        "row-wise with the seed/clip draws",
    )
    require(np.all(np.isfinite(values)), "expanded_image_counts is nonfinite")
    require(np.all(values >= 0), "expanded_image_counts must be nonnegative")
    require(
        np.all(values == values.astype(np.int64)),
        "expanded_image_counts must be integral",
    )
    clip_sizes_i64 = np.asarray(clip_sizes, dtype=np.int64)
    clip_count = len(clip_sizes_i64)
    for row in range(replicates):
        counts = np.bincount(
            clip_draws[row].astype(np.int64),
            minlength=clip_count,
        ).astype(np.int64)
        expected = int(
            np.dot(counts.astype(np.float64), clip_sizes_i64.astype(np.float64))
        )
        require(
            int(values[row]) == expected,
            "expanded_image_counts row mismatch with clip draws",
        )
    if expected_replicates is not None:
        require(
            replicates == expected_replicates,
            f"bootstrap replicate count must be exactly {expected_replicates}",
        )
    return values.astype(np.int64)


def bootstrap_lower_bounds(
    inputs: Mapping[str, np.ndarray],
    seed_position_draws: np.ndarray,
    clip_position_draws: np.ndarray,
    *,
    expanded_image_counts: np.ndarray | None = None,
    expected_replicates: int | None = None,
) -> dict[str, Any]:
    """Recompute D draws from the provided shared draws (expanded clips).

    ``expanded_image_counts`` (optional) is validated for exact row alignment,
    bounds/integrality and equality with the bincount-aggregated clip sizes.

    Returns the four ``D_*_draws`` component arrays plus their q=0.0125 linear
    float64 lower bounds.
    """
    clip_count = inputs["clip_count"]
    seed_draws = np.asarray(seed_position_draws)
    clip_draws = np.asarray(clip_position_draws)
    replicates = _validate_draws(seed_draws, clip_draws, clip_count)
    _validate_expanded_image_counts(
        expanded_image_counts,
        clip_draws,
        inputs["clip_sizes"],
        replicates,
        expected_replicates,
    )

    maximum_expanded = clip_count * int(inputs["clip_sizes"].max())
    harmonic = harmonic_numbers(maximum_expanded)

    draws: dict[str, np.ndarray] = {
        axis: np.empty(replicates, dtype=np.float64) for axis in D_AXES
    }

    for replicate in range(replicates):
        selected_seeds = seed_draws[replicate]
        counts = np.bincount(
            clip_draws[replicate].astype(np.int64),
            minlength=clip_count,
        ).astype(np.int64)
        expanded = int(np.dot(counts.astype(np.float64), inputs["clip_sizes"].astype(np.float64)))
        require(expanded > 0, "expanded bootstrap image sample is empty")
        require(np.isfinite(float(expanded)), "expanded bootstrap image count nonfinite")

        replicate_d: dict[str, float] = {axis: 0.0 for axis in D_AXES}
        for seed_index in selected_seeds.astype(np.int64):
            curves = recompute_seed_metrics(inputs, int(seed_index), counts, harmonic)
            cells = seed_d_cells(curves)
            scores = seed_d_scores(cells)
            for axis in D_AXES:
                replicate_d[axis] += scores[axis]
        for axis in D_AXES:
            draws[axis][replicate] = replicate_d[axis] / float(SEED_COUNT)

    require(
        all(np.all(np.isfinite(draws[axis])) for axis in D_AXES),
        "bootstrap produced nonfinite D draws",
    )
    lower_bounds = {
        axis: float(np.quantile(draws[axis], LOWER_QUANTILE, method="linear"))
        for axis in D_AXES
    }
    return {"bootstrap_draws": draws, "lower_bounds": lower_bounds}


def assess_gate(
    *,
    d_c1_point: float,
    d_c1_lower: float,
    per_seed_dc1: np.ndarray,
    per_family_dc1: np.ndarray,
    d_a_lower: float,
    d_r_lower: float,
    d_s_lower: float,
) -> dict[str, Any]:
    """Apply the frozen PASS / PARTIAL / FAIL gates with raw float64
    (non-)strict comparisons.  No rounding.

    Checks (frozen wording):
      * D_C1 grand point estimate >= 0.01 (non-strict)
      * D_C1 q=0.0125 lower bound > 0.0 (strict)
      * >= 4 of 5 seed-specific D_C1 values > 0.0 (strict)
      * each of 3 family-specific D_C1 values >= -0.01 (non-strict)
      * D_A / D_R / D_S q=0.0125 lower bounds > -0.01 (strict)
    """
    seed_values = np.asarray(per_seed_dc1, dtype=np.float64)
    family_values = np.asarray(per_family_dc1, dtype=np.float64)
    require(seed_values.shape == (SEED_COUNT,), "per-seed D_C1 must be length 5")
    require(family_values.shape == (FAMILY_COUNT,), "per-family D_C1 must be length 3")
    require(
        all(np.isfinite(x) for x in (d_c1_point, d_c1_lower, d_a_lower, d_r_lower, d_s_lower)),
        "gate scalar D_C1 / D_A / D_R / D_S values must be finite",
    )
    require(
        np.all(np.isfinite(seed_values)) and np.all(np.isfinite(family_values)),
        "per-seed and per-family D_C1 values must be finite",
    )

    checks = {
        "D_C1 point >= 0.01": bool(d_c1_point >= C1_POINT_MINIMUM),
        "D_C1 q=0.0125 lower bound > 0.0": bool(d_c1_lower > C1_LOWER_STRICT_POSITIVE),
        ">= 4 of 5 seed-specific D_C1 > 0.0": bool(
            int(np.sum(seed_values > C1_LOWER_STRICT_POSITIVE))
            >= C1_MINIMUM_POSITIVE_SEEDS
        ),
        "each family D_C1 >= -0.01": bool(
            np.all(family_values >= C1_FAMILY_GUARDRAIL_FLOOR)
        ),
        "D_A q=0.0125 lower bound > -0.01": bool(
            d_a_lower > AR_S_NON_INFERIORITY_FLOOR
        ),
        "D_R q=0.0125 lower bound > -0.01": bool(
            d_r_lower > AR_S_NON_INFERIORITY_FLOOR
        ),
        "D_S q=0.0125 lower bound > -0.01": bool(
            d_s_lower > AR_S_NON_INFERIORITY_FLOOR
        ),
    }
    c1_pass = all(checks[k] for k in (
        "D_C1 point >= 0.01",
        "D_C1 q=0.0125 lower bound > 0.0",
        ">= 4 of 5 seed-specific D_C1 > 0.0",
        "each family D_C1 >= -0.01",
    ))
    ars_pass = all(checks[k] for k in (
        "D_A q=0.0125 lower bound > -0.01",
        "D_R q=0.0125 lower bound > -0.01",
        "D_S q=0.0125 lower bound > -0.01",
    ))
    if c1_pass and ars_pass:
        verdict = "PASS"
    elif c1_pass:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    return {
        "verdict": verdict,
        "checks": checks,
        "c1_pass": c1_pass,
        "ars_pass": ars_pass,
    }


def round12_statistics(
    inputs: Mapping[str, Any],
    seed_position_draws: np.ndarray,
    clip_position_draws: np.ndarray,
    *,
    expanded_image_counts: np.ndarray,
    expected_replicates: int | None = None,
) -> dict[str, Any]:
    """Full Phase-1 pure Round 12 statistics core.

    ``expanded_image_counts`` is **required** and, when ``expected_replicates``
    is supplied, the bootstrap replicate count is enforced exactly.  Pure dict
    output only: point estimates, per-seed/per-family C1 guardrails, bootstrap
    lower bounds, component D draw arrays, and the gate verdict.  No file is
    read or written and no aggregate outcome array is accepted.
    """
    validated = validate_raw_inputs(inputs)

    point = point_statistics(validated)
    bootstrap = bootstrap_lower_bounds(
        validated,
        seed_position_draws,
        clip_position_draws,
        expanded_image_counts=expanded_image_counts,
        expected_replicates=expected_replicates,
    )
    lower_bounds = bootstrap["lower_bounds"]
    gate = assess_gate(
        d_c1_point=point["point_estimates"]["D_C1"],
        d_c1_lower=lower_bounds["D_C1"],
        per_seed_dc1=point["per_seed_D_C1"],
        per_family_dc1=point["per_family_D_C1"],
        d_a_lower=lower_bounds["D_A"],
        d_r_lower=lower_bounds["D_R"],
        d_s_lower=lower_bounds["D_S"],
    )
    return {
        "point_estimates": point["point_estimates"],
        "per_seed_D_C1": point["per_seed_D_C1"],
        "per_family_D_C1": point["per_family_D_C1"],
        "lower_bounds": lower_bounds,
        "gates": gate,
        "bootstrap_draws": bootstrap["bootstrap_draws"],
    }
