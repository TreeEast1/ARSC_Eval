"""Create the result-blind, deliberately non-executable Round 11 binding draft.

This helper performs no archive, video, or label access.  Unknown archive-layout
facts stay explicit instead of being guessed.  The formal runner must reject the
result because its decision is NOT_RUN_DRAFT_ONLY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = PROJECT_ROOT / "outputs/validity/round11_daadx_preflight_protocol.json"
DEFAULT_REVIEW = PROJECT_ROOT / "outputs/validity/round11_runner_reviewer_decision.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/validity/round11_daadx_execution_binding.draft.json"
RUNNER = PROJECT_ROOT / "scripts/run_round11_daadx_preflight.py"
RUNNER_TESTS = PROJECT_ROOT / "tests/test_round11_daadx_preflight_runner.py"
CORE = PROJECT_ROOT / "src/arsc_eval/daadx_preflight.py"
EXPECTED_RUNNER_REVIEW_SCHEMA = "ARSC_ROUND11_RUNNER_REVIEWER_DECISION_V1"
EXPECTED_RUNNER_REVIEW_DECISION = "GO_CREATE_EXECUTION_BINDING_NOT_RUN"
EXPECTED_PROTOCOL_SHA256 = "01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880"
PROVENANCE_CLASSES = [
    "AUTHORITATIVE_SOURCE_ID",
    "AUTHORITATIVE_SESSION_ID",
    "AUTHORITATIVE_RAW_VIDEO_ID",
    "AUDITABLE_RAW_RECORDING_TOKEN",
    "AUDITABLE_ACQUISITION_RIG_SESSION",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def atomic_write(path: Path, payload: str) -> None:
    """Publish payload to ``path`` via same-directory tmp + flush + fsync + replace.

    The temporary file lives next to the target so the final ``os.replace`` is
    atomic on the same filesystem.  The temporary file is always cleaned up,
    including when the write or rename fails.
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def publish_draft(output: Path, payload: str, *, force: bool) -> None:
    """Refuse to clobber an existing output unless ``force`` is explicitly set.

    Publishing is always atomic (see :func:`atomic_write`).
    """
    output = output.resolve()
    if output.exists() and not force:
        raise FileExistsError(
            f"output already exists: {output}; pass --force to overwrite"
        )
    atomic_write(output, payload)


def tool_record(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "sha256": None, "status": "UNRESOLVED"}
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "status": "HOST_VERIFIED_DRAFT_ONLY",
    }


def validate_runner_review(review: Path, protocol: Path) -> dict[str, Any]:
    document = json.loads(review.read_text(encoding="utf-8"))
    if document.get("schema_version") != EXPECTED_RUNNER_REVIEW_SCHEMA:
        raise ValueError("unexpected runner-review schema")
    if document.get("decision") != EXPECTED_RUNNER_REVIEW_DECISION:
        raise ValueError("runner review does not authorize a NOT_RUN draft")
    if document.get("candidate_bytes_frozen_for_this_review") is not True:
        raise ValueError("runner review did not freeze candidate bytes")
    authorization = document.get("authorization", {})
    if (
        authorization.get("create_nonrun_execution_binding_draft") is not True
        or authorization.get("required_draft_decision") != "NOT_RUN_DRAFT_ONLY"
        or authorization.get("formal_runner_execution") is not False
        or authorization.get("archive_member_inventory") is not False
        or authorization.get("real_video_decode") is not False
        or authorization.get("real_label_read") is not False
    ):
        raise ValueError("runner-review authorization boundary differs")
    # Fail-closed: any of these capabilities being authorized would lift the
    # NOT_RUN draft beyond its permitted boundary.  Each must remain false.
    fail_closed_authorizations = (
        "create_go_run_execution_binding",
        "create_execution_go_reviewer_decision",
        "external_training_or_inference",
        "modify_or_refreeze_protocol",
        "write_attempt01_outputs",
    )
    for field in fail_closed_authorizations:
        if authorization.get(field) is not False:
            raise ValueError(
                f"runner-review authorization is not fail-closed: {field}"
            )
    expected = {
        relative(RUNNER): sha256_file(RUNNER),
        relative(RUNNER_TESTS): sha256_file(RUNNER_TESTS),
        relative(CORE): sha256_file(CORE),
        relative(protocol): sha256_file(protocol),
    }
    reviewed_items = [
        item
        for item in document.get("reviewed_files", [])
        if isinstance(item, dict)
    ]
    # Each of the four critical key paths (runner, runner tests, core,
    # protocol) must appear exactly once in reviewed_files.  A plain
    # dict comprehension would silently mask duplicates (last wins), so the
    # occurrence count is checked explicitly to fail closed on a duplicated or
    # missing critical path.
    for key_path in expected:
        occurrences = [
            item for item in reviewed_items if item.get("path") == key_path
        ]
        if len(occurrences) != 1:
            raise ValueError(
                f"runner review must bind {key_path} exactly once; "
                f"found {len(occurrences)}"
            )
    reviewed = {item.get("path"): item.get("sha256") for item in reviewed_items}
    mismatched = [path for path, digest in expected.items() if reviewed.get(path) != digest]
    if mismatched:
        raise ValueError(f"runner review does not bind current bytes: {mismatched}")
    if expected[relative(protocol)] != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("frozen protocol bytes differ")
    return document


def create_draft(
    *,
    protocol: Path,
    review: Path,
    scratch_root: Path,
    python_executable: Path,
    ffmpeg: Path | None,
    ffprobe: Path | None,
) -> dict[str, Any]:
    required = (protocol, review, RUNNER, RUNNER_TESTS, CORE, scratch_root)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"required draft inputs absent: {missing}")
    if not scratch_root.resolve().is_dir():
        raise NotADirectoryError(scratch_root)
    validate_runner_review(review, protocol)

    operational_draft = {
        "schema_version": "ARSC_ROUND11_DAADX_OPERATIONAL_CONTRACT_INCOMPLETE_DRAFT_V1",
        "archive_layout": {
            "annotation_members": {"train": None, "val": None, "test": None},
            "front_member_regex": None,
            "provenance_member": None,
            "provenance_allowed_classes": PROVENANCE_CLASSES,
            "uuid_column": "uuid",
            "status": "UNRESOLVED_NO_ARCHIVE_INVENTORY_AUTHORIZED",
        },
        "media_tools": {
            "ffmpeg": tool_record(ffmpeg),
            "ffprobe": tool_record(ffprobe),
        },
        "archive_bounds": {
            "max_raw_headers": 100_000,
            "max_members": 100_000,
            "max_member_bytes": 64 * 1024**2,
            "max_uncompressed_member_bytes": 32 * 1024**3,
            "max_tar_stream_bytes": 64 * 1024**3,
            "status": "DRAFT_REQUIRES_LAYOUT_INVENTORY_AND_INDEPENDENT_CAPACITY_REVIEW",
        },
        "scratch": {
            "root": str(scratch_root.resolve()),
            "work_directory_name": "round11-daadx-preflight.restricted",
            "minimum_free_bytes": 20 * 1024**3,
            "maximum_total_written_bytes": 32 * 1024**3,
            "maximum_single_file_bytes": 64 * 1024**2,
            "front_lifecycle": "EXTRACT_ONE_PROBE_REHASH_DELETE",
            "status": "HOST_PATH_VERIFIED_DRAFT_ONLY",
        },
        "label_worker": {
            "python_executable": str(python_executable.resolve()),
            "python_sha256": sha256_file(python_executable.resolve()),
            "isolation_flags": ["-I"],
            "timeout_seconds": 300,
            "environment_policy": "CLEAN_ALLOWLIST_NO_PYTHONPATH_NO_USER_SITE",
        },
        "artifact_topology": {
            "mode": "ATOMIC_FINAL_DIRECTORY_WITH_LOGICAL_READONLY_ALIASES",
            "external_alias_materialization": "FORBIDDEN_TO_PRESERVE_ATOMICITY",
            "internal_log_name": "round11_daadx_preflight.log",
            "internal_index_name": "round11_daadx_artifact_index.json",
        },
        "phase_policy": {
            "all_G0_G1_G2_G3_pass": "PREFLIGHT_PHASE1_DIAGNOSTIC_ONLY_NO_FORMAL_PUBLISH",
            "any_G0_G1_G2_fail": "FORMAL_STOP_WITH_CLOSED_ARTIFACTS",
            "G3_fail_after_G0_G1_G2_pass": "FORMAL_STOP_SHORT_CIRCUIT_G4_G7_INCONCLUSIVE",
        },
    }
    unresolved = [
        "promotion.final_execution_binding_schema_and_exact_field_allowlist",
        "promotion.final_operational_contract_schema_and_status_field_removal",
        "promotion.independent_execution_reviewer_GO_RUN_decision_and_hash_binding",
        "promotion.archive_and_selected_metadata_caps_after_authorized_layout_inventory",
        "operational_contract_draft.archive_layout.annotation_members.train",
        "operational_contract_draft.archive_layout.annotation_members.val",
        "operational_contract_draft.archive_layout.annotation_members.test",
        "operational_contract_draft.archive_layout.front_member_regex",
        "operational_contract_draft.archive_layout.provenance_member",
    ]
    if ffmpeg is None:
        unresolved.append("operational_contract_draft.media_tools.ffmpeg")
    if ffprobe is None:
        unresolved.append("operational_contract_draft.media_tools.ffprobe")

    return {
        "schema_version": "ARSC_ROUND11_DAADX_EXECUTION_BINDING_INCOMPLETE_DRAFT_V1",
        "decision": "NOT_RUN_DRAFT_ONLY",
        "claim_boundary": "NO_ARCHIVE_READ_NO_VIDEO_DECODE_NO_LABEL_READ_NO_FORMAL_OUTPUT_NO_TRAINING",
        "protocol_path": relative(protocol),
        "protocol_sha256": sha256_file(protocol),
        "runner_path": relative(RUNNER),
        "runner_sha256": sha256_file(RUNNER),
        "runner_tests_path": relative(RUNNER_TESTS),
        "runner_tests_sha256": sha256_file(RUNNER_TESTS),
        "core_path": relative(CORE),
        "core_sha256": sha256_file(CORE),
        "runner_reviewer_decision_path": relative(review),
        "runner_reviewer_decision_sha256": sha256_file(review),
        "future_execution_reviewer_decision_path": None,
        "operational_contract_draft": operational_draft,
        "unresolved_fields": unresolved,
        "protocol_override_authorized": False,
        "formal_output_authorized": False,
        "archive_access_authorized": False,
        "training_authorized": False,
        "attempt": "attempt01",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing output file (default refuses)",
    )
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--ffprobe", type=Path)
    args = parser.parse_args()
    draft = create_draft(
        protocol=args.protocol.resolve(),
        review=args.review.resolve(),
        scratch_root=args.scratch_root.resolve(),
        python_executable=args.python_executable.resolve(),
        ffmpeg=args.ffmpeg.resolve() if args.ffmpeg else None,
        ffprobe=args.ffprobe.resolve() if args.ffprobe else None,
    )
    payload = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    publish_draft(args.output, payload, force=args.force)
    print(f"NOT_RUN_DRAFT_ONLY {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
