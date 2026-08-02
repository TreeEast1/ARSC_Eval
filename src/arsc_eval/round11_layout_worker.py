"""Restricted stdin-only worker for the Round 11 layout inventory.

The worker never receives an archive path.  Its only data input is stdin, and
its only outputs are the two owned inventory sinks plus a small inherited
control pipe.  Control messages deliberately contain no paths.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import BinaryIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arsc_eval.round11_layout_inventory import (  # type: ignore[import-not-found]
        LayoutInventoryError,
        OwnedStagingSink,
        parse_layout,
    )
else:
    from .round11_layout_inventory import LayoutInventoryError, OwnedStagingSink, parse_layout


CONTROL_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"
READY_MESSAGE = b'{"event":"READY","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
MAX_CONTROL_BYTES = 65_536
ERROR_CODES = frozenset({"PARSER_REJECTED", "WORKER_CONTROL_FAILURE"})


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _write_all(stream: BinaryIO, value: bytes) -> None:
    view = memoryview(value)
    offset = 0
    while offset < len(view):
        written = stream.write(view[offset:])
        if type(written) is not int or written <= 0:
            raise RuntimeError("control write failed")
        offset += written
    stream.flush()


def _control_stream(kind: str, number: str) -> BinaryIO:
    value = int(number)
    if value < 0:
        raise ValueError("negative control descriptor")
    if kind == "--control-handle":
        if os.name != "nt":
            raise RuntimeError("Windows control handle used off Windows")
        import msvcrt

        descriptor = msvcrt.open_osfhandle(value, os.O_WRONLY | os.O_BINARY)
    elif kind == "--control-fd":
        if os.name == "nt":
            raise RuntimeError("POSIX control fd used on Windows")
        descriptor = value
    else:
        raise ValueError("control selector differs")
    return os.fdopen(descriptor, "wb", buffering=0, closefd=True)


def _parse_argv(argv: list[str]) -> tuple[str, str, int, str]:
    if len(argv) != 6:
        raise ValueError("worker argv field count differs")
    control_kind, control_number, bytes_flag, bytes_text, sha_flag, expected_sha = argv
    if bytes_flag != "--expected-bytes" or sha_flag != "--expected-sha256":
        raise ValueError("worker argv flags differ")
    if not bytes_text.isascii() or not bytes_text.isdecimal() or bytes_text.startswith("0"):
        raise ValueError("expected byte count differs")
    expected_bytes = int(bytes_text)
    if expected_bytes <= 0:
        raise ValueError("expected byte count differs")
    if len(expected_sha) != 64 or any(c not in "0123456789ABCDEF" for c in expected_sha):
        raise ValueError("expected SHA256 differs")
    return control_kind, control_number, expected_bytes, expected_sha


def _terminal_complete(summary: object) -> bytes:
    fields = {
        "compressed_bytes": summary.compressed_bytes,
        "compressed_sha256": summary.compressed_sha256,
        "directory_member_count": summary.directory_member_count,
        "logical_member_count": summary.logical_member_count,
        "post_end_zero_padding_bytes": summary.post_end_zero_padding_bytes,
        "raw_header_count": summary.raw_header_count,
        "regular_member_count": summary.regular_member_count,
        "total_regular_payload_bytes": summary.total_regular_payload_bytes,
        "uncompressed_tar_stream_bytes": summary.uncompressed_tar_stream_bytes,
    }
    return _canonical(
        {"event": "COMPLETE", "schema_version": CONTROL_SCHEMA, "summary": fields}
    )


def _terminal_error(code: str) -> bytes:
    if code not in ERROR_CODES:
        raise ValueError("worker error code differs")
    return _canonical(
        {"code": code, "event": "ERROR", "schema_version": CONTROL_SCHEMA}
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    control: BinaryIO | None = None
    sink: OwnedStagingSink | None = None
    try:
        kind, number, expected_bytes, expected_sha = _parse_argv(args)
        control = _control_stream(kind, number)
        cwd = Path.cwd()
        sink = OwnedStagingSink(
            (cwd / OwnedStagingSink.PUBLIC_NAME).resolve(),
            (cwd / OwnedStagingSink.RESTRICTED_NAME).resolve(),
        )
        _write_all(control, READY_MESSAGE)
        summary = parse_layout(
            sys.stdin.buffer,
            expected_compressed_bytes=expected_bytes,
            expected_compressed_sha256=expected_sha,
            sink=sink,
        )
        _write_all(control, _terminal_complete(summary))
        return 0
    except LayoutInventoryError:
        if control is not None:
            try:
                _write_all(control, _terminal_error("PARSER_REJECTED"))
            except BaseException:
                pass
        return 20
    except BaseException:
        if control is not None:
            try:
                _write_all(control, _terminal_error("WORKER_CONTROL_FAILURE"))
            except BaseException:
                pass
        return 21
    finally:
        if sink is not None and not sink.closed:
            try:
                OwnedStagingSink.close(sink)
            except BaseException:
                pass
        if control is not None:
            control.close()


if __name__ == "__main__":
    raise SystemExit(main())
