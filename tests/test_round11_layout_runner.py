from __future__ import annotations

import hashlib
import io
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from arsc_eval.round11_layout_runner import run_layout_worker_supervised  # noqa: E402
from arsc_eval import round11_layout_runner as runner  # noqa: E402
from arsc_eval.round11_layout_worker import READY_MESSAGE  # noqa: E402

WORKER = (ROOT / "src/arsc_eval/round11_layout_worker.py").resolve()
PYTHON = Path(sys.executable).resolve()


def test_windows_minimal_environment_uses_canonical_systemroot_key() -> None:
    environment = runner._minimal_environment()
    if os.name == "nt":
        assert set(environment) == {"PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING", "PYTHONUTF8", "SYSTEMROOT"}
        assert environment["SYSTEMROOT"] == os.environ["SYSTEMROOT"]
        assert "SystemRoot" not in environment


def _octal(value: int, width: int) -> bytes:
    digits = f"{value:o}".encode("ascii")
    return b"0" * (width - 1 - len(digits)) + digits + b"\x00"


def _archive(payload: bytes = b"abc") -> bytes:
    header = bytearray(512)
    path = b"safe/file.bin"
    header[: len(path)] = path
    header[100:108] = _octal(0o644, 8)
    header[108:116] = _octal(0, 8)
    header[116:124] = _octal(0, 8)
    header[124:136] = _octal(len(payload), 12)
    header[136:148] = _octal(0, 12)
    header[148:156] = b" " * 8
    header[156:157] = b"0"
    header[257:263] = b"ustar\x00"
    header[263:265] = b"00"
    header[329:337] = _octal(0, 8)
    header[337:345] = _octal(0, 8)
    header[148:156] = f"{sum(header):06o}".encode("ascii") + b"\x00 "
    raw = bytes(header) + payload + b"\x00" * ((-len(payload)) % 512) + b"\x00" * 1024
    compressor = zlib.compressobj(level=6, wbits=-zlib.MAX_WBITS)
    compressed = compressor.compress(raw) + compressor.flush()
    return (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
        + compressed
        + struct.pack("<II", zlib.crc32(raw), len(raw) & 0xFFFFFFFF)
    )


def _run(tmp_path: Path, opener, data: bytes, **kwargs):
    return run_layout_worker_supervised(
        opener,
        expected_bytes=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest().upper(),
        cwd=tmp_path.resolve(),
        log_path=(tmp_path / "round11_daadx_layout_inventory.log").resolve(),
        python_executable=PYTHON,
        worker_path=WORKER,
        timeout_seconds=kwargs.pop("timeout_seconds", 5),
        require_formal_windows=os.name == "nt",
        **kwargs,
    )


def test_supervised_worker_opens_archive_only_after_ready(tmp_path: Path) -> None:
    data = _archive()
    opened = []

    def opener():
        assert (tmp_path / "round11_daadx_layout_public_inventory.csv").read_bytes() == READY_HEADER
        assert (tmp_path / "round11_daadx_layout_restricted_path_seal.jsonl").is_file()
        opened.append(True)
        return io.BytesIO(data)

    outcome = _run(tmp_path, opener, data)
    assert opened == [True]
    assert outcome.complete and outcome.ready and outcome.returncode == 0
    assert outcome.supplied_bytes == len(data)
    assert outcome.supplied_sha256 == hashlib.sha256(data).hexdigest().upper()
    assert outcome.formally_contained is (os.name == "nt")
    assert outcome.terminal["summary"]["logical_member_count"] == 1


READY_HEADER = b"member_ordinal,raw_path_sha256,resolved_path_sha256,member_type,size,pax_flags\n"


def test_parser_rejection_is_contained_and_preserves_partial_sinks(tmp_path: Path) -> None:
    data = _archive()[:-4]
    outcome = _run(tmp_path, lambda: io.BytesIO(data), data)
    assert not outcome.complete and outcome.ready
    assert outcome.failure_code == "PARSER_REJECTED"
    assert outcome.returncode == 20
    assert (tmp_path / "round11_daadx_layout_public_inventory.csv").is_file()
    assert (tmp_path / "round11_daadx_layout_restricted_path_seal.jsonl").is_file()


def test_archive_open_failure_occurs_after_ready_and_is_contained(tmp_path: Path) -> None:
    data = _archive()

    def fail():
        assert (tmp_path / "round11_daadx_layout_public_inventory.csv").is_file()
        raise OSError("synthetic open failure")

    outcome = _run(tmp_path, fail, data)
    assert not outcome.complete and outcome.ready
    assert outcome.failure_code == "ARCHIVE_OPEN_FAILURE"
    assert outcome.supplied_bytes == 0 and outcome.supplied_sha256 is None


class _FailingSource(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        raise OSError("synthetic read failure")


def test_archive_feeder_failure_terminates_contained_tree(tmp_path: Path) -> None:
    data = _archive()
    outcome = _run(tmp_path, lambda: _FailingSource(data), data)
    assert not outcome.complete and outcome.ready
    assert outcome.failure_code == "ARCHIVE_FEED_FAILURE"


def test_blocking_archive_opener_cannot_bypass_deadline(tmp_path: Path) -> None:
    data = _archive()

    def delayed():
        time.sleep(0.5)
        return io.BytesIO(data)

    started = time.monotonic()
    outcome = _run(tmp_path, delayed, data, timeout_seconds=0.3)
    assert not outcome.complete and outcome.failure_code == "WORKER_TIMEOUT"
    assert time.monotonic() - started < 2


def _control_script(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "synthetic_worker.py"
    script.write_text(
        "import os,sys,time\n"
        "kind,num=sys.argv[1],int(sys.argv[2])\n"
        "if kind=='--control-handle':\n"
        " import msvcrt\n"
        " fd=msvcrt.open_osfhandle(num,os.O_WRONLY|os.O_BINARY)\n"
        "else: fd=num\n"
        "control=os.fdopen(fd,'wb',buffering=0)\n"
        + body,
        encoding="utf-8",
    )
    return script.resolve()


def _run_custom(tmp_path: Path, worker: Path, data: bytes, *, timeout: float = 2, log_cap: int = 1024):
    return run_layout_worker_supervised(
        lambda: io.BytesIO(data),
        expected_bytes=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest().upper(),
        cwd=tmp_path.resolve(),
        log_path=(tmp_path / "round11_daadx_layout_inventory.log").resolve(),
        python_executable=PYTHON,
        worker_path=worker,
        timeout_seconds=timeout,
        max_log_bytes=log_cap,
        require_formal_windows=os.name == "nt",
    )


def test_invalid_ready_never_opens_archive(tmp_path: Path) -> None:
    data = _archive()
    worker = _control_script(tmp_path, "control.write(b'BAD\\n'); time.sleep(10)\n")
    opened = []
    outcome = run_layout_worker_supervised(
        lambda: opened.append(True) or io.BytesIO(data),
        expected_bytes=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest().upper(),
        cwd=tmp_path.resolve(),
        log_path=(tmp_path / "round11_daadx_layout_inventory.log").resolve(),
        python_executable=PYTHON,
        worker_path=worker,
        timeout_seconds=2,
        require_formal_windows=os.name == "nt",
    )
    assert not outcome.complete and outcome.failure_code == "INVALID_READY"
    assert not outcome.ready and opened == []


@pytest.mark.parametrize("failure", ["timeout", "log"])
def test_timeout_or_log_overflow_kills_contained_job(tmp_path: Path, failure: str) -> None:
    data = _archive()
    if failure == "timeout":
        body = f"control.write({READY_MESSAGE!r}); time.sleep(10)\n"
        worker = _control_script(tmp_path, body)
        outcome = _run_custom(tmp_path, worker, data, timeout=0.1)
        assert outcome.failure_code == "WORKER_TIMEOUT"
    else:
        body = f"control.write({READY_MESSAGE!r}); sys.stdout.buffer.write(b'x'*100000); sys.stdout.flush(); time.sleep(10)\n"
        worker = _control_script(tmp_path, body)
        outcome = _run_custom(tmp_path, worker, data, log_cap=64)
        assert outcome.failure_code == "LOG_OVERFLOW"
        assert (tmp_path / "round11_daadx_layout_inventory.log").stat().st_size == 64
    assert not outcome.complete
    if os.name == "nt":
        assert outcome.formally_contained


@pytest.mark.parametrize("kind", ["extra", "arbitrary_code"])
def test_terminal_control_protocol_is_exact(tmp_path: Path, kind: str) -> None:
    data = _archive()
    if kind == "extra":
        terminal = b'{"code":"PARSER_REJECTED","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
        body = f"control.write({READY_MESSAGE!r}); control.write({terminal!r}); control.write({terminal!r}); raise SystemExit(20)\n"
        expected = "MULTIPLE_TERMINAL_MESSAGES"
    else:
        terminal = b'{"code":"PRIVATE/PATH","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
        body = f"control.write({READY_MESSAGE!r}); control.write({terminal!r}); raise SystemExit(20)\n"
        expected = "INVALID_ERROR_TERMINAL"
    worker = _control_script(tmp_path, body)
    outcome = _run_custom(tmp_path, worker, data)
    assert not outcome.complete and outcome.failure_code == expected


@pytest.mark.skipif(os.name != "nt", reason="formal Job Object is Windows-only")
def test_windows_job_active_process_limit_blocks_descendant(tmp_path: Path) -> None:
    data = _archive()
    error_terminal = b'{"code":"PARSER_REJECTED","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
    escaped_terminal = b'{"code":"CHILD_SPAWNED","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
    body = (
        f"control.write({READY_MESSAGE!r})\n"
        "import subprocess\n"
        "try:\n"
        " subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])\n"
        "except OSError:\n"
        f" control.write({error_terminal!r}); raise SystemExit(20)\n"
        "else:\n"
        f" control.write({escaped_terminal!r}); raise SystemExit(21)\n"
    )
    worker = _control_script(tmp_path, body)
    outcome = _run_custom(tmp_path, worker, data)
    assert outcome.formally_contained
    assert outcome.failure_code == "PARSER_REJECTED"


@pytest.mark.skipif(os.name != "nt", reason="formal handle-list isolation is Windows-only")
def test_windows_handle_list_excludes_unrelated_inheritable_handle(tmp_path: Path) -> None:
    import msvcrt

    data = _archive()
    extra_read, extra_write = os.pipe()
    extra_handle = int(msvcrt.get_osfhandle(extra_read))
    os.set_handle_inheritable(extra_handle, True)
    os.write(extra_write, b"X")
    rejected = b'{"code":"PARSER_REJECTED","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
    leaked = b'{"code":"HANDLE_LEAKED","event":"ERROR","schema_version":"ARSC_ROUND11_DAADX_LAYOUT_WORKER_CONTROL_V1"}\n'
    body = (
        f"control.write({READY_MESSAGE!r})\n"
        "import ctypes\n"
        "available=ctypes.c_uint32()\n"
        f"visible=ctypes.windll.kernel32.PeekNamedPipe(ctypes.c_void_p({extra_handle}),None,0,None,ctypes.byref(available),None) and available.value>0\n"
        "if visible:\n"
        f" control.write({leaked!r}); raise SystemExit(21)\n"
        "else:\n"
        f" control.write({rejected!r}); raise SystemExit(20)\n"
    )
    try:
        worker = _control_script(tmp_path, body)
        outcome = _run_custom(tmp_path, worker, data)
    finally:
        os.set_handle_inheritable(extra_handle, False)
        os.close(extra_read)
        os.close(extra_write)
    assert outcome.formally_contained
    assert outcome.failure_code == "PARSER_REJECTED"


@pytest.mark.skipif(os.name != "nt", reason="patches the formal Windows spawn path")
def test_log_or_control_thread_failure_is_nonpublishable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _archive()

    class BrokenReader:
        def read(self, _size=-1):
            raise OSError("synthetic log drain failure")

        def close(self):
            pass

    class FakeChild:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = BrokenReader()
            self.control = io.BytesIO(READY_MESSAGE)
            self.formally_contained = True
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate_tree(self):
            self.returncode = 70

        def close(self):
            pass

    monkeypatch.setattr(runner, "_spawn_windows_contained", lambda *args: FakeChild())
    with pytest.raises(runner.LayoutRunnerError, match="supervisor thread failed"):
        _run(tmp_path, lambda: io.BytesIO(data), data)
