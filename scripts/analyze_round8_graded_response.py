"""Run the preregistered Round 8 graded association-response study.

``--preflight-only`` verifies hashes, outcome-blind map/component invariants,
synthetic tests, and the Round 7 q=0 bridge. It does not compute any q>0
response metric or the new real-data tie-averaged primary.

The default mode repeats preflight, refuses to overwrite an existing result,
then performs the single frozen point-estimate and association-component
bootstrap run. No training, inference, threshold selection, or data download
occurs here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.association_components import (
    shared_component_bootstrap_draw,
    validate_association_components,
)
from arsc_eval.axis_falsification import array_sha256
from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.graded_association import validate_graded_maps
from arsc_eval.graded_response import (
    AXIS_DIRECTIONS,
    MODEL_KEYS,
    PERTURBATION_KEYS,
    axis_bottlenecks,
    confidence_diagnostics,
    graded_axis_curves,
    mean_curve_checks,
)
from arsc_eval.internal_validity import (
    action_flip_samples,
    percentile_interval,
    rationale_jaccard_samples,
)
from arsc_eval.metric_validity import selective_metrics_from_confidence
from arsc_eval.metrics import exact_set_errors, multilabel_f1
from arsc_eval.rq1 import (
    MODEL_ACTION,
    MODEL_JOINT,
    prepare_rq1_arrays,
)
from arsc_eval.utils import write_json


SEEDS = (43, 44, 45, 46, 47)
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
Q_KEYS = (
    "q_000_source_indices",
    "q_025_source_indices",
    "q_050_source_indices",
    "q_075_source_indices",
    "q_100_source_indices",
)
MODEL_LABELS = {
    "action_only": MODEL_ACTION,
    "joint": MODEL_JOINT,
}
AXIS_COMPONENT_NAMES = {
    "A": (
        "Action-Only Macro-F1",
        "Joint Action-Rationale Macro-F1",
    ),
    "R": ("Joint Action-Rationale 21-label Macro-F1",),
    "S": (
        "Action-Only tie-averaged AURC",
        "Joint Action-Rationale tie-averaged AURC",
    ),
    "C1": (
        "Action-Only mean-three action flip",
        "Joint Action-Rationale mean-three action flip",
        "Joint Action-Rationale mean-three rationale Jaccard",
    ),
}
THRESHOLD = 0.5
SAMPLE_COUNT = 4557
COMPONENT_COUNT = 1625
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 20260803

PROTOCOL_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_protocol.json"
)
AMENDMENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_protocol_amendment01.json"
)
PREREG_REVIEW_PATH = (
    PROJECT_ROOT / "outputs" / "research_review_memo_round8_preregister.md"
)
AMENDMENT_REVIEW_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "research_review_memo_round8_amendment01.md"
)
MAP_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_maps.npz"
)
MAP_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_association_map_manifest.json"
)
COMPONENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_association_components.npz"
)
COMPONENT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_association_component_manifest.json"
)
ROUND7_RESULT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_results.json"
)
ROUND7_INDEX_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_artifact_index.json"
)
ROUND7_PRIMITIVES_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "arsc_axis_falsification_primitives.npz"
)
ATTEMPT01_FAILURE_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_formal_attempt01_failed.log"
)
ATTEMPT01_REVIEW_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "research_review_memo_round8_attempt01_failure.md"
)
PREFLIGHT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_preflight.json"
)
RUN_MANIFEST_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_run_manifest.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_results.json"
)
POINT_CSV_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_point_estimates.csv"
)
BOOTSTRAP_CSV_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_bootstrap.csv"
)
PRIMITIVES_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round8_graded_response_primitives.npz"
)

FROZEN_HASHES = {
    PROTOCOL_PATH: (
        "B96AC789BA12DD0FE65AF2138C54248C2154C1E1489D911571422EDE94B65357"
    ),
    AMENDMENT_PATH: (
        "D15E6F93FFEF686172F3887BAB609E6DA724ECE975BB125485A717688A020C8A"
    ),
    PREREG_REVIEW_PATH: (
        "83C13D1112ABAF9CBA6504E26BBB0BDBBDD99C5D7A45DB27A840D0A695B65BF2"
    ),
    AMENDMENT_REVIEW_PATH: (
        "CBF47293F5D983772C305B53E7C1DACD056D1609C7BA4F0A3B284BFAEEC9B66A"
    ),
    MAP_PATH: (
        "8685E1A4605B5D6355A432BC6CA03CF61930BAB23D41D899478A5C1D8FC47ED1"
    ),
    MAP_MANIFEST_PATH: (
        "73B89C3438262BA272E0E90EDC2A6F9408B196CCBD4A30D9FA6FFFA798C273DC"
    ),
    COMPONENT_PATH: (
        "F1DF45A526EEBE02C2CDA6EA2FB1FE8B034A3FDD3B1582B3598B602916CDD0E8"
    ),
    COMPONENT_MANIFEST_PATH: (
        "7E5EA6AB9E83A0CCE03FDBBBAC274AB01D1B7773CA43833348C77ED71127653F"
    ),
    ROUND7_RESULT_PATH: (
        "E0A1802EC426989B2F46FE5DED8F554A0CCAA63CFA5D1011A5F46808A56775EA"
    ),
    ROUND7_INDEX_PATH: (
        "1A3B27102F3497A987E344B04BB723B3992383DF7943C7C006290D9BC2EF8C74"
    ),
    ROUND7_PRIMITIVES_PATH: (
        "D832D136D482377EF013853CC8772A792EEC6EADE20FED627082BF72D2F4E2B7"
    ),
}
CACHE_HASHES = {
    43: "0794249465A4EFEDB5177E8B74CC76C4537B4044411EE17E7BACBC66FA6E47A3",
    44: "BA2D0E2061158358BE5D5B3D68AAFDA7FF57E7C571C0C679502A9CC9C6ADB465",
    45: "A7C179876FC3C57F06D3D7A9FE8EDFA286B6667C1B125933F8E350F657AD1187",
    46: "1EA70BC6F3D59D9B07D28369982D271FA3951E97FFFE1870A3E7C7530054EAD0",
    47: "7DDE8E4ACDFA06004ADE4AF33C679EC2A53E9F689B214A2ED36EDF91598AF743",
}
CALIBRATION_HASHES = {
    43: {
        "action_only": "42BED1E43902103AB37864FFA7F48CDD2516C59205FE810AB461511095AA7AD0",
        "joint": "A8A9AD227BAB110778E3D49F8BA78BAB21500FD3ECAEE7280763C6AF25CC137F",
    },
    44: {
        "action_only": "F670A6EE78230DE9856DA3BFEDA16DF59C8C02E2962F4518C651DA5560D6C6CF",
        "joint": "89B07811122FE266C79541AD00AA1BEFFCE6E466CCB8B7D2E34D8B5E73A8B19B",
    },
    45: {
        "action_only": "E8E01FE05656BDCB188700875609E1FFDF16B5C62FB99658F89B0CB983DD913F",
        "joint": "817A007E33AF09AE1DBBF1C3B45216D427C116A15E2DC4A172E5DE8C897857FB",
    },
    46: {
        "action_only": "D7C8C90570D357EA144642F4628538D6D2B1B61F018302AFB248FD82507698BE",
        "joint": "F9935A65A0B187373FC16742207720D54C41C46071A1498393985ABB18E5E29A",
    },
    47: {
        "action_only": "E9FCAF432BC857AB3A4CEF69403975D6B22D86DD52A2540E65B96C9C1F9B07EB",
        "joint": "06E05CA5334EBF74DCBE72829133A31707CFA94FADDA0FE6BE38F249E3A86101",
    },
}
COMMON_ARRAY_HASHES = {
    "test_file_names": (
        "9D9D4E74272AB3A71390B4204CE56F1831350A29EED009111EF1AD5A29026DF6"
    ),
    "test_action_targets": (
        "C28063DE57B7E4CAF8B1A19C074BB5F1DF05C4984377856EDF2522387CEB7A39"
    ),
    "test_rationale_targets": (
        "F787A947EC2ECA728166DC83B621402EDE27CAF7DDB1E7C3D3BBDD36B2BED469"
    ),
}
SOURCE_HASHES = {
    "q_000_source_indices": (
        "AECED390CC5B008AFFAE6274401884BE7A455A5C793F1C1105CA812C89323F3F"
    ),
    "q_025_source_indices": (
        "03C88BA66A9F11075C7562994B4B3837E8AACB6474D2DD4B563D673E3BFE2F9B"
    ),
    "q_050_source_indices": (
        "A14CE26622F4306EA718037858CBE8C1DD8018168F157A6E5615D68883E2119F"
    ),
    "q_075_source_indices": (
        "3D89FFDAB4AE0FD5121D498F72AB071881620D89118CBED7A4426EEB1B657A00"
    ),
    "q_100_source_indices": (
        "CEF0D9B1E82DCECC6B4D31C1664DD868E7B64FA6F065244A6539D27C1CE2D446"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="verify frozen inputs and q=0 bridge without q>0 outcomes",
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
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
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


def calibration_temperature(path: Path, model_key: str) -> float:
    data = read_json(path)
    if data["model_type"] != model_key:
        raise RuntimeError(f"calibration model mismatch at {relative(path)}")
    value = float(data["temperature"])
    if not np.isfinite(value) or value <= 0:
        raise RuntimeError(f"invalid calibration at {relative(path)}")
    return value


def cache_path(seed: int) -> Path:
    return (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / f"rq1_seed_{seed}"
        / "prediction_cache"
        / "rq1_lossless.npz"
    )


def calibration_path(seed: int, model_key: str) -> Path:
    return (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / f"rq1_seed_{seed}"
        / f"calibration_{model_key}.json"
    )


def load_maps_and_components() -> tuple[
    np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]
]:
    with np.load(MAP_PATH, allow_pickle=False) as archive:
        file_names = archive["file_names"].copy()
        maps = {key: archive[key].copy() for key in Q_KEYS}
        clip_group_ids = archive["clip_group_ids"].copy()
    with np.load(COMPONENT_PATH, allow_pickle=False) as archive:
        components = {
            key: archive[key].copy() for key in archive.files
        }
    components["clip_group_ids"] = clip_group_ids
    source_maps = np.stack([maps[key] for key in Q_KEYS])
    return file_names, {"stacked": source_maps, **maps}, components


def load_seed(seed: int) -> dict[str, Any]:
    path = cache_path(seed)
    with np.load(path, allow_pickle=False) as archive:
        cache = {key: archive[key].copy() for key in archive.files}
    temperatures = {
        model: calibration_temperature(
            calibration_path(seed, model), model
        )
        for model in MODEL_KEYS
    }
    rq1 = prepare_rq1_arrays(
        cache, temperatures["action_only"], temperatures["joint"]
    )
    primitive = {
        "action_targets": rq1["action_targets"].astype(bool),
        "rationale_targets": rq1["rationale_targets"].astype(bool),
        "action_predictions": {
            "action_only": (
                rq1["raw_clean"][MODEL_ACTION] >= THRESHOLD
            ),
            "joint": rq1["raw_clean"][MODEL_JOINT] >= THRESHOLD,
        },
        "rationale_predictions": (
            rq1["rationale_clean"] >= THRESHOLD
        ),
        "exact_set_errors": {},
        "confidence": {},
        "action_perturbed_predictions": {},
        "rationale_perturbed_predictions": {},
    }
    calibrated_by_key = {
        "action_only": rq1["calibrated_clean"][MODEL_ACTION],
        "joint": rq1["calibrated_clean"][MODEL_JOINT],
    }
    for model in MODEL_KEYS:
        primitive["exact_set_errors"][model] = exact_set_errors(
            primitive["action_targets"],
            calibrated_by_key[model],
            THRESHOLD,
        )
        primitive["confidence"][model] = calibrated_by_key[model].max(
            axis=1
        )
    for perturbation in PERTURBATION_KEYS:
        primitive["action_perturbed_predictions"][perturbation] = {
            "action_only": (
                rq1["raw_perturbed"][perturbation][MODEL_ACTION]
                >= THRESHOLD
            ),
            "joint": (
                rq1["raw_perturbed"][perturbation][MODEL_JOINT]
                >= THRESHOLD
            ),
        }
        primitive["rationale_perturbed_predictions"][perturbation] = (
            rq1["rationale_perturbed"][perturbation] >= THRESHOLD
        )
    return {
        "seed": seed,
        "path": path,
        "cache": cache,
        "temperatures": temperatures,
        "rq1": rq1,
        "primitive": primitive,
        "calibrated_by_key": calibrated_by_key,
    }


def multilabel_detail(
    targets: np.ndarray,
    predictions: np.ndarray,
    names: list[str],
) -> dict[str, Any]:
    result = multilabel_f1(
        targets, predictions.astype(np.float64), names, THRESHOLD
    )
    result["target_positive_count"] = {
        name: int(targets[:, index].astype(bool).sum())
        for index, name in enumerate(names)
    }
    result["predicted_positive_count"] = {
        name: int(predictions[:, index].astype(bool).sum())
        for index, name in enumerate(names)
    }
    return result


def c1_point_detail(
    primitive: dict[str, Any],
    source: np.ndarray,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action": {},
        "rationale": {},
    }
    for model in MODEL_KEYS:
        clean = primitive["action_predictions"][model]
        values = {}
        for perturbation in PERTURBATION_KEYS:
            perturbed = primitive["action_perturbed_predictions"][
                perturbation
            ][model]
            values[perturbation] = float(
                action_flip_samples(
                    clean, perturbed[source], THRESHOLD
                ).mean()
            )
        values["mean_three"] = float(
            np.mean([values[key] for key in PERTURBATION_KEYS])
        )
        result["action"][model] = values
    rationale_clean = primitive["rationale_predictions"]
    rationale_values = {}
    for perturbation in PERTURBATION_KEYS:
        perturbed = primitive["rationale_perturbed_predictions"][
            perturbation
        ]
        rationale_values[perturbation] = float(
            rationale_jaccard_samples(
                rationale_clean, perturbed[source], THRESHOLD
            ).mean()
        )
    rationale_values["mean_three"] = float(
        np.mean(
            [rationale_values[key] for key in PERTURBATION_KEYS]
        )
    )
    result["rationale"]["joint"] = rationale_values
    return result


def run_synthetic_tests() -> dict[str, Any]:
    suite_paths = [
        PROJECT_ROOT / "tests" / "test_graded_response.py",
        PROJECT_ROOT / "tests" / "test_association_components.py",
        PROJECT_ROOT / "tests" / "test_graded_association.py",
    ]
    command = [
        sys.executable,
        "-m",
        "pytest",
        *[relative(path) for path in suite_paths],
        "-q",
    ]
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src") + (
        os.pathsep + existing if existing else ""
    )
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": command,
        "suite_sha256": {
            relative(path): sha256_file(path) for path in suite_paths
        },
        "deterministic_summary": (
            "PASS" if completed.returncode == 0 else "FAIL"
        ),
    }
    if completed.returncode != 0:
        result["failure_stdout"] = completed.stdout.strip()
        result["failure_stderr"] = completed.stderr.strip()
    return result


def git_last_commit(paths: list[Path]) -> str | None:
    completed = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            *[relative(path) for path in paths],
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() or None


def run_preflight() -> tuple[
    dict[str, Any],
    dict[int, dict[str, Any]],
    np.ndarray,
    dict[str, np.ndarray],
]:
    checks: list[dict[str, Any]] = []
    for path, expected in FROZEN_HASHES.items():
        observed = sha256_file(path)
        append_check(
            checks,
            f"frozen_hash::{relative(path)}",
            observed == expected,
            {"expected": expected, "observed": observed},
        )

    amendment_review = AMENDMENT_REVIEW_PATH.read_text(encoding="utf-8")
    attempt01_review = ATTEMPT01_REVIEW_PATH.read_text(encoding="utf-8")
    governance_detail = {
        "amendment_GO_memo_sha256": sha256_file(
            AMENDMENT_REVIEW_PATH
        ),
        "attempt01_failed_log_expected_sha256": (
            "E3D3D58FF47663F7031AA85963D3AA81702BA4CA21F35C60DA77DEEA10E95296"
        ),
        "attempt01_failed_log_observed_sha256": sha256_file(
            ATTEMPT01_FAILURE_PATH
        ),
        "attempt01_GO_RERUN_memo_expected_sha256": (
            "9E051D174D3DC4117C6F4F9005EE03791CF297E0E5495E0C38953D6BA3ED54B8"
        ),
        "attempt01_GO_RERUN_memo_observed_sha256": sha256_file(
            ATTEMPT01_REVIEW_PATH
        ),
    }
    append_check(
        checks,
        "independent_reviews_and_attempt01_binding",
        "\n**GO**" in amendment_review
        and "没有读取、运行或推导任何 q-response metric outcome"
        in amendment_review
        and "\n**GO_RERUN**" in attempt01_review
        and governance_detail[
            "attempt01_failed_log_expected_sha256"
        ]
        == governance_detail["attempt01_failed_log_observed_sha256"]
        and governance_detail[
            "attempt01_GO_RERUN_memo_expected_sha256"
        ]
        == governance_detail[
            "attempt01_GO_RERUN_memo_observed_sha256"
        ],
        governance_detail,
    )

    file_names, maps, components = load_maps_and_components()
    source_maps = maps["stacked"]
    for key in Q_KEYS:
        append_check(
            checks,
            f"source_hash::{key}",
            array_sha256(maps[key]) == SOURCE_HASHES[key],
            array_sha256(maps[key]),
        )
    map_audit = validate_graded_maps(
        file_names,
        {q: source_maps[index] for index, q in enumerate(Q_VALUES)},
    )
    expected_active = [0, 1140, 2278, 3418, 4557]
    observed_active = [
        map_audit["by_severity"][str(q)]["active_images"]
        for q in Q_VALUES
    ]
    append_check(
        checks,
        "graded_map_exact_invariants",
        map_audit["all_passed"] and observed_active == expected_active,
        {
            "all_passed": map_audit["all_passed"],
            "active_images": observed_active,
        },
    )

    component_audit = validate_association_components(
        components["clip_group_ids"],
        {key: maps[key] for key in Q_KEYS},
        components["component_id_by_clip"],
        components["component_id_by_image"],
    )
    expected_clip_hist = {
        "2": 1191,
        "3": 291,
        "4": 101,
        "5": 22,
        "6": 7,
        "7": 11,
        "8": 2,
    }
    append_check(
        checks,
        "association_component_exact_invariants",
        (
            component_audit["all_maps_passed"]
            and component_audit["component_count"] == COMPONENT_COUNT
            and component_audit["clip_count_histogram"]
            == expected_clip_hist
            and component_audit["maximum_images_per_component"] == 14
        ),
        component_audit,
    )
    component_manifest = read_json(COMPONENT_MANIFEST_PATH)
    array_hash_mismatches = {}
    for key, spec in component_manifest["arrays"].items():
        observed = array_sha256(components[key])
        if observed != spec["sha256"]:
            array_hash_mismatches[key] = {
                "expected": spec["sha256"],
                "observed": observed,
            }
    append_check(
        checks,
        "component_array_hashes",
        not array_hash_mismatches,
        array_hash_mismatches,
    )

    seed_data = {seed: load_seed(seed) for seed in SEEDS}
    round7 = read_json(ROUND7_RESULT_PATH)
    with np.load(ROUND7_PRIMITIVES_PATH, allow_pickle=False) as archive:
        round7_primitives = {
            key: archive[key].copy() for key in archive.files
        }

    canonical = seed_data[SEEDS[0]]["cache"]
    for key, expected in COMMON_ARRAY_HASHES.items():
        append_check(
            checks,
            f"common_array_hash::{key}",
            array_sha256(canonical[key]) == expected,
            array_sha256(canonical[key]),
        )
    append_check(
        checks,
        "map_filename_order_equals_cache",
        np.array_equal(file_names, canonical["test_file_names"]),
        {"samples": len(file_names)},
    )

    canonical_targets = {
        "action": canonical["test_action_targets"],
        "rationale": canonical["test_rationale_targets"],
    }
    original_cache_hashes = {
        seed: {
            key: array_sha256(value)
            for key, value in data["cache"].items()
        }
        for seed, data in seed_data.items()
    }
    for seed, data in seed_data.items():
        append_check(
            checks,
            f"seed_{seed}_cache_hash",
            sha256_file(data["path"]) == CACHE_HASHES[seed],
            sha256_file(data["path"]),
        )
        for model in MODEL_KEYS:
            path = calibration_path(seed, model)
            append_check(
                checks,
                f"seed_{seed}_{model}_calibration_hash",
                sha256_file(path) == CALIBRATION_HASHES[seed][model],
                sha256_file(path),
            )
        common_equal = {
            "file_names": np.array_equal(
                canonical["test_file_names"],
                data["cache"]["test_file_names"],
            ),
            "action_targets": np.array_equal(
                canonical_targets["action"],
                data["cache"]["test_action_targets"],
            ),
            "rationale_targets": np.array_equal(
                canonical_targets["rationale"],
                data["cache"]["test_rationale_targets"],
            ),
        }
        append_check(
            checks,
            f"seed_{seed}_common_arrays_equal",
            all(common_equal.values()),
            common_equal,
        )

        primitive = data["primitive"]
        raw_calibrated_prediction_equal = {}
        for model, label in MODEL_LABELS.items():
            calibrated_prediction = (
                data["calibrated_by_key"][model] >= THRESHOLD
            )
            raw_calibrated_prediction_equal[model] = np.array_equal(
                calibrated_prediction,
                primitive["action_predictions"][model],
            )
            confidence = primitive["confidence"][model]
            errors = primitive["exact_set_errors"][model]
            invariant = {
                "finite": bool(
                    np.all(np.isfinite(confidence))
                    and np.all(np.isfinite(errors))
                ),
                "confidence_range": bool(
                    np.all((confidence >= 0.0) & (confidence <= 1.0))
                ),
                "binary_errors": bool(np.all(np.isin(errors, (0.0, 1.0)))),
                "has_correct_and_error": bool(
                    np.any(errors == 0.0) and np.any(errors == 1.0)
                ),
            }
            append_check(
                checks,
                f"seed_{seed}_{model}_S_primitive_invariants",
                all(invariant.values()),
                invariant,
            )
        append_check(
            checks,
            f"seed_{seed}_raw_calibrated_predictions_equal",
            all(raw_calibrated_prediction_equal.values()),
            raw_calibrated_prediction_equal,
        )

        prevalence_checks = {}
        confidence_checks = {}
        for q_index, q in enumerate(Q_VALUES):
            source = source_maps[q_index]
            prevalence_checks[str(q)] = {
                "action": np.array_equal(
                    canonical_targets["action"][source].sum(axis=0),
                    canonical_targets["action"].sum(axis=0),
                ),
                "rationale": np.array_equal(
                    canonical_targets["rationale"][source].sum(axis=0),
                    canonical_targets["rationale"].sum(axis=0),
                ),
            }
            confidence_checks[str(q)] = {
                model: np.array_equal(
                    np.sort(primitive["confidence"][model][source]),
                    np.sort(primitive["confidence"][model]),
                )
                for model in MODEL_KEYS
            }
        append_check(
            checks,
            f"seed_{seed}_q_multisets_preserved",
            all(
                all(values.values())
                for values in prevalence_checks.values()
            )
            and all(
                all(values.values())
                for values in confidence_checks.values()
            ),
            {
                "target_prevalence": prevalence_checks,
                "confidence": confidence_checks,
            },
        )

        reference = round7["point_estimates_by_seed"][str(seed)]
        action_mismatch = {}
        for model, label in MODEL_LABELS.items():
            observed = multilabel_detail(
                primitive["action_targets"],
                primitive["action_predictions"][model],
                list(ACTION_NAMES),
            )
            expected = reference["A"][label]["original"]
            if observed != expected:
                action_mismatch[model] = {
                    "observed": observed,
                    "expected": expected,
                }
        append_check(
            checks,
            f"seed_{seed}_q0_A_exact_round7",
            not action_mismatch,
            action_mismatch,
        )

        observed_rationale = multilabel_detail(
            primitive["rationale_targets"],
            primitive["rationale_predictions"],
            list(RATIONALE_NAMES),
        )
        expected_rationale = reference["R"][MODEL_JOINT]["original"]
        append_check(
            checks,
            f"seed_{seed}_q0_R_exact_round7",
            observed_rationale == expected_rationale,
            (
                {}
                if observed_rationale == expected_rationale
                else {
                    "observed": observed_rationale,
                    "expected": expected_rationale,
                }
            ),
        )

        q0_c1 = c1_point_detail(
            primitive, np.arange(SAMPLE_COUNT, dtype=np.int64)
        )
        c1_mismatch = {}
        for model, label in MODEL_LABELS.items():
            expected = reference["C1"]["action"][label]["correct"]
            observed = q0_c1["action"][model]
            if observed != expected:
                c1_mismatch[f"action::{model}"] = {
                    "observed": observed,
                    "expected": expected,
                }
        expected = reference["C1"]["rationale"][MODEL_JOINT]["correct"]
        observed = q0_c1["rationale"]["joint"]
        if observed != expected:
            c1_mismatch["rationale::joint"] = {
                "observed": observed,
                "expected": expected,
            }
        append_check(
            checks,
            f"seed_{seed}_q0_C1_exact_round7",
            not c1_mismatch,
            c1_mismatch,
        )

        s_mismatch = {}
        for model, label in MODEL_LABELS.items():
            estimates = selective_metrics_from_confidence(
                primitive["action_targets"],
                data["calibrated_by_key"][model],
                primitive["confidence"][model],
                THRESHOLD,
            )
            estimates.pop("risk_curve")
            expected = reference["S"][label]["original"]
            for metric in (
                "aurc",
                "unsafe_acceptance_rate_90",
                "correctness_auroc",
                "ece",
                "exact_set_error_rate",
                "highest_confidence_decile_error_rate",
                "lowest_confidence_decile_error_rate",
            ):
                if estimates[metric] != expected[metric]:
                    s_mismatch[f"{model}::{metric}"] = {
                        "observed": estimates[metric],
                        "expected": expected[metric],
                    }
            stem = model
            primitive_pairs = {
                "prediction": (
                    primitive["action_predictions"][model],
                    round7_primitives[
                        f"seed_{seed}_{stem}_action_predictions"
                    ],
                ),
                "error": (
                    primitive["exact_set_errors"][model],
                    round7_primitives[
                        f"seed_{seed}_{stem}_exact_set_errors"
                    ],
                ),
                "confidence": (
                    primitive["confidence"][model],
                    round7_primitives[
                        f"seed_{seed}_{stem}_original_confidence"
                    ],
                ),
            }
            for name, (left, right) in primitive_pairs.items():
                if not np.array_equal(left, right):
                    s_mismatch[f"{model}::primitive::{name}"] = False
        append_check(
            checks,
            f"seed_{seed}_q0_S_stable_and_primitives_exact_round7",
            not s_mismatch,
            s_mismatch,
        )

    final_cache_hashes = {
        seed: {
            key: array_sha256(value)
            for key, value in data["cache"].items()
        }
        for seed, data in seed_data.items()
    }
    mutation_mismatches = {
        str(seed): [
            key
            for key, digest in original_cache_hashes[seed].items()
            if final_cache_hashes[seed][key] != digest
        ]
        for seed in SEEDS
    }
    append_check(
        checks,
        "no_cache_array_mutation",
        all(not values for values in mutation_mismatches.values()),
        mutation_mismatches,
    )

    synthetic = run_synthetic_tests()
    append_check(
        checks,
        "frozen_synthetic_tests",
        synthetic["passed"],
        synthetic,
    )

    audit = {
        "study": "Round 8 graded response pre-outcome exact audit",
        "status": "PASS" if all(row["passed"] for row in checks) else "STOP",
        "q_greater_than_zero_metric_outcomes_computed": False,
        "real_data_tie_averaged_primary_computed": False,
        "q0_bridge_scope": (
            "Round 7 A/R/correct-pair C1 point estimates, S primitives, "
            "and canonical-stable S diagnostics only"
        ),
        "checks": checks,
        "summary": {
            "passed": int(sum(row["passed"] for row in checks)),
            "total": len(checks),
            "failed_names": [
                row["name"] for row in checks if not row["passed"]
            ],
        },
        "map_audit": map_audit,
        "component_audit": component_audit,
        "claim_boundary": (
            "A PASS authorizes exactly one frozen Round 8 outcome run; "
            "it is not an empirical graded-response result."
        ),
    }
    write_json(PREFLIGHT_PATH, audit)

    implementation_paths = [
        Path(__file__).resolve(),
        PROJECT_ROOT / "src" / "arsc_eval" / "graded_response.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "association_components.py",
        PROJECT_ROOT / "tests" / "test_graded_response.py",
        PROJECT_ROOT / "tests" / "test_association_components.py",
        PROJECT_ROOT / "tests" / "test_graded_association.py",
    ]
    input_manifest: dict[str, Any] = {}
    for seed in SEEDS:
        item = {
            "cache": {
                "path": relative(cache_path(seed)),
                "sha256": sha256_file(cache_path(seed)),
            }
        }
        for model in MODEL_KEYS:
            path = calibration_path(seed, model)
            item[model] = {
                "path": relative(path),
                "sha256": sha256_file(path),
            }
        input_manifest[str(seed)] = item
    manifest = {
        "study": "Round 8 immutable pre-outcome implementation/input manifest",
        "status": (
            "PRE_OUTCOME_PREFLIGHT_PASSED"
            if audit["status"] == "PASS"
            else "STOP"
        ),
        "q_greater_than_zero_metric_outcomes_computed": False,
        "real_data_tie_averaged_primary_computed": False,
        "frozen_artifacts": {
            relative(path): sha256_file(path) for path in FROZEN_HASHES
        },
        "failed_attempt01": {
            "failed_log": {
                "path": relative(ATTEMPT01_FAILURE_PATH),
                "sha256": sha256_file(ATTEMPT01_FAILURE_PATH),
            },
            "independent_GO_RERUN_review": {
                "path": relative(ATTEMPT01_REVIEW_PATH),
                "sha256": sha256_file(ATTEMPT01_REVIEW_PATH),
            },
            "formal_result_artifacts_written": False,
            "authorized_correction": (
                "canonical Round 7 C1 reduction order plus deterministic "
                "synthetic-test audit detail"
            ),
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
        "inputs": input_manifest,
        "frozen_parameters": {
            "seeds": list(SEEDS),
            "q_values": list(Q_VALUES),
            "sample_count": SAMPLE_COUNT,
            "threshold": THRESHOLD,
            "bootstrap_unit": "association component",
            "association_components": COMPONENT_COUNT,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bottleneck_order": (
                "minimum adjacent expected-direction step within each "
                "selected seed, then mean across five selected seeds"
            ),
        },
    }
    write_json(RUN_MANIFEST_PATH, manifest)
    if audit["status"] != "PASS":
        raise RuntimeError(
            "Round 8 pre-outcome exact audit failed; formal analysis STOP"
        )
    return audit, seed_data, source_maps, components


def append_metric_row(
    rows: list[dict[str, Any]],
    seed: int,
    axis: str,
    model: str,
    q: float,
    metric: str,
    estimate: float | None,
    gate_component: bool,
    direction: str,
) -> None:
    rows.append(
        {
            "seed": seed,
            "axis": axis,
            "model": model,
            "q": q,
            "metric": metric,
            "estimate": estimate,
            "gate_component": gate_component,
            "expected_direction": direction,
        }
    )


def point_outcomes(
    seed_data: dict[int, dict[str, Any]],
    source_maps: np.ndarray,
) -> tuple[
    dict[str, Any],
    dict[int, dict[str, np.ndarray]],
    list[dict[str, Any]],
]:
    outcomes: dict[str, Any] = {}
    curves_by_seed: dict[int, dict[str, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    for seed, data in seed_data.items():
        primitive = data["primitive"]
        curves = graded_axis_curves(primitive, source_maps)
        curves_by_seed[seed] = curves
        result: dict[str, Any] = {
            "A": {model: [] for model in MODEL_KEYS},
            "R": {"joint": []},
            "S": {model: [] for model in MODEL_KEYS},
            "C1": {"action": {model: [] for model in MODEL_KEYS}, "rationale": {"joint": []}},
            "primary_curves": {
                axis: values.tolist() for axis, values in curves.items()
            },
            "axis_bottlenecks": axis_bottlenecks(curves),
        }
        for q_index, q in enumerate(Q_VALUES):
            source = source_maps[q_index]
            for model_index, model in enumerate(MODEL_KEYS):
                detail = multilabel_detail(
                    primitive["action_targets"][source],
                    primitive["action_predictions"][model],
                    list(ACTION_NAMES),
                )
                result["A"][model].append({"q": q, **detail})
                append_metric_row(
                    rows,
                    seed,
                    "A",
                    model,
                    q,
                    "macro_f1",
                    detail["macro_f1"],
                    True,
                    "decreasing",
                )
                append_metric_row(
                    rows,
                    seed,
                    "A",
                    model,
                    q,
                    "micro_f1",
                    detail["micro_f1"],
                    False,
                    "diagnostic_only",
                )
                for name, value in detail["per_class_f1"].items():
                    append_metric_row(
                        rows,
                        seed,
                        "A",
                        model,
                        q,
                        f"per_class_f1::{name}",
                        value,
                        False,
                        "diagnostic_only",
                    )
                if detail["macro_f1"] != curves["A"][model_index, q_index]:
                    raise RuntimeError("A point/curve implementation mismatch")

            rationale_detail = multilabel_detail(
                primitive["rationale_targets"][source],
                primitive["rationale_predictions"],
                list(RATIONALE_NAMES),
            )
            result["R"]["joint"].append({"q": q, **rationale_detail})
            append_metric_row(
                rows,
                seed,
                "R",
                "joint",
                q,
                "macro_f1",
                rationale_detail["macro_f1"],
                True,
                "decreasing",
            )
            append_metric_row(
                rows,
                seed,
                "R",
                "joint",
                q,
                "micro_f1",
                rationale_detail["micro_f1"],
                False,
                "diagnostic_only",
            )
            for name, value in rationale_detail["per_class_f1"].items():
                append_metric_row(
                    rows,
                    seed,
                    "R",
                    "joint",
                    q,
                    f"per_class_f1::{name}",
                    value,
                    False,
                    "diagnostic_only",
                )
            if rationale_detail["macro_f1"] != curves["R"][0, q_index]:
                raise RuntimeError("R point/curve implementation mismatch")

            for model_index, model in enumerate(MODEL_KEYS):
                diagnostics = confidence_diagnostics(
                    primitive["exact_set_errors"][model],
                    primitive["confidence"][model][source],
                )
                result["S"][model].append({"q": q, **diagnostics})
                for metric, value in diagnostics.items():
                    append_metric_row(
                        rows,
                        seed,
                        "S",
                        model,
                        q,
                        metric,
                        value,
                        metric == "tie_averaged_aurc",
                        (
                            "increasing"
                            if metric == "tie_averaged_aurc"
                            else "diagnostic_only"
                        ),
                    )
                if (
                    diagnostics["tie_averaged_aurc"]
                    != curves["S"][model_index, q_index]
                ):
                    raise RuntimeError("S point/curve implementation mismatch")

            c1 = c1_point_detail(primitive, source)
            for model_index, model in enumerate(MODEL_KEYS):
                result["C1"]["action"][model].append(
                    {"q": q, **c1["action"][model]}
                )
                for metric, value in c1["action"][model].items():
                    append_metric_row(
                        rows,
                        seed,
                        "C1",
                        model,
                        q,
                        f"action_flip::{metric}",
                        value,
                        metric == "mean_three",
                        (
                            "increasing"
                            if metric == "mean_three"
                            else "diagnostic_only"
                        ),
                    )
                if (
                    c1["action"][model]["mean_three"]
                    != curves["C1"][model_index, q_index]
                ):
                    raise RuntimeError(
                        "C1 action point/curve implementation mismatch"
                    )
            result["C1"]["rationale"]["joint"].append(
                {"q": q, **c1["rationale"]["joint"]}
            )
            for metric, value in c1["rationale"]["joint"].items():
                append_metric_row(
                    rows,
                    seed,
                    "C1",
                    "joint",
                    q,
                    f"rationale_jaccard::{metric}",
                    value,
                    metric == "mean_three",
                    (
                        "decreasing"
                        if metric == "mean_three"
                        else "diagnostic_only"
                    ),
                )
            if (
                c1["rationale"]["joint"]["mean_three"]
                != curves["C1"][2, q_index]
            ):
                raise RuntimeError(
                    "C1 rationale point/curve implementation mismatch"
                )
        outcomes[str(seed)] = result
    return outcomes, curves_by_seed, rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_primitives(
    seed_data: dict[int, dict[str, Any]],
    source_maps: np.ndarray,
    components: dict[str, np.ndarray],
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
        "source_maps": source_maps.astype(np.int64),
        "component_image_offsets": components[
            "component_image_offsets"
        ].astype(np.int64),
        "component_image_indices": components[
            "component_image_indices"
        ].astype(np.int64),
        "component_id_by_image": components[
            "component_id_by_image"
        ].astype(np.int64),
    }
    for seed, data in seed_data.items():
        primitive = data["primitive"]
        for model in MODEL_KEYS:
            arrays[f"seed_{seed}_{model}_action_predictions"] = (
                primitive["action_predictions"][model].astype(np.uint8)
            )
            arrays[f"seed_{seed}_{model}_exact_set_errors"] = primitive[
                "exact_set_errors"
            ][model].astype(np.uint8)
            arrays[f"seed_{seed}_{model}_confidence"] = primitive[
                "confidence"
            ][model].astype(np.float64)
            for perturbation in PERTURBATION_KEYS:
                arrays[
                    f"seed_{seed}_{model}_{perturbation}_action_predictions"
                ] = primitive["action_perturbed_predictions"][
                    perturbation
                ][model].astype(np.uint8)
        arrays[f"seed_{seed}_joint_rationale_predictions"] = primitive[
            "rationale_predictions"
        ].astype(np.uint8)
        for perturbation in PERTURBATION_KEYS:
            arrays[
                f"seed_{seed}_joint_{perturbation}_rationale_predictions"
            ] = primitive["rationale_perturbed_predictions"][
                perturbation
            ].astype(np.uint8)
    np.savez_compressed(PRIMITIVES_PATH, **arrays)
    return {
        "path": relative(PRIMITIVES_PATH),
        "sha256": sha256_file(PRIMITIVES_PATH),
        "bytes": PRIMITIVES_PATH.stat().st_size,
        "array_count": len(arrays),
        "contains_pixels_or_model_weights": False,
        "sufficient_for": (
            "independent reproduction of all point curves, raw seed "
            "bottlenecks, and the exact association-component bootstrap"
        ),
    }


def run_bootstrap(
    seed_data: dict[int, dict[str, Any]],
    source_maps: np.ndarray,
    components: dict[str, np.ndarray],
    curves_by_seed: dict[int, dict[str, np.ndarray]],
    replicates: int,
    bootstrap_seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]]]:
    rng = np.random.default_rng(bootstrap_seed)
    draws = {
        axis: np.empty(replicates, dtype=np.float64)
        for axis in AXIS_DIRECTIONS
    }
    primitive_by_position = [
        seed_data[seed]["primitive"] for seed in SEEDS
    ]
    offsets = components["component_image_offsets"]
    flat_images = components["component_image_indices"]
    image_counts = np.empty(replicates, dtype=np.int64)
    for replicate in range(replicates):
        selected_seeds, selected_components, shared_images = (
            shared_component_bootstrap_draw(
                rng,
                len(SEEDS),
                offsets,
                flat_images,
            )
        )
        image_counts[replicate] = len(shared_images)
        per_position = {}
        for position in np.unique(selected_seeds):
            curves = graded_axis_curves(
                primitive_by_position[int(position)],
                source_maps,
                shared_images,
            )
            per_position[int(position)] = axis_bottlenecks(curves)
        for axis in AXIS_DIRECTIONS:
            draws[axis][replicate] = float(
                np.mean(
                    [
                        per_position[int(position)][axis]
                        for position in selected_seeds
                    ]
                )
            )
        if (replicate + 1) % 100 == 0:
            print(
                json.dumps(
                    {
                        "bootstrap_completed": replicate + 1,
                        "bootstrap_total": replicates,
                        "shared_component_draws": len(
                            selected_components
                        ),
                        "shared_images": len(shared_images),
                    }
                ),
                flush=True,
            )

    full_curves = [curves_by_seed[seed] for seed in SEEDS]
    mean_checks = mean_curve_checks(full_curves)
    raw_by_seed = {
        str(seed): axis_bottlenecks(curves_by_seed[seed])
        for seed in SEEDS
    }
    summaries: dict[str, dict[str, Any]] = {}
    for axis in AXIS_DIRECTIONS:
        raw = [raw_by_seed[str(seed)][axis] for seed in SEEDS]
        lower, upper = percentile_interval(draws[axis], 0.95)
        subgates = {
            "positive_five_seed_mean": bool(np.mean(raw) > 0.0),
            "at_least_four_positive_seeds": (
                sum(value > 0.0 for value in raw) >= 4
            ),
            "pointwise_ci_lower_positive": lower > 0.0,
            "mean_component_curves_no_reversal": mean_checks[axis],
        }
        summaries[axis] = {
            "mean_across_seeds": float(np.mean(raw)),
            "sd_across_seeds": float(np.std(raw, ddof=1)),
            "raw_by_seed": {
                str(seed): raw_by_seed[str(seed)][axis] for seed in SEEDS
            },
            "positive_seed_count": int(
                sum(value > 0.0 for value in raw)
            ),
            "association_component_bootstrap_ci": [lower, upper],
            "subgates": subgates,
            "passed": all(subgates.values()),
        }
    summaries["_bootstrap_diagnostics"] = {
        "replicate_image_count_min": int(image_counts.min()),
        "replicate_image_count_max": int(image_counts.max()),
        "replicate_image_count_mean": float(image_counts.mean()),
        "one_shared_component_draw_per_replicate": True,
        "components_drawn_per_replicate": COMPONENT_COUNT,
        "inference_unit": "association component",
    }
    return draws, summaries


def mean_curve_summary(
    curves_by_seed: dict[int, dict[str, np.ndarray]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for axis, names in AXIS_COMPONENT_NAMES.items():
        values = np.stack(
            [curves_by_seed[seed][axis] for seed in SEEDS]
        )
        result[axis] = {
            name: {
                "q": list(Q_VALUES),
                "mean": values[:, index, :].mean(axis=0).tolist(),
                "sd": values[:, index, :].std(
                    axis=0, ddof=1
                ).tolist(),
                "expected_direction": AXIS_DIRECTIONS[axis][index],
            }
            for index, name in enumerate(names)
        }
    return result


def main() -> int:
    args = parse_args()
    if args.replicates != BOOTSTRAP_REPLICATES:
        raise ValueError("replicates are frozen to 2000")
    if args.bootstrap_seed != BOOTSTRAP_SEED:
        raise ValueError("bootstrap seed is frozen to 20260803")

    audit, seed_data, source_maps, components = run_preflight()
    if args.preflight_only:
        print(
            json.dumps(
                {
                    "preflight": audit["status"],
                    "checks": audit["summary"],
                    "run_manifest": relative(RUN_MANIFEST_PATH),
                },
                indent=2,
            )
        )
        return 0
    if RESULT_PATH.exists():
        raise RuntimeError(
            f"one-shot result already exists: {relative(RESULT_PATH)}"
        )

    outcomes, curves_by_seed, point_rows = point_outcomes(
        seed_data, source_maps
    )
    write_csv(POINT_CSV_PATH, point_rows)
    primitives = write_primitives(seed_data, source_maps, components)
    _, bootstrap_summary = run_bootstrap(
        seed_data,
        source_maps,
        components,
        curves_by_seed,
        args.replicates,
        args.bootstrap_seed,
    )
    bootstrap_rows = [
        {
            "axis": axis,
            "mean_across_seeds": values["mean_across_seeds"],
            "sd_across_seeds": values["sd_across_seeds"],
            "positive_seed_count": values["positive_seed_count"],
            "ci_lower": values["association_component_bootstrap_ci"][0],
            "ci_upper": values["association_component_bootstrap_ci"][1],
            "mean_curve_no_reversal": values["subgates"][
                "mean_component_curves_no_reversal"
            ],
            "axis_gate_passed": values["passed"],
        }
        for axis, values in bootstrap_summary.items()
        if not axis.startswith("_")
    ]
    write_csv(BOOTSTRAP_CSV_PATH, bootstrap_rows)

    axis_pass = {
        axis: bootstrap_summary[axis]["passed"]
        for axis in AXIS_DIRECTIONS
    }
    full_pass = bool(
        audit["status"] == "PASS" and all(axis_pass.values())
    )
    result = {
        "study": "BDD-OIA Round 8 graded association response",
        "status": "COMPLETED_ONE_SHOT",
        "scope": {
            "training": False,
            "inference": False,
            "new_data": False,
            "masks": False,
            "threshold_selection": False,
            "dataset": "BDD-OIA frozen test population",
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
            "q_values": list(Q_VALUES),
            "threshold": THRESHOLD,
            "sample_count": SAMPLE_COUNT,
            "bootstrap": {
                "unit": "association component",
                "components": COMPONENT_COUNT,
                "replicates": args.replicates,
                "seed": args.bootstrap_seed,
                "confidence_level": 0.95,
                "interval": "percentile pointwise by axis",
                "shared_draw": (
                    "one component multiset expanded to complete images and "
                    "used by every selected seed/q/model/axis/perturbation"
                ),
                "statistic_order": (
                    "within selected seed take minimum adjacent step, then "
                    "average five selected seed bottlenecks"
                ),
            },
        },
        "point_estimates_by_seed": outcomes,
        "mean_component_curves": mean_curve_summary(curves_by_seed),
        "bootstrap_summary": bootstrap_summary,
        "decisions": {
            "exact_preflight_passed": audit["status"] == "PASS",
            "axis_gates": axis_pass,
            "full_Round8_measurement_pass": full_pass,
        },
        "claim_boundary": {
            "if_passed_supports": (
                "In five frozen BDD-OIA training seeds, under one "
                "outcome-blind nested association map and association-"
                "component-cluster conditional inference, A/R Macro-F1, "
                "S tie-averaged AURC, and C1 mean-three correspondence "
                "metrics satisfy the preregistered strict adjacent-step "
                "monotonic response gates."
            ),
            "does_not_support": [
                "construct, ontology, grounding, faithfulness, causal, or real-safety validity",
                "visual perturbation severity",
                "monotonicity of A/R Micro-F1 or every R class",
                "monotonicity of every C1 perturbation or S diagnostic",
                "other maps, salts, thresholds, models, training protocols, datasets, or real driving",
                "simultaneous 95 percent familywise coverage",
            ],
            "diagnostic_only": (
                "A/R Micro-F1 and per-class; S stable AURC, UAR@90, "
                "AUROC, ECE, and deciles; individual C1 perturbations"
            ),
        },
        "failure_policy": (
            "Preserve every result. Do not change q, map, salt, metric, "
            "bootstrap, bottleneck, threshold, seed, component, or gate."
        ),
    }
    write_json(RESULT_PATH, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "axis_gates": axis_pass,
                "full_Round8_measurement_pass": full_pass,
                "result": relative(RESULT_PATH),
                "result_sha256": sha256_file(RESULT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
