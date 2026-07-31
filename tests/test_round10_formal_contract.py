from __future__ import annotations

import copy
from pathlib import Path

import pytest

from arsc_eval.round10_formal_contract import (
    validate_atomic_output_layout,
    validate_preformal_go,
    require_paths_absent,
)


def valid_go() -> dict:
    return {
        "schema_version": "ARSC_ROUND10_PREFORMAL_REVIEWER_DECISION_V1",
        "review_mode": {
            "outcome_blind": True,
            "checkpoint_tensors_loaded": False,
            "model_inference_run": False,
            "round10_nonzero_severity_predictions_read_or_computed": False,
            "round10_nonzero_severity_metric_outcomes_read_or_computed": False,
        },
        "verdict": {
            "decision": "GO_ROUND10_FORMAL_RUN_ATTEMPT01",
            "formal_run_authorized": True,
            "authorized_attempt": "attempt01",
        },
        "bindings": {"implementation_commit": "abc"},
        "reviewed_files_sha256": {"a": "A", "b": "B"},
    }


def test_preformal_go_requires_exact_commit_and_hash_set() -> None:
    validate_preformal_go(valid_go(), "abc", {"a": "A", "b": "B"})
    wrong_commit = valid_go()
    wrong_commit["bindings"]["implementation_commit"] = "other"
    with pytest.raises(ValueError, match="commit"):
        validate_preformal_go(wrong_commit, "abc", {"a": "A", "b": "B"})
    missing = valid_go()
    del missing["reviewed_files_sha256"]["b"]
    with pytest.raises(ValueError, match="path set"):
        validate_preformal_go(missing, "abc", {"a": "A", "b": "B"})


def test_preformal_go_rejects_outcome_access_and_run_false() -> None:
    seen = valid_go()
    seen["review_mode"][
        "round10_nonzero_severity_metric_outcomes_read_or_computed"
    ] = True
    with pytest.raises(ValueError, match="review mode"):
        validate_preformal_go(seen, "abc", {"a": "A", "b": "B"})
    stopped = valid_go()
    stopped["verdict"]["formal_run_authorized"] = False
    with pytest.raises(ValueError, match="not authorized"):
        validate_preformal_go(stopped, "abc", {"a": "A", "b": "B"})


def test_one_shot_guard_rejects_any_existing_artifact(
    tmp_path: Path,
) -> None:
    absent = [tmp_path / "a", tmp_path / "b"]
    require_paths_absent(absent)
    absent[1].write_text("occupied", encoding="utf-8")
    with pytest.raises(ValueError, match="already exist"):
        require_paths_absent(absent)


def test_atomic_output_layout_is_strict(tmp_path: Path) -> None:
    validate_atomic_output_layout(
        tmp_path / "round10_attempt01.staging",
        tmp_path / "round10_attempt01",
        tmp_path / "round10_attempt01.log",
        tmp_path / "round10_artifact_index.json",
    )
    with pytest.raises(ValueError, match="marked"):
        validate_atomic_output_layout(
            tmp_path / "temporary",
            tmp_path / "round10_attempt01",
            tmp_path / "run.log",
            tmp_path / "index.json",
        )
