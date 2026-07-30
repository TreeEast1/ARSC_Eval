"""Run the frozen five-seed ARSC-axis falsification suite.

The script has two phases:

1. ``--preflight-only`` verifies every frozen input and exact invariant without
   computing intervention-direction outcomes.
2. The default mode repeats preflight, computes the one-shot point estimates,
   and runs the crossed seed-by-shared-image bootstrap.

No model inference, training, mask generation, threshold selection, or data
selection occurs here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.axis_falsification import (
    action_pairing_estimates,
    array_sha256,
    confidence_control_scores,
    crossed_bootstrap_draw,
    cyclic_source_indices,
    f1_control_estimates,
    fixed_random_scores,
    intervene_targets,
    rationale_pairing_estimates,
    safety_control_estimates,
    shifted_column_sources,
)
from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.internal_validity import (
    PERTURBATIONS,
    action_flip_samples,
    macro_f1,
    percentile_interval,
    rationale_jaccard_samples,
)
from arsc_eval.metrics import multilabel_f1
from arsc_eval.rq1 import (
    MODEL_ACTION,
    MODEL_JOINT,
    prepare_rq1_arrays,
    rq1_metric_estimates,
)
from arsc_eval.utils import write_json


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_protocol.json"
)
AMENDMENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_protocol_amendment01.json"
)
PREREG_REVIEW_PATH = (
    PROJECT_ROOT / "outputs" / "research_review_memo_round7_preregister.md"
)
AMENDMENT_REVIEW_PATH = (
    PROJECT_ROOT / "outputs" / "research_review_memo_round7_amendment01.md"
)
PREFLIGHT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_preflight.json"
)
RUN_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_run_manifest.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_results.json"
)
POINT_CSV_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_point_estimates.csv"
)
BOOTSTRAP_CSV_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_bootstrap.csv"
)
PRIMITIVES_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_primitives.npz"
)

PROTOCOL_SHA256 = (
    "21504FD66E984E211C3E8C51AF013C7C30F8D6E14CFCE01A832FD53711482442"
)
AMENDMENT_SHA256 = (
    "BD089BED634FC7D50D391AE17FFEEC54EB1D3ADBA91035EB553D8C5D7E0CE91F"
)
PREREG_REVIEW_SHA256 = (
    "BDE9B4387F5B2015B29387B96E7033B0E43E1940098B807CA811C30CD1486A9D"
)
AMENDMENT_REVIEW_SHA256 = (
    "6A6734719C779A603B3926F7A93B469A7EC44A6FC61779598DEA345E3E7EEA71"
)
SEEDS = (43, 44, 45, 46, 47)
THRESHOLD = 0.5
TARGET_ROW_OFFSET = 2281
ACTION_CLASS_SHIFT = 1
RATIONALE_CLASS_SHIFT = 7
WRONG_PAIR_OFFSET = 997
RANDOM_ORDER_SEED = 20260801
BOOTSTRAP_SEED = 20260802
BOOTSTRAP_REPLICATES = 2000
SAMPLE_COUNT = 4557

MODEL_STEMS = {
    MODEL_ACTION: "action_only",
    MODEL_JOINT: "joint",
}
PRIMARY_CONTRASTS = (
    f"A::original_minus_combined::{MODEL_ACTION}",
    f"A::original_minus_combined::{MODEL_JOINT}",
    f"R::original_minus_combined::{MODEL_JOINT}",
    f"S_confidence::random_minus_original::{MODEL_ACTION}",
    f"S_confidence::random_minus_original::{MODEL_JOINT}",
    f"C1_action::wrong_minus_correct::{MODEL_ACTION}",
    f"C1_action::wrong_minus_correct::{MODEL_JOINT}",
    f"C1_rationale::correct_minus_wrong::{MODEL_JOINT}",
)
MEASUREMENT_DIRECTION_CONTRASTS = (
    f"A::original_minus_combined::{MODEL_ACTION}",
    f"A::original_minus_combined::{MODEL_JOINT}",
    f"R::original_minus_combined::{MODEL_JOINT}",
    f"C1_action::wrong_minus_correct::{MODEL_ACTION}",
    f"C1_action::wrong_minus_correct::{MODEL_JOINT}",
    f"C1_rationale::correct_minus_wrong::{MODEL_JOINT}",
)
CONFIDENCE_CONTRASTS = (
    f"S_confidence::random_minus_original::{MODEL_ACTION}",
    f"S_confidence::random_minus_original::{MODEL_JOINT}",
)
S_MEASUREMENT_CONTRASTS = (
    f"S_measurement::adversarial_minus_oracle::{MODEL_ACTION}",
    f"S_measurement::adversarial_minus_oracle::{MODEL_JOINT}",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify frozen inputs/invariants without intervention outcomes",
    )
    parser.add_argument(
        "--replicates", type=int, default=BOOTSTRAP_REPLICATES
    )
    parser.add_argument(
        "--bootstrap-seed", type=int, default=BOOTSTRAP_SEED
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def append_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: Any,
) -> None:
    checks.append(
        {"name": name, "passed": bool(passed), "detail": detail}
    )


def clip_group(file_name: str) -> str:
    stem = Path(file_name).stem
    return re.sub(r"_(?:1|3)$", "", stem)


def calibration_temperature(path: Path, model_type: str) -> float:
    result = read_json(path)
    if result["model_type"] != model_type:
        raise RuntimeError(f"wrong calibration model type at {path}")
    value = float(result["temperature"])
    if not np.isfinite(value) or value <= 0.0:
        raise RuntimeError(f"invalid calibration temperature at {path}")
    return value


def metric_rows_to_dict(path: Path) -> dict[str, float]:
    result = read_json(path)
    return {
        str(row["metric"]): float(row["estimate"])
        for row in result["metrics"]
    }


def load_seed(
    seed: int,
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> dict[str, Any]:
    cache_spec = protocol["frozen_inputs"]["cache_files"][str(seed)]
    cache_path = PROJECT_ROOT / cache_spec["path"]
    with np.load(cache_path, allow_pickle=False) as archive:
        cache = {key: np.asarray(archive[key]).copy() for key in archive.files}

    calibration_spec = protocol["frozen_inputs"]["calibration_files"][
        str(seed)
    ]
    action_calibration_path = (
        PROJECT_ROOT / calibration_spec["action_only"]["path"]
    )
    joint_calibration_path = (
        PROJECT_ROOT / calibration_spec["joint"]["path"]
    )
    action_temperature = calibration_temperature(
        action_calibration_path, "action_only"
    )
    joint_temperature = calibration_temperature(
        joint_calibration_path, "joint"
    )
    prepared = prepare_rq1_arrays(
        cache, action_temperature, joint_temperature
    )
    reference_spec = amendment["round5_exact_reproduction_references"][
        "per_seed"
    ][str(seed)]
    reference_path = PROJECT_ROOT / reference_spec["path"]
    return {
        "seed": seed,
        "cache_path": cache_path,
        "cache_spec": cache_spec,
        "cache": cache,
        "prepared": prepared,
        "action_temperature": action_temperature,
        "joint_temperature": joint_temperature,
        "calibration_spec": calibration_spec,
        "action_calibration_path": action_calibration_path,
        "joint_calibration_path": joint_calibration_path,
        "reference_path": reference_path,
        "reference_spec": reference_spec,
        "reference_metrics": metric_rows_to_dict(reference_path),
    }


def git_last_commit(paths: list[Path]) -> str | None:
    arguments = [
        "git",
        "log",
        "-1",
        "--format=%H",
        "--",
        *[str(path.relative_to(PROJECT_ROOT)) for path in paths],
    ]
    completed = subprocess.run(
        arguments,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    return value or None


def run_preflight() -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    protocol = read_json(PROTOCOL_PATH)
    amendment = read_json(AMENDMENT_PATH)
    checks: list[dict[str, Any]] = []

    frozen_artifacts = (
        (PROTOCOL_PATH, PROTOCOL_SHA256, "protocol_sha256"),
        (AMENDMENT_PATH, AMENDMENT_SHA256, "amendment_sha256"),
        (
            PREREG_REVIEW_PATH,
            PREREG_REVIEW_SHA256,
            "preregister_review_sha256",
        ),
        (
            AMENDMENT_REVIEW_PATH,
            AMENDMENT_REVIEW_SHA256,
            "amendment_review_sha256",
        ),
    )
    for path, expected, name in frozen_artifacts:
        observed = sha256_file(path)
        append_check(
            checks,
            name,
            observed == expected,
            {
                "path": relative(path),
                "expected": expected,
                "observed": observed,
            },
        )

    seed_data = {
        seed: load_seed(seed, protocol, amendment) for seed in SEEDS
    }
    for seed, data in seed_data.items():
        cache_observed = sha256_file(data["cache_path"])
        append_check(
            checks,
            f"seed_{seed}_cache_sha256",
            cache_observed == data["cache_spec"]["sha256"],
            {
                "expected": data["cache_spec"]["sha256"],
                "observed": cache_observed,
            },
        )
        for model_name, path_key in (
            ("action_only", "action_calibration_path"),
            ("joint", "joint_calibration_path"),
        ):
            expected = data["calibration_spec"][model_name]["sha256"]
            observed = sha256_file(data[path_key])
            append_check(
                checks,
                f"seed_{seed}_{model_name}_calibration_sha256",
                observed == expected,
                {"expected": expected, "observed": observed},
            )
        reference_observed = sha256_file(data["reference_path"])
        append_check(
            checks,
            f"seed_{seed}_round5_reference_sha256",
            reference_observed == data["reference_spec"]["sha256"],
            {
                "expected": data["reference_spec"]["sha256"],
                "observed": reference_observed,
            },
        )

    aggregate_spec = amendment["round5_exact_reproduction_references"][
        "aggregate"
    ]
    aggregate_path = PROJECT_ROOT / aggregate_spec["path"]
    aggregate_observed = sha256_file(aggregate_path)
    append_check(
        checks,
        "round5_aggregate_sha256",
        aggregate_observed == aggregate_spec["sha256"],
        {
            "expected": aggregate_spec["sha256"],
            "observed": aggregate_observed,
        },
    )

    canonical = seed_data[SEEDS[0]]["cache"]
    file_names = np.asarray(canonical["test_file_names"])
    action_targets = np.asarray(canonical["test_action_targets"])
    rationale_targets = np.asarray(canonical["test_rationale_targets"])
    common_hashes = protocol["frozen_inputs"]["common_array_hashes"]
    append_check(
        checks,
        "canonical_sample_count",
        len(file_names) == SAMPLE_COUNT,
        {"expected": SAMPLE_COUNT, "observed": len(file_names)},
    )
    append_check(
        checks,
        "canonical_file_name_hash",
        array_sha256(file_names)
        == common_hashes["test_file_names_raw_array_bytes_sha256"],
        array_sha256(file_names),
    )
    append_check(
        checks,
        "canonical_action_target_hash",
        array_sha256(action_targets)
        == common_hashes["test_action_targets_raw_array_bytes_sha256"],
        array_sha256(action_targets),
    )
    append_check(
        checks,
        "canonical_rationale_target_hash",
        array_sha256(rationale_targets)
        == common_hashes["test_rationale_targets_raw_array_bytes_sha256"],
        array_sha256(rationale_targets),
    )
    append_check(
        checks,
        "unique_file_names",
        len(set(file_names.tolist())) == SAMPLE_COUNT,
        len(set(file_names.tolist())),
    )
    append_check(
        checks,
        "binary_finite_action_targets",
        bool(
            np.all(np.isfinite(action_targets))
            and np.all(np.isin(action_targets, (0.0, 1.0)))
        ),
        action_targets.sum(axis=0).astype(int).tolist(),
    )
    append_check(
        checks,
        "binary_finite_rationale_targets",
        bool(
            np.all(np.isfinite(rationale_targets))
            and np.all(np.isin(rationale_targets, (0.0, 1.0)))
        ),
        rationale_targets.sum(axis=0).astype(int).tolist(),
    )
    append_check(
        checks,
        "all_action_classes_supported",
        bool(np.all(action_targets.sum(axis=0) > 0)),
        action_targets.sum(axis=0).astype(int).tolist(),
    )
    append_check(
        checks,
        "all_rationale_classes_supported",
        bool(np.all(rationale_targets.sum(axis=0) > 0)),
        rationale_targets.sum(axis=0).astype(int).tolist(),
    )

    common_arrays_match = {}
    for seed, data in seed_data.items():
        cache = data["cache"]
        common_arrays_match[str(seed)] = {
            "file_names": bool(
                np.array_equal(file_names, cache["test_file_names"])
            ),
            "action_targets": bool(
                np.array_equal(action_targets, cache["test_action_targets"])
            ),
            "rationale_targets": bool(
                np.array_equal(
                    rationale_targets, cache["test_rationale_targets"]
                )
            ),
        }
    append_check(
        checks,
        "five_seed_common_arrays_bitwise_identical",
        all(all(values.values()) for values in common_arrays_match.values()),
        common_arrays_match,
    )

    row_sources = cyclic_source_indices(
        SAMPLE_COUNT, TARGET_ROW_OFFSET
    )
    action_columns = shifted_column_sources(
        len(ACTION_NAMES), ACTION_CLASS_SHIFT
    )
    rationale_columns = shifted_column_sources(
        len(RATIONALE_NAMES), RATIONALE_CLASS_SHIFT
    )
    wrong_sources = cyclic_source_indices(
        SAMPLE_COUNT, WRONG_PAIR_OFFSET
    )
    maps = {
        "target_rows": (row_sources, SAMPLE_COUNT),
        "action_columns": (action_columns, len(ACTION_NAMES)),
        "rationale_columns": (
            rationale_columns,
            len(RATIONALE_NAMES),
        ),
        "wrong_pairs": (wrong_sources, SAMPLE_COUNT),
    }
    for name, (mapping, size) in maps.items():
        append_check(
            checks,
            f"{name}_bijection",
            np.array_equal(np.sort(mapping), np.arange(size)),
            {
                "size": size,
                "unique": int(len(np.unique(mapping))),
            },
        )
        append_check(
            checks,
            f"{name}_zero_fixed_points",
            int(np.sum(mapping == np.arange(size))) == 0,
            int(np.sum(mapping == np.arange(size))),
        )

    row_action = intervene_targets(
        action_targets, row_sources=row_sources
    )
    row_rationale = intervene_targets(
        rationale_targets, row_sources=row_sources
    )
    append_check(
        checks,
        "row_only_action_prevalence_preserved",
        np.array_equal(
            action_targets.sum(axis=0), row_action.sum(axis=0)
        ),
        {
            "original": action_targets.sum(axis=0).astype(int).tolist(),
            "row_only": row_action.sum(axis=0).astype(int).tolist(),
        },
    )
    append_check(
        checks,
        "row_only_rationale_prevalence_preserved",
        np.array_equal(
            rationale_targets.sum(axis=0), row_rationale.sum(axis=0)
        ),
        {
            "original": rationale_targets.sum(axis=0).astype(int).tolist(),
            "row_only": row_rationale.sum(axis=0).astype(int).tolist(),
        },
    )
    append_check(
        checks,
        "original_targets_unchanged_after_map_construction",
        bool(
            array_sha256(action_targets)
            == common_hashes[
                "test_action_targets_raw_array_bytes_sha256"
            ]
            and array_sha256(rationale_targets)
            == common_hashes[
                "test_rationale_targets_raw_array_bytes_sha256"
            ]
        ),
        {
            "action": array_sha256(action_targets),
            "rationale": array_sha256(rationale_targets),
        },
    )

    names = file_names.tolist()
    groups = [clip_group(value) for value in names]
    same_names = int(
        sum(names[index] == names[wrong_sources[index]] for index in range(SAMPLE_COUNT))
    )
    same_groups = int(
        sum(
            groups[index] == groups[wrong_sources[index]]
            for index in range(SAMPLE_COUNT)
        )
    )
    append_check(
        checks,
        "wrong_pair_zero_same_filename",
        same_names == 0,
        same_names,
    )
    append_check(
        checks,
        "wrong_pair_zero_same_clip_group",
        same_groups == 0,
        same_groups,
    )

    perfect_action = multilabel_f1(
        action_targets,
        action_targets,
        ACTION_NAMES,
        THRESHOLD,
    )
    perfect_rationale = multilabel_f1(
        rationale_targets,
        rationale_targets,
        RATIONALE_NAMES,
        THRESHOLD,
    )
    append_check(
        checks,
        "perfect_action_exact",
        perfect_action["macro_f1"] == 1.0
        and perfect_action["micro_f1"] == 1.0,
        {
            "macro_f1": perfect_action["macro_f1"],
            "micro_f1": perfect_action["micro_f1"],
        },
    )
    append_check(
        checks,
        "perfect_rationale_exact",
        perfect_rationale["macro_f1"] == 1.0
        and perfect_rationale["micro_f1"] == 1.0,
        {
            "macro_f1": perfect_rationale["macro_f1"],
            "micro_f1": perfect_rationale["micro_f1"],
            "zero_denominator_convention": (
                "F1=0 only when both target and prediction have no "
                "positive support; not activated because all 21 classes "
                "have positive support."
            ),
        },
    )

    random_scores = fixed_random_scores(
        SAMPLE_COUNT, RANDOM_ORDER_SEED
    )
    append_check(
        checks,
        "random_scores_finite_unique",
        bool(
            np.all(np.isfinite(random_scores))
            and len(np.unique(random_scores)) == SAMPLE_COUNT
        ),
        {
            "unique": int(len(np.unique(random_scores))),
            "minimum": float(random_scores.min()),
            "maximum": float(random_scores.max()),
        },
    )

    logit_keys = [
        key
        for key in canonical
        if key.endswith("_logits")
    ]
    original_array_hashes = {
        seed: {
            key: array_sha256(value)
            for key, value in data["cache"].items()
        }
        for seed, data in seed_data.items()
    }
    original_points: dict[int, dict[str, float]] = {}
    original_reproduction_detail = {}
    exact_identity_detail = {}
    s_invariant_detail = {}
    alignment_detail = {}
    for seed, data in seed_data.items():
        cache = data["cache"]
        prepared = data["prepared"]
        finite_by_key = {
            key: bool(np.all(np.isfinite(cache[key])))
            for key in logit_keys
        }
        append_check(
            checks,
            f"seed_{seed}_required_logits_finite",
            all(finite_by_key.values()),
            finite_by_key,
        )
        alignment_by_key = {
            key: int(np.asarray(cache[key]).shape[0])
            for key in logit_keys
        }
        alignment_detail[str(seed)] = alignment_by_key
        append_check(
            checks,
            f"seed_{seed}_correct_pair_shared_order",
            all(value == SAMPLE_COUNT for value in alignment_by_key.values()),
            {
                "shared_file_name_key": "test_file_names",
                "first_dimensions": alignment_by_key,
            },
        )

        identity_action = {}
        for model in (MODEL_ACTION, MODEL_JOINT):
            per_image = action_flip_samples(
                prepared["raw_clean"][model],
                prepared["raw_clean"][model],
                THRESHOLD,
            )
            identity_action[model] = {
                "all_zero": bool(np.all(per_image == 0.0)),
                "maximum": float(per_image.max()),
            }
        identity_rationale = rationale_jaccard_samples(
            prepared["rationale_clean"],
            prepared["rationale_clean"],
            THRESHOLD,
        )
        exact_identity_detail[str(seed)] = {
            "action": identity_action,
            "rationale_all_one": bool(
                np.all(identity_rationale == 1.0)
            ),
            "rationale_minimum": float(identity_rationale.min()),
        }
        append_check(
            checks,
            f"seed_{seed}_identity_c1_per_image_exact",
            all(
                values["all_zero"] for values in identity_action.values()
            )
            and np.all(identity_rationale == 1.0),
            exact_identity_detail[str(seed)],
        )

        s_invariant_detail[str(seed)] = {}
        for model in (MODEL_ACTION, MODEL_JOINT):
            probabilities = prepared["calibrated_clean"][model]
            probabilities_before = array_sha256(probabilities)
            errors, controls = confidence_control_scores(
                action_targets,
                probabilities,
                random_scores,
                THRESHOLD,
            )
            correct = errors == 0.0
            error = ~correct
            declared_random_order = np.argsort(
                -random_scores, kind="stable"
            )
            observed_random_order = np.argsort(
                -controls["random"], kind="stable"
            )
            expected_oracle_order = np.concatenate(
                (
                    declared_random_order[correct[declared_random_order]],
                    declared_random_order[error[declared_random_order]],
                )
            )
            expected_adversarial_order = np.concatenate(
                (
                    declared_random_order[error[declared_random_order]],
                    declared_random_order[correct[declared_random_order]],
                )
            )
            ordering_exact = {
                "oracle": bool(
                    np.array_equal(
                        np.argsort(
                            -controls["oracle"], kind="stable"
                        ),
                        expected_oracle_order,
                    )
                ),
                "random": bool(
                    np.array_equal(
                        declared_random_order, observed_random_order
                    )
                ),
                "adversarial": bool(
                    np.array_equal(
                        np.argsort(
                            -controls["adversarial"], kind="stable"
                        ),
                        expected_adversarial_order,
                    )
                ),
            }
            separation = {
                "oracle": bool(
                    controls["oracle"][error].max()
                    < controls["oracle"][correct].min()
                ),
                "adversarial": bool(
                    controls["adversarial"][correct].max()
                    < controls["adversarial"][error].min()
                ),
            }
            synthetic_unique = {
                name: bool(
                    np.all(np.isfinite(scores))
                    and len(np.unique(scores)) == SAMPLE_COUNT
                )
                for name, scores in controls.items()
                if name != "original"
            }
            predictions = probabilities >= THRESHOLD
            prediction_hashes = {
                name: array_sha256(predictions)
                for name in controls
            }
            error_hashes = {
                name: array_sha256(errors) for name in controls
            }
            action_f1_by_ordering = {
                name: {
                    key: value
                    for key, value in multilabel_f1(
                        action_targets,
                        probabilities,
                        ACTION_NAMES,
                        THRESHOLD,
                    ).items()
                    if key in ("macro_f1", "micro_f1")
                }
                for name in controls
            }
            s_invariant_detail[str(seed)][model] = {
                "correct_samples": int(correct.sum()),
                "error_samples": int(error.sum()),
                "separation": separation,
                "synthetic_unique": synthetic_unique,
                "ordering_exact": ordering_exact,
                "prediction_hashes": prediction_hashes,
                "error_hashes": error_hashes,
                "action_f1_by_ordering": action_f1_by_ordering,
                "calibrated_probability_unchanged": bool(
                    probabilities_before == array_sha256(probabilities)
                ),
            }
            f1_pairs = {
                (
                    values["macro_f1"],
                    values["micro_f1"],
                )
                for values in action_f1_by_ordering.values()
            }
            append_check(
                checks,
                f"seed_{seed}_{MODEL_STEMS[model]}_S_exact_invariants",
                bool(
                    correct.any()
                    and error.any()
                    and all(separation.values())
                    and all(synthetic_unique.values())
                    and all(ordering_exact.values())
                    and len(set(prediction_hashes.values())) == 1
                    and len(set(error_hashes.values())) == 1
                    and len(f1_pairs) == 1
                    and probabilities_before == array_sha256(probabilities)
                ),
                s_invariant_detail[str(seed)][model],
            )

        original = rq1_metric_estimates(prepared, THRESHOLD)
        original_points[seed] = original
        reference = data["reference_metrics"]
        mismatches = {
            key: {
                "recomputed": original.get(key),
                "round5": reference.get(key),
            }
            for key in sorted(set(original) | set(reference))
            if key not in original
            or key not in reference
            or original[key] != reference[key]
        }
        original_reproduction_detail[str(seed)] = {
            "metric_count": len(original),
            "reference_metric_count": len(reference),
            "mismatches": mismatches,
        }
        append_check(
            checks,
            f"seed_{seed}_round5_point_estimates_exact",
            not mismatches,
            original_reproduction_detail[str(seed)],
        )

    aggregate = read_json(aggregate_path)
    aggregate_rows = {
        str(row["metric"]): row for row in aggregate["metric_summary"]
    }
    aggregate_mismatches = {}
    for metric in sorted(original_points[SEEDS[0]]):
        values = [original_points[seed][metric] for seed in SEEDS]
        mean_value = float(np.mean(values))
        sd_value = float(np.std(values, ddof=1))
        row = aggregate_rows.get(metric)
        if (
            row is None
            or mean_value != float(row["mean_across_seeds"])
            or sd_value != float(row["sd_across_seeds"])
        ):
            aggregate_mismatches[metric] = {
                "recomputed_mean": mean_value,
                "recomputed_sd": sd_value,
                "round5": row,
            }
    append_check(
        checks,
        "round5_aggregate_point_estimates_exact",
        not aggregate_mismatches,
        {
            "metric_count": len(aggregate_rows),
            "mismatches": aggregate_mismatches,
        },
    )

    final_array_hashes = {
        seed: {
            key: array_sha256(value)
            for key, value in data["cache"].items()
        }
        for seed, data in seed_data.items()
    }
    mutation_mismatches = {
        str(seed): [
            key
            for key in original_array_hashes[seed]
            if original_array_hashes[seed][key]
            != final_array_hashes[seed][key]
        ]
        for seed in SEEDS
    }
    append_check(
        checks,
        "no_in_place_cache_mutation",
        all(not values for values in mutation_mismatches.values()),
        mutation_mismatches,
    )

    audit = {
        "study": "ARSC axis falsification pre-analysis exact audit",
        "status": "PASS" if all(row["passed"] for row in checks) else "STOP",
        "intervention_direction_outcomes_computed": false,
        "protocol_sha256": PROTOCOL_SHA256,
        "amendment_sha256": AMENDMENT_SHA256,
        "amendment_review_sha256": AMENDMENT_REVIEW_SHA256,
        "checks": checks,
        "summary": {
            "passed": int(sum(row["passed"] for row in checks)),
            "total": len(checks),
            "failed_names": [
                row["name"] for row in checks if not row["passed"]
            ],
        },
        "frozen_maps": {
            "target_row_source_sha256": array_sha256(row_sources),
            "action_column_sources": action_columns.tolist(),
            "rationale_column_sources": rationale_columns.tolist(),
            "wrong_pair_source_sha256": array_sha256(wrong_sources),
            "random_score_sha256": array_sha256(random_scores),
        },
        "claim_boundary": (
            "Passing this audit only authorizes the one-shot frozen "
            "intervention analysis."
        ),
    }
    write_json(PREFLIGHT_PATH, audit)

    implementation_paths = [
        PROJECT_ROOT / "src" / "arsc_eval" / "axis_falsification.py",
        Path(__file__).resolve(),
        PROJECT_ROOT / "tests" / "test_axis_falsification.py",
    ]
    manifest = {
        "study": "ARSC axis falsification immutable pre-run manifest",
        "status": (
            "PRE_OUTCOME_PREFLIGHT_PASSED"
            if audit["status"] == "PASS"
            else "STOP"
        ),
        "intervention_direction_outcomes_computed": false,
        "frozen_artifacts": {
            relative(path): sha256_file(path)
            for path, _, _ in frozen_artifacts
        },
        "implementation": {
            relative(path): sha256_file(path)
            for path in implementation_paths
        },
        "implementation_last_commit": git_last_commit(
            implementation_paths
        ),
        "preflight": {
            "path": relative(PREFLIGHT_PATH),
            "sha256": sha256_file(PREFLIGHT_PATH),
            "status": audit["status"],
        },
        "inputs": {
            str(seed): {
                "cache": {
                    "path": relative(data["cache_path"]),
                    "sha256": sha256_file(data["cache_path"]),
                },
                "action_calibration": {
                    "path": relative(data["action_calibration_path"]),
                    "sha256": sha256_file(
                        data["action_calibration_path"]
                    ),
                },
                "joint_calibration": {
                    "path": relative(data["joint_calibration_path"]),
                    "sha256": sha256_file(
                        data["joint_calibration_path"]
                    ),
                },
                "round5_reference": {
                    "path": relative(data["reference_path"]),
                    "sha256": sha256_file(data["reference_path"]),
                },
            }
            for seed, data in seed_data.items()
        },
        "frozen_parameters": {
            "seeds": list(SEEDS),
            "sample_count": SAMPLE_COUNT,
            "threshold": THRESHOLD,
            "target_row_offset": TARGET_ROW_OFFSET,
            "action_class_shift": ACTION_CLASS_SHIFT,
            "rationale_class_shift": RATIONALE_CLASS_SHIFT,
            "wrong_pair_offset": WRONG_PAIR_OFFSET,
            "random_order_seed": RANDOM_ORDER_SEED,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap": (
                "crossed seed x shared-image paired bootstrap; one common "
                "canonical image multiset per replicate"
            ),
        },
    }
    write_json(RUN_MANIFEST_PATH, manifest)
    if audit["status"] != "PASS":
        raise RuntimeError(
            "pre-analysis exact audit failed; intervention analysis STOP"
        )
    return audit, seed_data


def aurc_from_scores(
    errors: np.ndarray,
    scores: np.ndarray,
    indices: np.ndarray,
) -> float:
    selected_errors = np.asarray(errors, dtype=np.float64)[indices]
    selected_scores = np.asarray(scores, dtype=np.float64)[indices]
    order = np.argsort(-selected_scores, kind="stable")
    cumulative = np.cumsum(selected_errors[order]) / np.arange(
        1, len(indices) + 1
    )
    return float(cumulative.mean())


def per_image_c1_primitives(
    prepared: dict[str, Any],
    wrong_sources: np.ndarray,
) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    for model in (MODEL_ACTION, MODEL_JOINT):
        correct = []
        wrong = []
        clean = prepared["raw_clean"][model]
        for kind in PERTURBATIONS:
            perturbed = prepared["raw_perturbed"][kind][model]
            correct.append(
                action_flip_samples(clean, perturbed, THRESHOLD)
            )
            wrong.append(
                action_flip_samples(
                    clean, perturbed[wrong_sources], THRESHOLD
                )
            )
        stem = MODEL_STEMS[model]
        result[f"action_correct_mean_three::{stem}"] = np.mean(
            correct, axis=0
        )
        result[f"action_wrong_mean_three::{stem}"] = np.mean(
            wrong, axis=0
        )
    rationale_correct = []
    rationale_wrong = []
    for kind in PERTURBATIONS:
        perturbed = prepared["rationale_perturbed"][kind]
        rationale_correct.append(
            rationale_jaccard_samples(
                prepared["rationale_clean"],
                perturbed,
                THRESHOLD,
            )
        )
        rationale_wrong.append(
            rationale_jaccard_samples(
                prepared["rationale_clean"],
                perturbed[wrong_sources],
                THRESHOLD,
            )
        )
    result["rationale_correct_mean_three"] = np.mean(
        rationale_correct, axis=0
    )
    result["rationale_wrong_mean_three"] = np.mean(
        rationale_wrong, axis=0
    )
    return result


def prepare_analysis_seed(
    data: dict[str, Any],
    random_scores: np.ndarray,
    action_destroyed: np.ndarray,
    rationale_destroyed: np.ndarray,
    wrong_sources: np.ndarray,
) -> dict[str, Any]:
    prepared = data["prepared"]
    result: dict[str, Any] = {
        "action_targets": prepared["action_targets"].astype(bool),
        "action_destroyed": action_destroyed.astype(bool),
        "rationale_targets": prepared["rationale_targets"].astype(bool),
        "rationale_destroyed": rationale_destroyed.astype(bool),
        "action_predictions": {},
        "rationale_predictions": (
            prepared["rationale_clean"] >= THRESHOLD
        ),
        "S": {},
    }
    for model in (MODEL_ACTION, MODEL_JOINT):
        result["action_predictions"][model] = (
            prepared["raw_clean"][model] >= THRESHOLD
        )
        errors, controls = confidence_control_scores(
            prepared["action_targets"],
            prepared["calibrated_clean"][model],
            random_scores,
            THRESHOLD,
        )
        result["S"][model] = {
            "errors": errors,
            "scores": controls,
        }
    result["C1"] = per_image_c1_primitives(
        prepared, wrong_sources
    )
    return result


def seed_contrasts(
    prepared: dict[str, Any],
    indices: np.ndarray,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for model in (MODEL_ACTION, MODEL_JOINT):
        predictions = prepared["action_predictions"][model]
        original = macro_f1(
            prepared["action_targets"][indices],
            predictions[indices],
            THRESHOLD,
        )
        destroyed = macro_f1(
            prepared["action_destroyed"][indices],
            predictions[indices],
            THRESHOLD,
        )
        values[
            f"A::original_minus_combined::{model}"
        ] = original - destroyed
        safety = prepared["S"][model]
        values[
            f"S_confidence::random_minus_original::{model}"
        ] = aurc_from_scores(
            safety["errors"],
            safety["scores"]["random"],
            indices,
        ) - aurc_from_scores(
            safety["errors"],
            safety["scores"]["original"],
            indices,
        )
        values[
            f"S_measurement::adversarial_minus_oracle::{model}"
        ] = aurc_from_scores(
            safety["errors"],
            safety["scores"]["adversarial"],
            indices,
        ) - aurc_from_scores(
            safety["errors"],
            safety["scores"]["oracle"],
            indices,
        )
        stem = MODEL_STEMS[model]
        values[
            f"C1_action::wrong_minus_correct::{model}"
        ] = float(
            np.mean(
                prepared["C1"][
                    f"action_wrong_mean_three::{stem}"
                ][indices]
                - prepared["C1"][
                    f"action_correct_mean_three::{stem}"
                ][indices]
            )
        )
    rationale_original = macro_f1(
        prepared["rationale_targets"][indices],
        prepared["rationale_predictions"][indices],
        THRESHOLD,
    )
    rationale_destroyed_value = macro_f1(
        prepared["rationale_destroyed"][indices],
        prepared["rationale_predictions"][indices],
        THRESHOLD,
    )
    values[
        f"R::original_minus_combined::{MODEL_JOINT}"
    ] = rationale_original - rationale_destroyed_value
    values[
        f"C1_rationale::correct_minus_wrong::{MODEL_JOINT}"
    ] = float(
        np.mean(
            prepared["C1"]["rationale_correct_mean_three"][indices]
            - prepared["C1"]["rationale_wrong_mean_three"][indices]
        )
    )
    return values


def point_outcomes(
    seed_data: dict[int, dict[str, Any]],
    row_sources: np.ndarray,
    action_columns: np.ndarray,
    rationale_columns: np.ndarray,
    wrong_sources: np.ndarray,
    random_scores: np.ndarray,
) -> tuple[
    dict[str, Any],
    dict[int, dict[str, Any]],
    list[dict[str, Any]],
]:
    outcomes: dict[str, Any] = {}
    prepared_analysis: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    action_destroyed = intervene_targets(
        seed_data[SEEDS[0]]["prepared"]["action_targets"],
        row_sources,
        action_columns,
    )
    rationale_destroyed = intervene_targets(
        seed_data[SEEDS[0]]["prepared"]["rationale_targets"],
        row_sources,
        rationale_columns,
    )
    for seed, data in seed_data.items():
        prepared = data["prepared"]
        seed_result: dict[str, Any] = {
            "A": {},
            "R": {},
            "S": {},
            "C1": {"action": {}, "rationale": {}},
        }
        for model in (MODEL_ACTION, MODEL_JOINT):
            estimates = f1_control_estimates(
                prepared["action_targets"],
                prepared["raw_clean"][model],
                ACTION_NAMES,
                row_sources,
                action_columns,
                THRESHOLD,
            )
            seed_result["A"][model] = estimates
            for control, control_values in estimates.items():
                for metric in ("macro_f1", "micro_f1"):
                    rows.append(
                        {
                            "seed": seed,
                            "axis": "A",
                            "model": model,
                            "control": control,
                            "metric": metric,
                            "estimate": control_values[metric],
                        }
                    )

        rationale_estimates = f1_control_estimates(
            prepared["rationale_targets"],
            prepared["rationale_clean"],
            RATIONALE_NAMES,
            row_sources,
            rationale_columns,
            THRESHOLD,
        )
        seed_result["R"][MODEL_JOINT] = rationale_estimates
        for control, control_values in rationale_estimates.items():
            for metric in ("macro_f1", "micro_f1"):
                rows.append(
                    {
                        "seed": seed,
                        "axis": "R",
                        "model": MODEL_JOINT,
                        "control": control,
                        "metric": metric,
                        "estimate": control_values[metric],
                    }
                )

        for model in (MODEL_ACTION, MODEL_JOINT):
            estimates = safety_control_estimates(
                prepared["action_targets"],
                prepared["calibrated_clean"][model],
                random_scores,
                THRESHOLD,
            )
            seed_result["S"][model] = estimates
            for control, control_values in estimates.items():
                for metric in (
                    "aurc",
                    "unsafe_acceptance_rate_90",
                    "ece",
                    "correctness_auroc",
                    "exact_set_error_rate",
                ):
                    rows.append(
                        {
                            "seed": seed,
                            "axis": "S",
                            "model": model,
                            "control": control,
                            "metric": metric,
                            "estimate": control_values[metric],
                        }
                    )

        for model in (MODEL_ACTION, MODEL_JOINT):
            estimates = action_pairing_estimates(
                prepared["raw_clean"][model],
                {
                    kind: prepared["raw_perturbed"][kind][model]
                    for kind in PERTURBATIONS
                },
                wrong_sources,
                THRESHOLD,
            )
            seed_result["C1"]["action"][model] = estimates
            for control in ("identity", "correct", "wrong"):
                for metric, estimate in estimates[control].items():
                    rows.append(
                        {
                            "seed": seed,
                            "axis": "C1_action",
                            "model": model,
                            "control": control,
                            "metric": metric,
                            "estimate": estimate,
                        }
                    )

        rationale_pairing = rationale_pairing_estimates(
            prepared["rationale_clean"],
            {
                kind: prepared["rationale_perturbed"][kind]
                for kind in PERTURBATIONS
            },
            wrong_sources,
            THRESHOLD,
        )
        seed_result["C1"]["rationale"][MODEL_JOINT] = (
            rationale_pairing
        )
        for control in ("identity", "correct", "wrong"):
            for metric, estimate in rationale_pairing[control].items():
                rows.append(
                    {
                        "seed": seed,
                        "axis": "C1_rationale",
                        "model": MODEL_JOINT,
                        "control": control,
                        "metric": metric,
                        "estimate": estimate,
                    }
                )

        prepared_analysis[seed] = prepare_analysis_seed(
            data,
            random_scores,
            action_destroyed,
            rationale_destroyed,
            wrong_sources,
        )
        full_indices = np.arange(SAMPLE_COUNT, dtype=np.int64)
        seed_result["primary_contrasts"] = seed_contrasts(
            prepared_analysis[seed], full_indices
        )
        outcomes[str(seed)] = seed_result
    return outcomes, prepared_analysis, rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_primitives(
    seed_data: dict[int, dict[str, Any]],
    prepared_analysis: dict[int, dict[str, Any]],
    row_sources: np.ndarray,
    action_columns: np.ndarray,
    rationale_columns: np.ndarray,
    wrong_sources: np.ndarray,
    random_scores: np.ndarray,
) -> dict[str, Any]:
    canonical = seed_data[SEEDS[0]]["cache"]
    arrays: dict[str, np.ndarray] = {
        "file_names": canonical["test_file_names"],
        "action_targets": canonical["test_action_targets"].astype(
            np.uint8
        ),
        "rationale_targets": canonical["test_rationale_targets"].astype(
            np.uint8
        ),
        "target_row_sources": row_sources,
        "action_column_sources": action_columns,
        "rationale_column_sources": rationale_columns,
        "wrong_pair_sources": wrong_sources,
        "random_scores": random_scores,
    }
    for seed, prepared in prepared_analysis.items():
        for model in (MODEL_ACTION, MODEL_JOINT):
            stem = MODEL_STEMS[model]
            arrays[f"seed_{seed}_{stem}_action_predictions"] = (
                prepared["action_predictions"][model].astype(np.uint8)
            )
            arrays[f"seed_{seed}_{stem}_exact_set_errors"] = prepared[
                "S"
            ][model]["errors"].astype(np.uint8)
            arrays[f"seed_{seed}_{stem}_original_confidence"] = prepared[
                "S"
            ][model]["scores"]["original"].astype(np.float64)
            arrays[
                f"seed_{seed}_{stem}_c1_correct_action_mean_three"
            ] = prepared["C1"][
                f"action_correct_mean_three::{stem}"
            ].astype(np.float64)
            arrays[
                f"seed_{seed}_{stem}_c1_wrong_action_mean_three"
            ] = prepared["C1"][
                f"action_wrong_mean_three::{stem}"
            ].astype(np.float64)
        arrays[f"seed_{seed}_joint_rationale_predictions"] = prepared[
            "rationale_predictions"
        ].astype(np.uint8)
        arrays[
            f"seed_{seed}_joint_c1_correct_rationale_mean_three"
        ] = prepared["C1"]["rationale_correct_mean_three"].astype(
            np.float64
        )
        arrays[
            f"seed_{seed}_joint_c1_wrong_rationale_mean_three"
        ] = prepared["C1"]["rationale_wrong_mean_three"].astype(
            np.float64
        )
    np.savez_compressed(PRIMITIVES_PATH, **arrays)
    return {
        "path": relative(PRIMITIVES_PATH),
        "sha256": sha256_file(PRIMITIVES_PATH),
        "bytes": PRIMITIVES_PATH.stat().st_size,
        "array_count": len(arrays),
        "contains_pixels": false_value(),
        "contains_model_weights": false_value(),
        "sufficient_for": (
            "offline verification of binary A/R controls, S ordering "
            "controls, and per-image C1 contrasts"
        ),
    }


def false_value() -> bool:
    """Keep machine-readable negative provenance explicit."""

    return False


def run_bootstrap(
    prepared_analysis: dict[int, dict[str, Any]],
    replicates: int,
    bootstrap_seed: int,
) -> tuple[
    dict[str, np.ndarray],
    dict[str, dict[str, Any]],
    dict[str, dict[str, float]],
]:
    rng = np.random.default_rng(bootstrap_seed)
    contrast_names = (*PRIMARY_CONTRASTS, *S_MEASUREMENT_CONTRASTS)
    draws = {
        name: np.empty(replicates, dtype=np.float64)
        for name in contrast_names
    }
    raw_seed = {
        str(seed): seed_contrasts(
            prepared_analysis[seed],
            np.arange(SAMPLE_COUNT, dtype=np.int64),
        )
        for seed in SEEDS
    }
    for replicate in range(replicates):
        selected_seeds, shared_images = crossed_bootstrap_draw(
            rng, SEEDS, SAMPLE_COUNT
        )
        by_selected_seed = {
            int(seed): seed_contrasts(
                prepared_analysis[int(seed)], shared_images
            )
            for seed in np.unique(selected_seeds)
        }
        for name in contrast_names:
            draws[name][replicate] = float(
                np.mean(
                    [
                        by_selected_seed[int(seed)][name]
                        for seed in selected_seeds
                    ]
                )
            )
        if (replicate + 1) % 100 == 0:
            print(
                json.dumps(
                    {
                        "bootstrap_completed": replicate + 1,
                        "bootstrap_total": replicates,
                        "shared_image_draw_per_replicate": 1,
                    }
                ),
                flush=True,
            )

    summaries: dict[str, dict[str, Any]] = {}
    for name in contrast_names:
        raw = [raw_seed[str(seed)][name] for seed in SEEDS]
        lower, upper = percentile_interval(draws[name], 0.95)
        summaries[name] = {
            "mean_across_seeds": float(np.mean(raw)),
            "sd_across_seeds": float(np.std(raw, ddof=1)),
            "raw_by_seed": {
                str(seed): raw_seed[str(seed)][name] for seed in SEEDS
            },
            "positive_seed_count": int(sum(value > 0.0 for value in raw)),
            "crossed_bootstrap_ci": [lower, upper],
            "direction_gate_passed": bool(
                np.mean(raw) > 0.0
                and sum(value > 0.0 for value in raw) >= 4
                and lower > 0.0
            ),
        }
    return draws, summaries, raw_seed


def main() -> int:
    args = parse_args()
    if args.replicates != BOOTSTRAP_REPLICATES:
        raise ValueError("replicates are frozen to 2000")
    if args.bootstrap_seed != BOOTSTRAP_SEED:
        raise ValueError("bootstrap seed is frozen to 20260802")

    audit, seed_data = run_preflight()
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "preflight": audit["status"],
                    "checks": audit["summary"],
                    "manifest": relative(RUN_MANIFEST_PATH),
                },
                indent=2,
            )
        )
        return 0
    if RESULT_PATH.exists():
        raise RuntimeError(
            f"one-shot result already exists at {relative(RESULT_PATH)}"
        )

    row_sources = cyclic_source_indices(
        SAMPLE_COUNT, TARGET_ROW_OFFSET
    )
    action_columns = shifted_column_sources(
        len(ACTION_NAMES), ACTION_CLASS_SHIFT
    )
    rationale_columns = shifted_column_sources(
        len(RATIONALE_NAMES), RATIONALE_CLASS_SHIFT
    )
    wrong_sources = cyclic_source_indices(
        SAMPLE_COUNT, WRONG_PAIR_OFFSET
    )
    random_scores = fixed_random_scores(
        SAMPLE_COUNT, RANDOM_ORDER_SEED
    )
    outcomes, prepared_analysis, point_rows = point_outcomes(
        seed_data,
        row_sources,
        action_columns,
        rationale_columns,
        wrong_sources,
        random_scores,
    )
    write_csv(POINT_CSV_PATH, point_rows)
    primitives = write_primitives(
        seed_data,
        prepared_analysis,
        row_sources,
        action_columns,
        rationale_columns,
        wrong_sources,
        random_scores,
    )

    _, bootstrap_summary, raw_seed_contrasts = run_bootstrap(
        prepared_analysis, args.replicates, args.bootstrap_seed
    )
    bootstrap_rows = [
        {
            "contrast": name,
            "mean_across_seeds": values["mean_across_seeds"],
            "sd_across_seeds": values["sd_across_seeds"],
            "positive_seed_count": values["positive_seed_count"],
            "ci_lower": values["crossed_bootstrap_ci"][0],
            "ci_upper": values["crossed_bootstrap_ci"][1],
            "direction_gate_passed": values[
                "direction_gate_passed"
            ],
        }
        for name, values in bootstrap_summary.items()
    ]
    write_csv(BOOTSTRAP_CSV_PATH, bootstrap_rows)

    s_extremal_detail = {}
    for seed in SEEDS:
        s_extremal_detail[str(seed)] = {}
        for model in (MODEL_ACTION, MODEL_JOINT):
            controls = outcomes[str(seed)]["S"][model]
            aurc = {
                name: float(values["aurc"])
                for name, values in controls.items()
            }
            passed = bool(
                aurc["oracle"] <= aurc["original"]
                and aurc["oracle"] <= aurc["random"]
                and aurc["adversarial"] >= aurc["original"]
                and aurc["adversarial"] >= aurc["random"]
                and aurc["adversarial"] > aurc["oracle"]
            )
            s_extremal_detail[str(seed)][model] = {
                "aurc": aurc,
                "passed": passed,
            }
    s_measurement_ordering_pass = all(
        values["passed"]
        for seed_values in s_extremal_detail.values()
        for values in seed_values.values()
    )
    measurement_directions_pass = all(
        bootstrap_summary[name]["direction_gate_passed"]
        for name in MEASUREMENT_DIRECTION_CONTRASTS
    )
    confidence_informativeness = {
        model: {
            "contrast": name,
            "passed": bootstrap_summary[name][
                "direction_gate_passed"
            ],
        }
        for model, name in zip(
            (MODEL_ACTION, MODEL_JOINT), CONFIDENCE_CONTRASTS
        )
    }
    full_suite_measurement_pass = bool(
        audit["status"] == "PASS"
        and measurement_directions_pass
        and s_measurement_ordering_pass
    )
    full_empirical_battery_pass = bool(
        full_suite_measurement_pass
        and all(
            values["passed"]
            for values in confidence_informativeness.values()
        )
    )

    result = {
        "study": "BDD-OIA five-seed frozen-cache ARSC-axis falsification",
        "status": "COMPLETED_ONE_SHOT",
        "scope": {
            "new_data": false_value(),
            "training": false_value(),
            "inference": false_value(),
            "masks": false_value(),
            "CEG": "closed and not evaluated",
        },
        "provenance": {
            "protocol": {
                "path": relative(PROTOCOL_PATH),
                "sha256": sha256_file(PROTOCOL_PATH),
            },
            "amendment": {
                "path": relative(AMENDMENT_PATH),
                "sha256": sha256_file(AMENDMENT_PATH),
            },
            "independent_GO_review": {
                "path": relative(AMENDMENT_REVIEW_PATH),
                "sha256": sha256_file(AMENDMENT_REVIEW_PATH),
            },
            "preflight": {
                "path": relative(PREFLIGHT_PATH),
                "sha256": sha256_file(PREFLIGHT_PATH),
                "status": audit["status"],
            },
            "run_manifest": {
                "path": relative(RUN_MANIFEST_PATH),
                "sha256": sha256_file(RUN_MANIFEST_PATH),
            },
            "primitives": primitives,
        },
        "frozen_parameters": {
            "seeds": list(SEEDS),
            "threshold": THRESHOLD,
            "sample_count": SAMPLE_COUNT,
            "bootstrap": {
                "method": (
                    "crossed paired bootstrap: resample training seeds, "
                    "then draw one shared canonical-image multiset and "
                    "apply it to every selected seed/control"
                ),
                "replicates": args.replicates,
                "seed": args.bootstrap_seed,
                "confidence_level": 0.95,
                "interval": "percentile",
            },
        },
        "point_estimates_by_seed": outcomes,
        "raw_seed_contrasts": raw_seed_contrasts,
        "bootstrap_summary": bootstrap_summary,
        "decisions": {
            "exact_preflight": {
                "passed": audit["status"] == "PASS",
                "checks": audit["summary"],
            },
            "A_R_C1_direction_gates": {
                name: bootstrap_summary[name][
                    "direction_gate_passed"
                ]
                for name in MEASUREMENT_DIRECTION_CONTRASTS
            },
            "S_measurement_ordering_gate": {
                "passed": s_measurement_ordering_pass,
                "per_seed_model": s_extremal_detail,
                "synthetic_ECE_role": (
                    "numeric diagnostic only; no directional claim"
                ),
            },
            "frozen_model_confidence_informativeness": (
                confidence_informativeness
            ),
            "full_suite_measurement_pass": (
                full_suite_measurement_pass
            ),
            "full_empirical_battery_pass": (
                full_empirical_battery_pass
            ),
        },
        "interpretation_boundaries": {
            "A_R": (
                "Sensitivity to severe frozen target-association "
                "destruction, not ontology, correctness, grounding, or "
                "faithfulness validity."
            ),
            "S": (
                "Ordering behavior and, separately, informativeness "
                "relative to one fixed random reference; not a safety "
                "guarantee."
            ),
            "C1": (
                "Sensitivity to correct versus destroyed sample "
                "correspondence; wrong pairing is not perturbation "
                "severity."
            ),
            "all": (
                "BDD-OIA internal evidence for this frozen five-seed "
                "protocol only; no CEG, causal, architecture, dataset, "
                "or real-world external validity."
            ),
        },
    }
    write_json(RESULT_PATH, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "decisions": result["decisions"],
                "result": relative(RESULT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
