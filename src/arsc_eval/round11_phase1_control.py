"""Fail-closed execution controls for the Round 11 DAAD-X Phase-1 run.

The functions in this module are data-agnostic.  They acquire the permanent
one-attempt claim and publish already-built evidence bytes atomically; they do
not open a transport receipt, range manifest, archive, label, or video.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

CLAIM_SCHEMA = "ARSC_ROUND11_DAADX_PHASE1_ATTEMPT_CLAIM_V1"
INDEX_SCHEMA = "ARSC_ROUND11_DAADX_PHASE1_ARTIFACT_INDEX_V1"
RESULTS_SCHEMA = "ARSC_ROUND11_DAADX_PHASE1_RESULTS_V1"
PHASE = "PHASE1_G0_G3_DIAGNOSTIC_ONLY"
ATTEMPT = "phase1_attempt01"
PASS_OUTCOME = "PHASE1_G0_G3_PASS_AWAIT_INDEPENDENT_CLOSURE"
STOP_OUTCOME = "STOP_DAADX_PHASE1_EARLY_GATE_FAILURE"
DEFERRED = "DEFERRED_NOT_RUN_PHASE1"

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
INDEX_NAME = ARTIFACTS[-1]
PAYLOAD_NAMES = ARTIFACTS[:-1]


class Phase1ControlError(RuntimeError):
    """A frozen Phase-1 execution-control invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase1ControlError(message)


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


def normalize_hex256(value: str, label: str) -> str:
    require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value),
        f"{label} must be 64 hexadecimal characters",
    )
    return value.upper()


def sync_directory_strict(path: Path) -> None:
    """Durably flush a directory or fail; there is no best-effort success."""

    require(path.is_dir() and not path.is_symlink(), "directory sync target is invalid")
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        flush = kernel32.FlushFileBuffers
        flush.argtypes = [ctypes.c_void_p]
        flush.restype = ctypes.c_int
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        handle = create_file(
            str(path),
            0x40000000,  # GENERIC_WRITE, required by FlushFileBuffers.
            0x00000007,  # FILE_SHARE_READ | WRITE | DELETE.
            None,
            3,  # OPEN_EXISTING.
            0x22000000,  # BACKUP_SEMANTICS | WRITE_THROUGH.
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if handle == invalid:
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
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def strict_canonical_json(value: bytes, label: str) -> Mapping[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise Phase1ControlError(f"{label} contains duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        parsed = json.loads(value.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Phase1ControlError(f"{label} JSON is invalid") from error
    require(isinstance(parsed, Mapping), f"{label} must be a JSON object")
    require(value == canonical_json_bytes(parsed), f"{label} JSON is not canonical")
    return parsed


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_nlink)


def _require_open_path_identity(descriptor: int, path: Path, label: str) -> None:
    opened = os.fstat(descriptor)
    try:
        current = os.lstat(path)
    except OSError as error:
        raise Phase1ControlError(f"{label} path disappeared or changed") from error
    require(stat.S_ISREG(opened.st_mode), f"{label} open handle is not regular")
    require(stat.S_ISREG(current.st_mode) and not path.is_symlink(), f"{label} path is not regular")
    require(_identity(opened) == _identity(current), f"{label} path/inode changed")
    require(opened.st_nlink == 1, f"{label} must not be hard-linked")


def claim_payload(binding_sha256: str, random_token: str) -> dict[str, str]:
    return {
        "schema_version": CLAIM_SCHEMA,
        "phase": PHASE,
        "attempt": ATTEMPT,
        "execution_binding_sha256": normalize_hex256(
            binding_sha256, "execution binding SHA256"
        ),
        "random_token": normalize_hex256(random_token, "random token"),
    }


def acquire_persistent_claim(
    path: Path,
    *,
    binding_sha256: str,
    random_token: str,
    after_create_hook: Callable[[Path], None] | None = None,
    file_fsync: Callable[[int], None] = os.fsync,
    directory_fsync: Callable[[Path], None] = sync_directory_strict,
) -> bytes:
    """Create and durably retain the unique claim; never clean it up."""

    require(path.is_absolute(), "claim path must be absolute")
    require(path.parent.is_dir(), "claim parent directory is absent")
    require(not path.parent.is_symlink(), "claim parent must not be a symlink")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"phase-1 attempt claim already exists: {path}")
    payload = canonical_json_bytes(claim_payload(binding_sha256, random_token))
    # A failure after this exclusive create intentionally leaves a blocking
    # zero-byte or partial claim.  Recovery requires a reviewed attempt02.
    with path.open("xb") as stream:
        # Durably establish the blocking directory entry before any later hook
        # or payload write can fail.
        stream.flush()
        file_fsync(stream.fileno())
        directory_fsync(path.parent)
        _require_open_path_identity(stream.fileno(), path, "claim")
        if after_create_hook is not None:
            after_create_hook(path)
        _require_open_path_identity(stream.fileno(), path, "claim")
        stream.write(payload)
        stream.flush()
        file_fsync(stream.fileno())
        _require_open_path_identity(stream.fileno(), path, "claim")
        directory_fsync(path.parent)
        _require_open_path_identity(stream.fileno(), path, "claim")
    require(read_regular_stable(path) == payload, "claim bytes changed after durable close")
    return payload


def validate_results_payload(value: Mapping[str, Any]) -> None:
    require(
        set(value)
        == {
            "schema_version",
            "phase",
            "attempt",
            "outcome",
            "gates",
            "is_formal_g0_g8_verdict",
            "training_authorized",
        },
        "Phase-1 results field set differs",
    )
    require(value["schema_version"] == RESULTS_SCHEMA, "results schema differs")
    require(value["phase"] == PHASE and value["attempt"] == ATTEMPT, "phase/attempt differs")
    require(value["is_formal_g0_g8_verdict"] is False, "formal G0-G8 verdict is forbidden")
    require(value["training_authorized"] is False, "training authority is forbidden")
    gates = value["gates"]
    require(isinstance(gates, Mapping), "gates must be an object")
    require(set(gates) == {f"G{index}" for index in range(8)}, "gate field set differs")
    for gate in ("G0", "G1", "G2", "G3"):
        require(gates[gate] in {"PASS", "FAIL", "INCONCLUSIVE"}, f"{gate} status differs")
    for gate in ("G4", "G5", "G6", "G7"):
        require(gates[gate] == DEFERRED, f"{gate} must remain deferred")
    passed = all(gates[gate] == "PASS" for gate in ("G0", "G1", "G2", "G3"))
    expected = PASS_OUTCOME if passed else STOP_OUTCOME
    require(value["outcome"] == expected, "outcome does not match G0-G3 states")


def validate_payloads(payloads: Mapping[str, bytes]) -> None:
    require(set(payloads) == set(PAYLOAD_NAMES), "Phase-1 payload allowlist differs")
    require(all(isinstance(value, bytes) for value in payloads.values()), "payload is not bytes")
    results = strict_canonical_json(
        payloads["round11_daadx_phase1_results.json"], "Phase-1 results"
    )
    validate_results_payload(results)


def artifact_index_bytes(payloads: Mapping[str, bytes]) -> bytes:
    validate_payloads(payloads)
    rows = [
        {"path": name, "bytes": len(payloads[name]), "sha256": sha256_bytes(payloads[name])}
        for name in sorted(PAYLOAD_NAMES)
    ]
    return canonical_json_bytes(
        {
            "schema_version": INDEX_SCHEMA,
            "artifact_count": len(rows),
            "artifact_index_self_excluded": True,
            "artifacts": rows,
        }
    )


def _regular_non_symlink(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not path.is_symlink() and metadata.st_nlink == 1


def read_regular_stable(
    path: Path, *, after_open_hook: Callable[[Path], None] | None = None
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "artifact")
        if after_open_hook is not None:
            after_open_hook(path)
        _require_open_path_identity(descriptor, path, "artifact")
        chunks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "artifact")
        require(
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "artifact changed while being read",
        )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def verify_phase1_closure(final: Path) -> bool:
    if not final.is_dir() or final.is_symlink():
        return False
    entries = list(final.iterdir())
    if {item.name for item in entries} != set(ARTIFACTS):
        return False
    if any(not _regular_non_symlink(item) for item in entries):
        return False
    try:
        index_bytes = read_regular_stable(final / INDEX_NAME)
        index = strict_canonical_json(index_bytes, "artifact index")
    except (OSError, Phase1ControlError):
        return False
    if (
        not isinstance(index, Mapping)
        or set(index) != {"schema_version", "artifact_count", "artifact_index_self_excluded", "artifacts"}
        or index.get("schema_version") != INDEX_SCHEMA
        or index.get("artifact_count") != len(PAYLOAD_NAMES)
        or index.get("artifact_index_self_excluded") is not True
        or not isinstance(index.get("artifacts"), list)
    ):
        return False
    try:
        final_payloads = {name: read_regular_stable(final / name) for name in PAYLOAD_NAMES}
        expected_index = artifact_index_bytes(final_payloads)
        if index_bytes != expected_index:
            return False
        results = strict_canonical_json(
            final_payloads["round11_daadx_phase1_results.json"], "Phase-1 results"
        )
        validate_results_payload(results)
    except (OSError, Phase1ControlError):
        return False
    return True


def rename_directory_no_replace(source: Path, target: Path) -> None:
    """Atomically rename a directory without replacing an existing target."""

    if os.name == "nt":
        os.rename(source, target)  # Windows rename is no-replace.
        return
    if os.name == "posix" and hasattr(os, "uname") and os.uname().sysname == "Linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOSYS, "renameat2 unavailable; refusing non-atomic fallback")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            -100,
            os.fsencode(source),
            -100,
            os.fsencode(target),
            1,  # RENAME_NOREPLACE
        )
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), target)
        return
    raise OSError(errno.ENOSYS, "no atomic no-replace directory rename on this platform")


def publish_phase1_atomically(
    staging: Path,
    final: Path,
    payloads: Mapping[str, bytes],
    *,
    rename_func: Callable[[Path, Path], None] = rename_directory_no_replace,
    file_fsync: Callable[[int], None] = os.fsync,
    directory_fsync: Callable[[Path], None] = sync_directory_strict,
) -> None:
    """Publish the exact evidence closure; preserve all crash residue."""

    validate_payloads(payloads)
    require(staging.is_absolute() and final.is_absolute(), "publication paths must be absolute")
    require(staging.parent == final.parent, "staging/final parents differ")
    require(staging.resolve() != final.resolve(), "staging/final alias")
    if staging.exists() or staging.is_symlink():
        raise FileExistsError(f"Phase-1 staging already exists: {staging}")
    if final.exists() or final.is_symlink():
        raise FileExistsError(f"Phase-1 final already exists: {final}")
    require(staging.parent.is_dir(), "publication parent is absent")
    require(not staging.parent.is_symlink(), "publication parent must not be a symlink")
    staging.mkdir(mode=0o700, exist_ok=False)
    directory_fsync(staging.parent)
    for name in PAYLOAD_NAMES:
        path = staging / name
        with path.open("xb") as stream:
            stream.write(payloads[name])
            stream.flush()
            file_fsync(stream.fileno())
    index_path = staging / INDEX_NAME
    with index_path.open("xb") as stream:
        stream.write(artifact_index_bytes(payloads))
        stream.flush()
        file_fsync(stream.fileno())
    directory_fsync(staging)
    rename_func(staging, final)
    directory_fsync(final.parent)
    require(verify_phase1_closure(final), "post-publish Phase-1 closure verification failed")
