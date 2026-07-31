"""Strict outcome-blind authorization and one-shot output guards."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


GO_SCHEMA = "ARSC_ROUND10_PREFORMAL_REVIEWER_DECISION_V1"
GO_DECISION = "GO_ROUND10_FORMAL_RUN_ATTEMPT01"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_preformal_go(
    decision: Mapping[str, Any],
    implementation_commit: str,
    expected_reviewed_hashes: Mapping[str, str],
) -> None:
    require(decision["schema_version"] == GO_SCHEMA, "wrong GO schema")
    review = decision["review_mode"]
    require(review["outcome_blind"] is True, "GO review was not outcome blind")
    for name in (
        "checkpoint_tensors_loaded",
        "model_inference_run",
        "round10_nonzero_severity_predictions_read_or_computed",
        "round10_nonzero_severity_metric_outcomes_read_or_computed",
    ):
        require(review[name] is False, f"GO review mode differs: {name}")
    verdict = decision["verdict"]
    require(
        verdict["decision"] == GO_DECISION,
        "formal-run GO decision differs",
    )
    require(
        verdict["formal_run_authorized"] is True,
        "formal run is not authorized",
    )
    require(
        verdict["authorized_attempt"] == "attempt01",
        "wrong authorized attempt",
    )
    bindings = decision["bindings"]
    require(
        bindings["implementation_commit"] == implementation_commit,
        "GO implementation commit differs",
    )
    reviewed = decision["reviewed_files_sha256"]
    require(
        set(reviewed) == set(expected_reviewed_hashes),
        "GO reviewed path set differs",
    )
    require(
        all(
            reviewed[path] == digest
            for path, digest in expected_reviewed_hashes.items()
        ),
        "GO reviewed file hash differs",
    )


def require_paths_absent(paths: Sequence[Path]) -> None:
    existing = sorted(str(path) for path in paths if path.exists())
    require(not existing, f"one-shot artifacts already exist: {existing}")


def validate_atomic_output_layout(
    staging_dir: Path,
    final_dir: Path,
    log_path: Path,
    artifact_index_path: Path,
) -> None:
    paths = (staging_dir, final_dir, log_path, artifact_index_path)
    require(len(set(paths)) == 4, "formal output paths must be distinct")
    require(
        staging_dir.parent == final_dir.parent,
        "staging and final directories must share a parent volume",
    )
    require(
        staging_dir.name.endswith(".staging"),
        "staging directory must be visibly marked",
    )
    require(
        "attempt01" in final_dir.name,
        "final directory must identify attempt01",
    )
