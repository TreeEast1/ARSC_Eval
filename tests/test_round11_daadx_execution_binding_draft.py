from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "round11_binding_draft",
    ROOT / "scripts/create_round11_daadx_execution_binding_draft.py",
)
assert SPEC and SPEC.loader
draft_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(draft_module)


def test_draft_is_explicitly_non_executable_and_preserves_unknowns(tmp_path: Path) -> None:
    protocol = ROOT / "outputs/validity/round11_daadx_preflight_protocol.json"
    review = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"

    draft = draft_module.create_draft(
        protocol=protocol,
        review=review,
        scratch_root=tmp_path,
        python_executable=Path(__import__("sys").executable),
        ffmpeg=None,
        ffprobe=None,
    )

    assert draft["decision"] == "NOT_RUN_DRAFT_ONLY"
    assert draft["archive_access_authorized"] is False
    assert draft["formal_output_authorized"] is False
    assert draft["training_authorized"] is False
    assert draft["operational_contract_draft"]["archive_layout"]["provenance_member"] is None
    assert "operational_contract" not in draft
    assert draft["unresolved_fields"]
    assert draft["schema_version"].endswith("INCOMPLETE_DRAFT_V1")
    assert draft["operational_contract_draft"]["archive_layout"]["provenance_allowed_classes"] == draft_module.PROVENANCE_CLASSES
    assert any(item.startswith("promotion.") for item in draft["unresolved_fields"])


def test_formal_runner_rejects_not_run_draft_before_data_access(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import run_round11_daadx_preflight as runner

    draft = draft_module.create_draft(
        protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
        review=ROOT / "outputs/validity/round11_runner_reviewer_decision.json",
        scratch_root=tmp_path,
        python_executable=Path(sys.executable),
        ffmpeg=None,
        ffprobe=None,
    )
    draft_path = tmp_path / "draft.json"
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    with pytest.raises(runner.ContractError, match="lacks operational_contract"):
        runner.validate_execution_authority(
            ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
            draft_path,
            require_binding_in_head=False,
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema_version", "WRONG"),
        ("decision", "GO_RUN"),
        ("candidate_bytes_frozen_for_this_review", False),
    ],
)
def test_generator_rejects_invalid_upstream_review(
    tmp_path: Path, field: str, bad_value: object
) -> None:
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    review[field] = bad_value
    bad_review = ROOT / "outputs/validity/.round11_runner_review.invalid-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(__import__("sys").executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


def test_draft_layout_bounds_tools_and_promotion_blockers(tmp_path: Path) -> None:
    # ffmpeg is resolved against a real repo file; ffprobe stays unresolved.
    ffmpeg_file = ROOT / "scripts/create_round11_daadx_execution_binding_draft.py"
    draft = draft_module.create_draft(
        protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
        review=ROOT / "outputs/validity/round11_runner_reviewer_decision.json",
        scratch_root=tmp_path,
        python_executable=Path(sys.executable),
        ffmpeg=ffmpeg_file,
        ffprobe=None,
    )

    layout = draft["operational_contract_draft"]["archive_layout"]
    assert layout["annotation_members"] == {"train": None, "val": None, "test": None}
    assert layout["front_member_regex"] is None
    assert layout["provenance_member"] is None

    promotion_blockers = [
        field for field in draft["unresolved_fields"] if field.startswith("promotion.")
    ]
    assert len(promotion_blockers) >= 4

    bounds = draft["operational_contract_draft"]["archive_bounds"]
    scratch = draft["operational_contract_draft"]["scratch"]
    assert bounds["max_member_bytes"] == 64 * 1024**2
    assert scratch["maximum_single_file_bytes"] == 64 * 1024**2
    assert bounds["max_member_bytes"] == scratch["maximum_single_file_bytes"]
    for status in (bounds["status"], scratch["status"]):
        assert "DRAFT" in status
        assert "CONSERVATIVE" not in status
        assert "FINAL" not in status

    tools = draft["operational_contract_draft"]["media_tools"]
    assert tools["ffmpeg"]["status"] == "HOST_VERIFIED_DRAFT_ONLY"
    assert tools["ffmpeg"]["path"] == str(ffmpeg_file.resolve())
    assert len(tools["ffmpeg"]["sha256"]) == 64
    assert tools["ffprobe"] == {
        "path": None,
        "sha256": None,
        "status": "UNRESOLVED",
    }


def test_publish_draft_refuses_existing_output_and_preserves_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "draft.json"
    target.write_text("ORIGINAL", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        draft_module.publish_draft(target, "NEW", force=False)
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_publish_draft_force_overwrites_atomically_and_cleans_temp(
    tmp_path: Path,
) -> None:
    target = tmp_path / "draft.json"
    target.write_text("OLD", encoding="utf-8")
    draft_module.publish_draft(target, "NEWX", force=True)
    assert target.read_text(encoding="utf-8") == "NEWX"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_atomic_write_replace_failure_cleans_temp_and_does_not_create_target(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "draft.json"

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("os.replace failed")

    monkeypatch.setattr(draft_module.os, "replace", boom)
    with pytest.raises(OSError):
        draft_module.atomic_write(target, "PAYLOAD")
    assert not target.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_generator_rejects_stale_reviewed_files_hash(tmp_path: Path) -> None:
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    for item in review.get("reviewed_files", []):
        if isinstance(item, dict) and item.get("sha256"):
            item["sha256"] = "0" * 64
            break
    bad_review = ROOT / "outputs/validity/.round11_runner_review.stale-hash-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match="bind current bytes"):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


def test_generator_rejects_create_nonrun_authorization_false(
    tmp_path: Path,
) -> None:
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    review["authorization"]["create_nonrun_execution_binding_draft"] = False
    bad_review = ROOT / "outputs/validity/.round11_runner_review.authnonrun-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "field",
    [
        "create_go_run_execution_binding",
        "create_execution_go_reviewer_decision",
        "external_training_or_inference",
        "modify_or_refreeze_protocol",
        "write_attempt01_outputs",
    ],
)
def test_generator_rejects_fail_closed_authorization_true(
    tmp_path: Path, field: str
) -> None:
    # Lifting any one new capability boundary must be rejected fail-closed.
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    review["authorization"][field] = True
    bad_review = ROOT / (
        f"outputs/validity/.round11_runner_review.{field}-true-.json"
    ).replace("-.-", "-")
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match=f"not fail-closed: {field}"):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


def test_generator_rejects_duplicated_critical_reviewed_path(
    tmp_path: Path,
) -> None:
    # A duplicated critical key path must fail closure, not be masked by the
    # last-wins dict comprehension.
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    items = [item for item in review.get("reviewed_files", []) if isinstance(item, dict)]
    runner_path = draft_module.relative(draft_module.RUNNER)
    runner_item = next(item for item in items if item.get("path") == runner_path)
    review["reviewed_files"].append(dict(runner_item))
    bad_review = ROOT / "outputs/validity/.round11_runner_review.dup-critical-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match="exactly once"):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


def test_generator_rejects_missing_critical_reviewed_path(
    tmp_path: Path,
) -> None:
    # Removing a critical key path must fail closure too.
    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    protocol_path = draft_module.relative(
        ROOT / "outputs/validity/round11_daadx_preflight_protocol.json"
    )
    review["reviewed_files"] = [
        item
        for item in review.get("reviewed_files", [])
        if not (isinstance(item, dict) and item.get("path") == protocol_path)
    ]
    bad_review = ROOT / "outputs/validity/.round11_runner_review.missing-critical-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match="exactly once"):
            draft_module.create_draft(
                protocol=ROOT / "outputs/validity/round11_daadx_preflight_protocol.json",
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_review.unlink(missing_ok=True)


def test_generator_rejects_error_protocol_bytes(tmp_path: Path) -> None:
    bad_protocol = ROOT / "outputs/validity/.round11_protocol.badbytes-test.json"
    bad_protocol.write_bytes(b"not-the-frozen-protocol-bytes" + b"\x00" * 16)

    source = ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
    review = json.loads(source.read_text(encoding="utf-8"))
    protocol_path_rel = draft_module.relative(bad_protocol)
    bad_sha = draft_module.sha256_file(bad_protocol)
    original_protocol_rel = draft_module.relative(
        ROOT / "outputs/validity/round11_daadx_preflight_protocol.json"
    )
    rewired = False
    for item in review.get("reviewed_files", []):
        if isinstance(item, dict) and item.get("path") == original_protocol_rel:
            item["path"] = protocol_path_rel
            item["sha256"] = bad_sha
            rewired = True
            break
    if not rewired:
        review.setdefault("reviewed_files", []).append(
            {"path": protocol_path_rel, "sha256": bad_sha}
        )

    bad_review = ROOT / "outputs/validity/.round11_runner_review.badproto-test.json"
    try:
        bad_review.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match="frozen protocol bytes differ"):
            draft_module.create_draft(
                protocol=bad_protocol,
                review=bad_review,
                scratch_root=tmp_path,
                python_executable=Path(sys.executable),
                ffmpeg=None,
                ffprobe=None,
            )
    finally:
        bad_protocol.unlink(missing_ok=True)
        bad_review.unlink(missing_ok=True)
