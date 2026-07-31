"""Outcome-blind input and semantic preflight for Round 10.

This script hashes frozen inputs and checks configuration invariants. It does
not load a checkpoint with torch, run a model, or read/compute any Round 10
nonzero-severity prediction, confidence, logit, or metric outcome.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.corruption_dose_response import (
    FAMILIES,
    LEVELS,
    NOISE_SEED,
    PARAMETERS,
    validate_grid,
)


PROTOCOL_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_dose_response_protocol.json"
)
EXPECTED_PROTOCOL_SHA256 = (
    "E3F54B24A50D847636FA644355BF78DB1AB2432CF74543E8AEF11A005D17029D"
)
ROUND9_DECISION_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_postresult_reviewer_decision.json"
)
EXPECTED_ROUND9_DECISION_SHA256 = (
    "7D362D283493440A2365149BADE802F6CA3B56FCED9824A7B5A5056571F387B3"
)
SEMANTIC_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit"
)
OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_preflight.json"
)
TEST_LOG_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_preflight_tests.log"
)
SEEDS = (43, 44, 45, 46, 47)
SAMPLE_COUNT = 4557
CLIP_COUNT = 3904
EXPECTED_TEST_COUNT = 67
EXPECTED_PARAMETERS = {
    "brightness": (1.0, 1.05, 1.10, 1.20, 1.30),
    "blur": (0.0, 0.5, 1.0, 1.5, 2.0),
    "noise": (0.0, 2.5, 5.0, 7.5, 10.0),
}
FORMAL_ARTIFACTS = (
    "outputs/validity/round10_corruption_results.json",
    "outputs/validity/round10_corruption_primitives.npz",
    "outputs/validity/round10_corruption_bootstrap_draws.npz",
    "outputs/validity/round10_corruption_point_diagnostics.csv",
    "outputs/validity/round10_corruption_bootstrap_summary.csv",
    "outputs/validity/round10_corruption_formal.log",
    "outputs/validity/round10_corruption_prediction_cache",
)
CODE_AND_PROTOCOL_FILES = (
    "outputs/validity/round10_corruption_dose_response_protocol.json",
    "outputs/validity/round10_corruption_semantic_audit/build_summary.json",
    "outputs/validity/round10_corruption_semantic_audit/audit_manifest.csv",
    "outputs/validity/round10_corruption_semantic_audit/review_decision.json",
    "outputs/validity/round10_corruption_semantic_audit/audit_summary.json",
    "scripts/build_round10_semantic_audit.py",
    "scripts/summarize_round10_semantic_audit.py",
    "scripts/preflight_round10_corruption.py",
    "src/arsc_eval/corruption_dose_response.py",
    "tests/test_corruption_dose_response.py",
    "requirements.txt",
    "requirements-dev.txt",
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


def fingerprint(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"required file missing: {relative(path)}")
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected JSON object: {relative(path)}")
    return value


def clip_group(file_name: str) -> str:
    return re.sub(r"_(?:1|3)$", "", Path(file_name).stem)


def validate_protocol() -> dict[str, Any]:
    require(
        sha256_file(PROTOCOL_PATH) == EXPECTED_PROTOCOL_SHA256,
        "Round 10 protocol hash differs from the frozen value",
    )
    protocol = read_json(PROTOCOL_PATH)
    require(
        protocol["schema_version"]
        == "ARSC_ROUND10_CORRUPTION_DOSE_RESPONSE_PROTOCOL_V1",
        "unexpected Round 10 protocol schema",
    )
    require(
        protocol["protocol_id"]
        == "ARSC_ROUND10_BDD_OIA_PIXEL_CORRUPTION_DOSE_RESPONSE_V1",
        "unexpected Round 10 protocol id",
    )
    require(
        protocol["authorization_source"]["formal_run_authorized"] is False,
        "protocol must not authorize the formal run",
    )
    require(
        protocol["authorization_source"]["sha256"]
        == EXPECTED_ROUND9_DECISION_SHA256,
        "protocol has wrong Round 9 authorization hash",
    )
    population = protocol["frozen_population_and_models"]
    require(population["sample_count"] == SAMPLE_COUNT, "wrong sample count")
    require(
        population["expected_source_clip_count"] == CLIP_COUNT,
        "wrong clip count",
    )
    require(tuple(population["training_seeds"]) == SEEDS, "wrong seed grid")
    require(population["threshold"] == 0.5, "wrong threshold")
    frozen = protocol["frozen_corruptions"]
    require(tuple(frozen["families"]) == FAMILIES, "wrong family grid")
    require(
        tuple(frozen["severity_levels"]) == LEVELS,
        "wrong severity levels",
    )
    protocol_parameters = {
        "brightness": tuple(
            frozen["parameters"]["brightness"]["factor_by_level"]
        ),
        "blur": tuple(frozen["parameters"]["blur"]["radius_by_level"]),
        "noise": tuple(frozen["parameters"]["noise"]["std_255_by_level"]),
    }
    require(
        protocol_parameters == EXPECTED_PARAMETERS,
        "protocol corruption parameters differ from frozen grid",
    )
    require(
        frozen["parameters"]["noise"]["seed"] == NOISE_SEED,
        "wrong noise seed",
    )
    require(
        protocol["frozen_inference"]["formal_run_count"] == 1,
        "formal run count must equal one",
    )
    require(
        protocol["frozen_inference"]["bootstrap"]["replicates"] == 5000,
        "wrong bootstrap replicate count",
    )
    require(
        protocol["frozen_inference"]["bootstrap"]["seed"] == 20260810,
        "wrong bootstrap seed",
    )
    require(
        len(protocol["decision_rules"]["family_axis_pass"]) == 5,
        "incomplete family-axis gate",
    )
    require(
        protocol["scientific_scope"]["no_association_maps_or_salts"] is True,
        "association maps or salts must remain prohibited",
    )
    return protocol


def validate_operator_grid() -> dict[str, Any]:
    validate_grid()
    observed = {
        family: tuple(float(value) for value in PARAMETERS[family])
        for family in FAMILIES
    }
    require(observed == EXPECTED_PARAMETERS, "operator grid differs")
    require(NOISE_SEED == 20260731, "operator noise seed differs")
    return {
        "families": list(FAMILIES),
        "levels": list(LEVELS),
        "parameters": {
            family: list(values) for family, values in observed.items()
        },
        "noise_seed": NOISE_SEED,
        "historical_level_two_exact": bool(
            observed["brightness"][2] == 1.10
            and observed["blur"][2] == 1.0
            and observed["noise"][2] == 5.0
        ),
    }


def validate_dataset() -> dict[str, Any]:
    manifest = PROJECT_ROOT / "data" / "processed" / "test.jsonl"
    image_root = PROJECT_ROOT / "data" / "raw" / "lastframe" / "data"
    names: list[str] = []
    with manifest.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            record = json.loads(line)
            require(
                isinstance(record.get("file_name"), str),
                f"missing filename at test manifest line {line_number}",
            )
            names.append(record["file_name"])
    require(len(names) == SAMPLE_COUNT, "test manifest row count differs")
    require(len(set(names)) == SAMPLE_COUNT, "test filenames are not unique")
    groups = {clip_group(name) for name in names}
    require(len(groups) == CLIP_COUNT, "source clip count differs")

    aggregate = hashlib.sha256()
    total_bytes = 0
    for name in names:
        require(Path(name).name == name, f"noncanonical filename: {name}")
        path = image_root / name
        require(path.is_file(), f"source image missing: {name}")
        item_hash = sha256_file(path)
        item_bytes = path.stat().st_size
        total_bytes += item_bytes
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(str(item_bytes).encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(item_hash.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "manifest": {
            "path": relative(manifest),
            **fingerprint(manifest),
        },
        "rows": len(names),
        "unique_filenames": len(set(names)),
        "source_clip_definition": "remove terminal _1 or _3 from filename stem",
        "source_clip_count": len(groups),
        "all_source_images_exist": True,
        "source_image_total_bytes": total_bytes,
        "ordered_source_image_inventory_sha256": (
            aggregate.hexdigest().upper()
        ),
        "inventory_digest_definition": (
            "SHA256 over manifest-order UTF-8 filename, NUL, decimal bytes, "
            "NUL, uppercase file SHA256, LF"
        ),
    }


def validate_configs_models_and_calibrations() -> dict[str, Any]:
    configurations = {}
    checkpoints = {}
    calibrations = {}
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
            f"wrong threshold in config {seed}",
        )
        require(
            config["perturbations"]
            == {
                "brightness_factor": 1.10,
                "blur_radius": 1.0,
                "noise_std_255": 5.0,
                "noise_seed": 20260731,
            },
            f"historical bridge differs in config {seed}",
        )
        require(
            config["paths"]["checkpoint_dir"]
            == f"checkpoints/validity/rq1_seed_{seed}",
            f"wrong checkpoint directory in config {seed}",
        )
        require(
            config["paths"]["output_dir"]
            == f"outputs/validity/rq1_seed_{seed}",
            f"wrong output directory in config {seed}",
        )
        configurations[str(seed)] = {
            "path": relative(config_path),
            **fingerprint(config_path),
            "seed": config["seed"],
            "image_size": config["image_size"],
            "backbone": config["model"]["backbone"],
            "threshold": config["training"]["threshold"],
            "historical_level_two": config["perturbations"],
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
            checkpoint_key = f"seed_{seed}_{model}"
            checkpoints[checkpoint_key] = {
                "path": relative(checkpoint_path),
                **fingerprint(checkpoint_path),
                "historical_selection": "best_action",
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
                f"wrong calibration model type: {checkpoint_key}",
            )
            require(
                Path(calibration["checkpoint"]).as_posix().replace("\\", "/")
                == relative(checkpoint_path),
                f"wrong calibration checkpoint: {checkpoint_key}",
            )
            temperature = float(calibration["temperature"])
            require(
                temperature > 0.0,
                f"nonpositive calibration temperature: {checkpoint_key}",
            )
            require(
                calibration["split"]
                == "official validation (valid four-action samples)",
                f"wrong calibration split: {checkpoint_key}",
            )
            require(
                calibration["validation_samples"] == 2258,
                f"wrong calibration population: {checkpoint_key}",
            )
            calibrations[checkpoint_key] = {
                "path": relative(calibration_path),
                **fingerprint(calibration_path),
                "model_type": calibration["model_type"],
                "checkpoint": relative(checkpoint_path),
                "split": calibration["split"],
                "validation_samples": calibration["validation_samples"],
                "temperature": temperature,
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


def validate_semantic_audit() -> dict[str, Any]:
    build_path = SEMANTIC_DIR / "build_summary.json"
    decision_path = SEMANTIC_DIR / "review_decision.json"
    summary_path = SEMANTIC_DIR / "audit_summary.json"
    manifest_path = SEMANTIC_DIR / "audit_manifest.csv"
    build = read_json(build_path)
    decision = read_json(decision_path)
    summary = read_json(summary_path)
    require(
        build["outcomes_read_or_computed"] is False,
        "semantic build was not outcome blind",
    )
    require(
        decision["reviewed_all_30_contact_sheets"] is True,
        "not all contact sheets were reviewed",
    )
    require(
        summary["status"] == "PASS_MODEL_OUTPUT_BLIND_SEMANTIC_GATE",
        "semantic audit did not pass",
    )
    require(
        summary["outcomes_read_or_computed"] is False,
        "semantic review was not outcome blind",
    )
    require(
        summary["reviewed_unique_images"] == 100,
        "wrong semantic sample count",
    )
    require(summary["reviewed_pairs"] == 1200, "wrong semantic pair count")
    require(
        summary["reviewed_decisions"] == 2400,
        "wrong semantic decision count",
    )
    require(len(summary["strata"]) == 12, "wrong semantic stratum count")
    require(
        all(item["passed"] for item in summary["strata"].values()),
        "at least one semantic stratum failed",
    )
    require(
        summary["complete_grid_passed"] is True,
        "complete semantic grid did not pass",
    )
    require(
        summary["technical_gate"]["passed"] is True,
        "technical transform gate did not pass",
    )
    require(
        sha256_file(manifest_path) == summary["manifest_sha256"],
        "semantic manifest hash differs from summary",
    )
    expected_pages = {
        item["path"]: item["sha256"] for item in build["pages"]
    }
    require(len(expected_pages) == 30, "wrong contact sheet count")
    require(
        decision["reviewed_page_sha256"] == expected_pages,
        "review decision page binding differs",
    )
    for path_text, expected_hash in expected_pages.items():
        page_path = PROJECT_ROOT / path_text
        require(
            sha256_file(page_path) == expected_hash,
            f"contact sheet hash differs: {path_text}",
        )
    return {
        "status": summary["status"],
        "complete_grid_passed": summary["complete_grid_passed"],
        "outcomes_read_or_computed": False,
        "reviewed_unique_images": summary["reviewed_unique_images"],
        "reviewed_pairs": summary["reviewed_pairs"],
        "reviewed_decisions": summary["reviewed_decisions"],
        "passed_strata": sum(
            item["passed"] for item in summary["strata"].values()
        ),
        "total_strata": len(summary["strata"]),
        "technical_gate_passed": summary["technical_gate"]["passed"],
        "page_hash_bindings_verified": len(expected_pages),
        "files": {
            relative(path): fingerprint(path)
            for path in (
                build_path,
                manifest_path,
                decision_path,
                summary_path,
            )
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
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest().upper()
    key_packages = {}
    for name in ("numpy", "pillow", "torch", "torchvision", "pyyaml", "pytest"):
        key_packages[name] = importlib.metadata.version(name)
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "key_packages": key_packages,
        "installed_distribution_count": len(distributions),
        "sorted_installed_distributions_sha256": digest,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def run_tests() -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--disable-warnings",
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = completed.stdout
    match = re.search(r"(\d+) passed", output)
    observed_count = int(match.group(1)) if match else None
    temp_path = TEST_LOG_PATH.with_suffix(TEST_LOG_PATH.suffix + ".tmp")
    temp_path.write_text(output, encoding="utf-8", newline="\n")
    os.replace(temp_path, TEST_LOG_PATH)
    require(completed.returncode == 0, "repository tests failed")
    require(
        observed_count == EXPECTED_TEST_COUNT,
        f"expected {EXPECTED_TEST_COUNT} passing tests, got {observed_count}",
    )
    return {
        "command": command,
        "return_code": completed.returncode,
        "expected_test_count": EXPECTED_TEST_COUNT,
        "observed_test_count": observed_count,
        "all_passed": True,
        "log": {
            "path": relative(TEST_LOG_PATH),
            **fingerprint(TEST_LOG_PATH),
        },
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
        f"preflight output already exists: {relative(OUTPUT_PATH)}",
    )
    validate_protocol()
    require(
        sha256_file(ROUND9_DECISION_PATH)
        == EXPECTED_ROUND9_DECISION_SHA256,
        "Round 9 authorization decision hash differs",
    )
    formal_absence = {
        path_text: not (PROJECT_ROOT / path_text).exists()
        for path_text in FORMAL_ARTIFACTS
    }
    require(
        all(formal_absence.values()),
        "at least one Round 10 formal artifact already exists",
    )

    operator_grid = validate_operator_grid()
    semantic_audit = validate_semantic_audit()
    dataset = validate_dataset()
    frozen_inputs = validate_configs_models_and_calibrations()
    tests = run_tests()
    code_and_protocol = {
        path_text: fingerprint(PROJECT_ROOT / path_text)
        for path_text in CODE_AND_PROTOCOL_FILES
    }
    result = {
        "schema_version": "ARSC_ROUND10_CORRUPTION_PREFLIGHT_V1",
        "status": (
            "PASS_AWAITING_INDEPENDENT_REVIEWER_IMPLEMENTATION_AUTHORIZATION"
        ),
        "study": (
            "Round 10 BDD-OIA pixel-space corruption severity "
            "dose-response construct validation"
        ),
        "preflight_base_commit": git_head(),
        "protocol": {
            "path": relative(PROTOCOL_PATH),
            **fingerprint(PROTOCOL_PATH),
            "expected_sha256": EXPECTED_PROTOCOL_SHA256,
            "exact_hash_passed": True,
        },
        "authorization_source": {
            "path": relative(ROUND9_DECISION_PATH),
            **fingerprint(ROUND9_DECISION_PATH),
            "expected_sha256": EXPECTED_ROUND9_DECISION_SHA256,
            "exact_hash_passed": True,
            "authorization": "OUTCOME_BLIND_PROTOCOL_AND_PREFLIGHT_ONLY",
        },
        "operator_grid": operator_grid,
        "semantic_audit": semantic_audit,
        "dataset": dataset,
        "frozen_inputs": frozen_inputs,
        "environment": environment_record(),
        "code_and_protocol_files": code_and_protocol,
        "formal_artifact_absence": formal_absence,
        "tests": tests,
        "outcome_blinding": {
            "new_nonzero_severity_predictions_read": False,
            "new_nonzero_severity_logits_read_or_computed": False,
            "new_nonzero_severity_confidences_read_or_computed": False,
            "new_nonzero_severity_metrics_read_or_computed": False,
            "checkpoints_loaded_with_torch": False,
            "checkpoint_bytes_only_hashed": True,
            "formal_run_authorized": False,
            "formal_analysis_implementation_authorized": False,
        },
        "next_gate": (
            "Independent reviewer must inspect and bind this complete "
            "outcome-blind protocol, semantic audit, operator code, tests, "
            "and input inventory before formal implementation begins."
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
                "semantic_strata": semantic_audit["total_strata"],
                "tests_passed": tests["observed_test_count"],
                "formal_artifacts_absent": all(formal_absence.values()),
                "outcomes_read_or_computed": False,
                "output": relative(OUTPUT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
