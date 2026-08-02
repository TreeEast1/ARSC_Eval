"""Result-blind, fail-closed Round 11 DAAD-X preflight runner draft.

This runner deliberately implements archive/population/decode/provenance gates
only.  Duplicate search, threshold QA, cross-dataset matching, grouping, split
construction, training, checkpoint loading, and model inference are absent.
Consequently G4-G7 remain INCONCLUSIVE in this draft and its scientific
verdict can only be STOP.  A formal invocation additionally requires a frozen
protocol and a reviewed hash binding for this exact runner.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.daadx_preflight import (
    EXPECTED_GATE_IDS,
    GateStatus,
    canonical_json_sha256,
    canonical_tar_path,
    parse_uuid_split_seal,
    sha256_bytes,
    sha256_file,
)


RUNNER_PATH = Path(__file__).resolve()
RUNNER_TEST_PATH = PROJECT_ROOT / "tests/test_round11_daadx_preflight_runner.py"
CORE_PATH = PROJECT_ROOT / "src/arsc_eval/daadx_preflight.py"
EXPECTED_ARCHIVE_BYTES = 18_585_647_156
EXPECTED_UUIDS = 1_566
PROTOCOL_SCHEMA = "ARSC_ROUND11_DAADX_PREFLIGHT_PROTOCOL_V1"
EXECUTION_BINDING_SCHEMA = "ARSC_ROUND11_DAADX_EXECUTION_BINDING_V1"
EXECUTION_REVIEW_SCHEMA = "ARSC_ROUND11_DAADX_EXECUTION_REVIEWER_DECISION_V1"
EXECUTION_REVIEWER_ROLE = "independent_round11_preflight_execution_reviewer"
EXECUTION_GO = "GO_RUN"

REQUIRED_ARTIFACTS = (
    "round11_daadx_preflight_protocol.json",
    "round11_daadx_download_receipt.json",
    "round11_daadx_archive_hashes.json",
    "round11_daadx_tar_inventory.csv",
    "round11_daadx_member_hashes.csv",
    "round11_daadx_label_seal.json",
    "round11_daadx_uuid_media_binding.csv",
    "round11_daadx_media_probe.csv",
    "round11_daadx_threshold_qa.json",
    "round11_daadx_duplicate_edges.csv",
    "round11_daadx_cross_dataset_overlap.csv",
    "round11_daadx_source_groups.csv",
    "round11_daadx_split_audit.csv",
    "round11_daadx_preflight_results.json",
    "round11_daadx_preflight.log",
    "round11_daadx_artifact_index.json",
)

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class ContractError(RuntimeError):
    """Frozen authorization or artifact contract is insufficient."""


class ArchiveSafetyError(RuntimeError):
    """Archive bytes, gzip structure, tar header, path, or type is unsafe."""


@dataclass(frozen=True)
class ArchiveMemberAudit:
    canonical_path: str
    path_sha256: str
    member_type: str
    size: int
    mtime: int | float
    content_sha256: str | None
    header_checksum_valid: bool


@dataclass(frozen=True)
class ArchiveAudit:
    archive_bytes: int
    sha256_read_1: str
    sha256_read_2: str
    double_read_match: bool
    gzip_integrity: bool
    tar_integrity: bool
    raw_header_count: int
    member_count: int
    uncompressed_member_bytes: int
    tar_stream_bytes: int
    members: tuple[ArchiveMemberAudit, ...]


@dataclass(frozen=True)
class ProvenanceAssessment:
    passed: bool
    eligible_count: int
    accepted_count: int
    missing_uuids: tuple[str, ...]
    invalid_uuids: tuple[str, ...]
    public_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class MediaProbe:
    codec: str
    fps: float
    duration_seconds: float
    container_frame_count: int
    decoded_frame_count: int
    width: int
    height: int
    full_decode_pass: bool
    error: str = ""


@dataclass(frozen=True)
class ArchiveBounds:
    max_raw_headers: int
    max_members: int
    max_member_bytes: int
    max_uncompressed_member_bytes: int
    max_tar_stream_bytes: int


@dataclass(frozen=True)
class ScratchContract:
    root: Path
    work_directory_name: str
    minimum_free_bytes: int
    maximum_total_written_bytes: int
    maximum_single_file_bytes: int


@dataclass(frozen=True)
class OperationalView:
    protocol: dict[str, Any]
    binding: dict[str, Any]
    operational_contract: dict[str, Any]
    staging: Path
    final: Path
    logical_aliases: tuple[tuple[str, str], ...]
    archive_bounds: ArchiveBounds
    scratch: ScratchContract


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _csv_bytes(fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _git_head_bytes(path: Path) -> bytes:
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as error:
        raise ContractError("review binding must be inside the repository") from error
    try:
        return subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "show", f"HEAD:{relative}"],
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as error:
        raise ContractError(f"binding is not committed in HEAD: {relative}") from error


def _require_head_exact(path: Path) -> None:
    if sha256_bytes(_git_head_bytes(path)) != sha256_file(path):
        raise ContractError(f"working bytes differ from HEAD: {_relative(path)}")


def validate_execution_authority(
    protocol_path: Path,
    execution_binding_path: Path | None,
    *,
    runner_path: Path = RUNNER_PATH,
    runner_test_path: Path = RUNNER_TEST_PATH,
    core_path: Path = CORE_PATH,
    require_binding_in_head: bool = True,
) -> OperationalView:
    """Return one protocol+binding operational view or fail before data access."""

    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise ContractError("unexpected or unfrozen protocol schema")
    if protocol.get("direction") != "DAADX_PREFLIGHT_FIRST_THEN_CANDIDATE_A_IF_STOP":
        raise ContractError("protocol direction is not frozen DAAD-X preflight")
    if protocol.get("authorization") != "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY":
        raise ContractError("protocol exceeds or lacks preflight-only authority")
    if protocol.get("result_blind") is not True or protocol.get("attempt") != "attempt01":
        raise ContractError("protocol is not the frozen result-blind attempt01")
    if protocol.get("training_authorized") is not False:
        raise ContractError("training must remain unauthorized")

    runner_relative = _relative(runner_path)
    test_relative = _relative(runner_test_path)
    core_relative = _relative(core_path)
    protocol_relative = _relative(protocol_path)
    runner_hash = sha256_file(runner_path)
    if execution_binding_path is None or not execution_binding_path.is_file():
        raise ContractError(
            "future independent execution binding is absent"
        )
    binding = json.loads(execution_binding_path.read_text(encoding="utf-8"))
    operational = binding.get("operational_contract")
    if not isinstance(operational, dict):
        raise ContractError("execution binding lacks operational_contract")
    reviewer_path_text = binding.get("reviewer_decision_path")
    if not isinstance(reviewer_path_text, str) or not reviewer_path_text:
        raise ContractError("execution binding lacks reviewer decision path")
    reviewer_path_value = Path(reviewer_path_text)
    reviewer_path = (
        reviewer_path_value.resolve()
        if reviewer_path_value.is_absolute()
        else (PROJECT_ROOT / reviewer_path_value).resolve()
    )
    if not reviewer_path.is_file():
        raise ContractError("bound independent reviewer decision is absent")
    reviewer_relative = _relative(reviewer_path)
    required = {
        "schema_version": EXECUTION_BINDING_SCHEMA,
        "decision": EXECUTION_GO,
        "protocol_path": protocol_relative,
        "protocol_sha256": sha256_file(protocol_path),
        "runner_path": runner_relative,
        "runner_sha256": runner_hash,
        "runner_tests_path": test_relative,
        "runner_tests_sha256": sha256_file(runner_test_path),
        "core_path": core_relative,
        "core_sha256": sha256_file(core_path),
        "reviewer_decision_path": reviewer_relative,
        "reviewer_decision_sha256": sha256_file(reviewer_path),
        "operational_contract_sha256": canonical_json_sha256(operational),
        "training_authorized": False,
        "attempt": protocol.get("attempt"),
    }
    mismatches = [key for key, value in required.items() if binding.get(key) != value]
    if mismatches:
        raise ContractError(f"execution binding mismatch: {mismatches}")

    reviewer_decision = json.loads(reviewer_path.read_text(encoding="utf-8"))
    reviewed = {
        "schema_version": EXECUTION_REVIEW_SCHEMA,
        "decision": EXECUTION_GO,
        "reviewer_role": EXECUTION_REVIEWER_ROLE,
        "protocol_path": protocol_relative,
        "protocol_sha256": required["protocol_sha256"],
        "runner_path": runner_relative,
        "runner_sha256": required["runner_sha256"],
        "runner_tests_path": test_relative,
        "runner_tests_sha256": required["runner_tests_sha256"],
        "core_path": core_relative,
        "core_sha256": required["core_sha256"],
        "operational_contract_sha256": required["operational_contract_sha256"],
        "training_authorized": False,
        "attempt": protocol.get("attempt"),
    }
    if set(reviewer_decision) != set(reviewed):
        raise ContractError("independent reviewer decision field set differs from fixed schema")
    review_mismatches = [
        key for key, value in reviewed.items() if reviewer_decision.get(key) != value
    ]
    if review_mismatches:
        raise ContractError(
            f"independent reviewer decision mismatch: {review_mismatches}"
        )
    if require_binding_in_head:
        _require_head_exact(execution_binding_path)
        _require_head_exact(protocol_path)
        _require_head_exact(runner_path)
        _require_head_exact(runner_test_path)
        _require_head_exact(core_path)
        _require_head_exact(reviewer_path)
    return validate_protocol_contract(protocol, binding)


def validate_protocol_contract(
    protocol: Mapping[str, Any], binding: Mapping[str, Any]
) -> OperationalView:
    """Overlay physical operations without changing any frozen scientific field."""

    official = protocol.get("official_input", {})
    if official.get("expected_content_length_bytes") != EXPECTED_ARCHIVE_BYTES:
        raise ContractError("official archive byte contract is not frozen exactly")
    if official.get("expected_unique_uuid_count") != EXPECTED_UUIDS:
        raise ContractError("frozen UUID count is not 1566")
    if official.get("expected_front_binding_count") != EXPECTED_UUIDS:
        raise ContractError("frozen front binding count is not 1566")

    formal = protocol.get("formal_output", {})
    if tuple(formal.get("required_artifacts", ())) != REQUIRED_ARTIFACTS:
        raise ContractError("formal artifact allowlist is absent or differs")
    staging_text, final_text = formal.get("staging"), formal.get("final")
    if not isinstance(staging_text, str) or not isinstance(final_text, str):
        raise ContractError("staging/final output paths are missing")
    staging = (PROJECT_ROOT / staging_text).resolve()
    final = (PROJECT_ROOT / final_text).resolve()
    if staging.parent != final.parent or not staging.name.endswith(".staging"):
        raise ContractError("atomic staging and final directories must share a parent")
    external_log = (PROJECT_ROOT / str(formal.get("log", ""))).resolve()
    external_index = (PROJECT_ROOT / str(formal.get("artifact_index", ""))).resolve()

    operational = binding.get("operational_contract", {})
    expected_operational_keys = {
        "schema_version",
        "archive_layout",
        "media_tools",
        "archive_bounds",
        "scratch",
        "label_worker",
        "artifact_topology",
        "phase_policy",
    }
    if set(operational) != expected_operational_keys:
        raise ContractError("operational_contract field set differs from allowlist")
    if operational.get("schema_version") != "ARSC_ROUND11_DAADX_OPERATIONAL_CONTRACT_V1":
        raise ContractError("unexpected operational contract schema")
    layout = operational.get("archive_layout", {})
    annotations = layout.get("annotation_members")
    if not isinstance(annotations, dict) or set(annotations) != {"train", "val", "test"}:
        raise ContractError("exact annotation member paths are not frozen")
    front_regex = layout.get("front_member_regex")
    if not isinstance(front_regex, str) or "?P<uuid>" not in front_regex:
        raise ContractError("front member regex with named UUID group is not frozen")
    provenance = layout.get("provenance_member")
    if not isinstance(provenance, str) or not provenance:
        raise ContractError("nonlabel provenance member is not frozen")
    if set(layout.get("provenance_allowed_classes", ())) != set(
        _PROVENANCE_REQUIREMENTS
    ):
        raise ContractError("authoritative/auditable provenance taxonomy is not frozen")
    if layout.get("uuid_column") != "uuid":
        raise ContractError("UUID seal column is not frozen")
    if protocol.get("group_split", {}).get("split_name_normalization") != {
        "val": "validation"
    }:
        raise ContractError("frozen val/validation normalization differs")

    tools = operational.get("media_tools", {})
    for name in ("ffmpeg", "ffprobe"):
        item = tools.get(name, {})
        if not isinstance(item.get("path"), str) or not re.fullmatch(
            r"[0-9A-F]{64}", str(item.get("sha256", ""))
        ):
            raise ContractError(f"explicit {name} path/hash is not frozen")
    bounds_value = operational.get("archive_bounds", {})
    try:
        bounds = ArchiveBounds(
            **{field: int(bounds_value[field]) for field in ArchiveBounds.__dataclass_fields__}
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError("archive bounds are incomplete") from error
    if set(bounds_value) != set(ArchiveBounds.__dataclass_fields__) or any(
        value <= 0 for value in asdict(bounds).values()
    ):
        raise ContractError("archive bounds must be exact positive integers")
    if bounds.max_members > bounds.max_raw_headers:
        raise ContractError("member bound cannot exceed raw-header bound")
    if bounds.max_member_bytes > bounds.max_uncompressed_member_bytes:
        raise ContractError("single-member bound exceeds total member bound")
    if bounds.max_uncompressed_member_bytes > bounds.max_tar_stream_bytes:
        raise ContractError("uncompressed member bound exceeds tar-stream bound")

    scratch_value = operational.get("scratch", {})
    expected_scratch = {
        "root",
        "work_directory_name",
        "minimum_free_bytes",
        "maximum_total_written_bytes",
        "maximum_single_file_bytes",
        "front_lifecycle",
    }
    if set(scratch_value) != expected_scratch:
        raise ContractError("scratch field set differs")
    scratch = ScratchContract(
        root=Path(str(scratch_value["root"])).resolve(),
        work_directory_name=str(scratch_value["work_directory_name"]),
        minimum_free_bytes=int(scratch_value["minimum_free_bytes"]),
        maximum_total_written_bytes=int(scratch_value["maximum_total_written_bytes"]),
        maximum_single_file_bytes=int(scratch_value["maximum_single_file_bytes"]),
    )
    if (
        not Path(str(scratch_value["root"])).is_absolute()
        or not scratch.root.is_dir()
        or scratch_value["front_lifecycle"] != "EXTRACT_ONE_PROBE_REHASH_DELETE"
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", scratch.work_directory_name)
        or min(
            scratch.minimum_free_bytes,
            scratch.maximum_total_written_bytes,
            scratch.maximum_single_file_bytes,
        ) <= 0
    ):
        raise ContractError("scratch root/capacity/lifecycle is invalid")

    worker = operational.get("label_worker", {})
    expected_worker = {
        "python_executable",
        "python_sha256",
        "isolation_flags",
        "timeout_seconds",
        "environment_policy",
    }
    if set(worker) != expected_worker or worker.get("isolation_flags") != ["-I"]:
        raise ContractError("label worker isolation contract differs")
    if worker.get("environment_policy") != "CLEAN_ALLOWLIST_NO_PYTHONPATH_NO_USER_SITE":
        raise ContractError("label worker environment policy differs")
    python_path = Path(str(worker.get("python_executable", ""))).resolve()
    if (
        not Path(str(worker.get("python_executable", ""))).is_absolute()
        or not python_path.is_file()
        or sha256_file(python_path) != worker.get("python_sha256")
        or not 1 <= int(worker.get("timeout_seconds", 0)) <= 3600
    ):
        raise ContractError("label worker interpreter/hash/timeout differs")

    topology = operational.get("artifact_topology", {})
    if topology != {
        "mode": "ATOMIC_FINAL_DIRECTORY_WITH_LOGICAL_READONLY_ALIASES",
        "external_alias_materialization": "FORBIDDEN_TO_PRESERVE_ATOMICITY",
        "internal_log_name": "round11_daadx_preflight.log",
        "internal_index_name": "round11_daadx_artifact_index.json",
    }:
        raise ContractError("artifact topology is not the safe compatibility mode")
    if operational.get("phase_policy") != {
        "all_G0_G1_G2_G3_pass": "PREFLIGHT_PHASE1_DIAGNOSTIC_ONLY_NO_FORMAL_PUBLISH",
        "any_G0_G1_G2_fail": "FORMAL_STOP_WITH_CLOSED_ARTIFACTS",
        "G3_fail_after_G0_G1_G2_pass": "FORMAL_STOP_SHORT_CIRCUIT_G4_G7_INCONCLUSIVE",
    }:
        raise ContractError("phase-1 publication policy differs")
    aliases = (
        (_relative(external_log), f"{_relative(final)}/round11_daadx_preflight.log"),
        (_relative(external_index), f"{_relative(final)}/round11_daadx_artifact_index.json"),
    )
    return OperationalView(
        protocol=dict(protocol),
        binding=dict(binding),
        operational_contract=dict(operational),
        staging=staging,
        final=final,
        logical_aliases=aliases,
        archive_bounds=bounds,
        scratch=scratch,
    )


def _strict_tar_member_path(name: str) -> str:
    """Apply extraction-platform aliases in addition to POSIX safety."""

    if name.endswith("//"):
        raise ArchiveSafetyError("multiple trailing slashes are non-canonical")
    try:
        canonical = canonical_tar_path(name)
    except (TypeError, ValueError) as error:
        raise ArchiveSafetyError(str(error)) from error
    if unicodedata.normalize("NFC", canonical) != canonical:
        raise ArchiveSafetyError("tar member path is not Unicode NFC")
    for part in canonical.split("/"):
        if ":" in part or part.endswith((" ", ".")):
            raise ArchiveSafetyError("Windows ADS or trailing-dot/space path")
        device_stem = part.split(".", 1)[0].upper()
        if device_stem in _WINDOWS_RESERVED:
            raise ArchiveSafetyError("Windows reserved device path")
    return canonical


def _tar_octal(field: bytes, label: str) -> int:
    stripped = field.rstrip(b"\0 ").lstrip(b" ")
    if not stripped:
        return 0
    if any(byte not in b"01234567" for byte in stripped):
        raise ArchiveSafetyError(f"non-octal tar {label} field")
    return int(stripped, 8)


def _drain_exact(stream: Any, byte_count: int) -> None:
    remaining = byte_count
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise ArchiveSafetyError("truncated tar member payload")
        remaining -= len(chunk)


def _audit_raw_tar_headers(path: Path, bounds: ArchiveBounds) -> tuple[int, int]:
    """Stream raw headers/payloads before tarfile can normalize names."""

    allowed_payload_types = {b"\0", b"0", b"5"}
    allowed_metadata_types = {b"x", b"g"}  # PAX only; GNU L/K are forbidden.
    raw_headers = 0
    tar_stream_bytes = 0
    try:
        with gzip.open(path, "rb") as stream:
            zero_blocks = 0
            while True:
                header = stream.read(512)
                if not header:
                    break
                tar_stream_bytes += len(header)
                if tar_stream_bytes > bounds.max_tar_stream_bytes:
                    raise ArchiveSafetyError("uncompressed tar stream exceeds frozen bound")
                if len(header) != 512:
                    raise ArchiveSafetyError("truncated tar header block")
                if header == b"\0" * 512:
                    zero_blocks += 1
                    continue
                if zero_blocks:
                    raise ArchiveSafetyError("nonzero tar data after end marker")
                raw_headers += 1
                if raw_headers > bounds.max_raw_headers:
                    raise ArchiveSafetyError("raw tar header count exceeds frozen bound")
                stored_checksum = _tar_octal(header[148:156], "checksum")
                checksum_header = header[:148] + b" " * 8 + header[156:]
                if sum(checksum_header) != stored_checksum:
                    raise ArchiveSafetyError("tar header checksum mismatch")
                raw_name = header[:100].split(b"\0", 1)[0]
                raw_prefix = header[345:500].split(b"\0", 1)[0]
                try:
                    combined = (
                        raw_prefix + (b"/" if raw_prefix else b"") + raw_name
                    ).decode("utf-8", errors="strict")
                except UnicodeDecodeError as error:
                    raise ArchiveSafetyError("tar header path is not UTF-8") from error
                typeflag = header[156:157]
                if typeflag not in allowed_payload_types | allowed_metadata_types:
                    raise ArchiveSafetyError("forbidden raw tar typeflag")
                _strict_tar_member_path(combined)
                size = _tar_octal(header[124:136], "size")
                if size > bounds.max_member_bytes:
                    raise ArchiveSafetyError("raw tar member exceeds frozen size bound")
                padded = ((size + 511) // 512) * 512
                if tar_stream_bytes + padded > bounds.max_tar_stream_bytes:
                    raise ArchiveSafetyError("uncompressed tar stream exceeds frozen bound")
                _drain_exact(stream, padded)
                tar_stream_bytes += padded
            if zero_blocks < 2:
                raise ArchiveSafetyError("tar lacks two zero end-marker blocks")
    except ArchiveSafetyError:
        raise
    except (OSError, EOFError) as error:
        raise ArchiveSafetyError(f"gzip integrity failed: {type(error).__name__}") from error
    return raw_headers, tar_stream_bytes


def audit_archive(
    path: Path, expected_size: int, *, bounds: ArchiveBounds
) -> ArchiveAudit:
    """Perform G0 byte, double-hash, gzip, tar/path/type, and member-hash audit."""

    archive = path.resolve()
    if not archive.is_file():
        raise ArchiveSafetyError("archive is not a regular file")
    actual_size = archive.stat().st_size
    if actual_size != expected_size:
        raise ArchiveSafetyError(
            f"archive bytes differ: expected {expected_size}, observed {actual_size}"
        )
    first = sha256_file(archive)
    second = sha256_file(archive)
    if first != second:
        raise ArchiveSafetyError("independent sequential SHA-256 reads differ")
    raw_header_count, tar_stream_bytes = _audit_raw_tar_headers(archive, bounds)

    members: list[ArchiveMemberAudit] = []
    seen_exact: set[str] = set()
    seen_platform: set[str] = set()
    uncompressed_member_bytes = 0
    try:
        with tarfile.open(archive, mode="r:gz", errorlevel=2) as handle:
            for member in handle:
                if len(members) >= bounds.max_members:
                    raise ArchiveSafetyError("resolved member count exceeds frozen bound")
                canonical = _strict_tar_member_path(member.name)
                platform_key = unicodedata.normalize("NFC", canonical).casefold()
                if canonical in seen_exact or platform_key in seen_platform:
                    raise ArchiveSafetyError("duplicate or case/Unicode-colliding tar path")
                seen_exact.add(canonical)
                seen_platform.add(platform_key)
                if getattr(member, "sparse", None):
                    raise ArchiveSafetyError("sparse tar members are forbidden")
                if member.size > bounds.max_member_bytes:
                    raise ArchiveSafetyError("resolved member exceeds frozen size bound")
                uncompressed_member_bytes += int(member.size)
                if uncompressed_member_bytes > bounds.max_uncompressed_member_bytes:
                    raise ArchiveSafetyError("member byte total exceeds frozen bound")
                if member.isdir():
                    member_type = "directory"
                    content_hash = None
                elif member.isreg():
                    member_type = "regular_file"
                    source = handle.extractfile(member)
                    if source is None:
                        raise ArchiveSafetyError("regular member cannot be read")
                    digest = hashlib.sha256()
                    observed = 0
                    while chunk := source.read(1024 * 1024):
                        observed += len(chunk)
                        digest.update(chunk)
                    if observed != member.size:
                        raise ArchiveSafetyError("member size differs from tar header")
                    content_hash = digest.hexdigest().upper()
                else:
                    raise ArchiveSafetyError("links, devices, FIFO, and special members are forbidden")
                members.append(
                    ArchiveMemberAudit(
                        canonical_path=canonical,
                        path_sha256=sha256_bytes(canonical.encode("utf-8")),
                        member_type=member_type,
                        size=int(member.size),
                        mtime=member.mtime,
                        content_sha256=content_hash,
                        # Python tarfile rejects invalid header checksums while parsing.
                        header_checksum_valid=True,
                    )
                )
    except ArchiveSafetyError:
        raise
    except (tarfile.TarError, OSError, EOFError) as error:
        raise ArchiveSafetyError(f"tar integrity failed: {type(error).__name__}") from error
    return ArchiveAudit(
        archive_bytes=actual_size,
        sha256_read_1=first,
        sha256_read_2=second,
        double_read_match=True,
        gzip_integrity=True,
        tar_integrity=True,
        raw_header_count=raw_header_count,
        member_count=len(members),
        uncompressed_member_bytes=uncompressed_member_bytes,
        tar_stream_bytes=tar_stream_bytes,
        members=tuple(members),
    )


def _member_map(audit: ArchiveAudit) -> dict[str, ArchiveMemberAudit]:
    return {member.canonical_path: member for member in audit.members}


def read_regular_member_bytes(
    archive_path: Path, audit: ArchiveAudit, member_name: str
) -> bytes:
    """Read exactly one previously audited regular member without extraction."""

    canonical = _strict_tar_member_path(member_name)
    audited = _member_map(audit).get(canonical)
    if audited is None or audited.member_type != "regular_file":
        raise ArchiveSafetyError("selected member is absent or not regular")
    with tarfile.open(archive_path, mode="r:gz", errorlevel=2) as handle:
        member = handle.getmember(canonical)
        source = handle.extractfile(member)
        if source is None:
            raise ArchiveSafetyError("selected regular member cannot be read")
        payload = source.read()
    if len(payload) != audited.size or sha256_bytes(payload) != audited.content_sha256:
        raise ArchiveSafetyError("selected member differs from audited bytes")
    return payload


def extract_selected_regular_members(
    archive_path: Path,
    audit: ArchiveAudit,
    selected_names: Iterable[str],
    destination: Path,
) -> dict[str, Path]:
    """Extract only an explicit audited allowlist into a new restricted directory."""

    selected = tuple(selected_names)
    if len(set(selected)) != len(selected):
        raise ArchiveSafetyError("selected extraction members are duplicated")
    if destination.exists():
        raise FileExistsError(f"refusing existing extraction destination: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    outputs: dict[str, Path] = {}
    try:
        for name in selected:
            canonical = _strict_tar_member_path(name)
            payload = read_regular_member_bytes(archive_path, audit, canonical)
            # The on-disk name is a path hash, never a raw sensitive token.
            suffix = Path(canonical).suffix
            target = destination / f"{sha256_bytes(canonical.encode('utf-8'))}{suffix}"
            with target.open("xb") as stream:
                stream.write(payload)
                _flush_fsync(stream)
            outputs[canonical] = target
        _fsync_directory(destination)
    except Exception:
        # Destination is newly created and contains only this explicit allowlist.
        shutil.rmtree(destination)
        raise
    return outputs


def _flush_fsync(stream: Any) -> None:
    stream.flush()
    os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync; Windows commonly rejects directory handles."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_exclusive_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        _flush_fsync(stream)


def probe_front_members_one_at_a_time(
    archive_path: Path,
    audit: ArchiveAudit,
    internal_bindings: Mapping[str, str],
    *,
    scratch: ScratchContract,
    work_directory: Path,
    ffprobe_path: Path,
    ffmpeg_path: Path,
) -> tuple[bool, list[dict[str, Any]]]:
    """Stream one eligible front to scratch, probe, rehash, and delete it."""

    if work_directory.exists():
        raise FileExistsError("restricted front work directory already exists")
    work_directory.mkdir(parents=True, exist_ok=False)
    path_to_uuid = {path: uuid for uuid, path in internal_bindings.items()}
    audited = _member_map(audit)
    records: dict[str, dict[str, Any]] = {}
    total_written = 0
    io_failure = False
    try:
        with tarfile.open(archive_path, mode="r:gz", errorlevel=2) as handle:
            for member in handle:
                uuid = path_to_uuid.get(member.name)
                if uuid is None:
                    continue
                expected = audited[member.name]
                target = work_directory / f"current{Path(member.name).suffix}"
                probe: MediaProbe | None = None
                try:
                    if member.size > scratch.maximum_single_file_bytes:
                        raise OSError("front member exceeds frozen scratch single-file cap")
                    if total_written + member.size > scratch.maximum_total_written_bytes:
                        raise OSError("front extraction exceeds frozen cumulative scratch cap")
                    free = shutil.disk_usage(scratch.root).free
                    if free - member.size < scratch.minimum_free_bytes:
                        raise OSError("scratch free space below frozen reserve")
                    source = handle.extractfile(member)
                    if source is None:
                        raise OSError("eligible front cannot be streamed")
                    digest = hashlib.sha256()
                    observed = 0
                    with target.open("xb") as stream:
                        while chunk := source.read(1024 * 1024):
                            observed += len(chunk)
                            if observed > scratch.maximum_single_file_bytes:
                                raise OSError("stream exceeds scratch single-file cap")
                            digest.update(chunk)
                            stream.write(chunk)
                        _flush_fsync(stream)
                    total_written += observed
                    if (
                        observed != expected.size
                        or digest.hexdigest().upper() != expected.content_sha256
                    ):
                        raise ArchiveSafetyError("front bytes changed after G0 audit")
                    probe = probe_and_full_decode(
                        target, ffprobe_path=ffprobe_path, ffmpeg_path=ffmpeg_path
                    )
                    if sha256_file(target) != expected.content_sha256:
                        raise ArchiveSafetyError("front rehash differs after probe")
                    records[uuid] = {
                        "uuid": uuid,
                        "front_member_content_sha256": expected.content_sha256 or "",
                        **asdict(probe),
                    }
                except OSError:
                    io_failure = True
                    records[uuid] = {
                        "uuid": uuid,
                        "front_member_content_sha256": expected.content_sha256 or "",
                        **asdict(MediaProbe("", 0.0, 0.0, 0, 0, 0, 0, False, "OSError")),
                    }
                    break
                finally:
                    if target.exists():
                        try:
                            target.unlink()
                            _fsync_directory(work_directory)
                        except OSError:
                            io_failure = True
                if probe is not None and not probe.full_decode_pass:
                    # Decode failure does not prevent the next explicit UUID probe.
                    pass
    except ArchiveSafetyError:
        raise
    except (OSError, tarfile.TarError, EOFError):
        io_failure = True
    for uuid in sorted(set(internal_bindings) - set(records)):
        expected = audited[internal_bindings[uuid]]
        records[uuid] = {
            "uuid": uuid,
            "front_member_content_sha256": expected.content_sha256 or "",
            **asdict(
                MediaProbe(
                    "", 0.0, 0.0, 0, 0, 0, 0, False,
                    "OSError_NOT_PROCESSED" if io_failure else "MISSING_IN_STREAM",
                )
            ),
        }
    rows = [records[uuid] for uuid in sorted(records)]
    passed = (
        len(rows) == len(internal_bindings)
        and not io_failure
        and all(bool(row["full_decode_pass"]) for row in rows)
    )
    return passed, rows


def build_front_bindings(
    uuid_split_rows: Sequence[tuple[str, str]],
    audit: ArchiveAudit,
    front_member_regex: str,
) -> tuple[bool, list[dict[str, str]], dict[str, str]]:
    """Bind every eligible UUID to exactly one front member, without substitution."""

    pattern = re.compile(front_member_regex)
    eligible = {uuid for uuid, _ in uuid_split_rows}
    candidates: dict[str, list[ArchiveMemberAudit]] = {uuid: [] for uuid in eligible}
    for member in audit.members:
        if member.member_type != "regular_file":
            continue
        match = pattern.fullmatch(member.canonical_path)
        if match and match.group("uuid") in candidates:
            candidates[match.group("uuid")].append(member)
    rows: list[dict[str, str]] = []
    internal: dict[str, str] = {}
    passed = True
    split_by_uuid = dict(uuid_split_rows)
    for uuid in sorted(eligible):
        matches = candidates[uuid]
        status = "PASS" if len(matches) == 1 else ("MISSING" if not matches else "AMBIGUOUS")
        passed &= status == "PASS"
        member = matches[0] if len(matches) == 1 else None
        if member is not None:
            internal[uuid] = member.canonical_path
        rows.append(
            {
                "uuid": uuid,
                "official_split": split_by_uuid[uuid],
                "front_binding_status": status,
                "front_member_path_sha256": member.path_sha256 if member else "",
                "front_member_content_sha256": member.content_sha256 if member else "",
            }
        )
    return bool(passed), rows, internal


_PROVENANCE_REQUIREMENTS = {
    "AUTHORITATIVE_SOURCE_ID": ("source_id",),
    "AUTHORITATIVE_SESSION_ID": ("session_id",),
    "AUTHORITATIVE_RAW_VIDEO_ID": ("raw_video_id",),
    "AUDITABLE_RAW_RECORDING_TOKEN": ("raw_recording_token",),
    "AUDITABLE_ACQUISITION_RIG_SESSION": (
        "acquisition_timestamp",
        "camera_rig_signature",
        "multiview_sync_signature",
    ),
}
_PROVENANCE_ALLOWED_COLUMNS = {
    "uuid",
    "provenance_class",
    "source_id",
    "session_id",
    "raw_video_id",
    "raw_recording_token",
    "acquisition_timestamp",
    "camera_rig_signature",
    "multiview_sync_signature",
}
_PROVENANCE_REQUIRED_COLUMNS = {"uuid", "provenance_class"}


def assess_source_provenance(
    eligible_uuids: Iterable[str], records: Iterable[Mapping[str, str]]
) -> ProvenanceAssessment:
    """Accept only frozen authoritative/auditable nonlabel provenance classes."""

    eligible = set(eligible_uuids)
    by_uuid: dict[str, Mapping[str, str]] = {}
    duplicated: set[str] = set()
    for record in records:
        uuid = str(record.get("uuid", ""))
        if uuid not in eligible:
            continue
        if uuid in by_uuid:
            duplicated.add(uuid)
        by_uuid[uuid] = record
    missing = tuple(sorted(eligible - set(by_uuid)))
    invalid: list[str] = sorted(duplicated)
    public_rows: list[dict[str, str]] = []
    for uuid in sorted(eligible.intersection(by_uuid)):
        record = by_uuid[uuid]
        evidence_class = str(record.get("provenance_class", ""))
        required_fields = _PROVENANCE_REQUIREMENTS.get(evidence_class)
        valid = bool(
            required_fields
            and all(str(record.get(field, "")).strip() for field in required_fields)
        )
        if not valid or uuid in duplicated:
            invalid.append(uuid)
            status = "FAIL"
        else:
            status = "PASS"
        public_rows.append(
            {
                "uuid": uuid,
                "provenance_class": evidence_class,
                "provenance_status": status,
            }
        )
    invalid_tuple = tuple(sorted(set(invalid)))
    accepted = len(eligible) - len(missing) - len(invalid_tuple)
    return ProvenanceAssessment(
        passed=not missing and not invalid_tuple and accepted == len(eligible),
        eligible_count=len(eligible),
        accepted_count=accepted,
        missing_uuids=missing,
        invalid_uuids=invalid_tuple,
        public_rows=tuple(public_rows),
    )


def parse_provenance_csv(payload: bytes) -> list[dict[str, str]]:
    """Parse only an exact nonlabel provenance allowlist; reject extra columns."""

    reader = csv.reader(
        io.StringIO(payload.decode("utf-8-sig", errors="strict")), strict=True
    )
    try:
        fields = next(reader)
    except StopIteration as error:
        raise ContractError("provenance member is empty") from error
    if not fields or len(fields) != len(set(fields)):
        raise ContractError("provenance member header must contain unique columns")
    if set(fields) - _PROVENANCE_ALLOWED_COLUMNS:
        raise ContractError("provenance member contains unfrozen or potentially label columns")
    if not _PROVENANCE_REQUIRED_COLUMNS.issubset(fields):
        raise ContractError("provenance member lacks UUID/class columns")
    records: list[dict[str, str]] = []
    try:
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(fields):
                raise ContractError(
                    f"provenance row {line_number} width differs from header"
                )
            records.append(dict(zip(fields, row, strict=True)))
    except csv.Error as error:
        raise ContractError("provenance member is not strict CSV") from error
    return records


def _positive_int(value: Any) -> int:
    if value in (None, "", "N/A"):
        raise ValueError("missing frame count")
    result = int(value)
    if result <= 0:
        raise ValueError("frame count is not positive")
    return result


def _positive_fraction(value: str) -> float:
    result = float(Fraction(value))
    if not math.isfinite(result) or result <= 0:
        raise ValueError("fps is invalid")
    return result


def probe_and_full_decode(
    video_path: Path,
    *,
    ffprobe_path: Path,
    ffmpeg_path: Path,
    timeout_seconds: int = 1800,
) -> MediaProbe:
    """Count/probe and independently full-decode one video with explicit tools."""

    for tool in (ffprobe_path, ffmpeg_path):
        if not tool.is_absolute() or not tool.is_file():
            raise ContractError("ffmpeg/ffprobe must be explicit existing absolute paths")
    probe_command = [
        str(ffprobe_path), "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries",
        "stream=codec_name,avg_frame_rate,duration,nb_frames,nb_read_frames,width,height",
        "-show_entries", "format=duration", "-of", "json", str(video_path),
    ]
    try:
        probe = subprocess.run(
            probe_command, check=True, capture_output=True, text=True,
            timeout=timeout_seconds,
        )
        payload = json.loads(probe.stdout)
        streams = payload.get("streams", [])
        if len(streams) != 1:
            raise ValueError("expected exactly one selected video stream")
        stream = streams[0]
        codec = str(stream.get("codec_name", ""))
        fps = _positive_fraction(str(stream.get("avg_frame_rate", "")))
        duration = float(stream.get("duration") or payload.get("format", {}).get("duration"))
        if not codec or not math.isfinite(duration) or duration <= 0:
            raise ValueError("codec/duration metadata is invalid")
        container_frames = _positive_int(stream.get("nb_read_frames"))
        width, height = _positive_int(stream.get("width")), _positive_int(stream.get("height"))

        decode_command = [
            str(ffmpeg_path), "-v", "error", "-nostdin", "-xerror",
            "-err_detect", "explode", "-threads", "1", "-i", str(video_path),
            "-map", "0:v:0", "-vsync", "0", "-progress", "pipe:1",
            "-nostats", "-f", "null", "-",
        ]
        decode = subprocess.run(
            decode_command, check=True, capture_output=True, text=True,
            timeout=timeout_seconds,
        )
        frames = [
            int(line.split("=", 1)[1])
            for line in decode.stdout.splitlines()
            if line.startswith("frame=")
        ]
        decoded_frames = max(frames) if frames else 0
        if decoded_frames != container_frames:
            raise ValueError("full decode frame count differs from ffprobe count")
        return MediaProbe(
            codec, fps, duration, container_frames, decoded_frames,
            width, height, True, "",
        )
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError, OSError) as error:
        return MediaProbe("", 0.0, 0.0, 0, 0, 0, 0, False, type(error).__name__)


def _public_inventory(audit: ArchiveAudit | None) -> list[dict[str, Any]]:
    if audit is None:
        return []
    return [
        {
            "member_path_sha256": item.path_sha256,
            "member_type": item.member_type,
            "size": item.size,
            "mtime": item.mtime,
            "header_checksum_valid": item.header_checksum_valid,
        }
        for item in audit.members
    ]


def _public_member_hashes(audit: ArchiveAudit | None) -> list[dict[str, str]]:
    if audit is None:
        return []
    return [
        {
            "member_path_sha256": item.path_sha256,
            "member_content_sha256": item.content_sha256 or "",
        }
        for item in audit.members
        if item.member_type == "regular_file"
    ]


def build_attempt_payloads(
    *,
    protocol_bytes: bytes,
    receipt: Mapping[str, Any],
    archive_audit: ArchiveAudit | None,
    label_seal: Mapping[str, Any] | None,
    binding_rows: Sequence[Mapping[str, Any]],
    probe_rows: Sequence[Mapping[str, Any]],
    provenance: ProvenanceAssessment | None,
    gate_statuses: Mapping[str, GateStatus | str],
    notes: Sequence[str],
) -> dict[str, bytes]:
    """Build the 15 non-index artifacts; unimplemented gates stay explicit."""

    if any("\n" in note or "\r" in note or "EXIT_CODE=" in note for note in notes):
        raise ContractError("log notes may not inject lines or exit markers")
    statuses: dict[str, str] = {}
    for gate in EXPECTED_GATE_IDS[:-1]:
        raw = gate_statuses.get(gate, GateStatus.INCONCLUSIVE)
        status = raw if isinstance(raw, GateStatus) else GateStatus(str(raw).upper())
        statuses[gate] = status.value
    if all(
        statuses[gate] == GateStatus.PASS.value
        for gate in ("G0", "G1", "G2", "G3")
    ):
        raise ContractError(
            "G0-G3 pass cannot be published as formal STOP while G4-G7 are unimplemented"
        )
    statuses["G8"] = "PENDING_EXTERNAL_CLOSURE"
    archive_hashes = {
        "schema_version": "ARSC_ROUND11_DAADX_ARCHIVE_HASHES_V1",
        "status": "PASS" if archive_audit else "FAIL_OR_INCONCLUSIVE",
        "audit": asdict(archive_audit) if archive_audit else None,
    }
    # Raw canonical paths are intentionally excluded from public JSON/CSV.
    if archive_hashes["audit"]:
        archive_hashes["audit"].pop("members", None)
    payloads = {
        "round11_daadx_preflight_protocol.json": protocol_bytes,
        "round11_daadx_download_receipt.json": _json_bytes(dict(receipt)),
        "round11_daadx_archive_hashes.json": _json_bytes(archive_hashes),
        "round11_daadx_tar_inventory.csv": _csv_bytes(
            ["member_path_sha256", "member_type", "size", "mtime", "header_checksum_valid"],
            _public_inventory(archive_audit),
        ),
        "round11_daadx_member_hashes.csv": _csv_bytes(
            ["member_path_sha256", "member_content_sha256"],
            _public_member_hashes(archive_audit),
        ),
        "round11_daadx_label_seal.json": _json_bytes(
            label_seal or {"status": "INCONCLUSIVE", "individual_labels_exposed": False}
        ),
        "round11_daadx_uuid_media_binding.csv": _csv_bytes(
            ["uuid", "official_split", "front_binding_status", "front_member_path_sha256", "front_member_content_sha256"],
            binding_rows,
        ),
        "round11_daadx_media_probe.csv": _csv_bytes(
            ["uuid", "front_member_content_sha256", "codec", "fps", "duration_seconds", "container_frame_count", "decoded_frame_count", "width", "height", "full_decode_pass", "error"],
            probe_rows,
        ),
        "round11_daadx_threshold_qa.json": _json_bytes(
            {"status": "INCONCLUSIVE_NOT_IMPLEMENTED_IN_DRAFT", "real_pairs_inspected": False}
        ),
        "round11_daadx_duplicate_edges.csv": _csv_bytes(
            ["left_public_id", "right_public_id", "edge_type", "status"], []
        ),
        "round11_daadx_cross_dataset_overlap.csv": _csv_bytes(
            ["daadx_public_group_id", "bdd_oia_public_id", "status"], []
        ),
        "round11_daadx_source_groups.csv": _csv_bytes(
            ["public_group_id", "group_size", "provenance_class", "status"], []
        ),
        "round11_daadx_split_audit.csv": _csv_bytes(
            ["public_group_id", "official_split", "frozen_split", "status"], []
        ),
        "round11_daadx_preflight_results.json": _json_bytes(
            {
                "schema_version": "ARSC_ROUND11_DAADX_PREFLIGHT_RESULTS_V1",
                "runner_scope": "G0_G3_DRAFT_ONLY",
                "publication_phase": "FORMAL_STOP_EVIDENCE_WITH_G8_EXTERNAL_CLOSURE",
                "gates": statuses,
                "G3": asdict(provenance) if provenance else None,
                "verdict": "STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY",
                "training_authorized": False,
                "notes": list(notes),
            }
        ),
        "round11_daadx_preflight.log": (
            "ROUND11_DAADX_PREFLIGHT_DRAFT\n"
            + "\n".join(f"NOTE={note}" for note in notes)
            + "\nEXIT_CODE=0\n"
        ).encode("utf-8"),
    }
    if set(payloads) != set(REQUIRED_ARTIFACTS) - {"round11_daadx_artifact_index.json"}:
        raise AssertionError("attempt payload set is not the frozen allowlist")
    return payloads


def _artifact_index_payload(
    payloads: Mapping[str, bytes], logical_aliases: Sequence[tuple[str, str]]
) -> bytes:
    rows = [
        {"path": name, "bytes": len(payloads[name]), "sha256": sha256_bytes(payloads[name])}
        for name in sorted(payloads)
    ]
    return _json_bytes(
        {
            "schema_version": "ARSC_ROUND11_DAADX_ARTIFACT_INDEX_V1",
            "self_hash_excluded_by_definition": True,
            "G8_evidence": (
                "external verifier checks this index, all 16 final files, and the "
                "unique exit marker; results intentionally retain G8=PENDING"
            ),
            "indexed_artifact_count": len(rows),
            "logical_readonly_aliases_not_materialized": [
                {"protocol_path": source, "authoritative_final_path": target}
                for source, target in logical_aliases
            ],
            "artifacts": rows,
        }
    )


def verify_artifact_closure(directory: Path) -> bool:
    """Verify exact 16-file allowlist, 15 indexed hashes, and one exit marker."""

    entries = list(directory.iterdir())
    if any(
        not path.is_file()
        or path.is_symlink()
        or bool(getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400)
        for path in entries
    ):
        return False
    observed = {path.name for path in entries}
    if observed != set(REQUIRED_ARTIFACTS):
        return False
    index = json.loads(
        (directory / "round11_daadx_artifact_index.json").read_text(encoding="utf-8")
    )
    if index.get("self_hash_excluded_by_definition") is not True:
        return False
    rows = index.get("artifacts", [])
    if len(rows) != len(REQUIRED_ARTIFACTS) - 1:
        return False
    expected_names = set(REQUIRED_ARTIFACTS) - {"round11_daadx_artifact_index.json"}
    if {row.get("path") for row in rows} != expected_names:
        return False
    for row in rows:
        path = directory / row["path"]
        if path.stat().st_size != row.get("bytes") or sha256_file(path) != row.get("sha256"):
            return False
    log_lines = (directory / "round11_daadx_preflight.log").read_text(
        encoding="utf-8"
    ).splitlines()
    results = json.loads(
        (directory / "round11_daadx_preflight_results.json").read_text(encoding="utf-8")
    )
    return (
        [line for line in log_lines if line.startswith("EXIT_CODE=")] == ["EXIT_CODE=0"]
        and results.get("gates", {}).get("G8") == "PENDING_EXTERNAL_CLOSURE"
        and results.get("verdict")
        == "STOP_DAADX_AND_SWITCH_TO_CANDIDATE_A_EXPLORATORY"
    )


def publish_attempt_atomically(
    staging: Path,
    final: Path,
    payloads_without_index: Mapping[str, bytes],
    *,
    logical_aliases: Sequence[tuple[str, str]] = (),
) -> None:
    """Exclusively stage, hash-close, verify, and atomically rename one attempt."""

    if staging.parent.resolve() != final.parent.resolve():
        raise ContractError("staging and final must share a parent volume")
    if staging.exists() or final.exists():
        raise FileExistsError("refusing to overwrite staging or final attempt")
    staging.mkdir(parents=True, exist_ok=False)
    for name, payload in payloads_without_index.items():
        if name not in REQUIRED_ARTIFACTS or name == "round11_daadx_artifact_index.json":
            raise ContractError("payload is outside the frozen artifact allowlist")
        _write_exclusive_fsync(staging / name, payload)
    index_payload = _artifact_index_payload(payloads_without_index, logical_aliases)
    _write_exclusive_fsync(
        staging / "round11_daadx_artifact_index.json", index_payload
    )
    _fsync_directory(staging)
    if not verify_artifact_closure(staging):
        raise ContractError("G8 artifact closure verification failed")
    os.replace(staging, final)
    _fsync_directory(final.parent)


def _load_and_validate_receipt(path: Path, protocol: Mapping[str, Any]) -> dict[str, Any]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    official = protocol["official_input"]
    if receipt.get("url") != official.get("url"):
        raise ContractError("download receipt URL differs from protocol")
    if receipt.get("expected_content_length_bytes") != EXPECTED_ARCHIVE_BYTES:
        raise ContractError("download receipt expected bytes differ")
    return receipt


def _tool_from_operational(operational: Mapping[str, Any], name: str) -> Path:
    item = operational["media_tools"][name]
    path = Path(item["path"]).resolve()
    if not path.is_absolute() or not path.is_file() or sha256_file(path) != item["sha256"]:
        raise ContractError(f"{name} path/hash differs from frozen protocol")
    return path


def _check_scratch_selection(
    audit: ArchiveAudit,
    names: Iterable[str],
    scratch: ScratchContract,
) -> None:
    members = _member_map(audit)
    sizes = [members[name].size for name in names]
    if any(size > scratch.maximum_single_file_bytes for size in sizes):
        raise OSError("selected scratch member exceeds frozen single-file cap")
    if sum(sizes) > scratch.maximum_total_written_bytes:
        raise OSError("selected scratch members exceed frozen cumulative cap")
    if shutil.disk_usage(scratch.root).free - sum(sizes) < scratch.minimum_free_bytes:
        raise OSError("scratch free space below frozen reserve")


def _seal_to_dict(seal: Any) -> dict[str, Any]:
    return {
        "schema_version": "ARSC_ROUND11_DAADX_LABEL_SEAL_V1",
        "parser_version": seal.parser_version,
        "source_sha256": dict(seal.source_sha256),
        "unique_uuid_count": seal.unique_uuid_count,
        "uuid_split_rows": [list(row) for row in seal.uuid_split_rows],
        "individual_labels_exposed": False,
    }


def label_seal_worker(spec_path: Path, output_path: Path) -> int:
    """Isolated worker: raw annotation bytes enter; only UUID/split seal exits."""

    if output_path.exists():
        raise FileExistsError("refusing to overwrite label seal worker output")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != "ARSC_ROUND11_LABEL_SEAL_WORKER_SPEC_V1":
        raise ContractError("unexpected label seal worker spec")
    files = spec.get("split_files", {})
    if set(files) != {"train", "val", "test"} or spec.get("uuid_column") != "uuid":
        raise ContractError("label seal worker input allowlist differs")
    sources = {split: Path(files[split]).read_bytes() for split in ("train", "val", "test")}
    seal = parse_uuid_split_seal(
        sources, uuid_column="uuid", expected_splits=("train", "val", "test")
    )
    del sources
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_exclusive_fsync(output_path, _json_bytes(_seal_to_dict(seal)))
    _fsync_directory(output_path.parent)
    return 0


def invoke_label_seal_worker(
    split_files: Mapping[str, Path],
    work_directory: Path,
    *,
    worker_contract: Mapping[str, Any],
    expected_uuid_count: int,
) -> dict[str, Any]:
    """Launch the exact bound runner as a separate label-sealing process."""

    spec_path = work_directory / "seal_worker_spec.json"
    output_path = work_directory / "seal_worker_output.json"
    spec = {
        "schema_version": "ARSC_ROUND11_LABEL_SEAL_WORKER_SPEC_V1",
        "uuid_column": "uuid",
        "split_files": {split: str(path.resolve()) for split, path in split_files.items()},
    }
    _write_exclusive_fsync(spec_path, _json_bytes(spec))
    _fsync_directory(work_directory)
    python_path = Path(str(worker_contract["python_executable"])).resolve()
    if sha256_file(python_path) != worker_contract["python_sha256"]:
        raise ContractError("label worker interpreter hash changed")
    clean_environment = {
        key: os.environ[key]
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
        if key in os.environ
    }
    clean_environment.update(
        {
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    subprocess.run(
        [
            str(python_path),
            *worker_contract["isolation_flags"],
            str(RUNNER_PATH),
            "seal-worker",
            "--spec",
            str(spec_path),
            "--output",
            str(output_path),
        ],
        check=True,
        cwd=str(PROJECT_ROOT),
        env=clean_environment,
        capture_output=True,
        text=True,
        timeout=int(worker_contract["timeout_seconds"]),
    )
    result = json.loads(output_path.read_text(encoding="utf-8"))
    # Canary-safe structural allowlist: no header or arbitrary CSV values.
    if set(result) != {
        "schema_version",
        "parser_version",
        "source_sha256",
        "unique_uuid_count",
        "uuid_split_rows",
        "individual_labels_exposed",
    } or result.get("individual_labels_exposed") is not False:
        raise ContractError("label seal worker returned fields outside the blind allowlist")
    if result.get("schema_version") != "ARSC_ROUND11_DAADX_LABEL_SEAL_V1":
        raise ContractError("label seal worker schema version differs")
    if result.get("parser_version") != "ARSC_DAADX_UUID_SPLIT_SEAL_V1":
        raise ContractError("label seal worker parser version differs")
    expected_hashes = {
        split: sha256_file(split_files[split]) for split in ("train", "val", "test")
    }
    if result.get("source_sha256") != expected_hashes:
        raise ContractError("label seal worker source SHA set differs")
    rows = result.get("uuid_split_rows")
    if (
        result.get("unique_uuid_count") != expected_uuid_count
        or not isinstance(rows, list)
        or len(rows) != expected_uuid_count
        or len({str(row[0]) for row in rows if isinstance(row, list) and len(row) == 2})
        != expected_uuid_count
        or any(
            not isinstance(row, list)
            or len(row) != 2
            or row[1] not in {"train", "val", "test"}
            for row in rows
        )
    ):
        raise ContractError("label seal worker UUID count/schema differs")
    return result


def run_formal(args: argparse.Namespace) -> int:
    """Formal CLI orchestration. Contract validation precedes any archive read."""

    protocol_path = args.protocol.resolve()
    binding_path = args.execution_binding.resolve() if args.execution_binding else None
    view = validate_execution_authority(protocol_path, binding_path)
    protocol = view.protocol
    operational = view.operational_contract
    staging, final = view.staging, view.final
    formal = protocol["formal_output"]
    external_paths = (
        (PROJECT_ROOT / formal["log"]).resolve(),
        (PROJECT_ROOT / formal["artifact_index"]).resolve(),
    )
    if staging.exists() or final.exists() or any(path.exists() for path in external_paths):
        raise FileExistsError("refusing existing formal output or logical-alias sentinel")
    receipt = _load_and_validate_receipt(args.download_receipt.resolve(), protocol)
    ffmpeg = _tool_from_operational(operational, "ffmpeg")
    ffprobe = _tool_from_operational(operational, "ffprobe")
    protocol_bytes = protocol_path.read_bytes()

    audit: ArchiveAudit | None = None
    label_seal_dict: dict[str, Any] | None = None
    binding_rows: list[dict[str, str]] = []
    probe_rows: list[dict[str, Any]] = []
    provenance: ProvenanceAssessment | None = None
    statuses = {gate: GateStatus.INCONCLUSIVE for gate in EXPECTED_GATE_IDS}
    notes = ["G4-G7 are intentionally not implemented in this phase-1 runner"]
    archive_path = args.archive.resolve()
    scratch_work = view.scratch.root / view.scratch.work_directory_name
    if scratch_work.exists():
        raise FileExistsError("refusing existing restricted scratch work directory")

    stage_errors = (
        ArchiveSafetyError,
        ContractError,
        KeyError,
        ValueError,
        UnicodeError,
        csv.Error,
        subprocess.SubprocessError,
        tarfile.TarError,
        EOFError,
        OSError,
    )
    try:
        audit = audit_archive(
            archive_path, EXPECTED_ARCHIVE_BYTES, bounds=view.archive_bounds
        )
    except (ArchiveSafetyError, tarfile.TarError, EOFError, OSError) as error:
        statuses["G0"] = GateStatus.FAIL
        notes.append(f"G0_FAIL={type(error).__name__}")
    else:
        statuses["G0"] = GateStatus.PASS
        layout = operational["archive_layout"]
        uuid_split_rows: tuple[tuple[str, str], ...] | None = None
        try:
            scratch_work.mkdir(parents=False, exist_ok=False)
            _fsync_directory(scratch_work.parent)
        except OSError as error:
            statuses["G1"] = GateStatus.FAIL
            notes.append(f"G1_FAIL={type(error).__name__}:scratch_setup")
        else:
            work = scratch_work
            try:
                annotation_members = tuple(layout["annotation_members"].values())
                _check_scratch_selection(audit, annotation_members, view.scratch)
                annotation_paths = extract_selected_regular_members(
                    archive_path,
                    audit,
                    annotation_members,
                    work / "eligible_annotations",
                )
                split_files = {
                    split: annotation_paths[member]
                    for split, member in layout["annotation_members"].items()
                }
                label_seal_dict = invoke_label_seal_worker(
                    split_files,
                    work,
                    worker_contract=operational["label_worker"],
                    expected_uuid_count=EXPECTED_UUIDS,
                )
                uuid_split_rows = tuple(
                    (str(row[0]), str(row[1]))
                    for row in label_seal_dict["uuid_split_rows"]
                )
                population_count_ok = (
                    label_seal_dict["unique_uuid_count"] == EXPECTED_UUIDS
                )
                binding_ok, binding_rows, internal_bindings = build_front_bindings(
                    uuid_split_rows, audit, layout["front_member_regex"]
                )
                statuses["G1"] = (
                    GateStatus.PASS
                    if population_count_ok and binding_ok
                    else GateStatus.FAIL
                )
            except stage_errors as error:
                # Annotation selection/read and blind label sealing belong to G1,
                # even when the selected member was absent from an otherwise safe tar.
                statuses["G1"] = GateStatus.FAIL
                notes.append(f"G1_FAIL={type(error).__name__}")

            if statuses["G1"] is GateStatus.PASS:
                try:
                    decode_ok, probe_rows = probe_front_members_one_at_a_time(
                        archive_path,
                        audit,
                        internal_bindings,
                        scratch=view.scratch,
                        work_directory=work / "eligible_front",
                        ffprobe_path=ffprobe,
                        ffmpeg_path=ffmpeg,
                    )
                    statuses["G2"] = (
                        GateStatus.PASS if decode_ok else GateStatus.FAIL
                    )
                except stage_errors as error:
                    # Front extraction, rehash, probe, and full decode are G2.
                    statuses["G2"] = GateStatus.FAIL
                    notes.append(f"G2_FAIL={type(error).__name__}")

            if uuid_split_rows is not None:
                try:
                    provenance_payload = read_regular_member_bytes(
                        archive_path, audit, layout["provenance_member"]
                    )
                    provenance_records = parse_provenance_csv(provenance_payload)
                    provenance = assess_source_provenance(
                        (uuid for uuid, _ in uuid_split_rows), provenance_records
                    )
                    del provenance_payload, provenance_records
                    statuses["G3"] = (
                        GateStatus.PASS if provenance.passed else GateStatus.FAIL
                    )
                    if not provenance.passed:
                        notes.append(
                            "G3 failed; G4-G7 remain INCONCLUSIVE by frozen rule"
                        )
                except stage_errors as error:
                    # Missing/read/parse/schema errors in the nonlabel provenance
                    # member are G3 failures and can never rewrite the G0 audit.
                    statuses["G3"] = GateStatus.FAIL
                    notes.append(f"G3_FAIL={type(error).__name__}")

            try:
                shutil.rmtree(scratch_work)
                _fsync_directory(scratch_work.parent)
            except OSError as error:
                # Scratch closure is assigned to the active physical stage.
                if statuses["G1"] is not GateStatus.PASS:
                    statuses["G1"] = GateStatus.FAIL
                else:
                    statuses["G2"] = GateStatus.FAIL
                notes.append(f"SCRATCH_CLOSURE_FAIL={type(error).__name__}")

    if all(statuses[gate] is GateStatus.PASS for gate in ("G0", "G1", "G2", "G3")):
        print(
            json.dumps(
                {
                    "phase": "PREFLIGHT_PHASE1_DIAGNOSTIC_ONLY",
                    "formal_attempt_published": False,
                    "reason": "G0-G3 passed; G4-G7 implementation and independent GO are required",
                    "training_authorized": False,
                },
                indent=2,
            )
        )
        return 3

    payloads = build_attempt_payloads(
        protocol_bytes=protocol_bytes,
        receipt=receipt,
        archive_audit=audit,
        label_seal=label_seal_dict,
        binding_rows=binding_rows,
        probe_rows=probe_rows,
        provenance=provenance,
        gate_statuses=statuses,
        notes=notes,
    )
    publish_attempt_atomically(
        staging, final, payloads, logical_aliases=view.logical_aliases
    )
    if not verify_artifact_closure(final):
        raise ContractError("post-publish external G8 verification failed")
    print("G8_EXTERNAL_CLOSURE=PASS")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    formal = subparsers.add_parser("run")
    formal.add_argument("--protocol", type=Path, required=True)
    formal.add_argument("--execution-binding", type=Path)
    formal.add_argument("--download-receipt", type=Path, required=True)
    formal.add_argument("--archive", type=Path, required=True)
    worker = subparsers.add_parser("seal-worker", help=argparse.SUPPRESS)
    worker.add_argument("--spec", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "seal-worker":
        return label_seal_worker(args.spec.resolve(), args.output.resolve())
    return run_formal(args)


if __name__ == "__main__":
    raise SystemExit(main())
