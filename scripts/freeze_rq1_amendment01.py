"""Freeze and validate the serialization-only RQ1 protocol amendment."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import write_json


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> int:
    original_protocol_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "rq1_multiseed_frozen_protocol.json"
    )
    original_protocol = json.loads(
        original_protocol_path.read_text(encoding="utf-8")
    )
    if (
        sha256_file(original_protocol_path)
        != "cc5fe969ea90efb1181f67ab5d18ce67c05de9207f903c7f14ebd964ac07ee0c"
    ):
        raise RuntimeError("original protocol hash changed")

    unchanged_code = {
        item["path"]: item
        for item in original_protocol["frozen_code"]
        if item["path"] != "src\\arsc_eval\\data.py"
    }
    for relative, expected in unchanged_code.items():
        path = PROJECT_ROOT / Path(relative)
        if sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"unauthorized frozen code change: {relative}")
    for expected in original_protocol["configs"]:
        path = PROJECT_ROOT / Path(expected["path"])
        if sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"frozen config changed: {path}")
    for expected in original_protocol["paired_design_checks"]:
        path = PROJECT_ROOT / Path(expected["path"])
        if sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"paired design record changed: {path}")

    seed43_output = (
        PROJECT_ROOT / "outputs" / "validity" / "rq1_seed_43"
    )
    forbidden_partial = [
        seed43_output / "prediction_cache" / "rq1_lossless.npz",
        seed43_output / "rq1_metrics.json",
    ]
    if any(path.exists() for path in forbidden_partial):
        raise RuntimeError("partial test result exists; amendment must stop")
    allowed_output_names = {
        "paired_design_check.json",
        "training_log_action_only.csv",
        "training_log_joint.csv",
        "calibration_action_only.json",
        "calibration_joint.json",
    }
    actual_output_names = {
        path.name for path in seed43_output.iterdir() if path.is_file()
    }
    if actual_output_names != allowed_output_names:
        raise RuntimeError(
            "unexpected seed43 output before restart: "
            f"{sorted(actual_output_names)}"
        )

    worker_check_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "rq1_amendment01_worker_check.json"
    )
    worker_check = json.loads(worker_check_path.read_text(encoding="utf-8"))
    if (
        not worker_check["all_conditions_passed"]
        or worker_check["num_workers"] != 8
        or set(worker_check["conditions"])
        != {"brightness", "blur", "noise"}
    ):
        raise RuntimeError("Windows worker smoke gate failed")

    tests_log_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "rq1_amendment01_tests.log"
    )
    tests_bytes = tests_log_path.read_bytes()
    tests_text = (
        tests_bytes.decode("utf-16")
        if tests_bytes.startswith((b"\xff\xfe", b"\xfe\xff"))
        else tests_bytes.decode("utf-8-sig")
    )
    if "Ran 29 tests" not in tests_text or "\nOK" not in tests_text:
        raise RuntimeError("amendment unit-test evidence incomplete")

    review_path = (
        PROJECT_ROOT
        / "outputs"
        / "research_review_memo_round4_amendment01.md"
    )
    review = review_path.read_text(encoding="utf-8")
    if "CONDITIONAL GO" not in review or "serialization-only" not in review:
        raise RuntimeError("independent amendment approval missing")

    checkpoints = [
        PROJECT_ROOT
        / "checkpoints"
        / "validity"
        / "rq1_seed_43"
        / "action_only_best_action.pt",
        PROJECT_ROOT
        / "checkpoints"
        / "validity"
        / "rq1_seed_43"
        / "joint_best_action.pt",
    ]
    calibrations = [
        seed43_output / "calibration_action_only.json",
        seed43_output / "calibration_joint.json",
    ]
    invariant_paths = [
        PROJECT_ROOT / "configs" / "rq1_seed43.yaml",
        PROJECT_ROOT / "data" / "processed" / "test.jsonl",
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "perturbation_semantic_audit"
        / "audit_summary.json",
        PROJECT_ROOT / "scripts" / "evaluate_rq1_seed.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "rq1.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "metrics.py",
        PROJECT_ROOT / "scripts" / "aggregate_rq1_multiseed.py",
        *checkpoints,
        *calibrations,
    ]
    old_data_fingerprint = next(
        item
        for item in original_protocol["frozen_code"]
        if item["path"] == "src\\arsc_eval\\data.py"
    )
    current_data_path = PROJECT_ROOT / "src" / "arsc_eval" / "data.py"
    if sha256_file(current_data_path) == old_data_fingerprint["sha256"]:
        raise RuntimeError("serialization fix was not applied")

    failed_log_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "tmux_rq1_multiseed_attempt01_failed.log"
    )
    failed_log = failed_log_path.read_text(
        encoding="utf-8", errors="replace"
    )
    if (
        "Can't pickle local object" not in failed_log
        or "rq1_metrics" in failed_log
    ):
        raise RuntimeError("failure provenance does not match amendment")

    amendment = {
        "amendment_id": "RQ1-AMENDMENT-01",
        "status": "frozen_pre_result_engineering_amendment",
        "independent_review_decision": (
            "GO serialization-only fix; CONDITIONAL GO evaluation restart"
        ),
        "original_protocol": fingerprint(original_protocol_path),
        "independent_review": fingerprint(review_path),
        "failed_attempt_log": fingerprint(failed_log_path),
        "result_visibility_gate": {
            "prediction_cache_absent": not forbidden_partial[0].exists(),
            "rq1_metrics_absent": not forbidden_partial[1].exists(),
            "saved_or_viewed_test_effect": False,
        },
        "authorized_change": {
            "file": "src\\arsc_eval\\data.py",
            "old": old_data_fingerprint,
            "new": fingerprint(current_data_path),
            "description": (
                "local closure replaced by module-level frozen dataclass "
                "callable; transform formulas and parameters unchanged"
            ),
        },
        "tests": {
            "unit_and_pixel_equivalence": fingerprint(tests_log_path),
            "windows_spawn_num_workers_8": fingerprint(worker_check_path),
            "worker_conditions": worker_check["conditions"],
        },
        "restart_invariants": [
            fingerprint(path) for path in invariant_paths
        ],
        "restart_boundary": {
            "first_stage": "seed43 evaluate_rq1",
            "reuse_seed43_training": True,
            "reuse_seed43_calibrations": True,
            "retrain_seed43": False,
            "recalibrate_seed43": False,
            "then_continue_seeds": [44, 45, 46, 47],
        },
    }
    output = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "rq1_protocol_amendment01.json"
    )
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != amendment:
            raise RuntimeError("frozen amendment differs; refusing overwrite")
    else:
        write_json(output, amendment)
    print(json.dumps(amendment, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
