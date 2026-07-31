"""Pure NumPy statistics for the preregistered Round 10 formal study."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np


FAMILIES = ("brightness", "blur", "noise")
LEVELS = (0, 1, 2, 3, 4)
MODELS = ("action_only", "joint")
AXES = ("A", "R", "S", "C1")
ACTION_COMPONENTS = ("action_only", "joint")
RATIONALE_COMPONENTS = ("joint_rationale",)
SAFETY_COMPONENTS = ("action_only", "joint")
CONSISTENCY_COMPONENTS = (
    "action_only_flip",
    "joint_flip",
    "joint_rationale_jaccard",
)
AXIS_COMPONENTS = {
    "A": ACTION_COMPONENTS,
    "R": RATIONALE_COMPONENTS,
    "S": SAFETY_COMPONENTS,
    "C1": CONSISTENCY_COMPONENTS,
}
AXIS_DIRECTIONS = {
    "A": ("decreasing", "decreasing"),
    "R": ("decreasing",),
    "S": ("increasing", "increasing"),
    "C1": ("increasing", "increasing", "decreasing"),
}
ENDPOINT_COMPONENTS = (
    "A::action_only",
    "A::joint",
    "R::joint_rationale",
    "S::action_only",
    "S::joint",
    "C1::action_only_flip",
    "C1::joint_flip",
    "C1::joint_rationale_jaccard",
)
PRACTICAL_THRESHOLDS = {
    "A::action_only": 0.01,
    "A::joint": 0.01,
    "R::joint_rationale": 0.01,
    "S::action_only": 0.01,
    "S::joint": 0.01,
    "C1::action_only_flip": 0.025,
    "C1::joint_flip": 0.025,
    "C1::joint_rationale_jaccard": 0.025,
}
SAFETY_DIAGNOSTICS = (
    "tie_averaged_aurc",
    "canonical_stable_aurc",
    "unsafe_acceptance_rate_90",
    "correctness_auroc",
    "ece",
    "exact_set_error_rate",
    "highest_confidence_decile_error_rate",
    "lowest_confidence_decile_error_rate",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sigmoid(logits: np.ndarray, temperature: float) -> np.ndarray:
    values = np.asarray(logits, dtype=np.float64)
    require(temperature > 0.0, "temperature must be positive")
    require(np.all(np.isfinite(values)), "logits must be finite")
    scaled = np.clip(values / float(temperature), -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-scaled))


def source_clip_key(file_name: str) -> str:
    return re.sub(r"_(?:1|3)$", "", file_name.rsplit(".", 1)[0])


def source_clip_membership(
    file_names: Sequence[str],
) -> tuple[np.ndarray, tuple[str, ...], np.ndarray]:
    require(len(file_names) > 0, "file names must be nonempty")
    ordered_keys: list[str] = []
    key_to_index: dict[str, int] = {}
    ids = np.empty(len(file_names), dtype=np.int32)
    for index, file_name in enumerate(file_names):
        require(type(file_name) is str, "file names must be strings")
        key = source_clip_key(file_name)
        if key not in key_to_index:
            key_to_index[key] = len(ordered_keys)
            ordered_keys.append(key)
        ids[index] = key_to_index[key]
    sizes = np.bincount(ids, minlength=len(ordered_keys)).astype(np.int32)
    require(np.all(sizes > 0), "every source clip must be nonempty")
    return ids, tuple(ordered_keys), sizes


def clip_sums(
    values: np.ndarray,
    clip_id_by_image: np.ndarray,
    clip_count: int,
    dtype: np.dtype[Any] | type,
) -> np.ndarray:
    array = np.asarray(values)
    ids = np.asarray(clip_id_by_image, dtype=np.int64)
    require(
        array.ndim >= 1 and array.shape[0] == len(ids),
        "values and clip ids must align",
    )
    require(
        clip_count > 0
        and np.all(ids >= 0)
        and np.all(ids < clip_count),
        "invalid source clip ids",
    )
    output = np.zeros((clip_count, *array.shape[1:]), dtype=dtype)
    np.add.at(output, ids, array.astype(dtype, copy=False))
    return output


def f1_from_counts(
    true_positive: np.ndarray,
    false_positive: np.ndarray,
    false_negative: np.ndarray,
) -> np.ndarray:
    tp = np.asarray(true_positive, dtype=np.float64)
    fp = np.asarray(false_positive, dtype=np.float64)
    fn = np.asarray(false_negative, dtype=np.float64)
    require(tp.shape == fp.shape == fn.shape, "F1 counts must align")
    require(
        np.all(np.isfinite(tp))
        and np.all(np.isfinite(fp))
        and np.all(np.isfinite(fn)),
        "F1 counts must be finite",
    )
    require(
        np.all(tp >= 0.0)
        and np.all(fp >= 0.0)
        and np.all(fn >= 0.0),
        "F1 counts must be nonnegative",
    )
    denominator = 2.0 * tp + fp + fn
    return np.divide(
        2.0 * tp,
        denominator,
        out=np.zeros_like(denominator, dtype=np.float64),
        where=denominator != 0.0,
    )


def confidence_group_ids(
    confidence: np.ndarray,
) -> tuple[np.ndarray, int]:
    values = np.asarray(confidence, dtype=np.float64)
    require(
        values.ndim == 1
        and len(values) > 0
        and np.all(np.isfinite(values)),
        "confidence must be a nonempty finite vector",
    )
    require(
        np.all((values >= 0.0) & (values <= 1.0)),
        "confidence must lie within [0, 1]",
    )
    _, ascending = np.unique(values, return_inverse=True)
    count = int(ascending.max()) + 1
    return (count - 1 - ascending).astype(np.int32), count


def harmonic_numbers(maximum: int) -> np.ndarray:
    require(maximum > 0, "maximum must be positive")
    values = np.zeros(maximum + 1, dtype=np.float64)
    values[1:] = np.cumsum(
        1.0 / np.arange(1, maximum + 1, dtype=np.float64)
    )
    return values


def weighted_tie_averaged_aurc(
    errors: np.ndarray,
    group_ids: np.ndarray,
    group_count: int,
    image_weights: np.ndarray,
    harmonic: np.ndarray,
) -> float:
    error_values = np.asarray(errors, dtype=np.int64)
    groups = np.asarray(group_ids, dtype=np.int64)
    weights = np.asarray(image_weights, dtype=np.int64)
    harmonic_values = np.asarray(harmonic, dtype=np.float64)
    require(
        error_values.ndim == 1
        and groups.shape == error_values.shape
        and weights.shape == error_values.shape,
        "weighted AURC arrays must align",
    )
    require(
        group_count > 0
        and np.all((groups >= 0) & (groups < group_count)),
        "invalid confidence groups",
    )
    require(
        np.all(np.isin(error_values, (0, 1))),
        "errors must be binary",
    )
    require(np.all(weights >= 0), "image weights must be nonnegative")
    counts = np.bincount(
        groups,
        weights=weights,
        minlength=group_count,
    )
    error_counts = np.bincount(
        groups,
        weights=weights * error_values,
        minlength=group_count,
    )
    active = counts > 0
    counts = counts[active]
    error_counts = error_counts[active]
    require(len(counts) > 0, "weighted AURC input is empty")
    integer_counts = counts.astype(np.int64)
    require(
        np.array_equal(counts, integer_counts.astype(np.float64)),
        "weighted AURC counts must be integers",
    )
    starts = np.cumsum(integer_counts) - integer_counts
    stops = starts + integer_counts
    require(
        int(stops[-1]) < len(harmonic_values),
        "harmonic array is too short",
    )
    spans = harmonic_values[stops] - harmonic_values[starts]
    prior_errors = np.cumsum(error_counts) - error_counts
    contribution = (
        prior_errors * spans
        + (error_counts / counts) * (counts - starts * spans)
    )
    result = float(contribution.sum() / stops[-1])
    require(np.isfinite(result), "weighted AURC is nonfinite")
    return result


def _binary_auroc(labels: np.ndarray, scores: np.ndarray) -> float:
    target = np.asarray(labels, dtype=np.int64)
    values = np.asarray(scores, dtype=np.float64)
    require(
        target.ndim == 1
        and values.shape == target.shape
        and np.all(np.isin(target, (0, 1))),
        "AUROC inputs must be aligned and binary",
    )
    positives = int(target.sum())
    negatives = len(target) - positives
    require(
        positives > 0 and negatives > 0,
        "correctness AUROC requires both classes",
    )
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        stop = start + 1
        while (
            stop < len(values)
            and sorted_values[stop] == sorted_values[start]
        ):
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    rank_sum = float(ranks[target == 1].sum())
    return (
        rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def confidence_diagnostics(
    errors: np.ndarray,
    confidence: np.ndarray,
    ece_bins: int = 15,
) -> dict[str, float]:
    error_values = np.asarray(errors, dtype=np.float64)
    score_values = np.asarray(confidence, dtype=np.float64)
    require(
        error_values.ndim == 1
        and score_values.shape == error_values.shape
        and len(error_values) > 0,
        "safety arrays must be nonempty and aligned",
    )
    require(
        np.all(np.isfinite(error_values))
        and np.all(np.isfinite(score_values)),
        "safety arrays must be finite",
    )
    require(
        np.all(np.isin(error_values, (0.0, 1.0))),
        "safety errors must be binary",
    )
    require(
        np.all((score_values >= 0.0) & (score_values <= 1.0)),
        "confidence must lie within [0, 1]",
    )
    require(ece_bins > 0, "ECE bin count must be positive")
    order = np.argsort(-score_values, kind="stable")
    cumulative_risk = np.cumsum(error_values[order]) / np.arange(
        1,
        len(error_values) + 1,
        dtype=np.float64,
    )
    accepted = max(1, int(math.ceil(0.90 * len(error_values))))
    correctness = 1.0 - error_values
    edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece = 0.0
    for index, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if index == 0:
            selected = (score_values >= lower) & (score_values <= upper)
        else:
            selected = (score_values > lower) & (score_values <= upper)
        count = int(selected.sum())
        if count:
            ece += (
                abs(
                    float(correctness[selected].mean())
                    - float(score_values[selected].mean())
                )
                * count
                / len(error_values)
            )
    groups, group_count = confidence_group_ids(score_values)
    tie_aurc = weighted_tie_averaged_aurc(
        error_values.astype(np.int64),
        groups,
        group_count,
        np.ones(len(error_values), dtype=np.int64),
        harmonic_numbers(len(error_values)),
    )
    tenth = max(1, len(error_values) // 10)
    result = {
        "tie_averaged_aurc": tie_aurc,
        "canonical_stable_aurc": float(cumulative_risk.mean()),
        "unsafe_acceptance_rate_90": float(
            cumulative_risk[accepted - 1]
        ),
        "correctness_auroc": float(
            _binary_auroc(correctness.astype(np.int64), score_values)
        ),
        "ece": float(ece),
        "exact_set_error_rate": float(error_values.mean()),
        "highest_confidence_decile_error_rate": float(
            error_values[order[:tenth]].mean()
        ),
        "lowest_confidence_decile_error_rate": float(
            error_values[order[-tenth:]].mean()
        ),
    }
    require(
        set(result) == set(SAFETY_DIAGNOSTICS)
        and all(np.isfinite(value) for value in result.values()),
        "safety diagnostics are incomplete or nonfinite",
    )
    return result


def _binary_count_triplet(
    targets: np.ndarray,
    predictions: np.ndarray,
    clip_id_by_image: np.ndarray,
    clip_count: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    target = np.asarray(targets, dtype=bool)
    prediction = np.asarray(predictions, dtype=bool)
    require(
        target.ndim == 2 and prediction.shape == target.shape,
        "targets and predictions must be aligned matrices",
    )
    return tuple(
        clip_sums(part, clip_id_by_image, clip_count, np.uint16)
        for part in (
            np.logical_and(target, prediction),
            np.logical_and(~target, prediction),
            np.logical_and(target, ~prediction),
        )
    )


def _rationale_jaccard_samples(
    clean: np.ndarray,
    perturbed: np.ndarray,
) -> np.ndarray:
    left = np.asarray(clean, dtype=bool)
    right = np.asarray(perturbed, dtype=bool)
    require(
        left.ndim == 2 and right.shape == left.shape,
        "rationale prediction matrices must align",
    )
    intersection = np.logical_and(left, right).sum(axis=1)
    union = np.logical_or(left, right).sum(axis=1)
    scores = np.ones(len(union), dtype=np.float64)
    nonempty = union > 0
    scores[nonempty] = intersection[nonempty] / union[nonempty]
    return scores


def prepare_seed_clip_statistics(
    action_targets: np.ndarray,
    rationale_targets: np.ndarray,
    action_only_logits: np.ndarray,
    joint_action_logits: np.ndarray,
    joint_rationale_logits: np.ndarray,
    action_temperature: float,
    joint_temperature: float,
    clip_id_by_image: np.ndarray,
    clip_count: int,
) -> dict[str, Any]:
    action_target = np.asarray(action_targets, dtype=bool)
    rationale_target = np.asarray(rationale_targets, dtype=bool)
    action_logits = np.asarray(action_only_logits, dtype=np.float64)
    joint_logits = np.asarray(joint_action_logits, dtype=np.float64)
    rationale_logits = np.asarray(
        joint_rationale_logits,
        dtype=np.float64,
    )
    sample_count = len(action_target)
    require(
        action_target.shape == (sample_count, 4)
        and rationale_target.shape == (sample_count, 21),
        "target arrays have wrong shape",
    )
    require(
        action_logits.shape == (3, 5, sample_count, 4)
        and joint_logits.shape == (3, 5, sample_count, 4)
        and rationale_logits.shape == (3, 5, sample_count, 21),
        "logit grid has wrong shape",
    )
    require(
        np.all(np.isfinite(action_logits))
        and np.all(np.isfinite(joint_logits))
        and np.all(np.isfinite(rationale_logits)),
        "formal logits must be finite",
    )
    require(
        np.asarray(clip_id_by_image).shape == (sample_count,),
        "clip ids do not align",
    )
    action_predictions = np.stack(
        (action_logits >= 0.0, joint_logits >= 0.0),
        axis=2,
    )
    rationale_predictions = rationale_logits >= 0.0
    calibrated = np.stack(
        (
            sigmoid(action_logits, action_temperature),
            sigmoid(joint_logits, joint_temperature),
        ),
        axis=2,
    )
    confidence = calibrated.max(axis=-1)
    errors = np.any(
        action_predictions != action_target[None, None, None, :, :],
        axis=-1,
    ).astype(np.uint8)

    a_shape = (3, 5, 2, clip_count, 4)
    r_shape = (3, 5, clip_count, 21)
    a_tp = np.empty(a_shape, dtype=np.uint16)
    a_fp = np.empty(a_shape, dtype=np.uint16)
    a_fn = np.empty(a_shape, dtype=np.uint16)
    r_tp = np.empty(r_shape, dtype=np.uint16)
    r_fp = np.empty(r_shape, dtype=np.uint16)
    r_fn = np.empty(r_shape, dtype=np.uint16)
    c1_action = np.empty(
        (3, 5, 2, clip_count),
        dtype=np.uint16,
    )
    c1_rationale = np.empty(
        (3, 5, clip_count),
        dtype=np.float64,
    )
    group_ids = np.empty(
        (3, 5, 2, sample_count),
        dtype=np.int32,
    )
    group_counts = np.empty((3, 5, 2), dtype=np.int32)

    for family in range(3):
        clean_action = action_predictions[family, 0]
        clean_rationale = rationale_predictions[family, 0]
        for level in range(5):
            for model in range(2):
                triplet = _binary_count_triplet(
                    action_target,
                    action_predictions[family, level, model],
                    clip_id_by_image,
                    clip_count,
                )
                a_tp[family, level, model] = triplet[0]
                a_fp[family, level, model] = triplet[1]
                a_fn[family, level, model] = triplet[2]
                action_events = np.any(
                    clean_action[model]
                    != action_predictions[family, level, model],
                    axis=1,
                )
                c1_action[family, level, model] = clip_sums(
                    action_events,
                    clip_id_by_image,
                    clip_count,
                    np.uint16,
                )
                ids, count = confidence_group_ids(
                    confidence[family, level, model]
                )
                group_ids[family, level, model] = ids
                group_counts[family, level, model] = count
            rationale_triplet = _binary_count_triplet(
                rationale_target,
                rationale_predictions[family, level],
                clip_id_by_image,
                clip_count,
            )
            r_tp[family, level] = rationale_triplet[0]
            r_fp[family, level] = rationale_triplet[1]
            r_fn[family, level] = rationale_triplet[2]
            c1_rationale[family, level] = clip_sums(
                _rationale_jaccard_samples(
                    clean_rationale,
                    rationale_predictions[family, level],
                ),
                clip_id_by_image,
                clip_count,
                np.float64,
            )

    require(
        np.all(c1_action[:, 0] == 0),
        "C1 level-zero action flip is not exactly zero",
    )
    clip_sizes = np.bincount(
        np.asarray(clip_id_by_image, dtype=np.int64),
        minlength=clip_count,
    )
    require(
        np.allclose(
            c1_rationale[:, 0].sum(axis=1),
            float(sample_count),
            rtol=0.0,
            atol=0.0,
        ),
        "C1 level-zero rationale Jaccard is not exactly one",
    )
    return {
        "sample_count": sample_count,
        "clip_count": clip_count,
        "clip_id_by_image": np.asarray(
            clip_id_by_image,
            dtype=np.int32,
        ),
        "clip_sizes": clip_sizes.astype(np.int32),
        "action_targets": action_target,
        "rationale_targets": rationale_target,
        "action_predictions": action_predictions,
        "rationale_predictions": rationale_predictions,
        "confidence": confidence,
        "errors": errors,
        "group_ids": group_ids,
        "group_counts": group_counts,
        "A_tp": a_tp,
        "A_fp": a_fp,
        "A_fn": a_fn,
        "R_tp": r_tp,
        "R_fp": r_fp,
        "R_fn": r_fn,
        "C1_action_clip_sums": c1_action,
        "C1_rationale_clip_sums": c1_rationale,
    }


def all_family_curves_from_clip_counts(
    prepared: Mapping[str, Any],
    clip_counts: np.ndarray,
    harmonic: np.ndarray,
) -> dict[str, np.ndarray]:
    counts = np.asarray(clip_counts, dtype=np.int64)
    clip_sizes = np.asarray(prepared["clip_sizes"], dtype=np.int64)
    require(
        counts.shape == clip_sizes.shape
        and np.all(counts >= 0)
        and int(counts.sum()) > 0,
        "clip counts must be aligned, nonnegative, and nonempty",
    )
    sample_total = int(counts @ clip_sizes)
    require(sample_total > 0, "expanded image sample is empty")
    a_tp = np.einsum("c,flmck->flmk", counts, prepared["A_tp"])
    a_fp = np.einsum("c,flmck->flmk", counts, prepared["A_fp"])
    a_fn = np.einsum("c,flmck->flmk", counts, prepared["A_fn"])
    a_curve = f1_from_counts(a_tp, a_fp, a_fn).mean(axis=-1)
    a_curve = np.transpose(a_curve, (0, 2, 1))

    r_tp = np.einsum("c,flck->flk", counts, prepared["R_tp"])
    r_fp = np.einsum("c,flck->flk", counts, prepared["R_fp"])
    r_fn = np.einsum("c,flck->flk", counts, prepared["R_fn"])
    r_curve = f1_from_counts(r_tp, r_fp, r_fn).mean(axis=-1)
    r_curve = r_curve[:, None, :]

    action_sum = np.einsum(
        "c,flmc->flm",
        counts,
        prepared["C1_action_clip_sums"],
    )
    c1_action = np.transpose(
        action_sum / float(sample_total),
        (0, 2, 1),
    )
    rationale_sum = np.einsum(
        "c,flc->fl",
        counts,
        prepared["C1_rationale_clip_sums"],
    )
    c1_rationale = rationale_sum[:, None, :] / float(sample_total)
    c1_curve = np.concatenate((c1_action, c1_rationale), axis=1)

    image_weights = counts[
        np.asarray(prepared["clip_id_by_image"], dtype=np.int64)
    ]
    s_curve = np.empty((3, 2, 5), dtype=np.float64)
    for family in range(3):
        for level in range(5):
            for model in range(2):
                s_curve[family, model, level] = (
                    weighted_tie_averaged_aurc(
                        prepared["errors"][family, level, model],
                        prepared["group_ids"][family, level, model],
                        int(
                            prepared["group_counts"][
                                family,
                                level,
                                model,
                            ]
                        ),
                        image_weights,
                        harmonic,
                    )
                )
    curves = {
        "A": np.asarray(a_curve, dtype=np.float64),
        "R": np.asarray(r_curve, dtype=np.float64),
        "S": np.asarray(s_curve, dtype=np.float64),
        "C1": np.asarray(c1_curve, dtype=np.float64),
    }
    for axis, values in curves.items():
        require(
            values.shape
            == (3, len(AXIS_COMPONENTS[axis]), 5),
            f"{axis} curve shape differs",
        )
        require(np.all(np.isfinite(values)), f"{axis} curve is nonfinite")
    return curves


def bottleneck(curves: np.ndarray, directions: Sequence[str]) -> float:
    values = np.asarray(curves, dtype=np.float64)
    require(
        values.ndim == 2
        and values.shape[1] == 5
        and values.shape[0] == len(directions),
        "bottleneck curves and directions do not align",
    )
    steps = []
    for curve, direction in zip(values, directions):
        if direction == "decreasing":
            steps.append(curve[:-1] - curve[1:])
        elif direction == "increasing":
            steps.append(curve[1:] - curve[:-1])
        else:
            raise ValueError("unknown bottleneck direction")
    result = float(np.min(np.concatenate(steps)))
    require(np.isfinite(result), "bottleneck is nonfinite")
    return result


def family_axis_bottlenecks(
    curves: Mapping[str, np.ndarray],
) -> np.ndarray:
    require(set(curves) == set(AXES), "curves must contain four axes")
    output = np.empty((3, 4), dtype=np.float64)
    for family in range(3):
        for axis_index, axis in enumerate(AXES):
            output[family, axis_index] = bottleneck(
                curves[axis][family],
                AXIS_DIRECTIONS[axis],
            )
    return output


def endpoint_effects(curves: Mapping[str, np.ndarray]) -> np.ndarray:
    require(set(curves) == set(AXES), "curves must contain four axes")
    output = np.empty((3, 8), dtype=np.float64)
    output[:, 0:2] = curves["A"][:, :, 0] - curves["A"][:, :, 4]
    output[:, 2] = curves["R"][:, 0, 0] - curves["R"][:, 0, 4]
    output[:, 3:5] = curves["S"][:, :, 4] - curves["S"][:, :, 0]
    output[:, 5:7] = (
        curves["C1"][:, 0:2, 4] - curves["C1"][:, 0:2, 0]
    )
    output[:, 7] = (
        curves["C1"][:, 2, 0] - curves["C1"][:, 2, 4]
    )
    require(np.all(np.isfinite(output)), "endpoint effects are nonfinite")
    return output


def mean_curve_no_reversal(
    seed_curves: np.ndarray,
    directions: Sequence[str],
) -> bool:
    values = np.asarray(seed_curves, dtype=np.float64)
    require(
        values.ndim == 3
        and values.shape[0] == 5
        and values.shape[2] == 5
        and values.shape[1] == len(directions),
        "seed curves have wrong shape",
    )
    require(np.all(np.isfinite(values)), "seed curves are nonfinite")
    mean_curve = values.mean(axis=0)
    for curve, direction in zip(mean_curve, directions):
        differences = np.diff(curve)
        if direction == "decreasing" and np.any(differences > 0.0):
            return False
        if direction == "increasing" and np.any(differences < 0.0):
            return False
        require(
            direction in ("decreasing", "increasing"),
            "unknown mean-curve direction",
        )
    return True


def practical_endpoint_pass(
    mean_endpoint_effects: np.ndarray,
) -> np.ndarray:
    values = np.asarray(mean_endpoint_effects, dtype=np.float64)
    require(values.shape == (3, 8), "mean endpoint shape differs")
    require(np.all(np.isfinite(values)), "mean endpoints are nonfinite")
    thresholds = np.asarray(
        [PRACTICAL_THRESHOLDS[name] for name in ENDPOINT_COMPONENTS],
        dtype=np.float64,
    )
    return values >= thresholds[None, :]


def quantile_diagnostic(
    values: np.ndarray,
    probability: float,
) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    require(
        array.ndim == 1
        and len(array) > 0
        and np.all(np.isfinite(array)),
        "quantile input must be a nonempty finite vector",
    )
    require(0.0 <= probability <= 1.0, "invalid quantile probability")
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(str(contiguous.shape).encode("ascii"))
    digest.update(contiguous.tobytes())
    result = float(
        np.quantile(contiguous, probability, method="linear")
    )
    require(np.isfinite(result), "quantile result is nonfinite")
    return {
        "input_array_sha256": digest.hexdigest().upper(),
        "finite_count": int(len(contiguous)),
        "minimum": float(contiguous.min()),
        "maximum": float(contiguous.max()),
        "quantile_probability": float(probability),
        "numpy_method": "linear",
        "unrounded_result": result,
    }


def run_shared_bootstrap(
    prepared_by_seed: Sequence[Mapping[str, Any]],
    replicates: int = 5000,
    seed: int = 20260810,
    progress: Callable[[int, int], None] | None = None,
    progress_every: int = 100,
) -> dict[str, np.ndarray]:
    require(len(prepared_by_seed) == 5, "bootstrap requires five seeds")
    require(replicates > 0, "replicates must be positive")
    require(progress_every > 0, "progress interval must be positive")
    clip_count = int(prepared_by_seed[0]["clip_count"])
    clip_sizes = np.asarray(prepared_by_seed[0]["clip_sizes"], dtype=np.int64)
    require(
        all(
            int(item["clip_count"]) == clip_count
            and np.array_equal(item["clip_sizes"], clip_sizes)
            for item in prepared_by_seed
        ),
        "source clip structure differs across seeds",
    )
    require(clip_count < 65536, "clip positions do not fit uint16")
    maximum_expanded = clip_count * int(clip_sizes.max())
    harmonic = harmonic_numbers(maximum_expanded)
    gate_draws = np.empty((replicates, 12), dtype=np.float64)
    endpoint_draws = np.empty((replicates, 24), dtype=np.float64)
    seed_draws = np.empty((replicates, 5), dtype=np.uint8)
    clip_draws = np.empty(
        (replicates, clip_count),
        dtype=np.uint16,
    )
    expanded_counts = np.empty(replicates, dtype=np.int32)
    rng = np.random.default_rng(seed)
    for replicate in range(replicates):
        selected_seeds = rng.integers(0, 5, size=5)
        selected_clips = rng.integers(
            0,
            clip_count,
            size=clip_count,
        )
        seed_draws[replicate] = selected_seeds
        clip_draws[replicate] = selected_clips
        counts = np.bincount(
            selected_clips,
            minlength=clip_count,
        ).astype(np.int64)
        expanded = int(counts @ clip_sizes)
        require(expanded > 0, "expanded bootstrap sample is empty")
        expanded_counts[replicate] = expanded
        per_seed_bottlenecks = np.empty((5, 3, 4), dtype=np.float64)
        per_seed_endpoints = np.empty((5, 3, 8), dtype=np.float64)
        for seed_index, prepared in enumerate(prepared_by_seed):
            curves = all_family_curves_from_clip_counts(
                prepared,
                counts,
                harmonic,
            )
            per_seed_bottlenecks[seed_index] = (
                family_axis_bottlenecks(curves)
            )
            per_seed_endpoints[seed_index] = endpoint_effects(curves)
        gate_draws[replicate] = per_seed_bottlenecks[
            selected_seeds
        ].mean(axis=0).reshape(-1)
        endpoint_draws[replicate] = per_seed_endpoints[
            selected_seeds
        ].mean(axis=0).reshape(-1)
        completed = replicate + 1
        if progress is not None and (
            completed % progress_every == 0 or completed == replicates
        ):
            progress(completed, replicates)
    require(
        np.all(np.isfinite(gate_draws))
        and np.all(np.isfinite(endpoint_draws)),
        "bootstrap produced nonfinite values",
    )
    return {
        "family_axis_gate_draws": gate_draws,
        "endpoint_draws": endpoint_draws,
        "seed_position_draws": seed_draws,
        "clip_position_draws": clip_draws,
        "expanded_image_counts": expanded_counts,
    }
