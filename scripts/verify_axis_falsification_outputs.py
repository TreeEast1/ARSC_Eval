"""Independently reproduce frozen axis contrasts from the compact primitives.

This verifier does not read the original logit caches.  It rebuilds all ten
reported contrasts and the 2,000 crossed-bootstrap intervals from the compact
binary/error/pairing primitives saved by the formal one-shot run.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.internal_validity import macro_f1, percentile_interval
from arsc_eval.rq1 import MODEL_ACTION, MODEL_JOINT
from arsc_eval.utils import write_json


RESULT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_results.json"
)
PRIMITIVES_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_primitives.npz"
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
LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "tmux_arsc_axis_falsification.log"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_reproduction_audit.json"
)
EXPECTED_HASHES = {
    RESULT_PATH: (
        "E0A1802EC426989B2F46FE5DED8F554A0CCAA63CFA5D1011A5F46808A56775EA"
    ),
    POINT_CSV_PATH: (
        "E105F0D46980F2C3BF405D25D24D0A9B107B5085D0C73A840035A1D1C101DEAD"
    ),
    BOOTSTRAP_CSV_PATH: (
        "06E56093815ABC28A7A6572E7D0E62475B23AB6A3ACF232171E93ACE180E84D0"
    ),
    PRIMITIVES_PATH: (
        "D832D136D482377EF013853CC8772A792EEC6EADE20FED627082BF72D2F4E2B7"
    ),
    LOG_PATH: (
        "5B2A9D551927F0E40B10A7224707D93F12AD6EC43EDB6618A446BFF09526D4A9"
    ),
}
SEEDS = (43, 44, 45, 46, 47)
MODELS = (MODEL_ACTION, MODEL_JOINT)
MODEL_STEMS = {
    MODEL_ACTION: "action_only",
    MODEL_JOINT: "joint",
}
THRESHOLD = 0.5
BOOTSTRAP_SEED = 20260802
BOOTSTRAP_REPLICATES = 2000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def aurc(
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


def source_arrays(
    archive: np.lib.npyio.NpzFile,
    seed: int,
) -> dict[str, Any]:
    random_scores = np.asarray(archive["random_scores"])
    result: dict[str, Any] = {
        "action_targets": np.asarray(
            archive["action_targets"]
        ).astype(bool),
        "rationale_targets": np.asarray(
            archive["rationale_targets"]
        ).astype(bool),
        "action_predictions": {},
        "S": {},
        "C1": {},
    }
    rows = np.asarray(archive["target_row_sources"], dtype=np.int64)
    action_columns = np.asarray(
        archive["action_column_sources"], dtype=np.int64
    )
    rationale_columns = np.asarray(
        archive["rationale_column_sources"], dtype=np.int64
    )
    result["action_destroyed"] = result["action_targets"][rows][
        :, action_columns
    ]
    result["rationale_destroyed"] = result["rationale_targets"][rows][
        :, rationale_columns
    ]
    result["rationale_predictions"] = np.asarray(
        archive[f"seed_{seed}_joint_rationale_predictions"]
    ).astype(bool)
    for model in MODELS:
        stem = MODEL_STEMS[model]
        errors = np.asarray(
            archive[f"seed_{seed}_{stem}_exact_set_errors"],
            dtype=np.float64,
        )
        original = np.asarray(
            archive[f"seed_{seed}_{stem}_original_confidence"],
            dtype=np.float64,
        )
        correct = errors == 0.0
        oracle = np.where(
            correct,
            0.75 + 0.25 * random_scores,
            0.25 * random_scores,
        )
        adversarial = np.where(
            ~correct,
            0.75 + 0.25 * random_scores,
            0.25 * random_scores,
        )
        result["action_predictions"][model] = np.asarray(
            archive[f"seed_{seed}_{stem}_action_predictions"]
        ).astype(bool)
        result["S"][model] = {
            "errors": errors,
            "original": original,
            "random": random_scores,
            "oracle": oracle,
            "adversarial": adversarial,
        }
        result["C1"][f"action_correct::{model}"] = np.asarray(
            archive[
                f"seed_{seed}_{stem}_c1_correct_action_mean_three"
            ],
            dtype=np.float64,
        )
        result["C1"][f"action_wrong::{model}"] = np.asarray(
            archive[
                f"seed_{seed}_{stem}_c1_wrong_action_mean_three"
            ],
            dtype=np.float64,
        )
    result["C1"]["rationale_correct"] = np.asarray(
        archive[
            f"seed_{seed}_joint_c1_correct_rationale_mean_three"
        ],
        dtype=np.float64,
    )
    result["C1"]["rationale_wrong"] = np.asarray(
        archive[
            f"seed_{seed}_joint_c1_wrong_rationale_mean_three"
        ],
        dtype=np.float64,
    )
    return result


def contrasts(
    values: dict[str, Any],
    indices: np.ndarray,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for model in MODELS:
        predictions = values["action_predictions"][model]
        original = macro_f1(
            values["action_targets"][indices],
            predictions[indices],
            THRESHOLD,
        )
        destroyed = macro_f1(
            values["action_destroyed"][indices],
            predictions[indices],
            THRESHOLD,
        )
        result[f"A::original_minus_combined::{model}"] = (
            original - destroyed
        )
        safety = values["S"][model]
        result[
            f"S_confidence::random_minus_original::{model}"
        ] = aurc(
            safety["errors"], safety["random"], indices
        ) - aurc(safety["errors"], safety["original"], indices)
        result[
            f"S_measurement::adversarial_minus_oracle::{model}"
        ] = aurc(
            safety["errors"], safety["adversarial"], indices
        ) - aurc(safety["errors"], safety["oracle"], indices)
        result[
            f"C1_action::wrong_minus_correct::{model}"
        ] = float(
            np.mean(
                values["C1"][f"action_wrong::{model}"][indices]
                - values["C1"][f"action_correct::{model}"][indices]
            )
        )
    result[
        f"R::original_minus_combined::{MODEL_JOINT}"
    ] = macro_f1(
        values["rationale_targets"][indices],
        values["rationale_predictions"][indices],
        THRESHOLD,
    ) - macro_f1(
        values["rationale_destroyed"][indices],
        values["rationale_predictions"][indices],
        THRESHOLD,
    )
    result[
        f"C1_rationale::correct_minus_wrong::{MODEL_JOINT}"
    ] = float(
        np.mean(
            values["C1"]["rationale_correct"][indices]
            - values["C1"]["rationale_wrong"][indices]
        )
    )
    return result


def main() -> int:
    checks: list[dict[str, Any]] = []
    for path, expected in EXPECTED_HASHES.items():
        observed = sha256_file(path)
        checks.append(
            {
                "name": f"sha256::{path.name}",
                "passed": observed == expected,
                "expected": expected,
                "observed": observed,
            }
        )

    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    with np.load(PRIMITIVES_PATH, allow_pickle=False) as archive:
        seed_arrays = {
            seed: source_arrays(archive, seed) for seed in SEEDS
        }
        sample_count = len(archive["file_names"])

    all_indices = np.arange(sample_count, dtype=np.int64)
    reproduced_raw = {
        str(seed): contrasts(seed_arrays[seed], all_indices)
        for seed in SEEDS
    }
    reported_raw = result["raw_seed_contrasts"]
    raw_mismatches = {}
    for seed in map(str, SEEDS):
        for name, value in reported_raw[seed].items():
            reproduced = reproduced_raw[seed][name]
            if reproduced != float(value):
                raw_mismatches[f"{seed}::{name}"] = {
                    "reported": value,
                    "reproduced": reproduced,
                    "absolute_difference": abs(reproduced - value),
                }
    checks.append(
        {
            "name": "all_raw_seed_contrasts_exact",
            "passed": not raw_mismatches,
            "detail": raw_mismatches,
        }
    )

    contrast_names = tuple(result["bootstrap_summary"])
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = {
        name: np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
        for name in contrast_names
    }
    for replicate in range(BOOTSTRAP_REPLICATES):
        selected_seeds = rng.choice(
            np.asarray(SEEDS, dtype=np.int64),
            size=len(SEEDS),
            replace=True,
        )
        shared_images = rng.integers(
            0,
            sample_count,
            size=sample_count,
            dtype=np.int64,
        )
        selected_values = {
            int(seed): contrasts(seed_arrays[int(seed)], shared_images)
            for seed in np.unique(selected_seeds)
        }
        for name in contrast_names:
            draws[name][replicate] = float(
                np.mean(
                    [
                        selected_values[int(seed)][name]
                        for seed in selected_seeds
                    ]
                )
            )

    bootstrap_mismatches = {}
    reproduced_summary = {}
    for name in contrast_names:
        raw = [reproduced_raw[str(seed)][name] for seed in SEEDS]
        lower, upper = percentile_interval(draws[name], 0.95)
        reproduced = {
            "mean_across_seeds": float(np.mean(raw)),
            "sd_across_seeds": float(np.std(raw, ddof=1)),
            "positive_seed_count": int(sum(value > 0.0 for value in raw)),
            "crossed_bootstrap_ci": [lower, upper],
        }
        reproduced_summary[name] = reproduced
        reported = result["bootstrap_summary"][name]
        for key in (
            "mean_across_seeds",
            "sd_across_seeds",
            "positive_seed_count",
            "crossed_bootstrap_ci",
        ):
            if reproduced[key] != reported[key]:
                bootstrap_mismatches[f"{name}::{key}"] = {
                    "reported": reported[key],
                    "reproduced": reproduced[key],
                }
    checks.append(
        {
            "name": "crossed_bootstrap_summary_exact",
            "passed": not bootstrap_mismatches,
            "detail": bootstrap_mismatches,
        }
    )

    with POINT_CSV_PATH.open(
        newline="", encoding="utf-8"
    ) as handle:
        point_rows = list(csv.DictReader(handle))
    with BOOTSTRAP_CSV_PATH.open(
        newline="", encoding="utf-8"
    ) as handle:
        bootstrap_rows = list(csv.DictReader(handle))
    log = LOG_PATH.read_text(encoding="utf-8")
    checks.extend(
        [
            {
                "name": "point_csv_row_count",
                "passed": len(point_rows) == 485,
                "detail": len(point_rows),
            },
            {
                "name": "bootstrap_csv_row_count",
                "passed": len(bootstrap_rows) == 10,
                "detail": len(bootstrap_rows),
            },
            {
                "name": "formal_log_completed_2000",
                "passed": (
                    log.count("bootstrap_completed") == 20
                    and '"bootstrap_completed": 2000' in log
                    and log.rstrip().endswith("EXIT_CODE=0")
                ),
                "detail": {
                    "progress_markers": log.count(
                        "bootstrap_completed"
                    ),
                    "exit_code_0": log.rstrip().endswith(
                        "EXIT_CODE=0"
                    ),
                },
            },
        ]
    )
    passed = all(check["passed"] for check in checks)
    audit = {
        "study": "Independent primitive-level reproduction of Round 7",
        "status": "PASS" if passed else "FAIL",
        "formal_outputs_modified": False,
        "original_logit_caches_read": False,
        "model_inference": False,
        "bootstrap": {
            "method": (
                "independent seed resample plus exactly one shared image "
                "multiset per replicate"
            ),
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
        },
        "checks": checks,
        "summary": {
            "passed": int(sum(check["passed"] for check in checks)),
            "total": len(checks),
            "failed": [
                check["name"] for check in checks if not check["passed"]
            ],
        },
        "reproduced_bootstrap_summary": reproduced_summary,
    }
    write_json(OUTPUT_PATH, audit)
    print(
        json.dumps(
            {
                "status": audit["status"],
                "summary": audit["summary"],
                "output": OUTPUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
