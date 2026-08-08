"""Restricted stdin-only worker for the Round 11 layout inventory.

The worker never receives an archive path.  Its only data input is stdin, and
its only outputs are the two owned inventory sinks plus a small inherited
control pipe.  Control messages deliberately contain no paths.

The worker is a self-contained chain: it attests its own interpreter startup,
then reads only the sibling ``round11_layout_inventory.py`` source, verifies a
hardcoded source SHA256, and builds the package+module ModuleType objects
directly (no ``sys.path`` mutation, no normal import machinery, no
``sys.meta_path`` consultation).  The parent supervisor holds the verified
source leases and never hands the worker a reconstructed namespace.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from pathlib import Path
from typing import BinaryIO


CONTROL_SCHEMA = "ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"
READY_MESSAGE = b'{"event":"READY","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
MAX_CONTROL_BYTES = 65_536
ERROR_CODES = frozenset({"PARSER_REJECTED", "WORKER_CONTROL_FAILURE"})
INVENTORY_SOURCE_SHA256 = "3D3AA0CD07DBFBFEBE874FBC80DD7ABF7AD658D0FFB90551F5267D4CD7D6CD4B"


def _attest_startup() -> None:
    """Fail-closed attestation of the interpreted worker boot.

    Runs before any source read or data access.  The worker process must be
    launched exactly as ``python -I -S -B <worker.py> --control-{fd,handle}
    <number> --expected-bytes <count> --expected-sha256 <sha256>`` and the
    interpreter state must match the required flag set.
    """
    argv = list(sys.orig_argv)
    if len(argv) != 11:
        raise ValueError("worker startup argv length differs")
    exe, f1, f2, f3, script = argv[0], argv[1], argv[2], argv[3], argv[4]
    if exe != sys.executable:
        raise ValueError("worker startup executable differs")
    if (f1, f2, f3) != ("-I", "-S", "-B"):
        raise ValueError("worker startup interpreter flags differ")
    if str(Path(script).resolve()) != str(Path(__file__).resolve()):
        raise ValueError("worker startup script differs")
    if argv[5] not in ("--control-handle", "--control-fd"):
        raise ValueError("worker startup control selector differs")
    if argv[7] != "--expected-bytes" or argv[9] != "--expected-sha256":
        raise ValueError("worker startup argument flags differ")
    state = sys.flags
    expected = {
        "isolated": 1,
        "no_site": 1,
        "no_user_site": 1,
        "safe_path": True,
        "dont_write_bytecode": 1,
        "ignore_environment": 1,
    }
    for name, want in expected.items():
        value = getattr(state, name)
        if type(value) is not type(want) or value != want:
            raise ValueError(f"worker startup {name} differs")


def _load_verified_inventory() -> types.ModuleType:
    """Read and load the sibling inventory source with a hardcoded lease.

    Reads only ``round11_layout_inventory.py`` bytes, requires the exact
    hardcoded SHA256, and creates the ``arsc_eval`` package plus the
    ``arsc_eval.round11_layout_inventory`` module directly.  The module is
    inserted into ``sys.modules`` before ``compile``/``exec`` (dataclasses
    need an addressable module) and both inserted modules are rolled back on
    any failure.
    """
    source_path = Path(__file__).resolve().with_name("round11_layout_inventory.py")
    data = source_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest().upper()
    if digest != INVENTORY_SOURCE_SHA256:
        raise ValueError("inventory source SHA256 differs")
    if "arsc_eval" in sys.modules or "arsc_eval.round11_layout_inventory" in sys.modules:
        raise ValueError("inventory namespace preloaded")
    package = types.ModuleType("arsc_eval", "Round 11 layout inventory contained package")
    package.__package__ = ""
    package.__file__ = str(source_path.with_name("__init__.py"))
    package.__path__ = [str(source_path.parent)]
    module = types.ModuleType("arsc_eval.round11_layout_inventory")
    module.__package__ = "arsc_eval"
    module.__file__ = str(source_path)
    module.__cached__ = None
    module.__source_sha256__ = digest
    sys.modules["arsc_eval"] = package
    sys.modules["arsc_eval.round11_layout_inventory"] = module
    try:
        code = compile(data, str(source_path), "exec", dont_inherit=True, optimize=0)
        exec(code, module.__dict__)
    except BaseException:
        sys.modules.pop("arsc_eval.round11_layout_inventory", None)
        sys.modules.pop("arsc_eval", None)
        raise
    return module


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
    _attest_startup()
    args = list(sys.argv[1:] if argv is None else argv)
    inventory = _load_verified_inventory()
    LayoutInventoryError = inventory.LayoutInventoryError
    OwnedStagingSink = inventory.OwnedStagingSink
    parse_layout = inventory.parse_layout
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
