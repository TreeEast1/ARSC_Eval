"""Fail-closed, streaming gzip/tar/PAX layout reader for Round 11 DAAD-X.

This module deliberately exposes archive *structure* only.  Regular member
payloads are decompressed because gzip integrity cannot otherwise be checked,
but are drained in bounded buffers and are never parsed, retained, sampled,
hashed, logged, or returned.  The formal archive is not named or opened here;
the caller must provide an already-open binary stream and exact transport
expectations.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import time
import unicodedata
import zlib
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO


class LayoutInventoryError(RuntimeError):
    """A frozen layout-inventory invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LayoutInventoryError(message)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


@dataclass(frozen=True)
class ResourceLimits:
    """Frozen resource ceilings; formal callers must not raise them."""

    max_uncompressed_tar_stream_bytes: int = 137_438_953_472
    max_raw_headers: int = 200_000
    max_logical_members: int = 200_000
    max_single_regular_member_bytes: int = 17_179_869_184
    max_single_pax_payload_bytes: int = 1_048_576
    max_cumulative_pax_payload_bytes: int = 67_108_864
    max_path_utf8_bytes: int = 4_096
    max_post_end_zero_padding_bytes: int = 16_777_216
    regular_payload_drain_buffer_bytes: int = 1_048_576
    max_compressed_input_buffer_bytes: int = 1_048_576
    max_decompressed_output_buffer_bytes: int = 1_048_576
    max_collision_digest_entries: int = 400_000
    max_elapsed_seconds: int = 21_600
    max_in_memory_bytes: int = 268_435_456
    max_public_inventory_output_bytes: int = 67_108_864
    max_restricted_path_seal_output_bytes: int = 2_147_483_648
    max_structure_summary_output_bytes: int = 16_777_216
    max_execution_log_output_bytes: int = 16_777_216

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ResourceLimits is sealed and cannot be subclassed")

    def validate(self) -> None:
        require(type(self) is ResourceLimits, "resource-limit type differs")
        for name, value in vars(self).items():
            require(isinstance(value, int) and value > 0, f"invalid resource limit: {name}")
            require(
                value <= _FROZEN_LIMIT_MAXIMA[name],
                f"resource limit exceeds frozen maximum: {name}",
            )
        require(
            self.regular_payload_drain_buffer_bytes
            <= self.max_decompressed_output_buffer_bytes,
            "drain buffer exceeds decompressed-output buffer",
        )
        require(
            self.max_logical_members * 2 <= self.max_collision_digest_entries,
            "collision-digest cap cannot cover the logical-member cap",
        )
        # The implementation retains at most two fixed 32-byte digests per
        # logical member.  This deliberately conservative accounting includes
        # Python container overhead and the bounded I/O/PAX/header workspace.
        estimated = (
            self.max_collision_digest_entries * 256
            + self.max_compressed_input_buffer_bytes * 2
            + self.max_decompressed_output_buffer_bytes * 3
            + self.max_single_pax_payload_bytes * 2
            + self.max_path_utf8_bytes * 8
            + 1_048_576
        )
        require(estimated <= self.max_in_memory_bytes, "estimated parser memory exceeds cap")


DEFAULT_LIMITS = ResourceLimits()
_FROZEN_LIMIT_MAXIMA = dict(vars(DEFAULT_LIMITS))


@dataclass(frozen=True)
class MemberRecord:
    """One logical member; raw paths are restricted-output material."""

    member_ordinal: int
    raw_header_path: str
    pax_path: str | None
    resolved_path: str
    raw_path_sha256: str
    resolved_path_sha256: str
    member_type: str
    size: int
    pax_flags: tuple[str, ...]


@dataclass(frozen=True)
class LayoutSummary:
    compressed_bytes: int
    compressed_sha256: str
    uncompressed_tar_stream_bytes: int
    raw_header_count: int
    logical_member_count: int
    regular_member_count: int
    directory_member_count: int
    total_regular_payload_bytes: int
    post_end_zero_padding_bytes: int
    type_counts: Mapping[str, int]
    depth_counts: Mapping[int, int]


def _canonical_json_bytes(value: object) -> bytes:
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


class OwnedStagingSink:
    """Concrete bounded sink; it never accumulates member paths or rows."""

    __slots__ = (
        "_limits",
        "_public_path",
        "_restricted_path",
        "_public",
        "_restricted",
        "_public_bytes",
        "_restricted_bytes",
        "_records_written",
        "_closed",
        "_sealed",
    )

    PUBLIC_NAME = "round11_daadx_layout_public_inventory.csv"
    RESTRICTED_NAME = "round11_daadx_layout_restricted_path_seal.jsonl"
    PUBLIC_HEADER = (
        b"member_ordinal,raw_path_sha256,resolved_path_sha256,member_type,size,pax_flags\n"
    )

    def __init__(
        self,
        public_path: os.PathLike[str] | str,
        restricted_path: os.PathLike[str] | str,
        *,
        limits: ResourceLimits = DEFAULT_LIMITS,
    ) -> None:
        from pathlib import Path

        require(type(limits) is ResourceLimits, "resource-limit type differs")
        ResourceLimits.validate(limits)
        self._limits = limits
        self._public_path = Path(public_path)
        self._restricted_path = Path(restricted_path)
        require(
            self._public_path.is_absolute() and self._restricted_path.is_absolute(),
            "sink paths must be absolute",
        )
        require(
            self._public_path.parent == self._restricted_path.parent,
            "sink output parents differ",
        )
        require(
            self._public_path.name == self.PUBLIC_NAME
            and self._restricted_path.name == self.RESTRICTED_NAME,
            "sink output names differ from frozen artifacts",
        )
        parent = self._public_path.parent
        require(parent.is_dir() and not parent.is_symlink(), "sink parent is invalid")
        for path in (self._public_path, self._restricted_path):
            if path.exists() or path.is_symlink():
                raise FileExistsError(f"owned staging output already exists: {path}")
        self._public = self._public_path.open("xb", buffering=0)
        try:
            self._restricted = self._restricted_path.open("xb", buffering=0)
        except BaseException:
            self._public.close()
            raise
        self._public_bytes = 0
        self._restricted_bytes = 0
        self._records_written = 0
        self._closed = False
        try:
            self._require_owned_regular(
                self._public.fileno(), self._public_path, "public inventory"
            )
            self._require_owned_regular(
                self._restricted.fileno(), self._restricted_path, "restricted path seal"
            )
            self._write_public(self.PUBLIC_HEADER)
            object.__setattr__(self, "_sealed", True)
        except BaseException:
            self._public.close()
            self._restricted.close()
            self._closed = True
            raise

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("OwnedStagingSink is sealed")
        object.__setattr__(self, name, value)

    @staticmethod
    def _require_owned_regular(descriptor: int, path: object, label: str) -> None:
        opened = os.fstat(descriptor)
        current = os.lstat(path)
        require(stat.S_ISREG(opened.st_mode), f"{label} handle is not regular")
        require(stat.S_ISREG(current.st_mode), f"{label} path is not regular")
        require(
            (opened.st_dev, opened.st_ino, opened.st_nlink)
            == (current.st_dev, current.st_ino, current.st_nlink),
            f"{label} path identity changed",
        )
        require(opened.st_nlink == 1, f"{label} must not be hard-linked")

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    @property
    def records_written(self) -> int:
        return self._records_written

    @property
    def closed(self) -> bool:
        return self._closed

    def _write_public(self, value: bytes) -> None:
        require(not self._closed, "sink is closed")
        next_size = self._public_bytes + len(value)
        require(
            next_size <= self._limits.max_public_inventory_output_bytes,
            "public inventory output cap exceeded",
        )
        self._write_all(self._public, value, "public inventory")
        object.__setattr__(self, "_public_bytes", next_size)

    def _write_restricted(self, value: bytes) -> None:
        require(not self._closed, "sink is closed")
        next_size = self._restricted_bytes + len(value)
        require(
            next_size <= self._limits.max_restricted_path_seal_output_bytes,
            "restricted path-seal output cap exceeded",
        )
        self._write_all(self._restricted, value, "restricted path seal")
        object.__setattr__(self, "_restricted_bytes", next_size)

    @staticmethod
    def _write_all(stream: BinaryIO, value: bytes, label: str) -> None:
        view = memoryview(value)
        offset = 0
        while offset < len(view):
            written = stream.write(view[offset:])
            require(
                isinstance(written, int) and written > 0,
                f"short or invalid write: {label}",
            )
            offset += written

    def _emit(self, record: MemberRecord) -> None:
        require(type(record) is MemberRecord, "sink record type differs")
        self._require_owned_regular(
            self._public.fileno(), self._public_path, "public inventory"
        )
        self._require_owned_regular(
            self._restricted.fileno(), self._restricted_path, "restricted path seal"
        )
        flags = "|".join(record.pax_flags)
        require(
            all(c not in flags for c in ",\r\n"),
            "public PAX flags are not CSV-safe",
        )
        public = (
            f"{record.member_ordinal},{record.raw_path_sha256},"
            f"{record.resolved_path_sha256},{record.member_type},"
            f"{record.size},{flags}\n"
        ).encode("ascii")
        restricted = _canonical_json_bytes(
            {
                "member_ordinal": record.member_ordinal,
                "member_type": record.member_type,
                "pax_flags": list(record.pax_flags),
                "pax_path": record.pax_path,
                "raw_header_path": record.raw_header_path,
                "raw_path_sha256": record.raw_path_sha256,
                "resolved_path": record.resolved_path,
                "resolved_path_sha256": record.resolved_path_sha256,
                "size": record.size,
            }
        )
        # Check both sizes before either row is written, preventing unequal
        # record counts on a deterministic cap failure.
        require(
            self._public_bytes + len(public)
            <= self._limits.max_public_inventory_output_bytes,
            "public inventory output cap exceeded",
        )
        require(
            self._restricted_bytes + len(restricted)
            <= self._limits.max_restricted_path_seal_output_bytes,
            "restricted path-seal output cap exceeded",
        )
        self._write_public(public)
        self._write_restricted(restricted)
        self._require_owned_regular(
            self._public.fileno(), self._public_path, "public inventory"
        )
        self._require_owned_regular(
            self._restricted.fileno(), self._restricted_path, "restricted path seal"
        )
        object.__setattr__(self, "_records_written", self._records_written + 1)

    def close(self) -> None:
        if self._closed:
            return
        error: BaseException | None = None
        for stream, path, label in (
            (self._public, self._public_path, "public inventory"),
            (self._restricted, self._restricted_path, "restricted path seal"),
        ):
            try:
                self._require_owned_regular(stream.fileno(), path, label)
                stream.flush()
                os.fsync(stream.fileno())
                self._require_owned_regular(stream.fileno(), path, label)
            except BaseException as caught:
                if error is None:
                    error = caught
            finally:
                stream.close()
        object.__setattr__(self, "_closed", True)
        if error is not None:
            raise error


class _HashedInput:
    def __init__(self, source: BinaryIO, *, max_read: int) -> None:
        self._source = source
        self._max_read = max_read
        self.count = 0
        self._digest = hashlib.sha256()

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest().upper()

    def read(self, size: int) -> bytes:
        require(0 < size <= self._max_read, "compressed read exceeds buffer cap")
        value = self._source.read(size)
        require(isinstance(value, bytes), "compressed source did not return bytes")
        require(len(value) <= size, "compressed source over-returned bytes")
        self.count += len(value)
        self._digest.update(value)
        return value

    def exact(self, size: int, label: str) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            block = self.read(min(remaining, self._max_read))
            require(block != b"", f"truncated {label}")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)

class _GzipReader:
    """Single-member gzip reader with an explicit raw-deflate state machine."""

    def __init__(
        self,
        source: BinaryIO,
        *,
        limits: ResourceLimits,
        expected_compressed_bytes: int,
        expected_compressed_sha256: str,
    ) -> None:
        require(
            isinstance(expected_compressed_bytes, int) and expected_compressed_bytes > 0,
            "expected compressed byte count is required",
        )
        require(
            isinstance(expected_compressed_sha256, str)
            and len(expected_compressed_sha256) == 64
            and all(c in "0123456789abcdefABCDEF" for c in expected_compressed_sha256),
            "expected compressed SHA256 is invalid",
        )
        self._limits = limits
        self._input = _HashedInput(
            source, max_read=limits.max_compressed_input_buffer_bytes
        )
        self._expected_bytes = expected_compressed_bytes
        self._expected_sha = expected_compressed_sha256.upper()
        self._inflater = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
        self._pending_compressed = b""
        self._output = b""
        self._finished = False
        self._crc32 = 0
        self._isize = 0
        self.uncompressed_count = 0
        self._read_header()

    @property
    def compressed_count(self) -> int:
        return self._input.count

    @property
    def compressed_sha256(self) -> str:
        return self._input.sha256

    def _header_piece(self, size: int, header: bytearray, label: str) -> bytes:
        value = self._input.exact(size, label)
        header.extend(value)
        require(
            len(header) <= self._limits.max_compressed_input_buffer_bytes,
            "gzip header exceeds compressed-input buffer cap",
        )
        return value

    def _zero_terminated(self, header: bytearray, label: str) -> None:
        while True:
            byte = self._header_piece(1, header, label)
            if byte == b"\x00":
                return

    def _read_header(self) -> None:
        header = bytearray()
        fixed = self._header_piece(10, header, "gzip header")
        require(fixed[:2] == b"\x1f\x8b", "gzip magic differs")
        require(fixed[2] == 8, "gzip compression method is not deflate")
        flags = fixed[3]
        require(flags & 0xE0 == 0, "gzip reserved flags are set")
        if flags & 0x04:  # FEXTRA
            xlen_raw = self._header_piece(2, header, "gzip XLEN")
            xlen = struct.unpack("<H", xlen_raw)[0]
            self._header_piece(xlen, header, "gzip extra field")
        if flags & 0x08:  # FNAME
            self._zero_terminated(header, "gzip filename")
        if flags & 0x10:  # FCOMMENT
            self._zero_terminated(header, "gzip comment")
        if flags & 0x02:  # FHCRC, low 16 bits of CRC32 over preceding header bytes.
            stored = struct.unpack("<H", self._input.exact(2, "gzip FHCRC"))[0]
            require(stored == (zlib.crc32(header) & 0xFFFF), "gzip FHCRC differs")

    def _record_output(self, value: bytes) -> None:
        require(
            len(value) <= self._limits.max_decompressed_output_buffer_bytes,
            "decompressed output buffer cap exceeded",
        )
        self.uncompressed_count += len(value)
        require(
            self.uncompressed_count <= self._limits.max_uncompressed_tar_stream_bytes,
            "uncompressed tar-stream cap exceeded",
        )
        self._crc32 = zlib.crc32(value, self._crc32)
        self._isize = (self._isize + len(value)) & 0xFFFFFFFF

    def _finish_member(self, initial_tail: bytes) -> None:
        tail = initial_tail
        while len(tail) < 8:
            block = self._input.read(
                min(
                    8 - len(tail),
                    self._limits.max_compressed_input_buffer_bytes,
                )
            )
            require(block != b"", "truncated gzip trailer")
            tail += block
        stored_crc, stored_isize = struct.unpack("<II", tail[:8])
        require(stored_crc == self._crc32, "gzip CRC32 differs")
        require(stored_isize == self._isize, "gzip ISIZE differs")
        require(tail[8:] == b"", "concatenated member or trailing gzip bytes")
        require(
            self._input.read(1) == b"",
            "concatenated member or trailing gzip bytes",
        )
        require(
            self._input.count == self._expected_bytes,
            "compressed archive byte count differs",
        )
        require(
            self._input.sha256 == self._expected_sha,
            "compressed archive SHA256 differs",
        )
        self._finished = True

    def _fill(self) -> None:
        while not self._output and not self._finished:
            if self._pending_compressed:
                compressed = self._pending_compressed
                self._pending_compressed = b""
            else:
                compressed = self._input.read(
                    self._limits.max_compressed_input_buffer_bytes
                )
                require(compressed != b"", "truncated raw-deflate stream")
            try:
                output = self._inflater.decompress(
                    compressed, self._limits.max_decompressed_output_buffer_bytes
                )
            except zlib.error as error:
                raise LayoutInventoryError("invalid raw-deflate stream") from error
            if self._inflater.unconsumed_tail:
                self._pending_compressed = self._inflater.unconsumed_tail
            if output:
                self._record_output(output)
                self._output = output
            if self._inflater.eof:
                require(
                    not self._pending_compressed,
                    "deflate state retained bytes after EOF",
                )
                self._finish_member(self._inflater.unused_data)

    def read(self, size: int) -> bytes:
        require(
            isinstance(size, int)
            and 0 < size <= self._limits.max_decompressed_output_buffer_bytes,
            "decompressed read exceeds buffer cap",
        )
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            if not self._output:
                self._fill()
                if not self._output:
                    break
            taken = self._output[:remaining]
            self._output = self._output[len(taken) :]
            chunks.append(taken)
            remaining -= len(taken)
        return b"".join(chunks)

    def exact(self, size: int, label: str) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            block = self.read(
                min(remaining, self._limits.max_decompressed_output_buffer_bytes)
            )
            require(block != b"", f"truncated {label}")
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)

    def drain_exact(self, size: int, label: str) -> None:
        """Consume opaque bytes without joining, returning, or retaining them."""

        remaining = size
        while remaining:
            block = self.read(
                min(remaining, self._limits.max_decompressed_output_buffer_bytes)
            )
            require(block != b"", f"truncated {label}")
            remaining -= len(block)


_NUMERIC_FIELDS = (
    (100, 108, "mode"),
    (108, 116, "uid"),
    (116, 124, "gid"),
    (124, 136, "size"),
    (136, 148, "mtime"),
    (329, 337, "devmajor"),
    (337, 345, "devminor"),
)
_ALLOWED_PAX_KEYS = frozenset(
    {"path", "size", "mtime", "atime", "ctime", "uid", "gid", "uname", "gname", "comment"}
)
_STRUCTURAL_PAX_KEYS = frozenset({"path", "size"})
_WINDOWS_DEVICES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _tar_text(raw: bytes, label: str) -> str:
    nul = raw.find(b"\x00")
    if nul >= 0:
        require(raw[nul:] == b"\x00" * (len(raw) - nul), f"{label} has bytes after NUL")
        raw = raw[:nul]
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise LayoutInventoryError(f"{label} is not strict UTF-8") from error


def _octal(raw: bytes, label: str, *, empty_zero: bool = False) -> int:
    require(raw and raw[0] & 0x80 == 0, f"{label} uses forbidden base-256 encoding")
    require(all(byte in b" 01234567\x00" for byte in raw), f"{label} is not strict ASCII octal")
    stripped = raw.strip(b" \x00")
    if not stripped:
        require(empty_zero, f"{label} has no octal digits")
        return 0
    require(all(byte in b"01234567" for byte in stripped), f"{label} has invalid octal padding")
    first = raw.find(stripped)
    require(
        all(byte in b" \x00" for byte in raw[:first] + raw[first + len(stripped) :]),
        f"{label} has embedded octal padding",
    )
    return int(stripped, 8)


def _verify_tar_checksum(header: bytes) -> None:
    stored = _octal(header[148:156], "tar checksum")
    checksum_view = header[:148] + b" " * 8 + header[156:]
    unsigned = sum(checksum_view)
    signed = sum(byte if byte < 128 else byte - 256 for byte in checksum_view)
    require(stored in {unsigned, signed}, "tar checksum differs")


def _canonical_path(value: str, limits: ResourceLimits, label: str) -> str:
    require(value != "", f"{label} is empty")
    require(unicodedata.normalize("NFC", value) == value, f"{label} is not NFC")
    encoded = value.encode("utf-8")
    require(len(encoded) <= limits.max_path_utf8_bytes, f"{label} exceeds path cap")
    require(not value.startswith("/"), f"{label} is absolute")
    require("\\" not in value and ":" not in value, f"{label} contains forbidden separator or ADS")
    require(not any(ord(character) < 32 or ord(character) == 127 for character in value), f"{label} contains control characters")
    parts = value.split("/")
    require(all(part not in {"", ".", ".."} for part in parts), f"{label} has unsafe segments")
    for part in parts:
        require(not part.endswith((".", " ")), f"{label} has trailing dot or space")
        device_stem = part.split(".", 1)[0].upper()
        require(device_stem not in _WINDOWS_DEVICES, f"{label} uses a device name")
    canonical = PurePosixPath(*parts).as_posix()
    require(canonical == value, f"{label} is noncanonical")
    return value


def _header_path(header: bytes, limits: ResourceLimits) -> str:
    require(
        header[257:263] == b"ustar\x00" and header[263:265] == b"00",
        "tar format is not exact POSIX USTAR",
    )
    name = _tar_text(header[0:100], "tar name")
    prefix = _tar_text(header[345:500], "tar prefix")
    value = f"{prefix}/{name}" if prefix else name
    return _canonical_path(value, limits, "raw header path")


def _ascii_decimal(value: str, label: str) -> None:
    require(value != "" and all(c in "0123456789" for c in value), f"{label} is not unsigned decimal")
    require(value == "0" or not value.startswith("0"), f"{label} has leading zero")


def _parse_pax(
    payload: bytes, *, global_header: bool, limits: ResourceLimits
) -> tuple[dict[str, str], frozenset[str]]:
    require(payload != b"", "empty PAX payload is forbidden")
    seen: set[str] = set()
    structural: dict[str, str] = {}
    nonstructural_hashes: set[str] = set()
    cursor = 0
    while cursor < len(payload):
        space = payload.find(b" ", cursor)
        require(space > cursor, "PAX record length is absent")
        length_raw = payload[cursor:space]
        require(length_raw.isdigit(), "PAX record length is not decimal")
        require(length_raw == b"0" or not length_raw.startswith(b"0"), "PAX record length has leading zero")
        require(
            len(length_raw) <= len(str(len(payload))),
            "PAX record length exceeds payload",
        )
        length = int(length_raw)
        require(length > space - cursor + 3, "PAX record is too short")
        end = cursor + length
        require(end <= len(payload), "PAX record exceeds payload")
        record = payload[space + 1 : end]
        require(record.endswith(b"\n"), "PAX record lacks newline")
        body = record[:-1]
        equals = body.find(b"=")
        require(equals > 0, "PAX record lacks key/value separator")
        key_raw, value_raw = body[:equals], body[equals + 1 :]
        try:
            key = key_raw.decode("ascii", errors="strict")
            value = value_raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise LayoutInventoryError("PAX key/value encoding differs") from error
        require(key in _ALLOWED_PAX_KEYS, f"unknown or forbidden PAX key: {key}")
        require(key not in seen, f"duplicate PAX key: {key}")
        seen.add(key)
        require(value != "", f"empty PAX value is forbidden: {key}")
        require("\x00" not in value, f"PAX value contains NUL: {key}")
        require(not any(ord(c) < 32 and c not in "\t" for c in value), f"PAX value contains control: {key}")
        if global_header:
            require(key not in _STRUCTURAL_PAX_KEYS, f"global PAX structural key forbidden: {key}")
        if key == "path":
            _canonical_path(value, limits, "PAX path")
            structural[key] = value
        elif key == "size":
            _ascii_decimal(value, "PAX size")
            require(
                len(value) <= len(str(limits.max_single_regular_member_bytes))
                and int(value) <= limits.max_single_regular_member_bytes,
                "PAX size exceeds regular-member cap",
            )
            structural[key] = value
        elif key in {"uid", "gid"}:
            _ascii_decimal(value, f"PAX {key}")
        elif key in {"mtime", "atime", "ctime"}:
            numeric = value[1:] if value.startswith("-") else value
            require(
                numeric != ""
                and numeric.count(".") <= 1
                and all(c in "0123456789." for c in numeric)
                and not numeric.startswith(".")
                and not numeric.endswith("."),
                f"PAX {key} is not a decimal timestamp",
            )
        if key not in _STRUCTURAL_PAX_KEYS:
            nonstructural_hashes.add(_sha256_text(key))
        cursor = end
    require(cursor == len(payload), "PAX payload has trailing bytes")
    return structural, frozenset(nonstructural_hashes)


def _pax_flags(
    global_key_hashes: frozenset[str],
    extended: Mapping[str, str],
    extended_key_hashes: frozenset[str],
) -> tuple[str, ...]:
    flags: list[str] = []
    if "path" in extended:
        flags.append("PATH_OVERRIDE")
    if "size" in extended:
        flags.append("SIZE_OVERRIDE")
    for key_hash in sorted(global_key_hashes):
        flags.append(f"GLOBAL_KEY_SHA256:{key_hash}")
    for key_hash in sorted(extended_key_hashes):
        flags.append(f"EXTENDED_KEY_SHA256:{key_hash}")
    return tuple(flags)


def _parse_layout_to_sink(
    source: BinaryIO,
    *,
    expected_compressed_bytes: int,
    expected_compressed_sha256: str,
    sink: OwnedStagingSink,
    limits: ResourceLimits = DEFAULT_LIMITS,
    clock: Callable[[], float] = time.monotonic,
) -> LayoutSummary:
    """Parse one gzip-compressed tar stream and emit logical members in order."""

    require(type(limits) is ResourceLimits, "resource-limit type differs")
    ResourceLimits.validate(limits)
    require(type(sink) is OwnedStagingSink, "formal member sink type differs")
    require(sink.limits == limits and not sink.closed, "member sink state or limits differ")
    require(callable(clock), "clock is not callable")
    started = clock()

    def check_elapsed() -> None:
        elapsed = clock() - started
        require(elapsed >= 0, "monotonic clock moved backwards")
        require(elapsed <= limits.max_elapsed_seconds, "layout parser elapsed-time cap exceeded")

    stream = _GzipReader(
        source,
        limits=limits,
        expected_compressed_bytes=expected_compressed_bytes,
        expected_compressed_sha256=expected_compressed_sha256,
    )
    raw_headers = 0
    logical_members = 0
    regular_members = 0
    directory_members = 0
    total_regular_bytes = 0
    cumulative_pax = 0
    global_pax_key_hashes: frozenset[str] = frozenset()
    extended_pax: dict[str, str] | None = None
    extended_pax_key_hashes: frozenset[str] | None = None
    resolved_digests: set[bytes] = set()
    folded_to_resolved: dict[bytes, bytes] = {}
    type_counts: Counter[str] = Counter()
    depth_counts: Counter[int] = Counter()
    post_end_padding = 0

    def read_padding(size: int, label: str) -> None:
        padding = (-size) % 512
        if padding:
            require(stream.exact(padding, label) == b"\x00" * padding, f"{label} is nonzero")

    while True:
        check_elapsed()
        header = stream.exact(512, "tar header")
        if header == b"\x00" * 512:
            require(
                extended_pax is None and extended_pax_key_hashes is None,
                "unconsumed extended PAX header",
            )
            require(stream.exact(512, "second tar end block") == b"\x00" * 512, "tar requires two zero end blocks")
            while True:
                block = stream.read(limits.max_decompressed_output_buffer_bytes)
                if not block:
                    break
                check_elapsed()
                post_end_padding += len(block)
                require(
                    post_end_padding <= limits.max_post_end_zero_padding_bytes,
                    "post-end zero padding cap exceeded",
                )
                require(block == b"\x00" * len(block), "nonzero bytes after tar end blocks")
            break

        raw_headers += 1
        require(raw_headers <= limits.max_raw_headers, "raw-header cap exceeded")
        _verify_tar_checksum(header)
        for start, end, label in _NUMERIC_FIELDS:
            empty_zero = label in {"devmajor", "devminor"}
            _octal(header[start:end], f"tar {label}", empty_zero=empty_zero)
        raw_path = _header_path(header, limits)
        raw_size = _octal(header[124:136], "tar size")
        typeflag = header[156:157]
        require(_tar_text(header[157:257], "tar linkname") == "", "tar link target is forbidden")

        if typeflag in {b"x", b"g"}:
            require(
                raw_size <= limits.max_single_pax_payload_bytes,
                "single PAX payload cap exceeded",
            )
            cumulative_pax += raw_size
            require(cumulative_pax <= limits.max_cumulative_pax_payload_bytes, "cumulative PAX cap exceeded")
            payload = stream.exact(raw_size, "PAX payload")
            read_padding(raw_size, "PAX padding")
            if typeflag == b"g":
                require(extended_pax is None, "global PAX interrupted extended PAX application")
                structural, key_hashes = _parse_pax(
                    payload, global_header=True, limits=limits
                )
                require(not structural, "global PAX retained structural metadata")
                global_pax_key_hashes = global_pax_key_hashes.union(key_hashes)
            else:
                require(extended_pax is None, "stacked extended PAX headers are forbidden")
                extended_pax, extended_pax_key_hashes = _parse_pax(
                    payload, global_header=False, limits=limits
                )
            continue

        require(typeflag in {b"", b"\x00", b"0", b"5"}, "forbidden or unknown tar member type")
        logical_members += 1
        require(logical_members <= limits.max_logical_members, "logical-member cap exceeded")
        extended = extended_pax or {}
        pax_path = extended.get("path")
        resolved_path = _canonical_path(pax_path or raw_path, limits, "resolved path")
        resolved_size = int(extended["size"]) if "size" in extended else raw_size
        member_type = "DIRECTORY" if typeflag == b"5" else "REGULAR"
        if member_type == "DIRECTORY":
            require(resolved_size == 0, "directory resolved size is nonzero")
            directory_members += 1
        else:
            require(
                resolved_size <= limits.max_single_regular_member_bytes,
                "single regular-member size cap exceeded",
            )
            regular_members += 1
            total_regular_bytes += resolved_size

        resolved_digest = hashlib.sha256(resolved_path.encode("utf-8")).digest()
        folded = unicodedata.normalize("NFC", resolved_path.casefold())
        folded_digest = hashlib.sha256(folded.encode("utf-8")).digest()
        require(resolved_digest not in resolved_digests, "duplicate resolved path")
        previous = folded_to_resolved.get(folded_digest)
        require(previous is None or previous == resolved_digest, "casefold Unicode path collision")
        require(
            len(resolved_digests) + len(folded_to_resolved) + 2
            <= limits.max_collision_digest_entries,
            "collision-digest entry cap exceeded",
        )
        resolved_digests.add(resolved_digest)
        folded_to_resolved[folded_digest] = resolved_digest

        record = MemberRecord(
            member_ordinal=logical_members,
            raw_header_path=raw_path,
            pax_path=pax_path,
            resolved_path=resolved_path,
            raw_path_sha256=_sha256_text(raw_path),
            resolved_path_sha256=resolved_digest.hex().upper(),
            member_type=member_type,
            size=resolved_size,
            pax_flags=_pax_flags(
                global_pax_key_hashes,
                extended,
                extended_pax_key_hashes or frozenset(),
            ),
        )
        OwnedStagingSink._emit(sink, record)
        type_counts[member_type] += 1
        depth_counts[len(resolved_path.split("/"))] += 1

        if member_type == "REGULAR":
            remaining = resolved_size
            while remaining:
                check_elapsed()
                take = min(remaining, limits.regular_payload_drain_buffer_bytes)
                # Intentionally discard the opaque bytes immediately.
                stream.drain_exact(take, "regular payload")
                remaining -= take
            read_padding(resolved_size, "regular padding")
        extended_pax = None
        extended_pax_key_hashes = None

    require(logical_members > 0, "tar archive has no logical members")
    require(sink.records_written == logical_members, "sink/member count differs")
    return LayoutSummary(
        compressed_bytes=stream.compressed_count,
        compressed_sha256=stream.compressed_sha256,
        uncompressed_tar_stream_bytes=stream.uncompressed_count,
        raw_header_count=raw_headers,
        logical_member_count=logical_members,
        regular_member_count=regular_members,
        directory_member_count=directory_members,
        total_regular_payload_bytes=total_regular_bytes,
        post_end_zero_padding_bytes=post_end_padding,
        type_counts=dict(sorted(type_counts.items())),
        depth_counts=dict(sorted(depth_counts.items())),
    )


def parse_layout(
    source: BinaryIO,
    *,
    expected_compressed_bytes: int,
    expected_compressed_sha256: str,
    sink: OwnedStagingSink,
    limits: ResourceLimits = DEFAULT_LIMITS,
    clock: Callable[[], float] = time.monotonic,
) -> LayoutSummary:
    """Parse into the concrete bounded sink and durably close it on every exit."""

    require(type(sink) is OwnedStagingSink, "formal member sink type differs")
    require(sink.limits == limits and not sink.closed, "member sink state or limits differ")
    try:
        return _parse_layout_to_sink(
            source,
            expected_compressed_bytes=expected_compressed_bytes,
            expected_compressed_sha256=expected_compressed_sha256,
            sink=sink,
            limits=limits,
            clock=clock,
        )
    finally:
        OwnedStagingSink.close(sink)
