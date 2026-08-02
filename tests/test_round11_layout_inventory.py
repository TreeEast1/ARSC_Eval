from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import struct
import sys
import tempfile
import unicodedata
import zlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src/arsc_eval/round11_layout_inventory.py"
PROTOCOL = ROOT / "outputs/validity/round11_daadx_layout_inventory_protocol.json"
SPEC = importlib.util.spec_from_file_location("round11_layout_inventory", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
DEFAULT_LIMITS = MODULE.DEFAULT_LIMITS
LayoutInventoryError = MODULE.LayoutInventoryError
ResourceLimits = MODULE.ResourceLimits
OwnedStagingSink = MODULE.OwnedStagingSink
parse_layout = MODULE.parse_layout


def test_defaults_and_sink_fields_match_frozen_protocol_exactly() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    bounds = protocol["resource_bounds"]
    for field, value in vars(DEFAULT_LIMITS).items():
        assert bounds[field] == value
    assert protocol["output_privacy"]["public_inventory_fields"] == [
        "member_ordinal",
        "raw_path_sha256",
        "resolved_path_sha256",
        "member_type",
        "size",
        "pax_flags",
    ]
    assert OwnedStagingSink.PUBLIC_NAME in protocol["artifact_contract"]["exact_files"]
    assert OwnedStagingSink.RESTRICTED_NAME in protocol["artifact_contract"]["exact_files"]


def _octal(value: int, width: int) -> bytes:
    digits = f"{value:o}".encode("ascii")
    assert len(digits) <= width - 1
    return b"0" * (width - 1 - len(digits)) + digits + b"\x00"


def _rechecksum(header: bytearray, *, signed: bool = False) -> bytes:
    header[148:156] = b" " * 8
    value = (
        sum(byte if byte < 128 else byte - 256 for byte in header)
        if signed
        else sum(header)
    )
    assert value >= 0
    header[148:156] = f"{value:06o}".encode("ascii") + b"\x00 "
    return bytes(header)


def _tar_header(
    path: str,
    *,
    size: int = 0,
    typeflag: bytes = b"0",
    linkname: str = "",
) -> bytes:
    encoded = path.encode("utf-8")
    assert len(encoded) <= 100 and len(typeflag) == 1
    header = bytearray(512)
    header[0 : len(encoded)] = encoded
    header[100:108] = _octal(0o644, 8)
    header[108:116] = _octal(0, 8)
    header[116:124] = _octal(0, 8)
    header[124:136] = _octal(size, 12)
    header[136:148] = _octal(0, 12)
    header[148:156] = b" " * 8
    header[156:157] = typeflag
    link = linkname.encode("utf-8")
    header[157 : 157 + len(link)] = link
    header[257:263] = b"ustar\x00"
    header[263:265] = b"00"
    header[329:337] = _octal(0, 8)
    header[337:345] = _octal(0, 8)
    return _rechecksum(header)


def _member(path: str, payload: bytes = b"", *, typeflag: bytes = b"0") -> bytes:
    return (
        _tar_header(path, size=len(payload), typeflag=typeflag)
        + payload
        + b"\x00" * ((-len(payload)) % 512)
    )


def _pax_record(key: str, value: str) -> bytes:
    body = f"{key}={value}\n".encode("utf-8")
    length = len(body) + 2
    while True:
        candidate = str(length).encode("ascii") + b" " + body
        if len(candidate) == length:
            return candidate
        length = len(candidate)


def _pax(records: list[tuple[str, str]], *, global_header: bool = False) -> bytes:
    payload = b"".join(_pax_record(key, value) for key, value in records)
    return _member(
        "PaxHeaders/entry",
        payload,
        typeflag=b"g" if global_header else b"x",
    )


def _tar(*parts: bytes, end_blocks: int = 2, post_padding: int = 0) -> bytes:
    return b"".join(parts) + b"\x00" * (512 * end_blocks + post_padding)


def _gzip(raw: bytes, *, fhcrc: bool = False, flags: int = 0, level: int = 6) -> bytes:
    flags |= 0x02 if fhcrc else 0
    header = bytearray(b"\x1f\x8b\x08" + bytes([flags]) + b"\x00\x00\x00\x00\x00\xff")
    if flags & 0x04:
        header += b"\x00\x00"
    if flags & 0x08:
        header += b"synthetic\x00"
    if flags & 0x10:
        header += b"comment\x00"
    if fhcrc:
        header += struct.pack("<H", zlib.crc32(header) & 0xFFFF)
    compressor = zlib.compressobj(level=level, wbits=-zlib.MAX_WBITS)
    deflate = compressor.compress(raw) + compressor.flush()
    trailer = struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)
    return bytes(header) + deflate + trailer


def _parse(
    gzip_bytes: bytes,
    *,
    limits: ResourceLimits = DEFAULT_LIMITS,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
    clock=None,
):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory).resolve()
        public = root / OwnedStagingSink.PUBLIC_NAME
        restricted = root / OwnedStagingSink.RESTRICTED_NAME
        sink = OwnedStagingSink(public, restricted, limits=limits)
        kwargs = {}
        if clock is not None:
            kwargs["clock"] = clock
        summary = parse_layout(
            io.BytesIO(gzip_bytes),
            expected_compressed_bytes=(
                len(gzip_bytes) if expected_bytes is None else expected_bytes
            ),
            expected_compressed_sha256=(
                hashlib.sha256(gzip_bytes).hexdigest()
                if expected_sha256 is None
                else expected_sha256
            ),
            sink=sink,
            limits=limits,
            **kwargs,
        )
        records = [
            SimpleNamespace(**json.loads(line))
            for line in restricted.read_text(encoding="utf-8").splitlines()
        ]
        return summary, records


def _regzip_tar(mutator) -> bytes:
    raw = bytearray(_tar(_member("safe/file.bin", b"payload")))
    mutator(raw)
    return _gzip(bytes(raw))


def test_happy_path_streams_structure_and_discards_regular_payload() -> None:
    payload = bytes(range(256)) * 9
    raw = _tar(
        _pax([("comment", "opaque"), ("path", "front/uuid-1.mp4")]),
        _member("raw-name", payload),
        _member("metadata", b"", typeflag=b"5"),
        post_padding=1024,
    )
    compressed = _gzip(raw, fhcrc=True, flags=0x04 | 0x08 | 0x10)
    summary, records = _parse(compressed)
    assert summary.compressed_bytes == len(compressed)
    assert summary.compressed_sha256 == hashlib.sha256(compressed).hexdigest().upper()
    assert summary.uncompressed_tar_stream_bytes == len(raw)
    assert summary.raw_header_count == 3
    assert summary.logical_member_count == 2
    assert summary.regular_member_count == 1
    assert summary.directory_member_count == 1
    assert summary.total_regular_payload_bytes == len(payload)
    assert summary.post_end_zero_padding_bytes == 1024
    assert summary.type_counts == {"DIRECTORY": 1, "REGULAR": 1}
    assert [record.resolved_path for record in records] == [
        "front/uuid-1.mp4",
        "metadata",
    ]
    assert records[0].pax_path == "front/uuid-1.mp4"
    assert records[0].size == len(payload)
    assert "PATH_OVERRIDE" in records[0].pax_flags
    assert all(not hasattr(record, "payload") for record in records)


def test_global_nonstructural_pax_is_key_hash_only() -> None:
    compressed = _gzip(
        _tar(
            _pax([("comment", "secret-ish metadata")], global_header=True),
            _member("safe/file.bin", b"x"),
        )
    )
    _, records = _parse(compressed)
    assert records[0].pax_flags == [
        "GLOBAL_KEY_SHA256:"
        + hashlib.sha256(b"comment").hexdigest().upper(),
    ]
    assert "secret-ish" not in repr(records[0])


def test_tiny_buffers_force_streaming_across_deflate_and_tar_boundaries() -> None:
    payload = bytes(range(251)) * 20
    raw = _tar(_member("safe/file.bin", payload), post_padding=17)
    compressed = _gzip(raw, level=0)
    limits = replace(
        DEFAULT_LIMITS,
        max_compressed_input_buffer_bytes=16,
        max_decompressed_output_buffer_bytes=13,
        regular_payload_drain_buffer_bytes=7,
    )
    summary, records = _parse(compressed, limits=limits)
    assert summary.uncompressed_tar_stream_bytes == len(raw)
    assert summary.post_end_zero_padding_bytes == 17
    assert records[0].size == len(payload)


@pytest.mark.parametrize("kind", ["crc", "isize", "fhcrc", "reserved", "trailing", "concat"])
def test_gzip_integrity_failures_are_closed(kind: str) -> None:
    raw = _tar(_member("safe/file", b"payload"))
    value = bytearray(_gzip(raw, fhcrc=(kind == "fhcrc")))
    if kind == "crc":
        value[-8] ^= 1
    elif kind == "isize":
        value[-4] ^= 1
    elif kind == "fhcrc":
        # Fixed header is ten bytes, then the two-byte FHCRC.
        value[10] ^= 1
    elif kind == "reserved":
        value[3] |= 0x20
    elif kind == "trailing":
        value += b"x"
    elif kind == "concat":
        value += _gzip(raw)
    with pytest.raises(LayoutInventoryError):
        _parse(bytes(value))


def test_wrong_transport_expectations_fail_closed() -> None:
    value = _gzip(_tar(_member("safe/file", b"x")))
    with pytest.raises(LayoutInventoryError, match="byte count"):
        _parse(value, expected_bytes=len(value) + 1)
    with pytest.raises(LayoutInventoryError, match="SHA256"):
        _parse(value, expected_sha256="A" * 64)


def test_corrupt_tar_checksum_rejected() -> None:
    def mutate(raw: bytearray) -> None:
        raw[148] ^= 1

    with pytest.raises(LayoutInventoryError, match="checksum"):
        _parse(_regzip_tar(mutate))


def test_base256_numeric_encoding_rejected_even_with_recomputed_checksum() -> None:
    header = bytearray(_tar_header("safe/file", size=0))
    header[124:136] = b"\x80" + b"\x00" * 11
    header[148:156] = b" " * 8
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}".encode() + b"\x00 "
    with pytest.raises(LayoutInventoryError, match="base-256"):
        _parse(_gzip(_tar(bytes(header))))


@pytest.mark.parametrize(
    "magic,version",
    [
        (b"\x00" * 6, b"\x00" * 2),
        (b"ustar ", b" \x00"),
        (b"ustar\x00", b"01"),
        (b"badfmt", b"00"),
    ],
)
def test_only_exact_posix_ustar_magic_and_version_are_accepted(
    magic: bytes, version: bytes
) -> None:
    header = bytearray(_tar_header("safe/file"))
    header[257:263] = magic
    header[263:265] = version
    with pytest.raises(LayoutInventoryError, match="POSIX USTAR"):
        _parse(_gzip(_tar(_rechecksum(header))))


def test_posix_ustar_prefix_is_applied_only_after_format_validation() -> None:
    header = bytearray(_tar_header("file.bin"))
    prefix = b"safe/prefix"
    header[345:500] = b"\x00" * 155
    header[345 : 345 + len(prefix)] = prefix
    _, records = _parse(_gzip(_tar(_rechecksum(header))))
    assert records[0].resolved_path == "safe/prefix/file.bin"


def test_signed_standard_tar_checksum_is_accepted() -> None:
    header = bytearray(_tar_header("safe/file"))
    # Uname is not semantic layout evidence, but a high byte makes the signed
    # and unsigned standard checksum sums differ.
    header[265] = 0xFF
    _, records = _parse(_gzip(_tar(_rechecksum(header, signed=True))))
    assert records[0].resolved_path == "safe/file"


@pytest.mark.parametrize("typeflag", [b"1", b"2", b"3", b"4", b"6", b"7", b"L", b"K", b"S", b"Z"])
def test_forbidden_tar_types_rejected(typeflag: bytes) -> None:
    with pytest.raises(LayoutInventoryError, match="type"):
        _parse(_gzip(_tar(_member("safe/file", typeflag=typeflag))))


def test_link_target_rejected_even_for_regular_member() -> None:
    raw = _tar(_tar_header("safe/file", typeflag=b"0", linkname="target"))
    with pytest.raises(LayoutInventoryError, match="link target"):
        _parse(_gzip(raw))


def test_exactly_two_zero_end_blocks_required() -> None:
    raw = _tar(_member("safe/file", b"x"), end_blocks=1)
    with pytest.raises(LayoutInventoryError, match="second tar end block"):
        _parse(_gzip(raw))


@pytest.mark.parametrize("kind", ["deflate", "payload", "padding", "trailer"])
def test_truncated_stream_components_fail_closed(kind: str) -> None:
    if kind == "deflate":
        value = _gzip(_tar(_member("safe/file", b"payload")))[:-10]
    elif kind == "payload":
        value = _gzip(_tar_header("safe/file", size=10) + b"abc")
    elif kind == "padding":
        value = _gzip(_tar_header("safe/file", size=1) + b"x")
    else:
        value = _gzip(_tar(_member("safe/file", b"payload")))[:-4]
    with pytest.raises(LayoutInventoryError, match="truncated"):
        _parse(value)


def test_oversized_optional_gzip_header_rejected_by_frozen_buffer_cap() -> None:
    raw = _tar(_member("safe/file", b"x"))
    base = _gzip(raw)
    value = base[:3] + b"\x08" + base[4:10] + b"a" * 20 + b"\x00" + base[10:]
    limits = replace(DEFAULT_LIMITS, max_compressed_input_buffer_bytes=16)
    with pytest.raises(LayoutInventoryError, match="gzip header"):
        _parse(value, limits=limits)


def test_nonzero_or_excess_post_end_padding_rejected() -> None:
    raw = _tar(_member("safe/file", b"x")) + b"\x00x"
    with pytest.raises(LayoutInventoryError, match="nonzero"):
        _parse(_gzip(raw))
    small = replace(DEFAULT_LIMITS, max_post_end_zero_padding_bytes=4)
    raw = _tar(_member("safe/file", b"x"), post_padding=5)
    with pytest.raises(LayoutInventoryError, match="padding cap"):
        _parse(_gzip(raw), limits=small)


@pytest.mark.parametrize(
    "records,global_header,message",
    [
        ([('GNU.sparse.map', '1')], False, "unknown"),
        ([('SCHILY.xattr', '1')], False, "unknown"),
        ([('linkpath', 'target')], False, "unknown"),
        ([('charset', 'UTF-8')], False, "unknown"),
        ([('path', 'safe/file')], True, "global"),
        ([('size', '1')], True, "global"),
    ],
)
def test_forbidden_pax_keys_rejected(records, global_header: bool, message: str) -> None:
    raw = _tar(
        _pax(records, global_header=global_header),
        _member("safe/file", b"x"),
    )
    with pytest.raises(LayoutInventoryError, match=message):
        _parse(_gzip(raw))


def test_duplicate_pax_key_rejected() -> None:
    raw = _tar(
        _pax([("comment", "one"), ("comment", "two")]),
        _member("safe/file", b"x"),
    )
    with pytest.raises(LayoutInventoryError, match="duplicate"):
        _parse(_gzip(raw))


def test_unconsumed_or_stacked_extended_pax_rejected() -> None:
    with pytest.raises(LayoutInventoryError, match="stacked"):
        _parse(
            _gzip(
                _tar(
                    _pax([("comment", "one")]),
                    _pax([("comment", "two")]),
                    _member("safe/file", b"x"),
                )
            )
        )
    with pytest.raises(LayoutInventoryError, match="unconsumed"):
        _parse(_gzip(_tar(_pax([("comment", "one")]))))


def test_pax_size_override_controls_physical_drain_and_padding() -> None:
    overridden = (
        _tar_header("raw-name", size=1)
        + b"abc"
        + b"\x00" * ((-3) % 512)
    )
    raw = _tar(
        _pax([("size", "3"), ("path", "safe/overridden.bin")]),
        overridden,
        _member("safe/next.bin", b"z"),
    )
    summary, records = _parse(_gzip(raw))
    assert summary.total_regular_payload_bytes == 4
    assert [(record.resolved_path, record.size) for record in records] == [
        ("safe/overridden.bin", 3),
        ("safe/next.bin", 1),
    ]


def test_directory_resolved_size_must_be_zero() -> None:
    header = _tar_header("safe/directory", size=1, typeflag=b"5")
    with pytest.raises(LayoutInventoryError, match="directory resolved size"):
        _parse(_gzip(_tar(header + b"x" + b"\x00" * 511)))


@pytest.mark.parametrize(
    "path",
    ["", "/absolute", "../escape", "a/../escape", "a//b", "a\\b", "a:b", "CON/file", "a./file", "a /file"],
)
def test_unsafe_paths_rejected(path: str) -> None:
    # Empty is representable in the header even though the helper otherwise accepts it.
    raw = _tar(_member(path, b"x"))
    with pytest.raises(LayoutInventoryError):
        _parse(_gzip(raw))


def test_non_nfc_path_rejected() -> None:
    nfd = unicodedata.normalize("NFD", "café/file")
    assert nfd != unicodedata.normalize("NFC", nfd)
    with pytest.raises(LayoutInventoryError, match="NFC"):
        _parse(_gzip(_tar(_member(nfd, b"x"))))


def test_duplicate_and_casefold_colliding_paths_rejected() -> None:
    with pytest.raises(LayoutInventoryError, match="duplicate"):
        _parse(_gzip(_tar(_member("a/file", b"1"), _member("a/file", b"2"))))
    with pytest.raises(LayoutInventoryError, match="casefold"):
        _parse(_gzip(_tar(_member("A/file", b"1"), _member("a/file", b"2"))))


def test_resource_limits_fail_closed() -> None:
    compressed = _gzip(_tar(_member("safe/file", b"12345")))
    with pytest.raises(LayoutInventoryError, match="single regular"):
        _parse(
            compressed,
            limits=replace(DEFAULT_LIMITS, max_single_regular_member_bytes=4),
        )
    two_members = _gzip(
        _tar(_member("safe/one", b"1"), _member("safe/two", b"2"))
    )
    with pytest.raises(LayoutInventoryError, match="logical-member"):
        _parse(
            two_members,
            limits=replace(
                DEFAULT_LIMITS,
                max_logical_members=1,
                max_collision_digest_entries=2,
            ),
        )


def test_invalid_limit_relationship_rejected_before_parsing() -> None:
    compressed = _gzip(_tar(_member("safe/file", b"x")))
    limits = replace(
        DEFAULT_LIMITS,
        max_logical_members=2,
        max_collision_digest_entries=3,
    )
    with pytest.raises(LayoutInventoryError, match="collision-digest cap"):
        _parse(compressed, limits=limits)


@pytest.mark.parametrize("field", list(vars(DEFAULT_LIMITS)))
def test_no_frozen_resource_limit_can_be_raised(field: str) -> None:
    raised = replace(
        DEFAULT_LIMITS,
        **{field: getattr(DEFAULT_LIMITS, field) + 1},
    )
    with pytest.raises(LayoutInventoryError, match="exceeds frozen maximum"):
        raised.validate()


def test_resource_limits_are_sealed_against_validate_override() -> None:
    with pytest.raises(TypeError, match="sealed"):
        type(
            "RaisedLimits",
            (ResourceLimits,),
            {"validate": lambda self: None},
        )


@pytest.mark.parametrize("which", ["public", "restricted"])
def test_owned_sink_enforces_both_streaming_output_caps(
    tmp_path: Path, which: str
) -> None:
    public_cap = len(OwnedStagingSink.PUBLIC_HEADER)
    limits = replace(
        DEFAULT_LIMITS,
        max_public_inventory_output_bytes=(
            public_cap if which == "public" else DEFAULT_LIMITS.max_public_inventory_output_bytes
        ),
        max_restricted_path_seal_output_bytes=(
            1 if which == "restricted" else DEFAULT_LIMITS.max_restricted_path_seal_output_bytes
        ),
    )
    public = (tmp_path / OwnedStagingSink.PUBLIC_NAME).resolve()
    restricted = (tmp_path / OwnedStagingSink.RESTRICTED_NAME).resolve()
    sink = OwnedStagingSink(public, restricted, limits=limits)
    compressed = _gzip(_tar(_member("safe/file", b"x")))
    with pytest.raises(LayoutInventoryError, match="output cap"):
        parse_layout(
            io.BytesIO(compressed),
            expected_compressed_bytes=len(compressed),
            expected_compressed_sha256=hashlib.sha256(compressed).hexdigest(),
            sink=sink,
            limits=limits,
        )
    assert sink.closed
    assert public.read_bytes() == OwnedStagingSink.PUBLIC_HEADER
    assert restricted.read_bytes() == b""


def test_arbitrary_or_subclassed_sink_is_rejected_before_source_access(tmp_path: Path) -> None:
    class ChildSink(OwnedStagingSink):
        pass

    class ExplodingSource:
        def read(self, _size):
            raise AssertionError("source must not be read")

    with pytest.raises(LayoutInventoryError, match="sink type"):
        parse_layout(
            ExplodingSource(),
            expected_compressed_bytes=1,
            expected_compressed_sha256="A" * 64,
            sink=lambda _record: None,
        )
    child = ChildSink(
        (tmp_path / OwnedStagingSink.PUBLIC_NAME).resolve(),
        (tmp_path / OwnedStagingSink.RESTRICTED_NAME).resolve(),
    )
    with pytest.raises(LayoutInventoryError, match="sink type"):
        parse_layout(
            ExplodingSource(),
            expected_compressed_bytes=1,
            expected_compressed_sha256="A" * 64,
            sink=child,
        )
    child.close()


def test_exact_sink_cannot_be_monkeypatched_to_retain_paths(tmp_path: Path) -> None:
    public = (tmp_path / OwnedStagingSink.PUBLIC_NAME).resolve()
    restricted = (tmp_path / OwnedStagingSink.RESTRICTED_NAME).resolve()
    sink = OwnedStagingSink(public, restricted)
    retained = []
    with pytest.raises(AttributeError, match="sealed"):
        sink._emit = lambda record: retained.append(record)
    with pytest.raises(AttributeError, match="sealed"):
        sink._records_written = 999
    compressed = _gzip(_tar(_member("private/raw/path.bin", b"x")))
    summary = parse_layout(
        io.BytesIO(compressed),
        expected_compressed_bytes=len(compressed),
        expected_compressed_sha256=hashlib.sha256(compressed).hexdigest(),
        sink=sink,
    )
    assert summary.logical_member_count == 1
    assert retained == []
    assert "private/raw/path.bin" not in public.read_text(encoding="ascii")


def test_elapsed_time_limit_is_enforced() -> None:
    compressed = _gzip(_tar(_member("safe/file", b"x")))
    ticks = iter([0.0, 2.0])
    with pytest.raises(LayoutInventoryError, match="elapsed-time"):
        _parse(
            compressed,
            limits=replace(DEFAULT_LIMITS, max_elapsed_seconds=1),
            clock=lambda: next(ticks),
        )
