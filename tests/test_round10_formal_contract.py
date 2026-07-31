from __future__ import annotations

import copy
from pathlib import Path

import pytest

from arsc_eval.round10_formal_contract import (
    PRE_RESULT_ARTIFACT_NAMES,
    REQUIRED_FORMAL_ARTIFACT_NAMES,
    validate_atomic_output_layout,
    validate_formal_artifacts,
    validate_preformal_go,
    require_paths_absent,
    unexpected_round10_output_paths,
)


def valid_go() -> dict:
    return {
        "schema_version": "ARSC_ROUND10_PREFORMAL_REVIEWER_DECISION_V1",
        "review_mode": {
            "outcome_blind": True,
            "checkpoint_tensors_loaded": False,
            "model_constructed_or_loaded": False,
            "model_inference_run": False,
            "round10_nonzero_severity_predictions_read_or_computed": False,
            "round10_nonzero_severity_logits_read_or_computed": False,
            "round10_nonzero_severity_confidences_read_or_computed": False,
            "round10_nonzero_severity_metric_outcomes_read_or_computed": False,
            "formal_run_started": False,
            "formal_implementation_modified": False,
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


@pytest.mark.parametrize(
    "name",
    (
        "model_constructed_or_loaded",
        "round10_nonzero_severity_logits_read_or_computed",
        "round10_nonzero_severity_confidences_read_or_computed",
    ),
)
def test_preformal_go_rejects_every_prohibited_true_state(name: str) -> None:
    decision = valid_go()
    decision["review_mode"][name] = True
    with pytest.raises(ValueError, match=name):
        validate_preformal_go(decision, "abc", {"a": "A", "b": "B"})


def test_preformal_go_rejects_missing_extra_and_mistyped_review_fields() -> None:
    missing = valid_go()
    del missing["review_mode"]["model_constructed_or_loaded"]
    with pytest.raises(ValueError, match="field set"):
        validate_preformal_go(missing, "abc", {"a": "A", "b": "B"})
    extra = valid_go()
    extra["review_mode"]["unbound"] = False
    with pytest.raises(ValueError, match="field set"):
        validate_preformal_go(extra, "abc", {"a": "A", "b": "B"})
    mistyped = valid_go()
    mistyped["review_mode"]["formal_run_started"] = 0
    with pytest.raises(ValueError, match="formal_run_started"):
        validate_preformal_go(mistyped, "abc", {"a": "A", "b": "B"})


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


def test_round10_output_allowlist_rejects_unknown_cache_and_tmp() -> None:
    paths = (
        "outputs/validity/round10_protocol.json",
        "outputs/validity/round10_semantic/page.png",
        "outputs/validity/round10_prediction_cache/cache.npz",
        "outputs/validity/custom_round10.tmp",
        "outputs/validity/round10_other/run_manifest.json",
        "scripts/analyze_round10_corruption.py",
        "outputs/unrelated.txt",
    )
    observed = unexpected_round10_output_paths(
        paths,
        allowed_exact=("outputs/validity/round10_protocol.json",),
        allowed_prefixes=("outputs/validity/round10_semantic",),
    )
    assert observed == [
        "outputs/validity/custom_round10.tmp",
        "outputs/validity/round10_other/run_manifest.json",
        "outputs/validity/round10_prediction_cache/cache.npz",
    ]


def make_formal_artifacts(tmp_path: Path) -> tuple[Path, dict]:
    final_dir = tmp_path / "outputs" / "validity" / "round10_attempt01"
    final_dir.mkdir(parents=True)
    internal = {}
    for name in PRE_RESULT_ARTIFACT_NAMES:
        path = final_dir / name
        path.write_bytes(name.encode("utf-8"))
        import hashlib

        internal[path.relative_to(tmp_path).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest().upper()
    result = {"artifact_sha256_before_result_json": internal}
    (final_dir / "round10_corruption_results.json").write_text(
        "{}",
        encoding="utf-8",
    )
    return final_dir, result


def test_final_artifact_contract_checks_exact_set_and_internal_hashes(
    tmp_path: Path,
) -> None:
    final_dir, result = make_formal_artifacts(tmp_path)
    observed = validate_formal_artifacts(final_dir, tmp_path, result)
    assert set(observed) == set(
        result["artifact_sha256_before_result_json"]
    )
    assert len(REQUIRED_FORMAL_ARTIFACT_NAMES) == 10


def test_final_artifact_contract_rejects_missing_extra_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    final_dir, result = make_formal_artifacts(tmp_path)
    missing = final_dir / PRE_RESULT_ARTIFACT_NAMES[0]
    missing.unlink()
    (final_dir / "replacement.bin").write_bytes(b"replacement")
    with pytest.raises(ValueError, match="path set"):
        validate_formal_artifacts(final_dir, tmp_path, result)
    (final_dir / "replacement.bin").unlink()
    missing.write_bytes(PRE_RESULT_ARTIFACT_NAMES[0].encode("utf-8"))
    result["artifact_sha256_before_result_json"][
        missing.relative_to(tmp_path).as_posix()
    ] = "0" * 64
    with pytest.raises(ValueError, match="hash differs"):
        validate_formal_artifacts(final_dir, tmp_path, result)
