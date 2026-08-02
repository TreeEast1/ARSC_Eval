"""Durable one-attempt and streaming closure controls for layout inventory.

This module is data-agnostic.  It never names or opens the real receipt,
manifest, archive, label, or video.  Callers own the strict preclaim/postclaim
ordering; these primitives make the claim and final evidence closure durable.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO


CLAIM_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_ATTEMPT_CLAIM_V1"
INDEX_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_ARTIFACT_INDEX_V1"
RESULTS_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_INVENTORY_RESULTS_V1"
ARCHIVE_HASHES_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_ARCHIVE_HASHES_V1"
SUMMARY_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_STRUCTURE_SUMMARY_V1"
PHASE = "ARCHIVE_LAYOUT_INVENTORY_ONLY"
ATTEMPT = "layout_inventory_attempt01"
COMPLETE_OUTCOME = "LAYOUT_INVENTORY_COMPLETE_AWAIT_INDEPENDENT_SELECTION"
STOP_OUTCOME = "STOP_LAYOUT_INTEGRITY_OR_POLICY_FAILURE"
COMPLETE_CLOSURE = "LAYOUT_INVENTORY_COMPLETE"
STOP_CLOSURE = "HASH_CLOSED_STOP"

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
INDEX_NAME = ARTIFACTS[-1]
PAYLOAD_NAMES = ARTIFACTS[:-1]
PUBLIC_NAME = ARTIFACTS[7]
RESTRICTED_NAME = ARTIFACTS[8]
RESULTS_NAME = ARTIFACTS[9]
LOG_NAME = ARTIFACTS[10]
PUBLIC_HEADER = b"member_ordinal,raw_path_sha256,resolved_path_sha256,member_type,size,pax_flags\n"

ARTIFACT_STATUS = frozenset(
    {"OBSERVED_COMPLETE", "OBSERVED_PARTIAL", "ABSENT_REPRESENTED_EMPTY"}
)
OBSERVED_SCOPES = frozenset({"NONE", "SUPPLIED_PREFIX", "COMPLETE_STREAM"})

MIB = 1_048_576
ARTIFACT_CAPS = {
    ARTIFACTS[0]: 16_777_216,
    ARTIFACTS[1]: 16_777_216,
    ARTIFACTS[2]: 16_777_216,
    ARTIFACTS[3]: 16_777_216,
    ARTIFACTS[4]: 16_777_216,
    ARTIFACTS[5]: 16_777_216,
    ARTIFACTS[6]: 16_777_216,
    PUBLIC_NAME: 67_108_864,
    RESTRICTED_NAME: 2_147_483_648,
    RESULTS_NAME: 16_777_216,
    LOG_NAME: 16_777_216,
    INDEX_NAME: 16_777_216,
}


class LayoutControlError(RuntimeError):
    """A durable-control or evidence-closure invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LayoutControlError(message)


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
        and re.fullmatch(r"[0-9A-Fa-f]{64}", value) is not None,
        f"{label} must be 64 hexadecimal characters",
    )
    return value.upper()


def strict_canonical_json(value: bytes, label: str) -> Mapping[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            require(key not in result, f"{label} contains duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        parsed = json.loads(value.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LayoutControlError(f"{label} JSON is invalid") from error
    require(isinstance(parsed, Mapping), f"{label} must be a JSON object")
    require(value == canonical_json_bytes(parsed), f"{label} JSON is not canonical")
    return parsed


def sync_directory_strict(path: Path) -> None:
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


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_nlink


def _require_open_path_identity(descriptor: int, path: Path, label: str) -> None:
    opened = os.fstat(descriptor)
    try:
        current = os.lstat(path)
    except OSError as error:
        raise LayoutControlError(f"{label} path disappeared or changed") from error
    require(stat.S_ISREG(opened.st_mode), f"{label} open handle is not regular")
    require(
        stat.S_ISREG(current.st_mode) and not path.is_symlink(),
        f"{label} path is not regular",
    )
    require(_identity(opened) == _identity(current), f"{label} path/inode changed")
    require(opened.st_nlink == 1, f"{label} must not be hard-linked")


def _write_all(stream: BinaryIO, payload: bytes, label: str) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        written = stream.write(view[offset:])
        require(
            isinstance(written, int) and written > 0,
            f"short or invalid write: {label}",
        )
        offset += written


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
) -> ClaimAcquisition:
    """Durably create the one-attempt claim; every failure retains it."""

    require(path.is_absolute(), "claim path must be absolute")
    require(path.parent.is_dir() and not path.parent.is_symlink(), "claim parent is invalid")
    parent_lease = _HeldPath(path.parent, is_directory=True)
    claim_lease: _HeldPath | None = None
    try:
        parent_lease.verify()
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"layout attempt claim already exists: {path}")
        payload = canonical_json_bytes(claim_payload(binding_sha256, random_token))
        with path.open("xb", buffering=0) as stream:
            file_fsync(stream.fileno())
            directory_fsync(path.parent)
            parent_lease.verify()
            _require_open_path_identity(stream.fileno(), path, "layout claim")
            if after_create_hook is not None:
                after_create_hook(path)
            parent_lease.verify()
            _require_open_path_identity(stream.fileno(), path, "layout claim")
            _write_all(stream, payload, "layout claim")
            file_fsync(stream.fileno())
            _require_open_path_identity(stream.fileno(), path, "layout claim")
            directory_fsync(path.parent)
            parent_lease.verify()
            _require_open_path_identity(stream.fileno(), path, "layout claim")
        claim_lease = _HeldPath(path, is_directory=False)
        observed = digest_regular_stable(path, max_bytes=len(payload))
        require(
            observed.bytes == len(payload) and observed.sha256 == sha256_bytes(payload),
            "layout claim bytes changed after durable close",
        )
        lease = AttemptLease(parent_lease, claim_lease, path, observed)
        lease.verify_claim()
        return ClaimAcquisition(payload, lease)
    except BaseException:
        if claim_lease is not None:
            claim_lease.close()
        parent_lease.close()
        raise


@dataclass(frozen=True)
class FileDigest:
    bytes: int
    sha256: str


@dataclass(frozen=True)
class PathIdentity:
    device: int
    inode: int
    links: int


class _WindowsFileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", ctypes.c_uint32),
        ("creation_low", ctypes.c_uint32),
        ("creation_high", ctypes.c_uint32),
        ("access_low", ctypes.c_uint32),
        ("access_high", ctypes.c_uint32),
        ("write_low", ctypes.c_uint32),
        ("write_high", ctypes.c_uint32),
        ("volume_serial", ctypes.c_uint32),
        ("size_high", ctypes.c_uint32),
        ("size_low", ctypes.c_uint32),
        ("links", ctypes.c_uint32),
        ("index_high", ctypes.c_uint32),
        ("index_low", ctypes.c_uint32),
    ]


class _HeldPath:
    """Lifetime identity lease; Windows also denies rename/delete sharing."""

    __slots__ = (
        "path",
        "is_directory",
        "identity",
        "_handle",
        "_descriptor",
        "_stream",
        "_closed",
    )

    def __init__(self, path: Path, *, is_directory: bool) -> None:
        require(path.is_absolute(), "held path must be absolute")
        self.path = path
        self.is_directory = is_directory
        self._handle: int | None = None
        self._descriptor: int | None = None
        self._stream: BinaryIO | None = None
        self._closed = False
        if os.name == "nt":
            if is_directory:
                self._handle = self._open_windows(path, is_directory=True)
            else:
                # CPython's CRT file open denies delete/replace sharing on the
                # intended Windows host; retain it for the entire attempt.
                import msvcrt

                self._stream = path.open("rb", buffering=0)
                self._handle = int(msvcrt.get_osfhandle(self._stream.fileno()))
            self.identity = self._windows_identity(self._handle, is_directory=is_directory)
        else:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            if is_directory:
                flags |= getattr(os, "O_DIRECTORY", 0)
            self._descriptor = os.open(path, flags)
            metadata = os.fstat(self._descriptor)
            require(
                stat.S_ISDIR(metadata.st_mode) if is_directory else stat.S_ISREG(metadata.st_mode),
                "held path type differs",
            )
            require(is_directory or metadata.st_nlink == 1, "held file must not be hard-linked")
            self.identity = PathIdentity(*_identity(metadata))
        self.verify()

    @staticmethod
    def _open_windows(path: Path, *, is_directory: bool) -> int:
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
        flags = 0x00200000 | (0x02000000 if is_directory else 0)
        handle = create_file(
            str(path),
            0,
            0x00000001 | 0x00000002,  # Share read/write, deliberately not delete.
            None,
            3,
            flags,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error), path)
        return int(handle)

    @staticmethod
    def _windows_identity(handle: int, *, is_directory: bool) -> PathIdentity:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_info = kernel32.GetFileInformationByHandle
        get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WindowsFileInformation)]
        get_info.restype = ctypes.c_int
        info = _WindowsFileInformation()
        if not get_info(ctypes.c_void_p(handle), ctypes.byref(info)):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))
        is_dir_attribute = bool(info.attributes & 0x10)
        is_reparse = bool(info.attributes & 0x400)
        require(is_dir_attribute == is_directory and not is_reparse, "held Windows path type differs")
        require(is_directory or info.links == 1, "held Windows file must not be hard-linked")
        inode = (int(info.index_high) << 32) | int(info.index_low)
        return PathIdentity(int(info.volume_serial), inode, int(info.links))

    def verify(self) -> None:
        require(not self._closed, "path lease is closed")
        if os.name == "nt":
            assert self._handle is not None
            temporary = self._open_windows(self.path, is_directory=self.is_directory)
            try:
                current = self._windows_identity(
                    temporary, is_directory=self.is_directory
                )
            finally:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                if not kernel32.CloseHandle(ctypes.c_void_p(temporary)):
                    error = ctypes.get_last_error()
                    raise OSError(error, os.strerror(error), self.path)
        else:
            assert self._descriptor is not None
            opened = os.fstat(self._descriptor)
            current_metadata = os.lstat(self.path)
            require(
                (stat.S_ISDIR(current_metadata.st_mode) if self.is_directory else stat.S_ISREG(current_metadata.st_mode))
                and not self.path.is_symlink(),
                "leased path type changed",
            )
            require(_identity(opened) == _identity(current_metadata), "leased path identity changed")
            current = PathIdentity(*_identity(current_metadata))
        require(current == self.identity, "leased path identity changed")

    def close(self) -> None:
        if self._closed:
            return
        if os.name == "nt":
            assert self._handle is not None
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            else:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                if not kernel32.CloseHandle(ctypes.c_void_p(self._handle)):
                    error = ctypes.get_last_error()
                    raise OSError(error, os.strerror(error), self.path)
            self._handle = None
        else:
            assert self._descriptor is not None
            os.close(self._descriptor)
            self._descriptor = None
        self._closed = True


class AttemptLease:
    """Sealed lifetime binding for parent, claim, staging and final identities."""

    __slots__ = (
        "parent",
        "claim",
        "claim_path",
        "claim_digest",
        "staging_path",
        "final_path",
        "staging",
        "final",
        "_released_staging_identity",
        "_sealed",
    )

    def __init__(
        self,
        parent: _HeldPath,
        claim: _HeldPath,
        claim_path: Path,
        claim_digest: FileDigest,
    ) -> None:
        self.parent = parent
        self.claim = claim
        self.claim_path = claim_path
        self.claim_digest = claim_digest
        self.staging_path: Path | None = None
        self.final_path: Path | None = None
        self.staging: _HeldPath | None = None
        self.final: _HeldPath | None = None
        self._released_staging_identity: PathIdentity | None = None
        self._sealed = True

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("AttemptLease is sealed")
        object.__setattr__(self, name, value)

    def verify_claim(self) -> None:
        require(type(self) is AttemptLease, "attempt lease type differs")
        self.parent.verify()
        self.claim.verify()
        require(self.claim_path.parent == self.parent.path, "claim parent binding differs")
        require(
            digest_regular_stable(
                self.claim_path, max_bytes=self.claim_digest.bytes
            )
            == self.claim_digest,
            "claim bytes changed during attempt",
        )

    def bind_staging(self, staging: Path, final: Path) -> None:
        self.verify_claim()
        require(self.staging is None and self.final is None, "staging lease already bound")
        held = _HeldPath(staging, is_directory=True)
        object.__setattr__(self, "staging_path", staging)
        object.__setattr__(self, "final_path", final)
        object.__setattr__(self, "staging", held)

    def verify_staging(self) -> None:
        self.verify_claim()
        require(self.staging is not None, "staging lease is absent")
        self.staging.verify()

    def release_staging_for_rename(self) -> PathIdentity:
        self.verify_staging()
        assert self.staging is not None
        identity = self.staging.identity
        self.staging.close()
        object.__setattr__(self, "staging", None)
        object.__setattr__(self, "_released_staging_identity", identity)
        return identity

    def bind_final_after_rename(self) -> None:
        self.verify_claim()
        require(self.final_path is not None, "final path binding is absent")
        require(self._released_staging_identity is not None, "released staging identity is absent")
        held = _HeldPath(self.final_path, is_directory=True)
        require(held.identity == self._released_staging_identity, "renamed final identity differs")
        object.__setattr__(self, "final", held)

    def verify_final(self) -> None:
        self.verify_claim()
        require(self.final is not None, "final lease is absent")
        self.final.verify()

    def close(self) -> None:
        for held in (self.final, self.staging, self.claim, self.parent):
            if held is not None:
                held.close()


@dataclass(frozen=True)
class ClaimAcquisition:
    payload: bytes
    lease: AttemptLease


@dataclass(frozen=True)
class AuthorityExpectation:
    name: str
    bytes: int
    sha256: str
    required_complete: bool


@dataclass(frozen=True)
class ArchiveExpectation:
    bytes: int
    sha256: str


@dataclass(frozen=True)
class ClosureExpectations:
    authorities: tuple[AuthorityExpectation, ...]
    archive: ArchiveExpectation


def validate_expectations(value: ClosureExpectations) -> None:
    require(type(value) is ClosureExpectations, "closure expectations type differs")
    require(type(value.archive) is ArchiveExpectation, "archive expectation type differs")
    require(
        type(value.archive.bytes) is int and value.archive.bytes > 0,
        "archive expected bytes are invalid",
    )
    require(
        normalize_hex256(value.archive.sha256, "archive expected SHA256")
        == value.archive.sha256,
        "archive expected SHA256 must be uppercase",
    )
    require(type(value.authorities) is tuple, "authority expectations container differs")
    require(
        all(type(item) is AuthorityExpectation for item in value.authorities),
        "authority expectation type differs",
    )
    expected_names = ARTIFACTS[:5]
    require(tuple(item.name for item in value.authorities) == expected_names, "authority expectation order differs")
    for index, item in enumerate(value.authorities):
        require(
            type(item.bytes) is int
            and item.bytes > 0
            and item.bytes <= ARTIFACT_CAPS[item.name],
            "authority expected bytes differ",
        )
        require(
            normalize_hex256(item.sha256, f"authority SHA256: {item.name}")
            == item.sha256,
            f"authority SHA256 must be uppercase: {item.name}",
        )
        require(
            item.required_complete is (index < 3),
            "authority required-complete policy differs",
        )


def digest_regular_stable(
    path: Path,
    *,
    max_bytes: int,
    chunk_bytes: int = MIB,
    after_open_hook: Callable[[Path], None] | None = None,
) -> FileDigest:
    """Stream-hash one stable, regular, single-link file without materializing it."""

    require(path.is_absolute(), "digest path must be absolute")
    require(isinstance(max_bytes, int) and max_bytes >= 0, "digest cap is invalid")
    require(isinstance(chunk_bytes, int) and 0 < chunk_bytes <= MIB, "digest chunk cap differs")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "artifact")
        require(before.st_size <= max_bytes, "artifact exceeds byte cap")
        if after_open_hook is not None:
            after_open_hook(path)
        digest = hashlib.sha256()
        count = 0
        while True:
            block = os.read(descriptor, chunk_bytes)
            if not block:
                break
            count += len(block)
            require(count <= max_bytes, "artifact exceeds byte cap")
            digest.update(block)
        after = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "artifact")
        require(
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "artifact changed while being hashed",
        )
        require(count == after.st_size, "artifact byte count differs from stable metadata")
        return FileDigest(count, digest.hexdigest().upper())
    finally:
        os.close(descriptor)


def read_small_regular_stable(path: Path, *, max_bytes: int) -> bytes:
    digest = digest_regular_stable(path, max_bytes=max_bytes)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "small artifact")
        chunks: list[bytes] = []
        count = 0
        while True:
            block = os.read(descriptor, min(MIB, max_bytes + 1))
            if not block:
                break
            count += len(block)
            require(count <= max_bytes, "small artifact exceeds byte cap")
            chunks.append(block)
        after = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "small artifact")
        require(
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "small artifact changed while being read",
        )
        value = b"".join(chunks)
        require(
            len(value) == digest.bytes and sha256_bytes(value) == digest.sha256,
            "small artifact changed between hash and read",
        )
        return value
    finally:
        os.close(descriptor)


def validate_results(value: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "phase",
        "attempt",
        "outcome",
        "completeness",
        "layout_complete",
        "observed_scope",
        "first_failure_stage",
        "first_failure_code",
        "artifact_status",
        "is_phase1_or_g0_g8_verdict",
        "external_validity_established",
        "training_authorized",
    }
    require(set(value) == expected_fields, "layout results field set differs")
    require(value["schema_version"] == RESULTS_SCHEMA, "layout results schema differs")
    require(value["phase"] == PHASE and value["attempt"] == ATTEMPT, "layout phase/attempt differs")
    require(value["is_phase1_or_g0_g8_verdict"] is False, "formal G0-G8 verdict is forbidden")
    require(value["external_validity_established"] is False, "external-validity claim is forbidden")
    require(value["training_authorized"] is False, "training authority is forbidden")
    require(value["observed_scope"] in OBSERVED_SCOPES, "observed scope differs")
    statuses = value["artifact_status"]
    require(isinstance(statuses, Mapping), "artifact status must be an object")
    require(set(statuses) == set(PAYLOAD_NAMES), "artifact status allowlist differs")
    require(all(item in ARTIFACT_STATUS for item in statuses.values()), "artifact status differs")
    for name in (
        ARTIFACTS[0],
        ARTIFACTS[1],
        ARTIFACTS[2],
        ARTIFACTS[5],
        ARTIFACTS[6],
        RESULTS_NAME,
        LOG_NAME,
    ):
        require(
            statuses[name] == "OBSERVED_COMPLETE",
            f"hash-closed authority/control artifact is incomplete: {name}",
        )
    if value["outcome"] == COMPLETE_OUTCOME:
        require(value["completeness"] == COMPLETE_CLOSURE, "complete closure state differs")
        require(value["layout_complete"] is True, "complete outcome lacks layout completion")
        require(value["observed_scope"] == "COMPLETE_STREAM", "complete outcome lacks full stream")
        require(value["first_failure_stage"] is None and value["first_failure_code"] is None, "complete outcome has failure")
        require(all(item == "OBSERVED_COMPLETE" for item in statuses.values()), "complete artifact status differs")
        return
    require(value["outcome"] == STOP_OUTCOME, "layout outcome differs")
    require(value["completeness"] == STOP_CLOSURE, "STOP closure state differs")
    require(value["layout_complete"] is False, "STOP cannot mark layout complete")
    for field in ("first_failure_stage", "first_failure_code"):
        item = value[field]
        require(
            isinstance(item, str)
            and re.fullmatch(r"[A-Z0-9_]{1,96}", item) is not None,
            f"STOP {field} is invalid",
        )


def validate_archive_hashes(
    value: Mapping[str, Any], expected: ArchiveExpectation
) -> None:
    require(
        set(value)
        == {
            "schema_version",
            "phase",
            "attempt",
            "expected_bytes",
            "expected_sha256",
            "observed_scope",
            "observed_bytes",
            "observed_sha256",
            "complete_stream_matches_expected",
        },
        "archive-hashes field set differs",
    )
    require(value["schema_version"] == ARCHIVE_HASHES_SCHEMA, "archive-hashes schema differs")
    require(value["phase"] == PHASE and value["attempt"] == ATTEMPT, "archive-hashes phase differs")
    require(
        value["expected_bytes"] == expected.bytes
        and value["expected_sha256"] == expected.sha256,
        "archive expectation binding differs",
    )
    scope = value["observed_scope"]
    require(scope in OBSERVED_SCOPES, "archive observed scope differs")
    observed_bytes = value["observed_bytes"]
    observed_sha = value["observed_sha256"]
    matches = value["complete_stream_matches_expected"]
    require(type(observed_bytes) is int and observed_bytes >= 0, "observed bytes are invalid")
    require(isinstance(matches, bool), "archive match flag is invalid")
    if scope == "NONE":
        require(observed_bytes == 0 and observed_sha is None and matches is False, "NONE observation is contradictory")
    elif scope == "SUPPLIED_PREFIX":
        require(0 < observed_bytes < expected.bytes, "prefix byte count is not a strict prefix")
        require(normalize_hex256(observed_sha, "prefix observed SHA256") == observed_sha, "prefix SHA256 must be uppercase")
        require(observed_sha != expected.sha256, "expected full SHA256 substituted as prefix observation")
        require(matches is False, "prefix cannot match complete archive")
    else:
        require(observed_bytes == expected.bytes, "complete-stream byte count differs")
        require(normalize_hex256(observed_sha, "complete observed SHA256") == observed_sha, "complete SHA256 must be uppercase")
        require(matches is (observed_sha == expected.sha256), "complete-stream match flag differs")


_SUMMARY_METRICS = (
    "uncompressed_tar_stream_bytes",
    "raw_header_count",
    "logical_member_count",
    "regular_member_count",
    "directory_member_count",
    "total_regular_payload_bytes",
    "post_end_zero_padding_bytes",
)


def validate_summary(value: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "phase",
        "attempt",
        "status",
        "public_rows_observed",
        "restricted_rows_observed",
        *_SUMMARY_METRICS,
    }
    require(set(value) == expected_fields, "structure-summary field set differs")
    require(value["schema_version"] == SUMMARY_SCHEMA, "structure-summary schema differs")
    require(value["phase"] == PHASE and value["attempt"] == ATTEMPT, "structure-summary phase differs")
    for field in ("public_rows_observed", "restricted_rows_observed"):
        require(type(value[field]) is int and value[field] >= 0, f"{field} is invalid")
    if value["status"] == "COMPLETE":
        for field in _SUMMARY_METRICS:
            require(type(value[field]) is int and value[field] >= 0, f"complete {field} is invalid")
        require(value["logical_member_count"] > 0, "complete summary has no members")
        require(
            value["regular_member_count"] + value["directory_member_count"]
            == value["logical_member_count"],
            "summary type counts differ",
        )
        require(
            value["public_rows_observed"]
            == value["restricted_rows_observed"]
            == value["logical_member_count"],
            "complete inventory row counts differ",
        )
        return
    require(value["status"] == "INCONCLUSIVE", "structure-summary status differs")
    require(all(value[field] is None for field in _SUMMARY_METRICS), "inconclusive summary contains numeric pseudo-observation")


def _iter_bounded_segments(path: Path, *, max_bytes: int, max_line_bytes: int):
    """Yield ``(bytes, complete_line)`` without rewriting a terminal fragment."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "streamed text artifact")
        require(before.st_size <= max_bytes, "streamed text artifact exceeds cap")
        buffer = bytearray()
        total = 0
        while True:
            block = os.read(descriptor, MIB - len(buffer))
            if not block:
                break
            total += len(block)
            require(total <= max_bytes, "streamed text artifact exceeds cap")
            buffer.extend(block)
            while True:
                newline = buffer.find(b"\n")
                if newline < 0:
                    break
                require(newline + 1 <= max_line_bytes, "streamed text line exceeds cap")
                yield bytes(buffer[: newline + 1]), True
                del buffer[: newline + 1]
            require(len(buffer) <= max_line_bytes, "streamed text line exceeds cap")
        if buffer:
            yield bytes(buffer), False
        after = os.fstat(descriptor)
        _require_open_path_identity(descriptor, path, "streamed text artifact")
        require(
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "streamed text artifact changed while validating",
        )
    finally:
        os.close(descriptor)


def _decimal_token(value: bytes, label: str) -> int:
    require(value and all(byte in b"0123456789" for byte in value), f"{label} is not decimal")
    require(value == b"0" or not value.startswith(b"0"), f"{label} has leading zero")
    return int(value)


def _validate_flag_bytes(value: bytes) -> tuple[str, ...]:
    if value == b"":
        return ()
    flags = value.split(b"|")
    parsed = []
    for flag in flags:
        text = flag.decode("ascii", errors="strict")
        require(
            text in {"PATH_OVERRIDE", "SIZE_OVERRIDE"}
            or re.fullmatch(r"(?:GLOBAL|EXTENDED)_KEY_SHA256:[0-9A-F]{64}", text)
            is not None,
            "public PAX flag grammar differs",
        )
        parsed.append(text)
    require(len(parsed) == len(set(parsed)), "duplicate public PAX flag")
    expected = []
    if "PATH_OVERRIDE" in parsed:
        expected.append("PATH_OVERRIDE")
    if "SIZE_OVERRIDE" in parsed:
        expected.append("SIZE_OVERRIDE")
    expected.extend(sorted(flag for flag in parsed if flag.startswith("GLOBAL_KEY_SHA256:")))
    expected.extend(sorted(flag for flag in parsed if flag.startswith("EXTENDED_KEY_SHA256:")))
    require(parsed == expected, "public PAX flag order differs from parser output")
    return tuple(parsed)


@dataclass(frozen=True)
class _PublicRow:
    ordinal: int
    raw_hash: str
    resolved_hash: str
    member_type: str
    size: int
    flags: tuple[str, ...]


@dataclass(frozen=True)
class InventoryObservation:
    public_complete_rows: int
    restricted_complete_rows: int
    paired_rows: int
    regular_member_count: int
    directory_member_count: int
    total_regular_payload_bytes: int
    public_terminal_fragment_bytes: int
    restricted_terminal_fragment_bytes: int


def _parse_public_row(value: bytes, expected_ordinal: int) -> _PublicRow:
    require(value.endswith(b"\n"), "public row is incomplete")
    fields = value[:-1].split(b",")
    require(len(fields) == 6, "public inventory field count differs")
    ordinal = _decimal_token(fields[0], "public ordinal")
    require(ordinal == expected_ordinal, "public ordinal is not contiguous")
    for field, label in ((fields[1], "raw hash"), (fields[2], "resolved hash")):
        require(
            re.fullmatch(rb"[0-9A-F]{64}", field) is not None,
            f"public {label} differs",
        )
    require(fields[3] in {b"REGULAR", b"DIRECTORY"}, "public member type differs")
    size = _decimal_token(fields[4], "public size")
    flags = _validate_flag_bytes(fields[5])
    from .round11_layout_inventory import DEFAULT_LIMITS

    require(expected_ordinal <= DEFAULT_LIMITS.max_logical_members, "logical-member cap exceeded")
    if fields[3] == b"DIRECTORY":
        require(size == 0, "public directory size differs")
    else:
        require(
            size <= DEFAULT_LIMITS.max_single_regular_member_bytes,
            "regular-member size cap exceeded",
        )
    return _PublicRow(
        ordinal,
        fields[1].decode("ascii"),
        fields[2].decode("ascii"),
        fields[3].decode("ascii"),
        size,
        flags,
    )


def _validate_restricted_row(value: bytes, public: _PublicRow) -> tuple[bytes, bytes]:
    parsed = strict_canonical_json(value, "restricted path row")
    require(
        set(parsed)
        == {
            "member_ordinal",
            "member_type",
            "pax_flags",
            "pax_path",
            "raw_header_path",
            "raw_path_sha256",
            "resolved_path",
            "resolved_path_sha256",
            "size",
        },
        "restricted row field set differs",
    )
    require(
        type(parsed["member_ordinal"]) is int
        and type(parsed["size"]) is int
        and parsed["member_ordinal"] > 0
        and parsed["size"] >= 0,
        "restricted numeric field type differs",
    )
    require(
        parsed["member_ordinal"] == public.ordinal
        and parsed["raw_path_sha256"] == public.raw_hash
        and parsed["resolved_path_sha256"] == public.resolved_hash
        and parsed["member_type"] == public.member_type
        and parsed["size"] == public.size
        and parsed["pax_flags"] == list(public.flags),
        "public/restricted row relation differs",
    )
    for name in ("raw_header_path", "resolved_path"):
        require(isinstance(parsed[name], str) and parsed[name] != "", f"restricted {name} differs")
    require(
        parsed["pax_path"] is None
        or (isinstance(parsed["pax_path"], str) and parsed["pax_path"] != ""),
        "restricted PAX path differs",
    )
    from .round11_layout_inventory import DEFAULT_LIMITS, _canonical_path

    _canonical_path(parsed["raw_header_path"], DEFAULT_LIMITS, "restricted raw path")
    _canonical_path(parsed["resolved_path"], DEFAULT_LIMITS, "restricted resolved path")
    if parsed["pax_path"] is not None:
        _canonical_path(parsed["pax_path"], DEFAULT_LIMITS, "restricted PAX path")
    require(
        sha256_bytes(parsed["raw_header_path"].encode("utf-8"))
        == parsed["raw_path_sha256"],
        "restricted raw path/hash relation differs",
    )
    require(
        sha256_bytes(parsed["resolved_path"].encode("utf-8"))
        == parsed["resolved_path_sha256"],
        "restricted resolved path/hash relation differs",
    )
    require(
        parsed["resolved_path"] == (parsed["pax_path"] or parsed["raw_header_path"]),
        "restricted raw/PAX/resolved path relation differs",
    )
    require(
        ("PATH_OVERRIDE" in public.flags) is (parsed["pax_path"] is not None),
        "restricted PAX path flag relation differs",
    )
    resolved_digest = bytes.fromhex(public.resolved_hash)
    folded = unicodedata.normalize("NFC", parsed["resolved_path"].casefold())
    folded_digest = hashlib.sha256(folded.encode("utf-8")).digest()
    return resolved_digest, folded_digest


def validate_inventory_pair(
    public_path: Path,
    restricted_path: Path,
    *,
    public_status: str,
    restricted_status: str,
) -> InventoryObservation:
    require(public_status == restricted_status, "public/restricted status differs")
    public_segments = _iter_bounded_segments(
        public_path,
        max_bytes=ARTIFACT_CAPS[PUBLIC_NAME],
        max_line_bytes=16_384,
    )
    require(next(public_segments, None) == (PUBLIC_HEADER, True), "public inventory header differs")
    restricted_segments = _iter_bounded_segments(
        restricted_path,
        max_bytes=ARTIFACT_CAPS[RESTRICTED_NAME],
        max_line_bytes=131_072,
    )
    public_rows = 0
    restricted_rows = 0
    paired_rows = 0
    regular_count = 0
    directory_count = 0
    total_regular_bytes = 0
    public_tail = 0
    restricted_tail = 0
    resolved_digests: set[bytes] = set()
    folded_to_resolved: dict[bytes, bytes] = {}
    while True:
        public_segment = next(public_segments, None)
        restricted_segment = next(restricted_segments, None)
        if public_segment is None and restricted_segment is None:
            break
        if public_segment is not None and not public_segment[1]:
            require(public_tail == 0, "multiple public terminal fragments")
            public_tail = len(public_segment[0])
            require(
                all(byte in b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ,_:|" for byte in public_segment[0]),
                "public terminal fragment grammar differs",
            )
            require(restricted_segment is None, "restricted data follows public terminal fragment")
            require(next(public_segments, None) is None, "public data follows terminal fragment")
            break
        require(public_segment is not None, "restricted inventory leads public inventory")
        public_row = _parse_public_row(public_segment[0], public_rows + 1)
        public_rows += 1
        if restricted_segment is None:
            require(next(public_segments, None) is None, "public inventory leads by more than one row")
            break
        if not restricted_segment[1]:
            restricted_tail = len(restricted_segment[0])
            require(next(restricted_segments, None) is None, "restricted data follows terminal fragment")
            require(next(public_segments, None) is None, "public inventory leads by more than one row")
            break
        restricted_rows += 1
        resolved_digest, folded_digest = _validate_restricted_row(
            restricted_segment[0], public_row
        )
        require(resolved_digest not in resolved_digests, "duplicate resolved path")
        previous = folded_to_resolved.get(folded_digest)
        require(
            previous is None or previous == resolved_digest,
            "casefold Unicode path collision",
        )
        from .round11_layout_inventory import DEFAULT_LIMITS

        require(
            len(resolved_digests) + len(folded_to_resolved) + 2
            <= DEFAULT_LIMITS.max_collision_digest_entries,
            "collision-digest entry cap exceeded",
        )
        resolved_digests.add(resolved_digest)
        folded_to_resolved[folded_digest] = resolved_digest
        paired_rows += 1
        if public_row.member_type == "REGULAR":
            regular_count += 1
            total_regular_bytes += public_row.size
        else:
            directory_count += 1
        require(
            total_regular_bytes <= DEFAULT_LIMITS.max_uncompressed_tar_stream_bytes,
            "regular payload total exceeds tar-stream cap",
        )
    require(public_rows - restricted_rows in {0, 1}, "public/restricted row count differs")
    require(restricted_tail == 0 or public_rows == restricted_rows + 1, "restricted tail/write-order relation differs")
    require(public_tail == 0 or public_rows == restricted_rows, "public tail/write-order relation differs")
    require(not (public_tail and restricted_tail), "both inventory files have terminal fragments")
    observation = InventoryObservation(
        public_rows,
        restricted_rows,
        paired_rows,
        regular_count,
        directory_count,
        total_regular_bytes,
        public_tail,
        restricted_tail,
    )
    if public_status == "ABSENT_REPRESENTED_EMPTY":
        require(observation == InventoryObservation(0, 0, 0, 0, 0, 0, 0, 0), "absent inventory representation contains observations")
        public_digest = digest_regular_stable(public_path, max_bytes=len(PUBLIC_HEADER))
        restricted_digest = digest_regular_stable(restricted_path, max_bytes=0)
        require(
            public_digest == FileDigest(len(PUBLIC_HEADER), sha256_bytes(PUBLIC_HEADER))
            and restricted_digest == FileDigest(0, sha256_bytes(b"")),
            "absent inventory representation differs",
        )
    elif public_status == "OBSERVED_COMPLETE":
        require(
            public_tail == restricted_tail == 0
            and public_rows == restricted_rows == paired_rows,
            "complete inventory contains partial write residue",
        )
    else:
        require(public_status == "OBSERVED_PARTIAL", "inventory status differs")
    return observation


def validate_closure_semantics(
    directory: Path, expectations: ClosureExpectations
) -> None:
    validate_expectations(expectations)
    results = strict_canonical_json(
        read_small_regular_stable(directory / RESULTS_NAME, max_bytes=ARTIFACT_CAPS[RESULTS_NAME]),
        "layout results",
    )
    validate_results(results)
    archive_hashes = strict_canonical_json(
        read_small_regular_stable(directory / ARTIFACTS[5], max_bytes=ARTIFACT_CAPS[ARTIFACTS[5]]),
        "archive hashes",
    )
    validate_archive_hashes(archive_hashes, expectations.archive)
    require(
        results["observed_scope"] == archive_hashes["observed_scope"],
        "results/archive observed scope differs",
    )
    summary = strict_canonical_json(
        read_small_regular_stable(directory / ARTIFACTS[6], max_bytes=ARTIFACT_CAPS[ARTIFACTS[6]]),
        "structure summary",
    )
    validate_summary(summary)
    statuses = results["artifact_status"]
    for authority in expectations.authorities:
        observed = digest_regular_stable(
            directory / authority.name, max_bytes=ARTIFACT_CAPS[authority.name]
        )
        status = statuses[authority.name]
        expected_digest = FileDigest(authority.bytes, authority.sha256)
        if status == "OBSERVED_COMPLETE":
            require(observed == expected_digest, f"authority differs: {authority.name}")
        elif status == "ABSENT_REPRESENTED_EMPTY":
            require(not authority.required_complete, f"required authority is absent: {authority.name}")
            require(observed == FileDigest(0, sha256_bytes(b"")), f"absent authority representation differs: {authority.name}")
        else:
            require(not authority.required_complete, f"required authority is partial: {authority.name}")
            require(observed.bytes > 0, f"partial authority is empty: {authority.name}")
            require(observed != expected_digest, f"partial authority exactly matches expected: {authority.name}")
    inventory = validate_inventory_pair(
        directory / PUBLIC_NAME,
        directory / RESTRICTED_NAME,
        public_status=statuses[PUBLIC_NAME],
        restricted_status=statuses[RESTRICTED_NAME],
    )
    require(
        summary["public_rows_observed"] == inventory.public_complete_rows
        and summary["restricted_rows_observed"]
        == inventory.restricted_complete_rows,
        "summary inventory row count differs",
    )
    if results["outcome"] == COMPLETE_OUTCOME:
        from .round11_layout_inventory import DEFAULT_LIMITS

        require(archive_hashes["observed_scope"] == "COMPLETE_STREAM", "complete result lacks complete stream")
        require(archive_hashes["complete_stream_matches_expected"] is True, "complete result archive mismatch")
        require(summary["status"] == "COMPLETE", "complete result summary is not complete")
        require(statuses[PUBLIC_NAME] == statuses[RESTRICTED_NAME] == "OBSERVED_COMPLETE", "complete result inventory status differs")
        require(
            summary["logical_member_count"] == inventory.paired_rows
            and summary["regular_member_count"] == inventory.regular_member_count
            and summary["directory_member_count"] == inventory.directory_member_count
            and summary["total_regular_payload_bytes"]
            == inventory.total_regular_payload_bytes,
            "complete summary/inventory aggregate differs",
        )
        require(
            summary["logical_member_count"] <= DEFAULT_LIMITS.max_logical_members
            and summary["raw_header_count"] <= DEFAULT_LIMITS.max_raw_headers
            and summary["raw_header_count"] >= summary["logical_member_count"],
            "complete header/member resource relation differs",
        )
        require(
            summary["uncompressed_tar_stream_bytes"]
            <= DEFAULT_LIMITS.max_uncompressed_tar_stream_bytes
            and summary["post_end_zero_padding_bytes"]
            <= DEFAULT_LIMITS.max_post_end_zero_padding_bytes,
            "complete tar-stream resource cap exceeded",
        )
        require(
            summary["total_regular_payload_bytes"]
            <= summary["uncompressed_tar_stream_bytes"],
            "regular payload total exceeds observed tar stream",
        )
        structural_tar_bytes = (
            summary["uncompressed_tar_stream_bytes"]
            - summary["post_end_zero_padding_bytes"]
        )
        require(
            structural_tar_bytes % 512 == 0
            and structural_tar_bytes
            >= summary["raw_header_count"] * 512
            + summary["total_regular_payload_bytes"]
            + 1024,
            "complete tar-stream structural byte relation differs",
        )
    else:
        require(summary["status"] == "INCONCLUSIVE", "STOP summary must be inconclusive")


def _index_bytes(rows: list[dict[str, Any]]) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": INDEX_SCHEMA,
            "artifact_count": len(rows),
            "artifact_index_self_excluded": True,
            "artifacts": rows,
        }
    )


def build_streaming_index(directory: Path, lease: AttemptLease) -> bytes:
    lease.verify_staging()
    require(directory == lease.staging_path, "index directory lease differs")
    require(directory.is_dir() and not directory.is_symlink(), "index directory is invalid")
    require(
        {item.name for item in directory.iterdir()} == set(PAYLOAD_NAMES),
        "pre-index artifact allowlist differs",
    )
    rows = []
    for name in sorted(PAYLOAD_NAMES):
        lease.verify_staging()
        observed = digest_regular_stable(
            directory / name, max_bytes=ARTIFACT_CAPS[name]
        )
        rows.append({"path": name, "bytes": observed.bytes, "sha256": observed.sha256})
    lease.verify_staging()
    require(
        {item.name for item in directory.iterdir()} == set(PAYLOAD_NAMES),
        "post-hash pre-index artifact allowlist differs",
    )
    value = _index_bytes(rows)
    require(len(value) <= ARTIFACT_CAPS[INDEX_NAME], "artifact index exceeds byte cap")
    return value


def _write_owned_file(
    path: Path,
    payload: bytes,
    *,
    max_bytes: int,
    file_fsync: Callable[[int], None] = os.fsync,
) -> None:
    require(len(payload) <= max_bytes, "owned payload exceeds byte cap")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"owned artifact already exists: {path}")
    with path.open("xb", buffering=0) as stream:
        _require_open_path_identity(stream.fileno(), path, "owned artifact")
        _write_all(stream, payload, "owned artifact")
        file_fsync(stream.fileno())
        _require_open_path_identity(stream.fileno(), path, "owned artifact")


def verify_layout_closure(
    directory: Path,
    lease: AttemptLease,
    expectations: ClosureExpectations,
) -> bool:
    if not directory.is_dir() or directory.is_symlink():
        return False
    try:
        if directory == lease.staging_path:
            lease.verify_staging()
        elif directory == lease.final_path:
            lease.verify_final()
        else:
            return False
        entries = list(directory.iterdir())
        if {item.name for item in entries} != set(ARTIFACTS):
            return False
        for item in entries:
            metadata = item.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or item.is_symlink()
                or metadata.st_nlink != 1
            ):
                return False
        results_bytes = read_small_regular_stable(
            directory / RESULTS_NAME, max_bytes=ARTIFACT_CAPS[RESULTS_NAME]
        )
        validate_results(strict_canonical_json(results_bytes, "layout results"))
        validate_closure_semantics(directory, expectations)
        index_bytes = read_small_regular_stable(
            directory / INDEX_NAME, max_bytes=ARTIFACT_CAPS[INDEX_NAME]
        )
        index = strict_canonical_json(index_bytes, "layout artifact index")
        expected_index = build_streaming_index_without_listing(directory, lease)
        if index_bytes != expected_index:
            return False
        if (
            set(index)
            != {"schema_version", "artifact_count", "artifact_index_self_excluded", "artifacts"}
            or index.get("schema_version") != INDEX_SCHEMA
            or index.get("artifact_count") != len(PAYLOAD_NAMES)
            or index.get("artifact_index_self_excluded") is not True
        ):
            return False
        if directory == lease.staging_path:
            lease.verify_staging()
        else:
            lease.verify_final()
        if {item.name for item in directory.iterdir()} != set(ARTIFACTS):
            return False
        return True
    except (OSError, LayoutControlError, TypeError, ValueError, UnicodeError):
        return False


def build_streaming_index_without_listing(
    directory: Path, lease: AttemptLease
) -> bytes:
    rows = []
    for name in sorted(PAYLOAD_NAMES):
        if directory == lease.staging_path:
            lease.verify_staging()
        else:
            lease.verify_final()
        observed = digest_regular_stable(
            directory / name, max_bytes=ARTIFACT_CAPS[name]
        )
        rows.append({"path": name, "bytes": observed.bytes, "sha256": observed.sha256})
    return _index_bytes(rows)


def rename_directory_no_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        os.rename(source, target)
        return
    if os.name == "posix" and hasattr(os, "uname") and os.uname().sysname == "Linux":
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOSYS, "renameat2 unavailable; refusing fallback")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), target)
        return
    raise OSError(errno.ENOSYS, "no atomic no-replace directory rename")


def create_exclusive_staging(
    lease: AttemptLease,
    staging: Path,
    final: Path,
    *,
    directory_fsync: Callable[[Path], None] = sync_directory_strict,
) -> None:
    """Create the owned staging directory after claim durability only."""

    require(type(lease) is AttemptLease, "attempt lease type differs")
    lease.verify_claim()
    require(staging.is_absolute() and final.is_absolute(), "staging/final paths must be absolute")
    require(staging.parent == final.parent, "staging/final parents differ")
    require(staging.parent == lease.parent.path, "staging parent lease differs")
    require(
        os.path.normcase(os.path.abspath(staging))
        != os.path.normcase(os.path.abspath(final)),
        "staging/final alias",
    )
    require(staging.parent.is_dir() and not staging.parent.is_symlink(), "staging parent is invalid")
    if staging.exists() or staging.is_symlink():
        raise FileExistsError(f"layout staging already exists: {staging}")
    if final.exists() or final.is_symlink():
        raise FileExistsError(f"layout final already exists: {final}")
    staging.mkdir(mode=0o700, exist_ok=False)
    directory_fsync(staging.parent)
    lease.verify_claim()
    require(staging.is_dir() and not staging.is_symlink(), "created staging is invalid")
    lease.bind_staging(staging, final)
    lease.verify_staging()


def finalize_and_publish(
    lease: AttemptLease,
    staging: Path,
    final: Path,
    *,
    expectations: ClosureExpectations,
    rename_func: Callable[[Path, Path], None] = rename_directory_no_replace,
    file_fsync: Callable[[int], None] = os.fsync,
    directory_fsync: Callable[[Path], None] = sync_directory_strict,
) -> None:
    """Index, sync, publish and stream-rehash an already complete staging dir."""

    require(type(lease) is AttemptLease, "attempt lease type differs")
    lease.verify_staging()
    require(staging == lease.staging_path and final == lease.final_path, "publication lease paths differ")
    require(staging.is_absolute() and final.is_absolute(), "publication paths must be absolute")
    require(staging.parent == final.parent, "staging/final parents differ")
    require(staging.is_dir() and not staging.is_symlink(), "staging directory is invalid")
    if final.exists() or final.is_symlink():
        raise FileExistsError(f"layout final already exists: {final}")
    require(not (staging / INDEX_NAME).exists(), "artifact index already exists")
    require(
        {item.name for item in staging.iterdir()} == set(PAYLOAD_NAMES),
        "pre-finalization artifact allowlist differs",
    )
    lease.verify_staging()
    results = strict_canonical_json(
        read_small_regular_stable(
            staging / RESULTS_NAME, max_bytes=ARTIFACT_CAPS[RESULTS_NAME]
        ),
        "layout results",
    )
    validate_results(results)
    validate_closure_semantics(staging, expectations)
    index = build_streaming_index(staging, lease)
    _write_owned_file(
        staging / INDEX_NAME,
        index,
        max_bytes=ARTIFACT_CAPS[INDEX_NAME],
        file_fsync=file_fsync,
    )
    directory_fsync(staging)
    lease.verify_staging()
    require(
        verify_layout_closure(staging, lease, expectations),
        "pre-publish layout closure verification failed",
    )
    lease.release_staging_for_rename()
    rename_func(staging, final)
    lease.bind_final_after_rename()
    directory_fsync(final.parent)
    lease.verify_final()
    require(
        verify_layout_closure(final, lease, expectations),
        "post-publish layout closure verification failed",
    )
