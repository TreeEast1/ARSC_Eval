"""Freeze the additive, non-running DAAD-X archive-layout inventory protocol.

Only small Git-tracked authority files are read.  This generator never opens
the real assembler manifest, archive, chunks, labels, or videos.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_PROTOCOL_V1"
OUTPUT_PATH = "outputs/validity/round11_daadx_layout_inventory_protocol.json"
CLAIM_PATH = "outputs/validity/.round11_daadx_layout_inventory_attempt01.claim"
STAGING_PATH = "outputs/validity/round11_daadx_layout_inventory_attempt01.staging"
FINAL_PATH = "outputs/validity/round11_daadx_layout_inventory_attempt01"

AUTHORITY_SPECS = (
    (
        "outputs/validity/round11_daadx_transport_receipt.json",
        "ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_V1",
        "D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F",
        None,
    ),
    (
        "outputs/validity/round11_transport_receipt_postgeneration_reviewer_decision.json",
        "ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_POSTGENERATION_REVIEWER_DECISION_V1",
        "050680A0014D489F68652DEFF87767A4BA92B0B087DE3DF400E8A6C25369F758",
        "ACCEPT_ROUND11_TRANSPORT_RECEIPT",
    ),
    (
        "outputs/validity/round11_daadx_preflight_protocol.json",
        "ARSC_ROUND11_DAADX_PREFLIGHT_PROTOCOL_V1",
        "01642976FAE14A43A25BDD65CA8D007E3C944D2B91771907ABE1B59553FAE880",
        None,
    ),
    (
        "outputs/validity/round11_daadx_phase1_diagnostic_amendment.json",
        "ARSC_ROUND11_DAADX_PHASE1_DIAGNOSTIC_AMENDMENT_V1",
        "4B760550C75CF17B9EF32A9F203F1A63EB8428D90FEB4755C74B7A120D7430D9",
        None,
    ),
    (
        "outputs/validity/round11_phase1_amendment_reviewer_decision.json",
        "ARSC_ROUND11_DAADX_PHASE1_AMENDMENT_REVIEWER_DECISION_V1",
        "3C27C0CAD8C39968329FA2BD322EB6B16CD6B2D2D5B0D23684369E58E77920F9",
        "GO_FREEZE_COMMIT_PHASE1_DIAGNOSTIC_AMENDMENT",
    ),
    (
        "outputs/validity/round11_layout_inventory_design_reviewer_decision.json",
        "ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_DESIGN_REVIEWER_DECISION_V1",
        "12BDA6A5F8058B04431A3439927540DF2C6B16AF7E0FB31FCA15F550B028D9A9",
        "GO_DESIGN_LAYOUT_INVENTORY_PROTOCOL_NOT_RUN",
    ),
)

ARTIFACTS = (
    "round11_daadx_layout_inventory_protocol.json",
    "round11_daadx_layout_inventory_execution_binding.json",
    "round11_daadx_layout_inventory_execution_reviewer_decision.json",
    "round11_daadx_transport_receipt.json",
    "round11_daadx_assembler_manifest.json",
    "round11_daadx_layout_archive_hashes.json",
    "round11_daadx_layout_structure_summary.json",
    "round11_daadx_layout_public_inventory.csv",
    "round11_daadx_layout_restricted_path_seal.jsonl",
    "round11_daadx_layout_inventory_results.json",
    "round11_daadx_layout_inventory.log",
    "round11_daadx_layout_inventory_artifact_index.json",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


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


def unique_json(value: bytes, label: str) -> Mapping[str, Any]:
    def object_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            require(key not in result, f"{label} duplicate JSON key: {key}")
            result[key] = item
        return result

    parsed = json.loads(value.decode("utf-8"), object_pairs_hook=object_hook)
    require(isinstance(parsed, Mapping), f"{label} must be a JSON object")
    return parsed


def safe_repo_path(value: str) -> None:
    path = PurePosixPath(value)
    require(bool(value) and not path.is_absolute(), f"unsafe path: {value}")
    require(".." not in path.parts and "." not in path.parts, f"unsafe path: {value}")
    require("\\" not in value, f"noncanonical path: {value}")


def load_authority_bytes(root: Path = ROOT) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for path, _schema, _digest, _decision in AUTHORITY_SPECS:
        candidate = root / path
        require(not candidate.is_symlink() and candidate.is_file(), f"authority missing: {path}")
        result[path] = candidate.read_bytes()
    return result


def build_protocol(authority_bytes: Mapping[str, bytes]) -> dict[str, Any]:
    require(set(authority_bytes) == {item[0] for item in AUTHORITY_SPECS}, "authority set differs")
    authorities: list[dict[str, Any]] = []
    parsed_by_path: dict[str, Mapping[str, Any]] = {}
    for path, schema, digest, decision in AUTHORITY_SPECS:
        payload = authority_bytes[path]
        require(sha256_bytes(payload) == digest, f"authority SHA differs: {path}")
        parsed = unique_json(payload, path)
        require(parsed.get("schema_version") == schema, f"authority schema differs: {path}")
        if decision is not None:
            require(parsed.get("decision") == decision, f"authority decision differs: {path}")
        parsed_by_path[path] = parsed
        authorities.append(
            {"path": path, "schema_version": schema, "sha256": digest, "bytes": len(payload)}
        )

    receipt = parsed_by_path[AUTHORITY_SPECS[0][0]]
    require(receipt.get("transport_only") is True, "accepted receipt is not transport-only")
    archive = receipt.get("assembled_archive", {})
    manifest = receipt.get("assembler_manifest", {})
    require(archive.get("byte_count") == 18_585_647_156, "archive byte count differs")
    require(
        archive.get("sha256")
        == "98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965",
        "archive SHA differs",
    )
    for path in (OUTPUT_PATH, CLAIM_PATH, STAGING_PATH, FINAL_PATH, archive["path"], manifest["path"]):
        safe_repo_path(path)
    protected_paths = {
        "outputs/validity/.round11_daadx_phase1_attempt01.claim",
        "outputs/validity/round11_daadx_phase1_attempt01.staging",
        "outputs/validity/round11_daadx_phase1_attempt01",
        "outputs/validity/round11_daadx_preflight_attempt01.staging",
        "outputs/validity/round11_daadx_preflight_attempt01",
    }
    require(not {CLAIM_PATH, STAGING_PATH, FINAL_PATH}.intersection(protected_paths), "layout paths overlap protected outputs")
    require(len(ARTIFACTS) == len(set(ARTIFACTS)) == 12, "artifact allowlist differs")

    return {
        "schema_version": SCHEMA,
        "generated_at_utc": "2026-08-02",
        "additive_only": True,
        "result_blind": True,
        "phase": "ARCHIVE_LAYOUT_INVENTORY_ONLY",
        "attempt": "layout_inventory_attempt01",
        "training_authorized": False,
        "authorities": authorities,
        "input_contract": {
            "accepted_receipt_snapshot": AUTHORITY_SPECS[0][0],
            "real_manifest_path_declared_only_not_opened_by_generator": manifest["path"],
            "real_manifest_schema": manifest["schema_version"],
            "real_manifest_sha256": manifest["sha256"],
            "real_archive_path_declared_only_not_opened_by_generator": archive["path"],
            "real_archive_bytes": archive["byte_count"],
            "real_archive_sha256": archive["sha256"],
            "protocol_generation_accesses_real_manifest_archive_or_chunks": False,
        },
        "authorization": {
            "structure_discovery_only": True,
            "raw_gzip_tar_pax_header_path_type_size_access_after_separate_go": True,
            "opaque_regular_payload_drain_after_separate_go": True,
            "regular_payload_semantic_access": False,
            "label_value_or_provenance_row_access": False,
            "video_frame_access": False,
            "phase1_or_g0_g8_execution": False,
            "training_or_inference": False,
        },
        "execution_control": {
            "claim_path": CLAIM_PATH,
            "staging_path": STAGING_PATH,
            "final_path": FINAL_PATH,
            "static_validation_before_claim": [
                "HEAD_EXACT_PROTOCOL_RUNNER_TESTS_CORE_BINDING_AND_REVIEWER_IDENTITY_ONLY"
            ],
            "claim_creation": "EXCLUSIVE_XB_DURABLE_BEFORE_ANY_RECEIPT_MANIFEST_ARCHIVE_READ_STAT_OR_HASH",
            "claim_payload": ["schema_version", "phase", "attempt", "execution_binding_sha256", "random_token"],
            "strict_file_and_parent_directory_sync": True,
            "open_handle_path_identity_checks": True,
            "post_close_exact_stable_read": True,
            "claim_persists_on_every_exit_exception_interrupt_or_crash": True,
            "automatic_delete_reuse_or_recovery_allowed": False,
            "existing_claim_staging_or_final_action": "STOP_REQUIRE_REVIEWED_ATTEMPT02",
        },
        "parser_contract": {
            "authoritative_parser": "CUSTOM_RAW_GZIP_TAR_PAX_STATE_MACHINE_ONLY",
            "tarfile_or_libarchive_authority_allowed": False,
            "gzip": {
                "member_count": 1,
                "compressed_archive_sha_and_bytes_recomputed_same_scan": True,
                "header_flags_reserved_bits_rejected": True,
                "optional_header_crc_validated_when_present": True,
                "crc32_isize_and_eof_required": True,
                "concatenated_members_or_trailing_compressed_bytes_allowed": False,
            },
            "tar": {
                "raw_header_bytes": 512,
                "checksum": "STORED_OCTAL_MUST_MATCH_EITHER_UNSIGNED_OR_SIGNED_STANDARD_SUM",
                "numeric_encoding": "STRICT_ASCII_OCTAL_NO_BASE256",
                "allowed_types": ["REGULAR", "DIRECTORY", "PAX_EXTENDED_X", "PAX_GLOBAL_G"],
                "forbidden_types": ["GNU_LONGNAME", "GNU_LONGLINK", "SPARSE", "SYMLINK", "HARDLINK", "DEVICE", "FIFO", "UNKNOWN"],
                "two_consecutive_zero_end_blocks_required": True,
                "after_end_only_bounded_zero_padding_to_gzip_eof": True,
            },
            "pax": {
                "record_format": "STRICT_DECIMAL_LENGTH_SPACE_UNIQUE_KEY_EQUALS_UTF8_VALUE_NEWLINE",
                "duplicate_keys_allowed": False,
                "exact_allowed_keys": [
                    "path", "size", "mtime", "atime", "ctime", "uid", "gid",
                    "uname", "gname", "comment",
                ],
                "extended_x_path_and_size_overrides_applied": True,
                "global_g_path_or_size_allowed": False,
                "sparse_link_linkpath_charset_schily_gnu_or_unknown_keys_allowed": False,
                "directory_resolved_size_must_be_zero": True,
                "nonstructural_allowed_keys_recorded_by_key_hash_only": True,
            },
            "path": {
                "encoding": "STRICT_UTF8_NFC_RELATIVE_CANONICAL_POSIX",
                "raw_header_pax_and_resolved_relation_retained_in_restricted_seal": True,
                "absolute_dotdot_empty_backslash_control_ads_device_trailing_dot_space_allowed": False,
                "casefold_unicode_collision_or_duplicate_resolved_path_allowed": False,
            },
            "regular_payload": {
                "physical_access": "FIXED_BUFFER_OPAQUE_DRAIN_AND_DISCARD_TO_REACH_NEXT_HEADER",
                "parse_save_extract_sample_inspect_hash_log_or_expose_allowed": False,
                "bytes_retained_in_python_object_or_output": 0,
                "only_pax_metadata_payload_may_be_parsed": True,
            },
        },
        "resource_bounds": {
            "compressed_archive_bytes_exact": 18_585_647_156,
            "max_uncompressed_tar_stream_bytes": 137_438_953_472,
            "max_raw_headers": 200_000,
            "max_logical_members": 200_000,
            "max_single_regular_member_bytes": 17_179_869_184,
            "max_single_pax_payload_bytes": 1_048_576,
            "max_cumulative_pax_payload_bytes": 67_108_864,
            "max_path_utf8_bytes": 4_096,
            "max_post_end_zero_padding_bytes": 16_777_216,
            "regular_payload_drain_buffer_bytes": 1_048_576,
            "max_elapsed_seconds": 21_600,
            "max_in_memory_bytes": 268_435_456,
            "max_compressed_input_buffer_bytes": 1_048_576,
            "max_decompressed_output_buffer_bytes": 1_048_576,
            "max_public_inventory_output_bytes": 67_108_864,
            "max_restricted_path_seal_output_bytes": 2_147_483_648,
            "max_structure_summary_output_bytes": 16_777_216,
            "max_execution_log_output_bytes": 16_777_216,
            "max_collision_digest_entries": 400_000,
        },
        "artifact_contract": {
            "exact_files": list(ARTIFACTS),
            "exact_count": 12,
            "artifact_index": ARTIFACTS[-1],
            "artifact_index_last_and_self_excluded": True,
            "index_records_first_eleven_bytes_and_sha256": True,
            "all_files_regular_non_symlink_single_link": True,
            "strict_file_and_directory_sync": True,
            "atomic_no_replace_rename_and_post_publish_rehash": True,
            "stop_outcome_also_hash_closed": True,
            "crash_preserves_staging_and_claim": True,
        },
        "output_privacy": {
            "public_inventory_fields": [
                "member_ordinal", "raw_path_sha256", "resolved_path_sha256",
                "member_type", "size", "pax_flags",
            ],
            "public_inventory_contains_raw_paths": False,
            "restricted_path_seal_format": "STRICT_CANONICAL_JSON_PER_LINE",
            "restricted_path_seal_fields": [
                "member_ordinal", "raw_header_path", "pax_path", "resolved_path",
                "raw_path_sha256", "resolved_path_sha256", "member_type", "size", "pax_flags",
            ],
            "sealed_means_hash_closed_not_encrypted": True,
            "restricted_path_seal_allowed_in_ordinary_log_or_public_git": False,
            "public_inventory_and_restricted_seal_write_mode": "STREAM_CANONICAL_ROWS_DIRECTLY_TO_OWNED_STAGING_FILES",
            "full_raw_or_resolved_path_lists_may_accumulate_in_memory": False,
            "collision_state": "ONLY_FIXED_32_BYTE_PATH_DIGESTS_WITH_FROZEN_ENTRY_AND_MEMORY_CAPS",
            "current_member_paths_released_after_stream_write": True,
        },
        "outcomes": {
            "LAYOUT_INVENTORY_COMPLETE_AWAIT_INDEPENDENT_SELECTION": {
                "condition": "ALL_TRANSPORT_GZIP_TAR_PAX_PATH_TYPE_SIZE_AND_CLOSURE_CONTRACTS_PASS",
                "is_phase1_or_g0_g8_verdict": False,
            },
            "STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE": {
                "condition": "ANY_CONTRACT_FAILS_OR_IS_INCONCLUSIVE",
                "is_phase1_or_g0_g8_verdict": False,
            },
        },
        "selection_contract": {
            "selection_occurs_only_after_independent_closure_review": True,
            "allowed_evidence": ["path", "member_type", "extension", "size", "cardinality", "directory_structure"],
            "payload_disambiguation_allowed": False,
            "annotation_candidates": "EXACTLY_ONE_EACH_FOR_TRAIN_VAL_TEST_OR_STOP",
            "front_candidate": "ONE_FULL_MATCH_REGEX_WITH_NAMED_UUID_GROUP_PLUS_PATH_HASH_SET_AND_COUNT_OR_STOP",
            "provenance_candidate": "EXACTLY_ONE_STRUCTURAL_CANDIDATE_WITHOUT_SCHEMA_VALIDITY_CLAIM_OR_STOP",
            "ambiguous_or_missing_action": "STOP_LAYOUT_AMBIGUOUS_NO_PAYLOAD_DISAMBIGUATION",
            "accepted_decision": "ACCEPT_LAYOUT_AND_FREEZE_CANDIDATES",
            "selector_may_issue_phase1_go_run": False,
        },
        "prohibited_effects": [
            "MODIFY_OR_REFREEZE_ORIGINAL_PROTOCOL_OR_PHASE1_AMENDMENT",
            "READ_RECEIPT_MANIFEST_OR_ARCHIVE_BEFORE_DURABLE_LAYOUT_CLAIM",
            "USE_TARFILE_OR_LIBARCHIVE_AS_AUTHORITATIVE_PATH_PARSER",
            "PARSE_SAVE_SAMPLE_HASH_LOG_OR_EXPOSE_REGULAR_MEMBER_PAYLOAD",
            "READ_ANNOTATION_VALUES_PROVENANCE_ROWS_OR_VIDEO_FRAMES",
            "USE_PAYLOAD_TO_DISAMBIGUATE_LAYOUT",
            "CREATE_PHASE1_CLAIM_OR_OUTPUTS",
            "ISSUE_G0_G8_FORMAL_PHASE1_EXTERNAL_VALIDITY_OR_TRAINING_CLAIM",
            "RUN_LAYOUT_INVENTORY_WITHOUT_SEPARATE_HEAD_EXACT_BINDING_AND_GO_REVIEW",
        ],
        "next_required_action": "INDEPENDENT_RESULT_BLIND_PROTOCOL_FREEZE_REVIEW_NOT_RUN",
    }


def sync_directory_strict(path: Path) -> None:
    require(path.is_dir() and not path.is_symlink(), "directory sync target is invalid")
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        flush = kernel32.FlushFileBuffers
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        handle = create_file(str(path), 0x40000000, 7, None, 3, 0x22000000, None)
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error), path)
        try:
            if not flush(handle):
                error = ctypes.get_last_error()
                raise OSError(error, os.strerror(error), path)
        finally:
            if not close(handle):
                error = ctypes.get_last_error()
                raise OSError(error, os.strerror(error), path)
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_no_overwrite(payload: Mapping[str, Any], output: Path, *, link_func: Any = os.link) -> None:
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
        sync_directory_strict(output.parent)
    finally:
        if owned and (temporary.exists() or temporary.is_symlink()):
            temporary.unlink()
            sync_directory_strict(output.parent)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = Path(os.path.abspath(args.output))
    require(output.resolve() == (ROOT / OUTPUT_PATH).resolve(), "formal protocol output path differs")
    protocol = build_protocol(load_authority_bytes())
    publish_no_overwrite(protocol, output)
    print(f"WROTE {OUTPUT_PATH}")
    print(f"SHA256 {sha256_bytes(output.read_bytes())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
