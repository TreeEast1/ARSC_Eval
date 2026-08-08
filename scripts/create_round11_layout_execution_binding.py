"""Create the non-running, host-specific Round 11 layout execution binding.

Only tracked repository authorities, executable toolchain files and lexical
path declarations are read.  The three declared run inputs are never touched.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_EXECUTION_BINDING_V1"
DECISION = "NOT_RUN_BINDING_FROZEN_AWAIT_INDEPENDENT_GO_RUN"
REVIEW_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_EXECUTION_REVIEWER_DECISION_V1"
REVIEW_DECISION = "GO_RUN_LAYOUT_INVENTORY_ATTEMPT01_ONCE"
OUTPUT = ROOT / "outputs/validity/round11_daadx_layout_inventory_execution_binding.json"
H0 = "c34bcb118d9f89dc25160f39ca916fe061b6754c"

# Exactly two tracked sources are intentionally allowed to drift between H0 and
# H1 (the contained worker chain).  Any other H0 artifact that changes is
# rejected as unplanned tracked drift.
INTENTIONAL_H0_TO_H1 = frozenset(
    {
        "src/arsc_eval/round11_layout_worker.py",
        "src/arsc_eval/round11_layout_runner.py",
        "tests/test_round11_layout_runner.py",
    }
)

BOUND_PATHS = (
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


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def safe_repo_path(text: str) -> Path:
    pure = PurePosixPath(text)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != text:
        raise ValueError(f"unsafe repository path: {text}")
    return ROOT.joinpath(*pure.parts)


def record(text: str, git: Path) -> dict[str, object]:
    data = safe_repo_path(text).read_bytes()
    listing = git_output(git, "ls-tree", H0, "--", text)
    mode = "100644"
    if listing:
        prefix, listed_path = listing.split("\t", 1)
        listed_mode, kind, listed_blob = prefix.split(" ")
        if listed_path != text or listed_mode != mode or kind != "blob":
            raise RuntimeError(f"H0 artifact differs: {text}")
        current_blob = git_blob(data)
        if text in INTENTIONAL_H0_TO_H1:
            if listed_blob == current_blob:
                raise RuntimeError(f"intentional H1 source did not change: {text}")
        elif listed_blob != current_blob:
            raise RuntimeError(f"unplanned H0 artifact drift: {text}")
    return {"path": text, "bytes": len(data), "sha256": digest(data), "git_blob": git_blob(data), "git_mode": mode}


def executable_record(path: Path) -> dict[str, object]:
    absolute = path.absolute()
    data = absolute.read_bytes()
    metadata = os.stat(absolute, follow_symlinks=False)
    return {"path": str(absolute), "bytes": len(data), "sha256": digest(data), "link_count": metadata.st_nlink}


def git_output(git: Path, *args: str) -> str:
    result = subprocess.run(
        [str(git), *args], cwd=ROOT, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="strict", env={"SYSTEMROOT": os.environ["SYSTEMROOT"]},
    )
    return result.stdout.strip()


def create_binding(*, python: Path, git: Path) -> dict[str, object]:
    if os.name != "nt" or sys.platform != "win32":
        raise RuntimeError("formal binding requires native Windows")
    git_absolute = git.absolute()
    if git_absolute.name != "git.exe" or git_absolute.parent.name != "bin" or git_absolute.parent.parent.name != "mingw64":
        raise RuntimeError("binding requires the real MinGit binary, not a wrapper or stub")
    if git_output(git, "rev-parse", "HEAD") != H0:
        raise RuntimeError("binding must be generated from reviewed H0")
    artifacts = [record(path, git) for path in BOUND_PATHS]
    protocol = json.loads(safe_repo_path(BOUND_PATHS[0]).read_text(encoding="utf-8"))
    transport_review = json.loads(
        safe_repo_path("outputs/validity/round11_transport_receipt_postgeneration_reviewer_decision.json").read_text(encoding="utf-8")
    )
    manifest = transport_review["assembler_manifest"]
    archive = transport_review["assembled_archive"]
    resource_bounds = protocol["resource_bounds"]
    output = protocol["execution_control"]
    system_root = os.environ["SYSTEMROOT"]
    exact_names = protocol["artifact_contract"]["exact_files"]
    exact_caps = {
        name: (
            resource_bounds["max_public_inventory_output_bytes"] if name == exact_names[7]
            else resource_bounds["max_restricted_path_seal_output_bytes"] if name == exact_names[8]
            else resource_bounds["max_execution_log_output_bytes"] if name == exact_names[10]
            else 16_777_216
        )
        for name in exact_names
    }
    return {
        "schema_version": SCHEMA,
        "decision": DECISION,
        "source_reviewed_head_h0": H0,
        "artifacts": artifacts,
        "reviewer_authority": {
            "path": "outputs/validity/round11_daadx_layout_inventory_execution_reviewer_decision.json",
            "schema_version": REVIEW_SCHEMA,
            "required_decision": REVIEW_DECISION,
            "digest_source": "OUT_OF_BAND_REVIEW_PIN",
        },
        "toolchain": {
            "python": {**executable_record(python), "version": sys.version, "implementation": platform.python_implementation()},
            "git": executable_record(git),
            "platform": {"os_name": os.name, "sys_platform": sys.platform, "machine": platform.machine(), "platform": platform.platform()},
        },
        "worker_process": {
            "argv_template": [str(python.absolute()), "-I", "-S", "-B", str(safe_repo_path("src/arsc_eval/round11_layout_worker.py")), "--control-handle", "<POSITIVE_INTEGER_INHERITED_HANDLE>", "--expected-bytes", "18585647156", "--expected-sha256", "98E6DD4D068004B090A5D62C648A727AF902EBF3B176BCE2CE044EABDE91E965"],
            "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "SYSTEMROOT": system_root},
            "windows_job": {"create_suspended": True, "extended_startupinfo_present": True, "create_no_window": True, "handle_list_only": True, "active_process_limit": 1, "kill_on_job_close": True},
        },
        "launcher_process": {
            "argv_template": [str(python.absolute()), "-I", "-S", "-B", str(safe_repo_path("scripts/run_round11_layout_inventory.py")), "--expected-launch-head", "<EXTERNAL_40_HEX_LOWER>", "--expected-reviewer-sha256", "<EXTERNAL_64_HEX_UPPER>", "--git-executable", str(git.absolute()), "--execute"],
            "environment": {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "SYSTEMROOT": system_root},
            "argparse_allow_abbrev": False,
            "duplicate_or_reordered_options_allowed": False,
        },
        "formal_run": {
            "attempt": "layout_inventory_attempt01",
            "phase": "ARCHIVE_LAYOUT_INVENTORY_ONLY",
            "timeout_seconds": 21600,
            "closure_reserve_seconds": 1800,
            "require_formal_windows": True,
            "claim_path": str(safe_repo_path(output["claim_path"])),
            "staging_path": str(safe_repo_path(output["staging_path"])),
            "final_path": str(safe_repo_path(output["final_path"])),
            "cwd_policy": "EXCLUSIVE_STAGING_CREATED_AFTER_DURABLE_CLAIM",
            "automatic_retry_delete_recovery": False,
        },
        "authorities": {
            "protocol": {"path": BOUND_PATHS[0], "bytes": artifacts[0]["bytes"], "sha256": artifacts[0]["sha256"]},
            "receipt": {"path": protocol["input_contract"]["accepted_receipt_snapshot"], "schema_version": "ARSC_ROUND11_DAADX_TRANSPORT_RECEIPT_V1", "bytes": 1629, "sha256": "D738E21E5DC1976C192CFA3982E2CA2941FF3D2AF8A811BA432D51778A6B1C7F"},
            "manifest": {"path": manifest["path"], "schema_version": manifest["schema_version"], "bytes": manifest["bytes"], "sha256": manifest["sha256"]},
            "archive": {"path": archive["path"], "bytes": archive["bytes"], "sha256": archive["sha256"]},
            "preclaim_real_input_access": False,
        },
        "artifact_contract": {"exact_names": exact_names, "exact_caps": exact_caps, "artifact_statuses": ["ABSENT_REPRESENTED_EMPTY", "OBSERVED_COMPLETE", "OBSERVED_PARTIAL"], "observed_scopes": ["COMPLETE_STREAM", "NONE", "SUPPLIED_PREFIX"], "complete_closure": "LAYOUT_INVENTORY_COMPLETE", "stop_closure": "HASH_CLOSED_STOP", "runtime_derived_output_hashes": True},
        "resource_bounds": resource_bounds,
        "capabilities": {"structure_inventory": True, "raw_header_path_type_size": True, "opaque_regular_payload_drain": True, "label_values": False, "provenance_rows": False, "video_frames": False, "regular_payload_semantics": False, "phase1": False, "g0_g8": False, "training": False, "inference": False},
        "external_anchor_required": {"expected_launch_head": True, "expected_reviewer_sha256": True},
        "this_is_go_run": False,
    }


REPARSE_POINT_ATTRIBUTE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT


def is_reparse_point(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if os.name == "nt":
        attributes = getattr(st, "st_file_attributes", 0)
        return bool(attributes & REPARSE_POINT_ATTRIBUTE)
    return stat.S_ISLNK(st.st_mode)


def directory_identity(path: Path) -> tuple[object, object]:
    st = os.stat(path, follow_symlinks=False)
    return (st.st_dev, st.st_ino)


def publish(path: Path, payload: bytes) -> None:
    path = path.absolute()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Reparse-pointed output parents are refused before any leaf is created.
    if is_reparse_point(parent):
        raise OSError("output parent is a reparse point")
    # Pin the identity of the already-existing output parent before leaf creation.
    pinned_parent = directory_identity(parent)
    # Once created, the exclusive leaf must not be a reparse point.
    if is_reparse_point(path):
        raise OSError("output leaf is a reparse point")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("binding write failed")
            offset += written
        opened = os.fstat(fd)
        current = os.lstat(path)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise OSError("binding path identity differs")
        if is_reparse_point(path):
            raise OSError("output leaf is a reparse point")
        os.fsync(fd)
        sync_directory(parent)
        if directory_identity(parent) != pinned_parent:
            raise OSError("output parent identity changed after sync")
    except BaseException:
        # A failed exclusive publication remains as blocking residue; never delete it.
        raise
    finally:
        os.close(fd)


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        flush = kernel32.FlushFileBuffers
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        handle = create(str(path), 0x40000000, 7, None, 3, 0x22000000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "directory open failed")
        try:
            try:
                if not flush(handle):
                    raise OSError(ctypes.get_last_error(), "directory sync failed")
            finally:
                if not close(handle):
                    # Every CloseHandle result is checked; a failure is surfaced
                    # and the blocking residue is left in place.
                    raise OSError(ctypes.get_last_error(), "directory close failed")
        except BaseException:
            raise
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    binding = create_binding(python=args.python, git=args.git)
    publish(args.output, canonical(binding))
    print(f"{DECISION} {args.output.absolute()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
