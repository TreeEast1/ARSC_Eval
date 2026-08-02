"""Freeze the additive, result-blind Round 11 DAAD-X Phase-1 amendment.

This module is pure protocol plumbing.  It never reads a receipt, range
manifest, archive, label, video, or model output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ARSC_ROUND11_DAADX_PHASE1_DIAGNOSTIC_AMENDMENT_V1"
PROTOCOL_SCHEMA = "ARSC_ROUND11_DAADX_PREFLIGHT_PROTOCOL_V1"
EXPECTED_PROTOCOL_SHA256 = (
    "01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880"
)
PROTOCOL_PATH = "outputs/validity/round11_daadx_preflight_protocol.json"
CLAIM_PATH = "outputs/validity/.round11_daadx_phase1_attempt01.claim"
STAGING_PATH = "outputs/validity/round11_daadx_phase1_attempt01.staging"
FINAL_PATH = "outputs/validity/round11_daadx_phase1_attempt01"
AMENDMENT_PATH = "outputs/validity/round11_daadx_phase1_diagnostic_amendment.json"

ARTIFACTS = (
    "round11_daadx_preflight_protocol.json",
    "round11_daadx_phase1_diagnostic_amendment.json",
    "round11_daadx_phase1_execution_binding.json",
    "round11_daadx_phase1_execution_reviewer_decision.json",
    "round11_daadx_download_receipt.json",
    "round11_daadx_assembler_manifest.json",
    "round11_daadx_archive_hashes.json",
    "round11_daadx_tar_inventory.csv",
    "round11_daadx_member_hashes.csv",
    "round11_daadx_label_seal.json",
    "round11_daadx_uuid_media_binding.csv",
    "round11_daadx_media_probe.csv",
    "round11_daadx_provenance_assessment.json",
    "round11_daadx_phase1_results.json",
    "round11_daadx_phase1.log",
    "round11_daadx_phase1_artifact_index.json",
)
LEGAL_OUTCOMES = (
    "STOP_DAADX_PHASE1_EARLY_GATE_FAILURE",
    "PHASE1_G0_G3_PASS_AWAIT_INDEPENDENT_CLOSURE",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_regular(path: Path) -> None:
    require(not path.is_symlink(), f"path must not be a symlink: {path}")
    require(path.is_file(), f"regular file missing: {path}")


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _safe_repo_path(value: str) -> None:
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"path must be repository-relative: {value}")
    require(".." not in path.parts and "." not in path.parts, f"unsafe path: {value}")
    require("\\" not in value and bool(value), f"non-canonical path: {value}")


def build_amendment(
    protocol_bytes: bytes,
    *,
    expected_protocol_sha256: str = EXPECTED_PROTOCOL_SHA256,
) -> dict[str, Any]:
    require(
        sha256_bytes(protocol_bytes) == expected_protocol_sha256,
        "frozen protocol SHA256 differs",
    )
    protocol = json.loads(protocol_bytes.decode("utf-8"))
    require(isinstance(protocol, Mapping), "frozen protocol must be a JSON object")
    require(protocol.get("schema_version") == PROTOCOL_SCHEMA, "protocol schema differs")
    require(protocol.get("result_blind") is True, "protocol is not result-blind")
    require(protocol.get("attempt") == "attempt01", "protocol attempt differs")
    require(protocol.get("training_authorized") is False, "protocol permits training")
    require(
        protocol.get("authorization")
        == "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY",
        "protocol authorization differs",
    )
    formal = protocol.get("formal_output")
    require(isinstance(formal, Mapping), "protocol formal output is absent")
    original_paths = {
        "staging": formal.get("staging"),
        "final": formal.get("final"),
        "log": formal.get("log"),
        "artifact_index": formal.get("artifact_index"),
    }
    for value in (
        PROTOCOL_PATH,
        CLAIM_PATH,
        STAGING_PATH,
        FINAL_PATH,
        AMENDMENT_PATH,
        *original_paths.values(),
    ):
        require(isinstance(value, str), "output path is not a string")
        _safe_repo_path(value)
    phase_paths = {CLAIM_PATH, STAGING_PATH, FINAL_PATH, AMENDMENT_PATH}
    require(len(phase_paths) == 4, "phase-1 paths alias")
    require(not phase_paths.intersection(original_paths.values()), "phase/formal paths overlap")
    require(len(ARTIFACTS) == 16 and len(set(ARTIFACTS)) == 16, "artifact allowlist differs")
    require(ARTIFACTS[-1].endswith("artifact_index.json"), "artifact index must be last")

    return {
        "schema_version": SCHEMA,
        "generated_at_utc": "2026-08-02",
        "additive_only": True,
        "result_blind": True,
        "phase": "PHASE1_G0_G3_DIAGNOSTIC_ONLY",
        "attempt": "phase1_attempt01",
        "training_authorized": False,
        "original_protocol": {
            "path": PROTOCOL_PATH,
            "schema_version": PROTOCOL_SCHEMA,
            "sha256": expected_protocol_sha256,
            "byte_identical_required": True,
            "override_allowed": False,
        },
        "scope": {
            "gates_executed": ["G0", "G1", "G2", "G3"],
            "deferred_gate_status": {
                "G4": "DEFERRED_NOT_RUN_PHASE1",
                "G5": "DEFERRED_NOT_RUN_PHASE1",
                "G6": "DEFERRED_NOT_RUN_PHASE1",
                "G7": "DEFERRED_NOT_RUN_PHASE1",
            },
            "g8_status_field_allowed": False,
            "formal_g0_g8_verdict_allowed": False,
            "archive_content_access_authorized_by_this_amendment": False,
        },
        "execution_control": {
            "claim_path": CLAIM_PATH,
            "claim_creation": "EXCLUSIVE_XB_AFTER_STATIC_AUTHORITY_BEFORE_ANY_RECEIPT_MANIFEST_ARCHIVE_ACCESS",
            "claim_payload": ["schema_version", "phase", "attempt", "execution_binding_sha256", "random_token"],
            "file_fsync_required": True,
            "parent_directory_fsync_required": True,
            "persist_after_every_exit_or_exception": True,
            "automatic_deletion_or_reuse_allowed": False,
            "existing_or_stale_claim_action": "STOP_REQUIRE_INDEPENDENT_ATTEMPT02_REVIEW",
        },
        "output_topology": {
            "staging": STAGING_PATH,
            "final": FINAL_PATH,
            "publication": "EXACT_ALLOWLIST_INDEX_LAST_FSYNC_ATOMIC_RENAME_POST_REHASH",
            "no_overwrite": True,
            "original_formal_paths": original_paths,
            "original_formal_paths_must_remain_absent": True,
        },
        "artifact_contract": {
            "exact_files": list(ARTIFACTS),
            "artifact_index": ARTIFACTS[-1],
            "artifact_index_self_excluded": True,
            "snapshots_are_exact_input_bytes": True,
            "all_entries_regular_non_symlink": True,
            "bytes_and_sha256_required": True,
            "console_only_pass_allowed": False,
        },
        "outcomes": {
            LEGAL_OUTCOMES[0]: {
                "condition": "ANY_OF_G0_G1_G2_G3_FAILS_OR_IS_INCONCLUSIVE",
                "publish_hash_closed_phase1_evidence": True,
                "is_formal_g0_g8_verdict": False,
                "next_action": "INDEPENDENT_PHASE1_CLOSURE_REVIEW",
            },
            LEGAL_OUTCOMES[1]: {
                "condition": "ALL_OF_G0_G1_G2_G3_PASS",
                "publish_hash_closed_phase1_evidence": True,
                "is_formal_g0_g8_verdict": False,
                "next_action": "INDEPENDENT_PHASE1_CLOSURE_REVIEW",
            },
        },
        "independent_closure_review": {
            "schema_version": "ARSC_ROUND11_DAADX_PHASE1_CLOSURE_REVIEWER_DECISION_V1",
            "early_failure_decision": "ACCEPT_PHASE1_STOP_EARLY_GATE_FAILURE",
            "all_pass_decision": "GO_IMPLEMENT_G4_G7_NOT_RUN",
            "go_run_allowed": False,
            "training_or_inference_allowed": False,
            "external_validity_claim_allowed": False,
        },
        "prohibited_effects": [
            "MODIFY_OR_REFREEZE_ORIGINAL_PROTOCOL",
            "CREATE_OR_MODIFY_ORIGINAL_FORMAL_OUTPUTS",
            "ISSUE_G0_G8_VERDICT",
            "EXECUTE_G4_G5_G6_G7_OR_G8",
            "AUTHORIZE_TRAINING_OR_INFERENCE",
            "AUTHORIZE_EXTERNAL_VALIDITY_CLAIM",
            "AUTHORIZE_ARCHIVE_ACCESS_WITHOUT_SEPARATE_HEAD_EXACT_BINDING_AND_GO_REVIEW",
        ],
    }


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def publish_no_overwrite(
    payload: Mapping[str, Any], output: Path, *, link_func: Any = os.link
) -> None:
    require(not output.exists() and not output.is_symlink(), "output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.parent.is_symlink(), "output parent must not be a symlink")
    temporary = output.with_name(output.name + ".tmp")
    require(not temporary.exists() and not temporary.is_symlink(), "temp already exists")
    owned = False
    try:
        with temporary.open("xb") as stream:
            owned = True
            stream.write(canonical_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        link_func(temporary, output)
        temporary.unlink()
        owned = False
        fsync_directory(output.parent)
    finally:
        if owned and (temporary.exists() or temporary.is_symlink()):
            temporary.unlink()
            fsync_directory(output.parent)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=Path, default=ROOT / PROTOCOL_PATH)
    parser.add_argument("--output", type=Path, default=ROOT / AMENDMENT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    protocol = Path(os.path.abspath(args.protocol))
    output = Path(os.path.abspath(args.output))
    require_regular(protocol)
    require(not output.is_symlink(), "output must not be a symlink")
    require(protocol.resolve() != output.resolve(), "protocol/output alias")
    amendment = build_amendment(protocol.read_bytes())
    publish_no_overwrite(amendment, output)
    print(f"WROTE {output.relative_to(ROOT.resolve()).as_posix()}")
    print(f"SHA256 {sha256_bytes(output.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
