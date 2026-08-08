"""Fail-closed launcher for the one authorized Round 11 layout attempt.

Static validation deliberately does not touch the three declared real inputs.
Only :func:`run_formal_layout_attempt`, after its durable claim, may do so.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.machinery
import json
import os
import platform
import re
import stat
import subprocess
import sys
import types
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BINDING_PATH = ROOT / "outputs/validity/round11_daadx_layout_inventory_execution_binding.json"
REVIEW_PATH = ROOT / "outputs/validity/round11_daadx_layout_inventory_execution_reviewer_decision.json"
REVIEW_MEMO_PATH = ROOT / "outputs/research_review_memo_round11_layout_execution_go_run.md"
BINDING_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_EXECUTION_BINDING_V1"
BINDING_DECISION = "NOT_RUN_BINDING_FROZEN_AWAIT_INDEPENDENT_GO_RUN"
REVIEW_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_EXECUTION_REVIEWER_DECISION_V1"
REVIEW_DECISION = "GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE"
SHA = re.compile(r"[0-9A-F]{64}")
H0 = "c34bcb118d9f89dc25160f39ca916fe061b6754c"
CLAIM_BOUNDARY = "GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE"
ATTEMPT = "layout_inventory_attempt01"
PHASE = "ARCHIVE_LAYOUT_INVENTORY_ONLY"
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
REQUIRED_BOUND_PATHS = (
    "outputs/validity/round11_daadx_layout_inventory_protocol.json",
    "src/arsc_eval/__init__.py",
    "src/arsc_eval/round11_layout_inventory.py",
    "src/arsc_eval/round11_layout_watchdog.py",
    "src/arsc_eval/round11_layout_control.py",
    "src/arsc_eval/round11_layout_worker.py",
    "src/arsc_eval/round11_layout_runner.py",
    "src/arsc_eval/round11_layout_formal_runner.py",
    "scripts/create_round11_layout_execution_binding.py",
    "scripts/run_round11_layout_inventory.py",
    "tests/test_round11_layout_inventory.py",
    "tests/test_round11_layout_watchdog.py",
    "tests/test_round11_layout_control.py",
    "tests/test_round11_layout_worker.py",
    "tests/test_round11_layout_runner.py",
    "tests/test_round11_layout_formal_runner.py",
    "tests/test_create_round11_layout_execution_binding.py",
    "tests/test_run_round11_layout_inventory.py",
    "outputs/validity/round11_layout_inventory_protocol_reviewer_decision.json",
    "outputs/validity/round11_layout_inventory_implementation_reviewer_decision.json",
    "outputs/validity/round11_layout_control_implementation_reviewer_decision.json",
    "outputs/validity/round11_layout_runner_implementation_reviewer_decision.json",
    "outputs/validity/round11_layout_formal_runner_implementation_reviewer_decision.json",
    "outputs/validity/round11_transport_receipt_postgeneration_reviewer_decision.json",
)
LAUNCH_OPTION_ORDER = (
    "--expected-launch-head",
    "--expected-reviewer-sha256",
    "--git-executable",
    "--execute",
)
LAUNCH_INTERPRETER_FLAGS = ("-I", "-S", "-B")
# Dependency order for the deterministic source-only loader.  ``runner``
# requires ``inventory`` and ``worker``; ``formal_runner`` requires ``control``,
# ``inventory``, and ``runner``.  ``inventory``, ``worker`` and ``control``
# import standard library only.
ARSC_EVAL_DEP_ORDER = (
    ("arsc_eval", "src/arsc_eval/__init__.py", ""),
    ("arsc_eval.round11_layout_inventory", "src/arsc_eval/round11_layout_inventory.py", "arsc_eval"),
    ("arsc_eval.round11_layout_worker", "src/arsc_eval/round11_layout_worker.py", "arsc_eval"),
    ("arsc_eval.round11_layout_control", "src/arsc_eval/round11_layout_control.py", "arsc_eval"),
    ("arsc_eval.round11_layout_runner", "src/arsc_eval/round11_layout_runner.py", "arsc_eval"),
    ("arsc_eval.round11_layout_formal_runner", "src/arsc_eval/round11_layout_formal_runner.py", "arsc_eval"),
)
REQUIRED_ARSC_EVAL_SOURCES = tuple(rel for _name, rel, _package in ARSC_EVAL_DEP_ORDER)


class StaticGateError(RuntimeError):
    """The attempt is unauthorized; no claim or input access occurred."""


@dataclass(frozen=True)
class StaticAuthority:
    binding_bytes: bytes
    reviewer_bytes: bytes
    inputs: Any
    leases: tuple[Any, ...]

    def close(self) -> None:
        for lease in reversed(self.leases):
            lease.close()


class _FileTime(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _HandleInfo(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_uint32),
        ("creation_time", _FileTime),
        ("last_access_time", _FileTime),
        ("last_write_time", _FileTime),
        ("volume_serial", ctypes.c_uint32),
        ("size_high", ctypes.c_uint32),
        ("size_low", ctypes.c_uint32),
        ("links", ctypes.c_uint32),
        ("file_index_high", ctypes.c_uint32),
        ("file_index_low", ctypes.c_uint32),
    ]


class _AttributeTagInfo(ctypes.Structure):
    _fields_ = [("attributes", ctypes.c_uint32), ("reparse_tag", ctypes.c_uint32)]


class WindowsReadLease:
    """Read and retain one non-reparse Windows file identity for its lifetime."""

    INVALID_HANDLE = ctypes.c_void_p(-1).value
    GENERIC_READ = 0x80000000
    FILE_READ_ATTRIBUTES = 0x00000080
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_ATTRIBUTE_TAG_INFO_CLASS = 9

    def __init__(self, path: Path) -> None:
        require(os.name == "nt", "formal lease requires Windows")
        require(path.is_absolute(), "static authority path must be absolute")
        absolute = path.absolute()
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create = self._kernel32.CreateFileW
        self._create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        self._create.restype = ctypes.c_void_p
        self._close = self._kernel32.CloseHandle
        self._close.argtypes = [ctypes.c_void_p]
        self._close.restype = ctypes.c_int
        self._information = self._kernel32.GetFileInformationByHandle
        self._information.argtypes = [ctypes.c_void_p, ctypes.POINTER(_HandleInfo)]
        self._information.restype = ctypes.c_int
        self._tag_information = self._kernel32.GetFileInformationByHandleEx
        self._tag_information.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self._tag_information.restype = ctypes.c_int
        self._read_file = self._kernel32.ReadFile
        self._read_file.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        self._read_file.restype = ctypes.c_int
        self._ancestor_handles: list[int] = []
        self._handle: int | None = None
        try:
            self._hold_nonreparse_ancestors(absolute.parent)
            self._handle = self._open(absolute, self.GENERIC_READ, self.FILE_SHARE_READ)
            before = self._snapshot(self._handle)
            require(not before["is_directory"], "static authority is not regular")
            self._initial_identity = before["identity"]
        except BaseException:
            self.close()
            raise

    def _open(self, path: Path, access: int, share: int) -> int:
        handle = self._create(
            str(path), access, share, None, self.OPEN_EXISTING,
            self.FILE_FLAG_BACKUP_SEMANTICS | self.FILE_FLAG_OPEN_REPARSE_POINT, None,
        )
        if handle == self.INVALID_HANDLE:
            raise StaticGateError("static authority lease unavailable")
        return int(handle)

    def _snapshot(self, handle: int) -> dict[str, Any]:
        info = _HandleInfo()
        tag = _AttributeTagInfo()
        if not self._information(handle, ctypes.byref(info)):
            raise StaticGateError("static authority identity unavailable")
        if not self._tag_information(handle, self.FILE_ATTRIBUTE_TAG_INFO_CLASS, ctypes.byref(tag), ctypes.sizeof(tag)):
            raise StaticGateError("static authority attributes unavailable")
        require(not (tag.attributes & self.FILE_ATTRIBUTE_REPARSE_POINT), "static authority reparse point rejected")
        return {
            "identity": (info.volume_serial, info.file_index_high, info.file_index_low),
            "size": (info.size_high << 32) | info.size_low,
            "links": info.links,
            "is_directory": bool(info.attributes & self.FILE_ATTRIBUTE_DIRECTORY),
        }

    def _hold_nonreparse_ancestors(self, parent: Path) -> None:
        chain: list[Path] = []
        current = parent
        while True:
            chain.append(current)
            if current.parent == current:
                break
            current = current.parent
        for directory in reversed(chain):
            handle = self._open(directory, self.FILE_READ_ATTRIBUTES, self.FILE_SHARE_READ | self.FILE_SHARE_WRITE)
            try:
                snapshot = self._snapshot(handle)
                require(snapshot["is_directory"], "static authority ancestor is not directory")
            except BaseException:
                self._close(handle)
                raise
            self._ancestor_handles.append(handle)

    def read(self, *, max_bytes: int = 32 * 1024 * 1024, required_links: int = 1) -> bytes:
        require(self._handle is not None, "static authority lease is closed")
        before = self._snapshot(self._handle)
        require(before["identity"] == self._initial_identity, "static authority identity differs")
        require(before["links"] == required_links, "static authority link policy differs")
        require(0 <= before["size"] <= max_bytes, "static authority size exceeds cap")
        chunks: list[bytes] = []
        count = 0
        while True:
            capacity = min(1_048_576, max_bytes + 1 - count)
            buffer = ctypes.create_string_buffer(capacity)
            received = ctypes.c_uint32()
            if not self._read_file(self._handle, buffer, capacity, ctypes.byref(received), None):
                raise StaticGateError("static authority read failed")
            if received.value == 0:
                break
            chunks.append(buffer.raw[: received.value])
            count += received.value
            require(count <= max_bytes, "static authority size exceeds cap")
        after = self._snapshot(self._handle)
        require(after["identity"] == before["identity"] and after["links"] == before["links"], "static authority changed")
        require(after["size"] == before["size"] == count, "static authority length changed")
        return b"".join(chunks)

    def close(self) -> None:
        failures: list[str] = []
        if self._handle is not None:
            if not self._close(self._handle):
                failures.append("leaf")
            self._handle = None
        while self._ancestor_handles:
            handle = self._ancestor_handles.pop()
            if not self._close(handle):
                failures.append(f"ancestor:{handle}")
        if failures:
            raise StaticGateError(f"static authority close failed: {', '.join(failures)}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StaticGateError(message)


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StaticGateError("duplicate JSON key")
        result[key] = value
    return result


def strict_document(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StaticGateError(f"invalid {label}") from error
    require(type(value) is dict and canonical(value) == data, f"noncanonical {label}")
    return value


def exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == keys, f"{label} fields differ")
    return value  # type: ignore[return-value]


def stable_read(path: Path, *, max_bytes: int = 32 * 1024 * 1024, required_links: int = 1) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise StaticGateError("static authority unavailable") from error
    try:
        before = os.fstat(descriptor)
        current = os.lstat(path)
        identity = lambda item: (item.st_dev, item.st_ino, item.st_nlink)
        require(stat.S_ISREG(before.st_mode), "static authority is not regular")
        require(before.st_nlink == required_links and not stat.S_ISLNK(current.st_mode), "static authority link policy differs")
        require(identity(before) == identity(current), "static authority identity differs")
        require(0 <= before.st_size <= max_bytes, "static authority size exceeds cap")
        chunks: list[bytes] = []
        count = 0
        while True:
            block = os.read(descriptor, min(1_048_576, max_bytes + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            require(count <= max_bytes, "static authority size exceeds cap")
        after = os.fstat(descriptor)
        current_after = os.lstat(path)
        require(identity(before) == identity(after) == identity(current_after), "static authority changed")
        require(after.st_size == count, "static authority length changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def lease_and_read(
    path: Path,
    leases: list[WindowsReadLease],
    *,
    max_bytes: int = 32 * 1024 * 1024,
    required_links: int = 1,
) -> bytes:
    lease = WindowsReadLease(path)
    leases.append(lease)
    return lease.read(max_bytes=max_bytes, required_links=required_links)


def repo_path(text: str) -> Path:
    require(type(text) is str, "repository path type differs")
    pure = PurePosixPath(text)
    require(not pure.is_absolute() and ".." not in pure.parts and str(pure) == text, "repository path differs")
    return ROOT.joinpath(*pure.parts)


def declared_input_path(text: object) -> Path:
    require(type(text) is str, "input path declaration type differs")
    pure = PurePosixPath(text)
    require(not pure.is_absolute() and ".." not in pure.parts and str(pure) == text, "input path declaration differs")
    # Lexical join only: never resolve/stat/exists an input here.
    return ROOT.joinpath(*pure.parts)


def git_call(git: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(git), *args], cwd=ROOT, check=check, capture_output=True, text=True,
        encoding="utf-8", errors="strict", env={"SYSTEMROOT": os.environ["SYSTEMROOT"]},
    )


def _require_boolean_fields(value: dict[str, Any], expected: dict[str, bool], label: str) -> None:
    """Enforce an exact bool truth value (``is True``/``is False``) for every field."""
    for key, wanted in expected.items():
        require(type(value.get(key)) is bool, f"{label}.{key} type differs")
        require(value[key] is wanted, f"{label}.{key} value differs")


def _require_real_git(git: Path) -> None:
    """Reject wrapper/stub toolchain paths; only the authoritative real git binary is allowed."""
    absolute = git.absolute()
    require(absolute.name == "git.exe", "git tool name differs")
    require(absolute.parent.name == "bin" and absolute.parent.parent.name == "mingw64", "git wrapper/stub toolchain path rejected")


def minimal_environment_contract() -> dict[str, str]:
    """Return the exact four-variable Windows minimal environment (SYSTEMROOT key)."""
    require(os.name == "nt", "minimal environment contract is Windows-only")
    system_root = os.environ.get("SYSTEMROOT")
    require(bool(system_root and system_root.strip()), "SYSTEMROOT is unavailable")
    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "SYSTEMROOT": str(system_root),
    }


def validate_launcher_environment(environment: object) -> dict[str, str]:
    """Require the exact four-variable environment observed by Windows CPython."""
    require(type(environment) is dict, "launcher environment type differs")
    expected_keys = {"PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING", "PYTHONUTF8", "SYSTEMROOT"}
    require(set(environment) == expected_keys, "launcher environment fields differ")
    require(environment["PYTHONDONTWRITEBYTECODE"] == "1", "launcher bytecode environment differs")
    require(environment["PYTHONIOENCODING"] == "utf-8", "launcher encoding environment differs")
    require(environment["PYTHONUTF8"] == "1", "launcher UTF-8 environment differs")
    system_root = environment["SYSTEMROOT"]
    require(type(system_root) is str and bool(system_root.strip()), "launcher SYSTEMROOT differs")
    return dict(environment)


TEST_EVIDENCE_ENTRY_KEYS = {"argv", "exit_code", "passed", "stdout_sha256"}


def validate_test_evidence(value: object) -> None:
    """Enforce the exact, nested test evidence schema for future independent review."""
    require(type(value) is dict, "review evidence type differs")
    require(set(value) == {"evidence"}, "review evidence fields differ")
    require(type(value["evidence"]) is list and value["evidence"], "review evidence list differs")
    for entry in value["evidence"]:
        require(type(entry) is dict and set(entry) == TEST_EVIDENCE_ENTRY_KEYS, "review evidence entry fields differ")
        require(type(entry["argv"]) is list and entry["argv"] and all(type(word) is str and word for word in entry["argv"]), "review evidence argv differs")
        require(type(entry["exit_code"]) is int and entry["exit_code"] == 0, "review evidence exit code differs")
        require(type(entry["passed"]) is bool and entry["passed"] is True, "review evidence passed type differs")
        require(type(entry["stdout_sha256"]) is str and SHA.fullmatch(entry["stdout_sha256"]) is not None, "review evidence digest differs")


def _record_matches(record: object, data: bytes, label: str) -> dict[str, Any]:
    item = exact_keys(record, {"path", "bytes", "sha256", "git_blob", "git_mode"}, label)
    require(type(item["bytes"]) is int and item["bytes"] == len(data), f"{label} bytes differ")
    require(type(item["sha256"]) is str and item["sha256"] == sha256(data), f"{label} sha differs")
    require(type(item["git_blob"]) is str and item["git_blob"] == git_blob(data), f"{label} blob differs")
    require(item["git_mode"] == "100644", f"{label} mode differs")
    return item


def require_head_entry(git: Path, revision: str, rel: str, data: bytes) -> None:
    listing = git_call(git, "ls-tree", revision, "--", rel).stdout.strip()
    require(bool(listing), "HEAD tree entry absent")
    try:
        prefix, listed_path = listing.split("\t", 1)
        mode, kind, blob = prefix.split(" ")
    except ValueError as error:
        raise StaticGateError("HEAD tree entry malformed") from error
    require((listed_path, mode, kind, blob) == (rel, "100644", "blob", git_blob(data)), "HEAD tree entry differs")


def _validate_binding_shape(binding: dict[str, Any]) -> None:
    exact_keys(binding, {"schema_version", "decision", "source_reviewed_head_h0", "artifacts", "reviewer_authority", "toolchain", "worker_process", "launcher_process", "formal_run", "authorities", "artifact_contract", "resource_bounds", "capabilities", "external_anchor_required", "this_is_go_run"}, "binding")
    require(binding["schema_version"] == BINDING_SCHEMA and binding["decision"] == BINDING_DECISION, "binding authority differs")
    require(type(binding["this_is_go_run"]) is bool and binding["this_is_go_run"] is False, "binding self-authorized execution")
    review = exact_keys(binding["reviewer_authority"], {"path", "schema_version", "required_decision", "digest_source"}, "reviewer authority")
    require(review == {"path": REVIEW_PATH.relative_to(ROOT).as_posix(), "schema_version": REVIEW_SCHEMA, "required_decision": REVIEW_DECISION, "digest_source": "OUT_OF_BAND_REVIEW_PIN"}, "reviewer authority differs")
    external_anchor = exact_keys(binding["external_anchor_required"], {"expected_launch_head", "expected_reviewer_sha256"}, "external anchor policy")
    _require_boolean_fields(external_anchor, {"expected_launch_head": True, "expected_reviewer_sha256": True}, "external anchor policy")
    caps = exact_keys(binding["capabilities"], {"structure_inventory", "raw_header_path_type_size", "opaque_regular_payload_drain", "label_values", "provenance_rows", "video_frames", "regular_payload_semantics", "phase1", "g0_g8", "training", "inference"}, "capabilities")
    _require_boolean_fields(caps, {"structure_inventory": True, "raw_header_path_type_size": True, "opaque_regular_payload_drain": True, "label_values": False, "provenance_rows": False, "video_frames": False, "regular_payload_semantics": False, "phase1": False, "g0_g8": False, "training": False, "inference": False}, "capabilities")
    process = exact_keys(binding["worker_process"], {"argv_template", "environment", "windows_job"}, "worker process")
    expected_worker = str(ROOT / "src/arsc_eval/round11_layout_worker.py")
    require(process["argv_template"] == [str(Path(sys.executable).absolute()), "-I", "-S", "-B", expected_worker, "--control-handle", "<POSITIVE_INTEGER_INHERITED_HANDLE>", "--expected-bytes", "18585647156", "--expected-sha256", "98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965"], "worker argv differs")
    require(process["environment"] == minimal_environment_contract(), "worker environment differs")
    job = exact_keys(process["windows_job"], {"create_suspended", "extended_startupinfo_present", "create_no_window", "handle_list_only", "active_process_limit", "kill_on_job_close"}, "Windows Job policy")
    _require_boolean_fields(job, {"create_suspended": True, "extended_startupinfo_present": True, "create_no_window": True, "handle_list_only": True, "kill_on_job_close": True}, "Windows Job policy")
    require(type(job["active_process_limit"]) is int and job["active_process_limit"] == 1, "active process limit type differs")
    launcher = exact_keys(binding["launcher_process"], {"argv_template", "environment", "argparse_allow_abbrev", "duplicate_or_reordered_options_allowed"}, "launcher process")
    git_path = binding["toolchain"]["git"]["path"]
    require(launcher["argv_template"] == [str(Path(sys.executable).absolute()), *LAUNCH_INTERPRETER_FLAGS, str(ROOT / "scripts/run_round11_layout_inventory.py"), "--expected-launch-head", "<EXTERNAL_40_HEX_LOWER>", "--expected-reviewer-sha256", "<EXTERNAL_64_HEX_UPPER>", "--git-executable", git_path, "--execute"], "launcher argv differs")
    require(launcher["environment"] == process["environment"], "launcher environment differs")
    _require_boolean_fields(launcher, {"argparse_allow_abbrev": False, "duplicate_or_reordered_options_allowed": False}, "launcher process")


def _validate_reviewer(review: dict[str, Any], binding_data: bytes, binding_document: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    exact_keys(review, {"schema_version", "decision", "reviewer_role", "binding_head_h1", "binding", "review_memo", "run_configuration", "input_declarations", "capabilities", "one_shot", "claim_boundary", "self_authentication", "external_anchor_required", "test_evidence"}, "reviewer decision")
    require(review["schema_version"] == REVIEW_SCHEMA and review["decision"] == REVIEW_DECISION, "GO_RUN authority differs")
    _require_boolean_fields(review, {"self_authentication": False, "external_anchor_required": True}, "reviewer trust policy")
    binding = exact_keys(review["binding"], {"path", "bytes", "sha256", "schema_version"}, "review binding")
    require(binding == {"path": BINDING_PATH.relative_to(ROOT).as_posix(), "bytes": len(binding_data), "sha256": sha256(binding_data), "schema_version": BINDING_SCHEMA}, "review binding differs")
    one_shot = exact_keys(review["one_shot"], {"attempt", "retry", "delete", "recover"}, "one-shot authority")
    _require_boolean_fields(one_shot, {"retry": False, "delete": False, "recover": False}, "one-shot authority")
    require(one_shot["attempt"] == "layout_inventory_attempt01", "one-shot attempt differs")
    review_caps = exact_keys(review["capabilities"], set(binding_document["capabilities"]), "review capabilities")
    _require_boolean_fields(review_caps, binding_document["capabilities"], "review capabilities")
    expected_configuration = {key: binding_document[key] for key in ("source_reviewed_head_h0", "toolchain", "launcher_process", "worker_process", "formal_run", "artifact_contract", "resource_bounds")}
    require(canonical(review["run_configuration"]) == canonical(expected_configuration), "review run configuration differs")
    require(canonical(review["input_declarations"]) == canonical(binding_document["authorities"]), "review input declarations differ")
    require(type(review["reviewer_role"]) is str and review["reviewer_role"] == "independent_result_blind_layout_execution_reviewer", "reviewer role differs")
    require(type(review["claim_boundary"]) is str and review["claim_boundary"] == CLAIM_BOUNDARY, "review claim boundary differs")
    validate_test_evidence(review["test_evidence"])
    require(type(review["binding_head_h1"]) is str and re.fullmatch(r"[0-9a-f]{40}", review["binding_head_h1"]), "H1 differs")
    memo = exact_keys(review["review_memo"], {"path", "bytes", "sha256"}, "review memo")
    require(memo["path"] == REVIEW_MEMO_PATH.relative_to(ROOT).as_posix(), "review memo path differs")
    return review["binding_head_h1"], memo


def validate_static_authority(*, expected_launch_head: str, expected_reviewer_sha256: str, git_executable: Path) -> StaticAuthority:
    require(re.fullmatch(r"[0-9a-f]{40}", expected_launch_head) is not None, "external HEAD pin differs")
    require(SHA.fullmatch(expected_reviewer_sha256) is not None, "external reviewer pin differs")
    _require_real_git(git_executable)
    leases: list[WindowsReadLease] = []

    def leased(path: Path, **kwargs: Any) -> bytes:
        return lease_and_read(path, leases, **kwargs)

    try:
        binding_data = leased(BINDING_PATH)
        binding = strict_document(binding_data, "binding")
        _validate_binding_shape(binding)
        reviewer_data = leased(REVIEW_PATH)
        require(sha256(reviewer_data) == expected_reviewer_sha256, "external reviewer pin mismatch")
        reviewer = strict_document(reviewer_data, "reviewer decision")
        h1, memo_record = _validate_reviewer(reviewer, binding_data, binding)

        toolchain = exact_keys(binding["toolchain"], {"python", "git", "platform"}, "toolchain")
        git_record = exact_keys(toolchain["git"], {"path", "bytes", "sha256", "link_count"}, "git tool")
        require(str(git_executable.absolute()) == git_record["path"], "git path differs")
        require(type(git_record["link_count"]) is int and git_record["link_count"] > 0, "git link count differs")
        git_data = leased(git_executable, max_bytes=256 * 1024 * 1024, required_links=git_record["link_count"])
        require(len(git_data) == git_record["bytes"] and sha256(git_data) == git_record["sha256"], "git executable differs")

        head = git_call(git_executable, "rev-parse", "HEAD").stdout.strip()
        require(head == expected_launch_head, "launch HEAD differs")
        require(git_call(git_executable, "rev-list", "--parents", "-n", "1", head).stdout.split() == [head, h1], "review commit topology differs")
        changed = {line for line in git_call(git_executable, "diff", "--name-only", h1, head).stdout.splitlines() if line}
        require(changed == {REVIEW_PATH.relative_to(ROOT).as_posix(), REVIEW_MEMO_PATH.relative_to(ROOT).as_posix()}, "H1-H2 review allowlist differs")
        require(binding["source_reviewed_head_h0"] == H0, "H0 differs")
        require(git_call(git_executable, "rev-list", "--parents", "-n", "1", h1).stdout.split() == [h1, H0], "binding commit topology differs")
        h1_changed = {line for line in git_call(git_executable, "diff", "--name-only", H0, h1).stdout.splitlines() if line}
        require(h1_changed == {"src/arsc_eval/round11_layout_worker.py", "src/arsc_eval/round11_layout_runner.py", "tests/test_round11_layout_runner.py", "scripts/create_round11_layout_execution_binding.py", "scripts/run_round11_layout_inventory.py", "tests/test_create_round11_layout_execution_binding.py", "tests/test_run_round11_layout_inventory.py", BINDING_PATH.relative_to(ROOT).as_posix()}, "H0-H1 binding allowlist differs")

        memo_data = leased(REVIEW_MEMO_PATH)
        require(type(memo_record["bytes"]) is int and len(memo_data) == memo_record["bytes"] and sha256(memo_data) == memo_record["sha256"], "review memo differs")
        for path, data in ((BINDING_PATH, binding_data), (REVIEW_PATH, reviewer_data), (REVIEW_MEMO_PATH, memo_data)):
            require_head_entry(git_executable, head, path.relative_to(ROOT).as_posix(), data)

        records = binding["artifacts"]
        require(type(records) is list and records, "artifact binding differs")
        seen: set[str] = set()
        artifact_data: dict[str, bytes] = {}
        for index, raw in enumerate(records):
            require(type(raw) is dict and type(raw.get("path")) is str and raw["path"] not in seen, "artifact path duplicate")
            seen.add(raw["path"])
            data = leased(repo_path(raw["path"]))
            item = _record_matches(raw, data, f"artifact {index}")
            require_head_entry(git_executable, head, item["path"], data)
            artifact_data[item["path"]] = data
        require(tuple(item["path"] for item in records) == REQUIRED_BOUND_PATHS, "required artifact list differs")

        python_record = exact_keys(toolchain["python"], {"path", "bytes", "sha256", "link_count", "version", "implementation"}, "python tool")
        require(str(Path(sys.executable).absolute()) == python_record["path"], "python path differs")
        require(type(python_record["link_count"]) is int and python_record["link_count"] > 0, "python link count differs")
        python_data = leased(Path(sys.executable), max_bytes=256 * 1024 * 1024, required_links=python_record["link_count"])
        require(len(python_data) == python_record["bytes"] and sha256(python_data) == python_record["sha256"], "python executable differs")
        require(sys.version == python_record["version"] and platform.python_implementation() == python_record["implementation"], "python runtime differs")
        require(toolchain["platform"] == {"os_name": os.name, "sys_platform": sys.platform, "machine": platform.machine(), "platform": platform.platform()}, "platform differs")

        run = exact_keys(binding["formal_run"], {"attempt", "phase", "timeout_seconds", "closure_reserve_seconds", "require_formal_windows", "claim_path", "staging_path", "final_path", "cwd_policy", "automatic_retry_delete_recovery"}, "formal run")
        require(run["attempt"] == ATTEMPT and run["phase"] == PHASE, "formal identity differs")
        require(type(run["timeout_seconds"]) is int and run["timeout_seconds"] == 21600, "timeout differs")
        require(type(run["closure_reserve_seconds"]) is int and run["closure_reserve_seconds"] == 1800, "closure reserve differs")
        _require_boolean_fields(run, {"require_formal_windows": True, "automatic_retry_delete_recovery": False}, "formal policy")
        require(run["cwd_policy"] == "EXCLUSIVE_STAGING_CREATED_AFTER_DURABLE_CLAIM", "cwd policy differs")
        claim, staging, final_path = (Path(run[key]) for key in ("claim_path", "staging_path", "final_path"))
        require(all(path.is_absolute() and path.parent == ROOT / "outputs/validity" for path in (claim, staging, final_path)), "output path differs")
        require((claim.name, staging.name, final_path.name) == (".round11_daadx_layout_inventory_attempt01.claim", "round11_daadx_layout_inventory_attempt01.staging", "round11_daadx_layout_inventory_attempt01"), "output topology differs")
        for path in (claim, staging, final_path):
            try:
                os.lstat(path)
            except FileNotFoundError:
                continue
            raise StaticGateError("attempt control path already exists")

        authorities = exact_keys(binding["authorities"], {"protocol", "receipt", "manifest", "archive", "preclaim_real_input_access"}, "authorities")
        protocol_bytes = artifact_data[REQUIRED_BOUND_PATHS[0]]
        protocol = authorities["protocol"]
        require(protocol == {"path": REQUIRED_BOUND_PATHS[0], "bytes": len(protocol_bytes), "sha256": sha256(protocol_bytes)}, "protocol authority differs")
        receipt, manifest, archive = authorities["receipt"], authorities["manifest"], authorities["archive"]
        require(authorities["preclaim_real_input_access"] is False, "input access policy differs")
        require(receipt == {"path": "outputs/validity/round11_daadx_transport_receipt.json", "schema_version": "ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_V1", "bytes": 1629, "sha256": "D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F"}, "receipt declaration differs")
        require(manifest == {"path": "data/external/daadx_official/daadx_assembled_ranges_manifest.json", "schema_version": "ARSC_ASSEMBLED_RANGES_MANIFEST_V1", "bytes": 15792, "sha256": "FDBCC19DD726F8CA5C93A8189C47A5ACBEA5E6D1EC131679B4302E7493A835DC"}, "manifest declaration differs")
        require(archive == {"path": "data/external/daadx_official/daadx.assembled.tar.gz", "bytes": 18585647156, "sha256": "98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965"}, "archive declaration differs")

        protocol_document = strict_document(protocol_bytes, "layout protocol")
        require(binding["resource_bounds"] == protocol_document["resource_bounds"], "resource bounds differ")
        contract = exact_keys(binding["artifact_contract"], {"exact_names", "exact_caps", "artifact_statuses", "observed_scopes", "complete_closure", "stop_closure", "runtime_derived_output_hashes"}, "artifact contract")
        require(contract["exact_names"] == list(ARTIFACTS) == protocol_document["artifact_contract"]["exact_files"], "artifact names differ")

        # Only after all executable bytes have been hash/tree verified and
        # lifetime-leased may repository modules execute.  They are built here
        # from the verified bytes with no normal import machinery.
        sys.dont_write_bytecode = True
        module_bytes = {rel: artifact_data[rel] for rel in REQUIRED_ARSC_EVAL_SOURCES}
        expected_source_sha = {rec["path"]: rec["sha256"] for rec in records if rec["path"] in REQUIRED_ARSC_EVAL_SOURCES}
        control, formal = load_arsc_eval_source_only(
            module_bytes=module_bytes,
            expected_sha256=expected_source_sha,
        )

        validate_verified_import_paths()
        require({key: value for key, value in binding["resource_bounds"].items() if key != "compressed_archive_bytes_exact"} == vars(formal.DEFAULT_LIMITS), "implementation resource bounds differ")
        require(contract["exact_caps"] == control.ARTIFACT_CAPS, "artifact caps differ")
        require(contract["artifact_statuses"] == sorted(control.ARTIFACT_STATUS) and contract["observed_scopes"] == sorted(control.OBSERVED_SCOPES), "artifact status contract differs")
        require(contract["complete_closure"] == control.COMPLETE_CLOSURE and contract["stop_closure"] == control.STOP_CLOSURE and contract["runtime_derived_output_hashes"] is True, "closure contract differs")

        trusted = {control.ARTIFACTS[0]: protocol_bytes, control.ARTIFACTS[1]: binding_data, control.ARTIFACTS[2]: reviewer_data}
        expectations = control.ClosureExpectations(
            authorities=tuple(control.AuthorityExpectation(name, len(data), sha256(data), True) for name, data in trusted.items()) + (
                control.AuthorityExpectation(control.ARTIFACTS[3], receipt["bytes"], receipt["sha256"], False),
                control.AuthorityExpectation(control.ARTIFACTS[4], manifest["bytes"], manifest["sha256"], False),
            ),
            archive=control.ArchiveExpectation(archive["bytes"], archive["sha256"]),
        )
        inputs = formal.FormalRunInputs(
            claim_path=claim, staging_path=staging, final_path=final_path,
            receipt_path=declared_input_path(receipt["path"]), manifest_path=declared_input_path(manifest["path"]), archive_path=declared_input_path(archive["path"]),
            trusted_payloads=trusted, expectations=expectations,
            receipt_schema=receipt["schema_version"], manifest_schema=manifest["schema_version"],
            python_executable=Path(python_record["path"]), worker_path=repo_path("src/arsc_eval/round11_layout_worker.py"),
            timeout_seconds=21600, closure_reserve_seconds=1800, require_formal_windows=True,
        )
        formal._validate_preclaim(inputs)
        require(git_call(git_executable, "rev-parse", "HEAD").stdout.strip() == head, "launch HEAD changed during validation")
        return StaticAuthority(binding_data, reviewer_data, inputs, tuple(leases))
    except BaseException:
        for lease in reversed(leases):
            try:
                lease.close()
            except BaseException:
                pass
        raise


def load_arsc_eval_source_only(
    module_bytes: dict[str, bytes],
    expected_sha256: dict[str, str],
) -> tuple[Any, Any]:
    """Deterministically build the verified ``arsc_eval`` namespace.

    Accepts bytes that were already leased and hash/tree verified by the static
    gate, creates plain :class:`types.ModuleType` objects directly, and never
    touches ``sys.path``, importlib loaders, ``sys.meta_path``, bytecode caches,
    or the filesystem.  Every source byte must hash to its ``expected_sha256``
    marker; on any failure all inserted ``arsc_eval`` modules are rolled back.
    Returns the verified ``control`` and ``formal_runner`` modules.
    """
    require(type(module_bytes) is dict and set(module_bytes) == set(REQUIRED_ARSC_EVAL_SOURCES), "loader source set differs")
    require(type(expected_sha256) is dict and set(expected_sha256) == set(REQUIRED_ARSC_EVAL_SOURCES), "loader sha set differs")
    for rel, data in module_bytes.items():
        require(type(data) is bytes, "loader source type differs")
        marker = expected_sha256[rel]
        require(type(marker) is str and marker == sha256(data), "tampered verified source sha differs")
    require(all(name not in sys.modules for name, _rel, _package in ARSC_EVAL_DEP_ORDER), "loader namespace already populated")
    inserted: list[str] = []
    attached: list[tuple[types.ModuleType, str]] = []
    loaded: dict[str, types.ModuleType] = {}
    try:
        for name, rel, package in ARSC_EVAL_DEP_ORDER:
            data = module_bytes[rel]
            file_path = repo_path(rel)
            module = types.ModuleType(name)
            module.__package__ = package
            module.__file__ = str(file_path)
            spec = importlib.machinery.ModuleSpec(
                name,
                None,
                origin=str(file_path),
                is_package=(name == ARSC_EVAL_DEP_ORDER[0][0]),
            )
            spec.loader = None
            spec.cached = None
            if name == ARSC_EVAL_DEP_ORDER[0][0]:
                spec.submodule_search_locations = [str(repo_path("src/arsc_eval"))]
            module.__spec__ = spec
            module.__cached__ = None
            module.__source_sha256__ = sha256(data)
            sys.modules[name] = module
            inserted.append(name)
            if package:
                parent = loaded[package]
                child = name.rsplit(".", 1)[1]
                setattr(parent, child, module)
                attached.append((parent, child))
            code = compile(data, str(file_path), "exec", dont_inherit=True, optimize=0)
            exec(code, module.__dict__)
            loaded[name] = module
        control = loaded["arsc_eval.round11_layout_control"]
        formal = loaded["arsc_eval.round11_layout_formal_runner"]
        return control, formal
    except BaseException:
        for parent, child in reversed(attached):
            if getattr(parent, child, None) is not None:
                try:
                    delattr(parent, child)
                except AttributeError:
                    pass
        for name in reversed(inserted):
            sys.modules.pop(name, None)
        raise


def _preloaded_arsc_eval_module(modules: object) -> str | None:
    """Return the name of any preloaded ``arsc_eval`` module, else ``None``."""
    require(hasattr(modules, "__iter__"), "startup module index differs")
    for name in modules:
        if name == "arsc_eval" or name.startswith("arsc_eval."):
            return name
    return None


def validate_startup_attestation(
    orig_argv: object,
    flags: object,
    executable: object,
    script_path: object,
    modules: object | None = None,
) -> None:
    """Pure fail-closed attestation of the interpreted boot.

    Enforces the exact ordered launcher argv (``python -I -S -B <script>`` plus
    the exact launcher option order), the exact interpreter flag set, no extra
    interpreter flags, and no preloaded ``arsc_eval`` namespace ahead of the
    verified imports below. Read-only against global interpreter state.
    """
    require(isinstance(orig_argv, (list, tuple)), "startup argv type differs")
    remaining_count = 2 * len(LAUNCH_OPTION_ORDER) - 1
    expected_length = 2 + len(LAUNCH_INTERPRETER_FLAGS) + remaining_count
    require(len(orig_argv) >= expected_length, "startup argv length differs")
    require(len(orig_argv) == expected_length, "startup extra interpreter flags")
    require(orig_argv[0] == executable, "startup executable differs")
    flag_tail = len(LAUNCH_INTERPRETER_FLAGS)
    require(tuple(orig_argv[1 : 1 + flag_tail]) == LAUNCH_INTERPRETER_FLAGS, "startup interpreter flags differ")
    require(orig_argv[1 + flag_tail] == script_path, "startup script path differs")
    remaining = orig_argv[1 + flag_tail + 1 :]
    require(
        tuple(remaining[2 * index] for index in range(len(LAUNCH_OPTION_ORDER))) == LAUNCH_OPTION_ORDER,
        "startup launcher option order differs",
    )
    require(bool(remaining[1]) and bool(remaining[3]) and bool(remaining[5]), "startup launcher option value differs")
    require(type(flags.isolated) is int and flags.isolated == 1, "startup isolation differ")
    require(type(flags.no_user_site) is int and flags.no_user_site == 1, "startup user-site differ")
    require(type(flags.no_site) is int and flags.no_site == 1, "startup site-policy differ")
    require(flags.safe_path is True, "startup safe_path differ")
    require(type(flags.dont_write_bytecode) is int and flags.dont_write_bytecode == 1, "startup bytecode policy differ")
    require(type(flags.ignore_environment) is int and flags.ignore_environment == 1, "startup environment policy differ")
    preloaded = _preloaded_arsc_eval_module(sys.modules if modules is None else modules)
    require(preloaded is None, f"arsc_eval namespace preloaded before verified imports: {preloaded}")


def validate_verified_import_paths() -> None:
    """Verify the verified arsc_eval package/control/formal modules resolve exactly to bound repo paths."""
    package = sys.modules.get("arsc_eval")
    control = sys.modules.get("arsc_eval.round11_layout_control")
    formal = sys.modules.get("arsc_eval.round11_layout_formal_runner")
    require(package is not None and control is not None and formal is not None, "verified module absent")
    expected: tuple[tuple[Any, str], ...] = (
        (package, "src/arsc_eval/__init__.py"),
        (control, "src/arsc_eval/round11_layout_control.py"),
        (formal, "src/arsc_eval/round11_layout_formal_runner.py"),
    )
    for module, rel in expected:
        require(Path(module.__file__).resolve() == repo_path(rel), "verified module path differs")


def main() -> int:
    script = str(Path(__file__).resolve())
    validate_startup_attestation(sys.orig_argv, sys.flags, sys.executable, script, sys.modules)
    raw = sys.argv[1:]
    require(len(raw) == 7 and raw[0] == "--expected-launch-head" and raw[2] == "--expected-reviewer-sha256" and raw[4] == "--git-executable" and raw[6] == "--execute", "launcher argv shape differs")
    expected_environment = minimal_environment_contract()
    require(validate_launcher_environment(dict(os.environ)) == expected_environment, "launcher environment differs")
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--expected-launch-head", required=True)
    parser.add_argument("--expected-reviewer-sha256", required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    require(args.execute, "explicit --execute is required")
    authority = validate_static_authority(expected_launch_head=args.expected_launch_head, expected_reviewer_sha256=args.expected_reviewer_sha256, git_executable=args.git_executable)
    try:
        from arsc_eval import round11_layout_formal_runner as formal

        result = formal.run_formal_layout_attempt(authority.inputs)
        print(f"{result.outcome} {result.completeness}")
        return 0
    finally:
        authority.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StaticGateError as error:
        print(f"STOP_STATIC_GATE {error}", file=sys.stderr)
        raise SystemExit(2)
