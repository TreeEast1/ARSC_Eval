"""Outcome-blind repaired preflight for Round 10 amendment 01.

This script independently recomputes the dataset and repaired semantic-audit
structure. It never loads checkpoint tensors or reads/computes any Round 10
nonzero-severity model output.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.corruption_dose_response_v2 import (
    FAMILIES,
    LEVELS,
    NOISE_SEED,
    PARAMETERS,
    validate_grid,
)
from arsc_eval.round10_protocol_validation import (
    canonical_sha256,
    expected_sample_indices,
    semantic_key_sha256,
    validate_amendment_schema,
    validate_bound_local_dependencies,
    validate_label_sidecar,
    validate_page_hash_binding,
    validate_review_decision,
    validate_semantic_raw_rows,
    require_no_forbidden_round10_paths,
)


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_dose_response_protocol.json"
)
AMENDMENT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_dose_response_protocol_amendment01.json"
)
STOP_DECISION_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_preregister_reviewer_decision.json"
)
SEMANTIC_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit_amendment01"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_preflight_attempt02.json"
)
TEST_LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_preflight_attempt02_tests.log"
)
EXPECTED_PROTOCOL_SHA256 = (
    "E3F54B24A50D847636FA644355BF78DB1AB2432CF74543E8AEF11A005D17029D"
)
EXPECTED_AMENDMENT_SHA256 = (
    "220D36BEB76CAFDE5BCC3528B49F737E6681A43FF2ECA9A3C22531A1FF88644B"
)
EXPECTED_STOP_DECISION_SHA256 = (
    "9B572FAFF4B46DCF31A034D64962C7E7304C1E3CC26342CA85F2C35E80889FDB"
)
EXPECTED_IMAGE_INVENTORY_SHA256 = (
    "8034D044D55973917D0719A1CC829EEA002582420D6F7E05BB18F9AFF8894901"
)
EXPECTED_TEST_MANIFEST_SHA256 = (
    "89364A265FE4C2EDCA5125D34C4C25D47C96AFB46A5C4A8FE86B649785539004"
)
SEEDS = (43, 44, 45, 46, 47)
SAMPLE_COUNT = 4557
CLIP_COUNT = 3904
EXPECTED_TEST_COUNT = 75
EXPECTED_PARAMETERS = {
    "brightness": (1.0, 1.05, 1.10, 1.20, 1.30),
    "blur": (0.0, 0.5, 1.0, 1.5, 2.0),
    "noise": (0.0, 2.5, 5.0, 7.5, 10.0),
}
CODE_AND_PROTOCOL_FILES = (
    "outputs/validity/round10_corruption_dose_response_protocol.json",
    (
        "outputs/validity/"
        "round10_corruption_dose_response_protocol_amendment01.json"
    ),
    "outputs/research_review_memo_round10_preregister.md",
    "outputs/validity/round10_preregister_reviewer_decision.json",
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "build_summary.json"
    ),
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "raw_manifest.csv"
    ),
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "label_sidecar.jsonl"
    ),
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "review_decision.json"
    ),
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "reviewed_manifest.csv"
    ),
    (
        "outputs/validity/round10_corruption_semantic_audit_amendment01/"
        "audit_summary.json"
    ),
    "scripts/build_round10_semantic_audit_amendment01.py",
    "scripts/summarize_round10_semantic_audit_amendment01.py",
    "scripts/preflight_round10_corruption_attempt02.py",
    "src/arsc_eval/corruption_dose_response_v2.py",
    "src/arsc_eval/round10_protocol_validation.py",
    "tests/test_round10_protocol_validation.py",
    "requirements.txt",
    "requirements-dev.txt",
)
PRESERVED_STOP_FILES = (
    "outputs/validity/round10_corruption_preflight.json",
    "outputs/validity/round10_corruption_preflight_tests.log",
    "outputs/validity/round10_corruption_semantic_audit/build_summary.json",
    "outputs/validity/round10_corruption_semantic_audit/audit_manifest.csv",
    "outputs/validity/round10_corruption_semantic_audit/review_decision.json",
    "outputs/validity/round10_corruption_semantic_audit/audit_summary.json",
    "scripts/preflight_round10_corruption.py",
    "scripts/build_round10_semantic_audit.py",
    "scripts/summarize_round10_semantic_audit.py",
    "src/arsc_eval/corruption_dose_response.py",
    "tests/test_corruption_dose_response.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest().upper()


def fingerprint(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"required file missing: {relative(path)}")
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected object: {relative(path)}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def clip_group(file_name: str) -> str:
    return re.sub(r"_(?:1|3)$", "", Path(file_name).stem)


def validate_protocol_amendment_operator() -> dict[str, Any]:
    require(
        sha256_file(PROTOCOL_PATH) == EXPECTED_PROTOCOL_SHA256,
        "original protocol hash differs",
    )
    require(
        sha256_file(AMENDMENT_PATH) == EXPECTED_AMENDMENT_SHA256,
        "amendment hash differs",
    )
    require(
        sha256_file(STOP_DECISION_PATH) == EXPECTED_STOP_DECISION_SHA256,
        "STOP decision hash differs",
    )
    protocol = read_json(PROTOCOL_PATH)
    amendment = read_json(AMENDMENT_PATH)
    stop_decision = read_json(STOP_DECISION_PATH)
    validate_amendment_schema(amendment)
    require(
        amendment["amends"]["sha256"] == EXPECTED_PROTOCOL_SHA256,
        "amendment original-protocol binding differs",
    )
    require(
        amendment["repair_authorization"]["sha256"]
        == EXPECTED_STOP_DECISION_SHA256,
        "amendment STOP-decision binding differs",
    )
    require(
        stop_decision["decision"] == "STOP/REPAIR_PROTOCOL_PREFLIGHT",
        "preserved reviewer decision is not STOP",
    )
    require(
        protocol["authorization_source"]["formal_run_authorized"] is False,
        "original protocol unexpectedly authorizes a formal run",
    )
    validate_grid()
    observed_parameters = {
        family: tuple(float(value) for value in PARAMETERS[family])
        for family in FAMILIES
    }
    require(
        observed_parameters == EXPECTED_PARAMETERS,
        "amended operator grid differs",
    )
    require(tuple(LEVELS) == (0, 1, 2, 3, 4), "level grid differs")
    require(NOISE_SEED == 20260731, "noise seed differs")
    operator_path = (
        PROJECT_ROOT / "src" / "arsc_eval" / "corruption_dose_response_v2.py"
    )
    operator_source = operator_path.read_text(encoding="utf-8")
    dependencies = validate_bound_local_dependencies(
        operator_source,
        {relative(operator_path)},
    )
    require(
        not dependencies,
        "amended operator must have no local ARSC dependency",
    )
    require(
        "deterministic_noise" not in operator_source.replace(
            "deterministic_noise_v2", ""
        ),
        "legacy deterministic_noise import/reference found",
    )
    return {
        "protocol": {
            "path": relative(PROTOCOL_PATH),
            **fingerprint(PROTOCOL_PATH),
            "expected_sha256": EXPECTED_PROTOCOL_SHA256,
        },
        "amendment": {
            "path": relative(AMENDMENT_PATH),
            **fingerprint(AMENDMENT_PATH),
            "expected_sha256": EXPECTED_AMENDMENT_SHA256,
        },
        "repair_authorization": {
            "path": relative(STOP_DECISION_PATH),
            **fingerprint(STOP_DECISION_PATH),
            "expected_sha256": EXPECTED_STOP_DECISION_SHA256,
            "decision": stop_decision["decision"],
        },
        "operator": {
            "path": relative(operator_path),
            **fingerprint(operator_path),
            "families": list(FAMILIES),
            "levels": list(LEVELS),
            "parameters": {
                family: list(values)
                for family, values in observed_parameters.items()
            },
            "noise_seed": NOISE_SEED,
            "local_arsc_dependencies": sorted(dependencies),
            "self_contained": True,
        },
    }


def validate_dataset() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = PROJECT_ROOT / "data" / "processed" / "test.jsonl"
    image_root = PROJECT_ROOT / "data" / "raw" / "lastframe" / "data"
    records = read_jsonl(manifest)
    names = [record["file_name"] for record in records]
    require(len(names) == SAMPLE_COUNT, "test manifest row count differs")
    require(len(set(names)) == SAMPLE_COUNT, "test filenames are not unique")
    groups = {clip_group(name) for name in names}
    require(len(groups) == CLIP_COUNT, "source clip count differs")
    require(
        sha256_file(manifest) == EXPECTED_TEST_MANIFEST_SHA256,
        "test manifest hash differs",
    )
    aggregate = hashlib.sha256()
    total_bytes = 0
    for name in names:
        require(Path(name).name == name, f"noncanonical filename: {name}")
        path = image_root / name
        require(path.is_file(), f"source image missing: {name}")
        item_bytes = path.stat().st_size
        total_bytes += item_bytes
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(item_bytes).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(sha256_file(path).encode("ascii"))
        aggregate.update(b"\n")
    inventory_hash = aggregate.hexdigest().upper()
    require(
        inventory_hash == EXPECTED_IMAGE_INVENTORY_SHA256,
        "source image inventory hash differs",
    )
    return (
        {
            "manifest": {
                "path": relative(manifest),
                **fingerprint(manifest),
                "expected_sha256": EXPECTED_TEST_MANIFEST_SHA256,
            },
            "rows": len(names),
            "unique_filenames": len(set(names)),
            "source_clip_count": len(groups),
            "all_source_images_exist": True,
            "source_image_total_bytes": total_bytes,
            "ordered_source_image_inventory_sha256": inventory_hash,
            "expected_ordered_source_image_inventory_sha256": (
                EXPECTED_IMAGE_INVENTORY_SHA256
            ),
        },
        records,
    )


def validate_configs_models_calibrations() -> dict[str, Any]:
    configurations: dict[str, Any] = {}
    checkpoints: dict[str, Any] = {}
    calibrations: dict[str, Any] = {}
    for seed in SEEDS:
        config_path = PROJECT_ROOT / "configs" / f"rq1_seed{seed}.yaml"
        with config_path.open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
        require(config["seed"] == seed, f"wrong config seed {seed}")
        require(config["image_size"] == 224, f"wrong image size {seed}")
        require(
            config["model"]["backbone"] == "resnet50",
            f"wrong backbone {seed}",
        )
        require(
            config["training"]["threshold"] == 0.5,
            f"wrong threshold {seed}",
        )
        require(
            config["perturbations"]
            == {
                "brightness_factor": 1.10,
                "blur_radius": 1.0,
                "noise_std_255": 5.0,
                "noise_seed": 20260731,
            },
            f"historical level-two bridge differs {seed}",
        )
        configurations[str(seed)] = {
            "path": relative(config_path),
            **fingerprint(config_path),
        }
        for model, checkpoint_name, calibration_name in (
            (
                "action_only",
                "action_only_best_action.pt",
                "calibration_action_only.json",
            ),
            ("joint", "joint_best_action.pt", "calibration_joint.json"),
        ):
            checkpoint_path = (
                PROJECT_ROOT
                / "checkpoints"
                / "validity"
                / f"rq1_seed_{seed}"
                / checkpoint_name
            )
            key = f"seed_{seed}_{model}"
            checkpoints[key] = {
                "path": relative(checkpoint_path),
                **fingerprint(checkpoint_path),
                "loaded_with_torch": False,
            }
            calibration_path = (
                PROJECT_ROOT
                / "outputs"
                / "validity"
                / f"rq1_seed_{seed}"
                / calibration_name
            )
            calibration = read_json(calibration_path)
            require(
                calibration["model_type"] == model,
                f"calibration model differs {key}",
            )
            require(
                Path(calibration["checkpoint"]).as_posix()
                == relative(checkpoint_path),
                f"calibration checkpoint differs {key}",
            )
            require(
                calibration["validation_samples"] == 2258,
                f"calibration population differs {key}",
            )
            require(
                float(calibration["temperature"]) > 0.0,
                f"calibration temperature invalid {key}",
            )
            calibrations[key] = {
                "path": relative(calibration_path),
                **fingerprint(calibration_path),
                "temperature": float(calibration["temperature"]),
                "refitted_for_round10": False,
            }
    require(len(configurations) == 5, "expected five configs")
    require(len(checkpoints) == 10, "expected ten checkpoints")
    require(len(calibrations) == 10, "expected ten calibrations")
    return {
        "configs": configurations,
        "checkpoints": checkpoints,
        "calibrations": calibrations,
    }


def validate_semantic_audit(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    build_path = SEMANTIC_DIR / "build_summary.json"
    raw_path = SEMANTIC_DIR / "raw_manifest.csv"
    sidecar_path = SEMANTIC_DIR / "label_sidecar.jsonl"
    decision_path = SEMANTIC_DIR / "review_decision.json"
    reviewed_path = SEMANTIC_DIR / "reviewed_manifest.csv"
    summary_path = SEMANTIC_DIR / "audit_summary.json"
    build = read_json(build_path)
    decision = read_json(decision_path)
    summary = read_json(summary_path)
    require(
        build["status"]
        == "AWAITING_LABEL_VISIBLE_MODEL_OUTPUT_BLIND_REVIEW",
        "semantic build status differs",
    )
    require(
        build["outcomes_read_or_computed"] is False,
        "semantic build was not outcome blind",
    )
    require(
        summary["status"]
        == "PASS_LABEL_VISIBLE_MODEL_OUTPUT_BLIND_SEMANTIC_GATE",
        "repaired semantic audit did not pass",
    )
    require(
        summary["outcomes_read_or_computed"] is False,
        "semantic summary was not outcome blind",
    )
    require(build["technical_gate"]["passed"] is True, "technical gate failed")
    require(
        sha256_file(raw_path) == build["raw_manifest_sha256"],
        "raw semantic manifest hash differs",
    )
    require(
        sha256_file(sidecar_path) == build["label_sidecar_sha256"],
        "label sidecar hash differs",
    )
    indices = expected_sample_indices(len(records))
    require(
        indices.tolist() == build["selected_dataset_indices"],
        "recomputed semantic sample differs",
    )
    require(
        array_sha256(indices) == build["selected_indices_array_sha256"],
        "sample index-array hash differs",
    )
    selected = [records[int(index)] for index in indices]
    raw_rows, fieldnames = read_csv(raw_path)
    valid_keys = validate_semantic_raw_rows(
        raw_rows,
        indices.tolist(),
        selected,
    )
    require(
        semantic_key_sha256(valid_keys) == build["row_key_sha256"],
        "semantic row-key hash differs",
    )
    sidecar_rows = read_jsonl(sidecar_path)
    validate_label_sidecar(sidecar_rows, indices.tolist(), selected)
    expected_pages = build["labelled_page_sha256"]
    require(
        canonical_sha256(expected_pages) == build["labelled_page_map_sha256"],
        "labelled page-map hash differs",
    )
    actual_pages = {
        path_text: sha256_file(PROJECT_ROOT / path_text)
        for path_text in expected_pages
    }
    validate_page_hash_binding(
        expected_pages,
        decision["reviewed_page_sha256"],
        actual_pages,
    )
    expected_bindings = {
        "raw_manifest_sha256": build["raw_manifest_sha256"],
        "label_sidecar_sha256": build["label_sidecar_sha256"],
        "row_key_sha256": build["row_key_sha256"],
        "selected_indices_array_sha256": (
            build["selected_indices_array_sha256"]
        ),
        "labelled_page_map_sha256": build["labelled_page_map_sha256"],
        "build_summary_sha256": sha256_file(build_path),
    }
    overrides = validate_review_decision(
        decision,
        valid_keys,
        expected_bindings,
    )
    defaults = decision["default_decisions"]
    reviewed_rows, reviewed_fields = read_csv(reviewed_path)
    require(reviewed_fields == fieldnames, "reviewed manifest schema differs")
    require(len(reviewed_rows) == 1200, "reviewed row count differs")
    strata: dict[tuple[str, int], list[tuple[bool, bool]]] = defaultdict(list)
    decision_fields = {
        "action_and_rationale_labels_still_applicable",
        "scene_semantics_preserved",
        "review_notes",
    }
    for raw, reviewed, key in zip(raw_rows, reviewed_rows, valid_keys):
        for field in fieldnames:
            if field not in decision_fields:
                require(
                    raw[field] == reviewed[field],
                    f"raw-to-reviewed provenance differs: {field}",
                )
        override = overrides.get(key)
        labels = (
            override["action_and_rationale_labels_still_applicable"]
            if override is not None
            else defaults["action_and_rationale_labels_still_applicable"]
        )
        scene = (
            override["scene_semantics_preserved"]
            if override is not None
            else defaults["scene_semantics_preserved"]
        )
        notes = override["review_notes"] if override is not None else ""
        require(
            reviewed["action_and_rationale_labels_still_applicable"]
            == ("true" if labels else "false"),
            "reviewed label decision differs",
        )
        require(
            reviewed["scene_semantics_preserved"]
            == ("true" if scene else "false"),
            "reviewed scene decision differs",
        )
        require(reviewed["review_notes"] == notes, "review notes differ")
        strata[(key[1], key[2])].append((labels, scene))
    recomputed_strata: dict[str, Any] = {}
    for (family, level), values in sorted(strata.items()):
        require(len(values) == 100, "semantic stratum size differs")
        labels_rate = sum(item[0] for item in values) / 100
        scene_rate = sum(item[1] for item in values) / 100
        joint_rate = sum(item[0] and item[1] for item in values) / 100
        recomputed_strata[f"{family}::level{level}"] = {
            "reviewed": 100,
            "labels_still_applicable_rate": labels_rate,
            "scene_semantics_preserved_rate": scene_rate,
            "joint_pass_rate": joint_rate,
            "passed": bool(
                labels_rate >= 0.95
                and scene_rate >= 0.95
                and joint_rate >= 0.95
            ),
        }
    require(len(recomputed_strata) == 12, "expected 12 semantic strata")
    require(
        recomputed_strata == summary["strata"],
        "independently recomputed semantic strata differ",
    )
    transition = summary["immutable_transition"]
    require(
        transition["raw_manifest_sha256_before"]
        == transition["raw_manifest_sha256_after"]
        == sha256_file(raw_path),
        "raw semantic manifest was not immutable",
    )
    require(
        transition["reviewed_manifest_sha256"] == sha256_file(reviewed_path),
        "reviewed semantic manifest hash differs",
    )
    require(
        summary["review_decision_sha256"] == sha256_file(decision_path),
        "review decision hash differs from summary",
    )
    require(
        summary["build_summary_sha256"] == sha256_file(build_path),
        "build summary hash differs from audit summary",
    )
    require(
        summary["complete_grid_passed"] is True
        and summary["manual_gate_passed"] is True,
        "complete semantic grid did not pass",
    )
    return {
        "status": summary["status"],
        "outcomes_read_or_computed": False,
        "recomputed_sample_count": len(indices),
        "recomputed_pair_count": len(raw_rows),
        "recomputed_strata": recomputed_strata,
        "page_hash_bindings_verified": len(expected_pages),
        "raw_to_reviewed_transition_verified": True,
        "all_decision_strings_verified_exact": True,
        "files": {
            relative(path): fingerprint(path)
            for path in (
                build_path,
                raw_path,
                sidecar_path,
                decision_path,
                reviewed_path,
                summary_path,
            )
        },
    }


def current_paths() -> list[str]:
    return [
        relative(path)
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def validate_forbidden_absence() -> dict[str, Any]:
    paths = current_paths()
    require_no_forbidden_round10_paths(paths)
    return {
        "enumerated_file_count": len(paths),
        "forbidden_round10_paths": [],
        "formal_analyzer_absent": True,
        "formal_launcher_absent": True,
        "formal_results_primitives_bootstrap_diagnostics_logs_absent": True,
        "formal_manifests_staging_temporary_prediction_cache_absent": True,
    }


def run_tests() -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout
    match = re.search(r"(\d+) passed", output)
    observed = int(match.group(1)) if match else None
    temp_path = TEST_LOG_PATH.with_suffix(TEST_LOG_PATH.suffix + ".tmp")
    temp_path.write_text(output, encoding="utf-8", newline="\n")
    os.replace(temp_path, TEST_LOG_PATH)
    require(completed.returncode == 0, "repository tests failed")
    require(
        observed == EXPECTED_TEST_COUNT,
        f"expected {EXPECTED_TEST_COUNT} tests, observed {observed}",
    )
    return {
        "command": command,
        "environment": {"PYTHONPATH": relative(PROJECT_ROOT / "src")},
        "return_code": completed.returncode,
        "expected_test_count": EXPECTED_TEST_COUNT,
        "observed_test_count": observed,
        "all_passed": True,
        "log": {
            "path": relative(TEST_LOG_PATH),
            **fingerprint(TEST_LOG_PATH),
        },
    }


def environment_record() -> dict[str, Any]:
    distributions = sorted(
        (
            distribution.metadata["Name"].lower(),
            distribution.version,
        )
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    )
    rendered = "\n".join(
        f"{name}=={version}" for name, version in distributions
    )
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "key_packages": {
            name: importlib.metadata.version(name)
            for name in (
                "numpy",
                "pillow",
                "torch",
                "torchvision",
                "pyyaml",
                "pytest",
            )
        },
        "installed_distribution_count": len(distributions),
        "sorted_installed_distributions_sha256": hashlib.sha256(
            rendered.encode("utf-8")
        ).hexdigest().upper(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def main() -> int:
    require(
        not OUTPUT_PATH.exists(),
        f"attempt02 output already exists: {relative(OUTPUT_PATH)}",
    )
    require(
        not TEST_LOG_PATH.exists(),
        f"attempt02 test log already exists: {relative(TEST_LOG_PATH)}",
    )
    forbidden_before = validate_forbidden_absence()
    protocol = validate_protocol_amendment_operator()
    dataset, records = validate_dataset()
    frozen_inputs = validate_configs_models_calibrations()
    semantic = validate_semantic_audit(records)
    tests = run_tests()
    forbidden_after = validate_forbidden_absence()
    bound_files = {
        path_text: fingerprint(PROJECT_ROOT / path_text)
        for path_text in CODE_AND_PROTOCOL_FILES
    }
    preserved_stop_files = {
        path_text: fingerprint(PROJECT_ROOT / path_text)
        for path_text in PRESERVED_STOP_FILES
    }
    result = {
        "schema_version": "ARSC_ROUND10_CORRUPTION_PREFLIGHT_ATTEMPT02_V1",
        "status": (
            "PASS_AWAITING_INDEPENDENT_REVIEWER_"
            "IMPLEMENTATION_AUTHORIZATION_ATTEMPT02"
        ),
        "study": (
            "Round 10 BDD-OIA pixel-space corruption severity dose-response "
            "construct validation, repaired preregistration"
        ),
        "preflight_base_commit": git_head(),
        "protocol_amendment_and_operator": protocol,
        "dataset": dataset,
        "frozen_inputs": frozen_inputs,
        "semantic_audit": semantic,
        "negative_and_repository_tests": tests,
        "forbidden_artifact_absence_before_tests": forbidden_before,
        "forbidden_artifact_absence_after_tests": forbidden_after,
        "bound_code_protocol_audit_and_review_files": bound_files,
        "preserved_original_stop_path_files": preserved_stop_files,
        "environment": environment_record(),
        "outcome_blinding": {
            "new_nonzero_severity_predictions_read": False,
            "new_nonzero_severity_logits_read_or_computed": False,
            "new_nonzero_severity_confidences_read_or_computed": False,
            "new_nonzero_severity_metrics_read_or_computed": False,
            "checkpoints_loaded_with_torch": False,
            "checkpoint_bytes_only_hashed": True,
            "formal_analysis_implementation_authorized": False,
            "formal_run_authorized": False,
        },
        "next_gate": (
            "Independent reviewer may only STOP for repair or authorize "
            "outcome-blind formal implementation; the formal run remains "
            "unauthorized."
        ),
    }
    temp_path = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp_path, OUTPUT_PATH)
    print(
        json.dumps(
            {
                "status": result["status"],
                "dataset_rows": dataset["rows"],
                "source_clips": dataset["source_clip_count"],
                "checkpoints": len(frozen_inputs["checkpoints"]),
                "calibrations": len(frozen_inputs["calibrations"]),
                "semantic_pairs": semantic["recomputed_pair_count"],
                "semantic_strata": len(semantic["recomputed_strata"]),
                "page_hashes": semantic["page_hash_bindings_verified"],
                "tests_passed": tests["observed_test_count"],
                "forbidden_artifacts_absent": True,
                "outcomes_read_or_computed": False,
                "output": relative(OUTPUT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
