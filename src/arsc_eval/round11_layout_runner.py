"""Contained parent supervisor for the Round 11 stdin-only layout worker.

This module is intentionally data-agnostic: callers provide an opener callback,
and the callback is not invoked until the contained worker has emitted READY.
It does not acquire a formal claim or publish the twelve-artifact closure.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import stat
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .round11_layout_inventory import DEFAULT_LIMITS
from .round11_layout_worker import CONTROL_SCHEMA, MAX_CONTROL_BYTES, READY_MESSAGE


MIB = 1_048_576
FORMAL_LOG_NAME = "round11_daadx_layout_inventory.log"
WORKER_ERROR_CODES = frozenset({"PARSER_REJECTED", "WORKER_CONTROL_FAILURE"})
CREATE_SUSPENDED = 0x00000004
EXTENDED_STARTUPINFO_PRESENT = 0x00080000


class LayoutRunnerError(RuntimeError):
    """The supervisor could not preserve a contained, stable outcome."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LayoutRunnerError(message)


@dataclass(frozen=True)
class WorkerRunObservation:
    complete: bool
    ready: bool
    returncode: int
    failure_code: str | None
    supplied_bytes: int
    supplied_sha256: str | None
    log_bytes: int
    terminal: Mapping[str, object] | None
    elapsed_seconds: float
    formally_contained: bool


class _Child:
    stdin: BinaryIO
    stdout: BinaryIO
    control: BinaryIO
    formally_contained: bool

    def poll(self) -> int | None:  # pragma: no cover - interface only
        raise NotImplementedError

    def terminate_tree(self) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - interface only
        raise NotImplementedError


class _PopenChild(_Child):
    def __init__(self, process: subprocess.Popen[bytes], control: BinaryIO) -> None:
        assert process.stdin is not None and process.stdout is not None
        self.process = process
        self.stdin = process.stdin
        self.stdout = process.stdout
        self.control = control
        self.formally_contained = False

    def poll(self) -> int | None:
        return self.process.poll()

    def terminate_tree(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            raise LayoutRunnerError("synthetic worker did not terminate") from error

    def close(self) -> None:
        for stream in (self.stdin, self.stdout, self.control):
            try:
                stream.close()
            except OSError:
                pass


class _WindowsChild(_Child):
    def __init__(
        self,
        process_handle: object,
        job_handle: int,
        stdin: BinaryIO,
        stdout: BinaryIO,
        control: BinaryIO,
    ) -> None:
        self.process_handle = process_handle
        self.job_handle = job_handle
        self.stdin = stdin
        self.stdout = stdout
        self.control = control
        self.formally_contained = True

    def poll(self) -> int | None:
        import _winapi

        result = _winapi.WaitForSingleObject(self.process_handle, 0)
        if result == _winapi.WAIT_TIMEOUT:
            return None
        require(result == _winapi.WAIT_OBJECT_0, "worker wait state differs")
        return int(_winapi.GetExitCodeProcess(self.process_handle))

    def terminate_tree(self) -> None:
        if self.poll() is not None:
            return
        import ctypes
        import _winapi

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        terminate = kernel32.TerminateJobObject
        terminate.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        terminate.restype = ctypes.c_int
        if not terminate(ctypes.c_void_p(self.job_handle), 70):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))
        result = _winapi.WaitForSingleObject(self.process_handle, 10_000)
        require(result == _winapi.WAIT_OBJECT_0, "contained worker tree did not terminate")

    def close(self) -> None:
        import ctypes
        import _winapi

        for stream in (self.stdin, self.stdout, self.control):
            try:
                stream.close()
            except OSError:
                pass
        _winapi.CloseHandle(self.process_handle)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.CloseHandle(ctypes.c_void_p(self.job_handle)):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))


def _minimal_environment() -> dict[str, str]:
    result = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT")
        require(bool(system_root and system_root.strip()), "SYSTEMROOT is unavailable")
        result["SYSTEMROOT"] = str(system_root)
    return result


def _worker_argv(
    python_executable: Path,
    worker_path: Path,
    selector: str,
    control_number: int,
    expected_bytes: int,
    expected_sha256: str,
) -> list[str]:
    return [
        str(python_executable),
        "-I",
        "-S",
        "-B",
        str(worker_path),
        selector,
        str(control_number),
        "--expected-bytes",
        str(expected_bytes),
        "--expected-sha256",
        expected_sha256,
    ]


def _spawn_posix_synthetic(
    python_executable: Path,
    worker_path: Path,
    cwd: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> _PopenChild:
    read_fd, write_fd = os.pipe()
    try:
        argv = _worker_argv(
            python_executable,
            worker_path,
            "--control-fd",
            write_fd,
            expected_bytes,
            expected_sha256,
        )
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=_minimal_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            close_fds=True,
            pass_fds=(write_fd,),
            bufsize=0,
        )
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    os.close(write_fd)
    return _PopenChild(process, os.fdopen(read_fd, "rb", buffering=0))


def _create_windows_job(process_handle: object) -> int:
    import ctypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BASIC_LIMITS(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class EXTENDED_LIMITS(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMITS),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateJobObjectW
    create.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    create.restype = ctypes.c_void_p
    set_info = kernel32.SetInformationJobObject
    set_info.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    set_info.restype = ctypes.c_int
    assign = kernel32.AssignProcessToJobObject
    assign.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    assign.restype = ctypes.c_int
    close = kernel32.CloseHandle
    close.argtypes = [ctypes.c_void_p]
    close.restype = ctypes.c_int

    job = create(None, None)
    if not job:
        error = ctypes.get_last_error()
        raise OSError(error, os.strerror(error))
    try:
        limits = EXTENDED_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x00000008 | 0x00002000
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        if not set_info(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))
        if not assign(job, ctypes.c_void_p(int(process_handle))):
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))
        return int(job)
    except BaseException:
        close(job)
        raise


def _spawn_windows_contained(
    python_executable: Path,
    worker_path: Path,
    cwd: Path,
    expected_bytes: int,
    expected_sha256: str,
) -> _WindowsChild:
    import _winapi
    import ctypes
    import msvcrt

    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    control_read, control_write = os.pipe()
    child_fds = (stdin_read, stdout_write, control_write)
    parent_fds = (stdin_write, stdout_read, control_read)
    process_handle = None
    thread_handle = None
    job_handle: int | None = None
    try:
        child_handles = [int(msvcrt.get_osfhandle(fd)) for fd in child_fds]
        for handle in child_handles:
            os.set_handle_inheritable(handle, True)
        for fd in parent_fds:
            os.set_handle_inheritable(msvcrt.get_osfhandle(fd), False)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESTDHANDLES
        startup.hStdInput = child_handles[0]
        startup.hStdOutput = child_handles[1]
        startup.hStdError = child_handles[1]
        startup.lpAttributeList = {"handle_list": child_handles}
        argv = _worker_argv(
            python_executable,
            worker_path,
            "--control-handle",
            child_handles[2],
            expected_bytes,
            expected_sha256,
        )
        flags = (
            CREATE_SUSPENDED
            | EXTENDED_STARTUPINFO_PRESENT
            | subprocess.CREATE_NO_WINDOW
        )
        process_handle, thread_handle, _, _ = _winapi.CreateProcess(
            str(python_executable),
            subprocess.list2cmdline(argv),
            None,
            None,
            True,
            flags,
            _minimal_environment(),
            str(cwd),
            startup,
        )
        for fd in child_fds:
            os.close(fd)
        child_fds = ()
        job_handle = _create_windows_job(process_handle)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        resume = kernel32.ResumeThread
        resume.argtypes = [ctypes.c_void_p]
        resume.restype = ctypes.c_uint32
        if resume(ctypes.c_void_p(int(thread_handle))) == 0xFFFFFFFF:
            error = ctypes.get_last_error()
            raise OSError(error, os.strerror(error))
        _winapi.CloseHandle(thread_handle)
        thread_handle = None
        return _WindowsChild(
            process_handle,
            job_handle,
            os.fdopen(stdin_write, "wb", buffering=0),
            os.fdopen(stdout_read, "rb", buffering=0),
            os.fdopen(control_read, "rb", buffering=0),
        )
    except BaseException:
        if job_handle is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.TerminateJobObject(ctypes.c_void_p(job_handle), 70)
            kernel32.CloseHandle(ctypes.c_void_p(job_handle))
        elif process_handle is not None:
            _winapi.TerminateProcess(process_handle, 70)
        if thread_handle is not None:
            _winapi.CloseHandle(thread_handle)
        if process_handle is not None:
            _winapi.CloseHandle(process_handle)
        for fd in (*child_fds, *parent_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _parse_control_line(line: bytes) -> Mapping[str, object]:
    require(line.endswith(b"\n") and len(line) <= MAX_CONTROL_BYTES, "control line framing differs")
    try:
        value = json.loads(line.decode("ascii"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LayoutRunnerError("control JSON is invalid") from error
    require(type(value) is dict, "control message is not an object")
    canonical = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("ascii")
    require(line == canonical, "control JSON is not canonical")
    require(value.get("schema_version") == CONTROL_SCHEMA, "control schema differs")
    return value


def _terminal_is_complete(value: Mapping[str, object]) -> bool:
    if set(value) != {"event", "schema_version", "summary"} or value["event"] != "COMPLETE":
        return False
    summary = value["summary"]
    if type(summary) is not dict:
        return False
    fields = {
        "compressed_bytes", "compressed_sha256", "directory_member_count",
        "logical_member_count", "post_end_zero_padding_bytes", "raw_header_count",
        "regular_member_count", "total_regular_payload_bytes",
        "uncompressed_tar_stream_bytes",
    }
    if set(summary) != fields:
        return False
    for name in fields - {"compressed_sha256"}:
        if type(summary[name]) is not int or summary[name] < 0:
            return False
    sha = summary["compressed_sha256"]
    return type(sha) is str and re.fullmatch(r"[0-9A-F]{64}", sha) is not None


def run_layout_worker_supervised(
    archive_opener: Callable[[], BinaryIO],
    *,
    expected_bytes: int,
    expected_sha256: str,
    cwd: Path,
    log_path: Path,
    python_executable: Path,
    worker_path: Path,
    timeout_seconds: float,
    max_log_bytes: int = DEFAULT_LIMITS.max_execution_log_output_bytes,
    require_formal_windows: bool = True,
) -> WorkerRunObservation:
    """Run one contained worker; call ``archive_opener`` only after READY."""

    require(callable(archive_opener), "archive opener is not callable")
    require(type(expected_bytes) is int and expected_bytes > 0, "expected bytes differ")
    require(type(expected_sha256) is str and re.fullmatch(r"[0-9A-F]{64}", expected_sha256) is not None, "expected SHA256 differs")
    for path, label in ((cwd, "cwd"), (log_path, "log"), (python_executable, "Python"), (worker_path, "worker")):
        require(path.is_absolute(), f"{label} path must be absolute")
    require(cwd.is_dir() and not cwd.is_symlink(), "worker cwd differs")
    require(log_path.parent == cwd and log_path.name == FORMAL_LOG_NAME, "worker log path differs")
    require(not log_path.exists() and not log_path.is_symlink(), "worker log already exists")
    require(python_executable.is_file() and worker_path.is_file(), "worker executable/code differs")
    require(type(timeout_seconds) in {int, float} and 0 < timeout_seconds <= DEFAULT_LIMITS.max_elapsed_seconds, "timeout differs")
    require(type(max_log_bytes) is int and 0 < max_log_bytes <= DEFAULT_LIMITS.max_execution_log_output_bytes, "log cap differs")
    if require_formal_windows:
        require(os.name == "nt", "formal runner is Windows-only")

    started = time.monotonic()
    deadline = started + float(timeout_seconds)
    log_overflow = threading.Event()
    control_overflow = threading.Event()
    infrastructure_errors: list[BaseException] = []
    feeder_errors: list[BaseException] = []
    control_queue: queue.Queue[bytes | None] = queue.Queue()
    supplied_lock = threading.Lock()
    supplied_bytes = 0
    supplied_hash = hashlib.sha256()
    feeder_done = threading.Event()
    feeder_failure = threading.Event()
    archive_open_failure = threading.Event()
    feeder_deadline = threading.Event()
    feeder_started = False
    log_written = 0

    with log_path.open("xb", buffering=0) as log_stream:
        metadata = os.fstat(log_stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "worker log is not owned regular")
        child = (
            _spawn_windows_contained(
                python_executable,
                worker_path,
                cwd,
                expected_bytes,
                expected_sha256,
            )
            if os.name == "nt"
            else _spawn_posix_synthetic(
                python_executable,
                worker_path,
                cwd,
                expected_bytes,
                expected_sha256,
            )
        )
        if require_formal_windows:
            require(child.formally_contained, "formal worker lacks Job containment")

        def drain_log() -> None:
            nonlocal log_written
            try:
                while True:
                    block = child.stdout.read(65_536)
                    if not block:
                        return
                    remaining = max_log_bytes - log_written
                    kept = block[: max(0, remaining)]
                    if kept:
                        view = memoryview(kept)
                        offset = 0
                        while offset < len(view):
                            count = log_stream.write(view[offset:])
                            if type(count) is not int or count <= 0:
                                raise LayoutRunnerError("worker log write failed")
                            offset += count
                        log_written += len(kept)
                    if len(block) > remaining:
                        log_overflow.set()
            except BaseException as error:
                infrastructure_errors.append(error)

        def read_control() -> None:
            total = 0
            try:
                while True:
                    line = child.control.readline(MAX_CONTROL_BYTES + 1)
                    if not line:
                        control_queue.put(None)
                        return
                    total += len(line)
                    if len(line) > MAX_CONTROL_BYTES or total > MAX_CONTROL_BYTES:
                        control_overflow.set()
                        return
                    control_queue.put(line)
            except BaseException as error:
                infrastructure_errors.append(error)

        log_thread = threading.Thread(target=drain_log, name="round11-layout-log", daemon=True)
        control_thread = threading.Thread(target=read_control, name="round11-layout-control", daemon=True)
        log_thread.start()
        control_thread.start()

        ready = False
        terminal: Mapping[str, object] | None = None
        failure_code: str | None = None

        def terminate(code: str) -> None:
            nonlocal failure_code
            if failure_code is None:
                failure_code = code
            try:
                child.stdin.close()
            except OSError:
                pass
            child.terminate_tree()

        try:
            while not ready and failure_code is None:
                if time.monotonic() >= deadline:
                    terminate("READY_TIMEOUT")
                    break
                if log_overflow.is_set():
                    terminate("LOG_OVERFLOW")
                    break
                if control_overflow.is_set():
                    terminate("CONTROL_OVERFLOW")
                    break
                if infrastructure_errors:
                    terminate("CONTROL_THREAD_FAILURE")
                    break
                try:
                    line = control_queue.get(timeout=min(0.02, max(0.001, deadline - time.monotonic())))
                except queue.Empty:
                    if child.poll() is not None:
                        terminate("EXIT_BEFORE_READY")
                    continue
                if line is None:
                    terminate("CONTROL_EOF_BEFORE_READY")
                    break
                if line != READY_MESSAGE:
                    terminate("INVALID_READY")
                    break
                ready = True

            if ready and failure_code is None:
                def feed() -> None:
                    nonlocal supplied_bytes
                    try:
                        if time.monotonic() >= deadline:
                            feeder_deadline.set()
                            return
                        try:
                            source = archive_opener()
                        except BaseException as error:
                            feeder_errors.append(error)
                            archive_open_failure.set()
                            return
                        with source:
                            while True:
                                if time.monotonic() >= deadline:
                                    feeder_deadline.set()
                                    return
                                block = source.read(MIB)
                                if block is None:
                                    raise LayoutRunnerError("archive read returned None")
                                if not isinstance(block, bytes):
                                    raise LayoutRunnerError("archive read returned non-bytes")
                                if len(block) > MIB:
                                    raise LayoutRunnerError("archive opener exceeded read cap")
                                if not block:
                                    break
                                view = memoryview(block)
                                offset = 0
                                while offset < len(view):
                                    if time.monotonic() >= deadline:
                                        feeder_deadline.set()
                                        return
                                    written = child.stdin.write(view[offset:])
                                    if type(written) is not int or written <= 0:
                                        raise LayoutRunnerError("worker stdin write failed")
                                    piece = view[offset : offset + written]
                                    with supplied_lock:
                                        supplied_hash.update(piece)
                                        supplied_bytes += written
                                    offset += written
                        child.stdin.close()
                    except BrokenPipeError:
                        try:
                            child.stdin.close()
                        except OSError:
                            pass
                    except OSError as error:
                        try:
                            child.stdin.close()
                        except OSError:
                            pass
                        if child.poll() is None:
                            feeder_errors.append(error)
                            feeder_failure.set()
                    except BaseException as error:
                        feeder_errors.append(error)
                        feeder_failure.set()
                    finally:
                        feeder_done.set()

                feeder_started = True
                feeder_thread = threading.Thread(
                    target=feed, name="round11-layout-feeder", daemon=True
                )
                feeder_thread.start()

            while failure_code is None:
                if time.monotonic() >= deadline:
                    terminate("WORKER_TIMEOUT")
                    break
                if log_overflow.is_set():
                    terminate("LOG_OVERFLOW")
                    break
                if control_overflow.is_set():
                    terminate("CONTROL_OVERFLOW")
                    break
                if feeder_deadline.is_set():
                    terminate("WORKER_TIMEOUT")
                    break
                if archive_open_failure.is_set():
                    terminate("ARCHIVE_OPEN_FAILURE")
                    break
                if feeder_failure.is_set():
                    terminate("ARCHIVE_FEED_FAILURE")
                    break
                if infrastructure_errors:
                    terminate("SUPERVISOR_THREAD_FAILURE")
                    break
                try:
                    line = control_queue.get(timeout=0.02)
                except queue.Empty:
                    line = b""
                if line is None:
                    if child.poll() is not None:
                        break
                elif line:
                    if terminal is not None:
                        terminate("MULTIPLE_TERMINAL_MESSAGES")
                        break
                    try:
                        terminal = _parse_control_line(line)
                    except LayoutRunnerError:
                        terminate("INVALID_TERMINAL")
                        break
                code = child.poll()
                if code is not None and (not feeder_started or feeder_done.is_set()):
                    break

            returncode = child.poll()
            if returncode is None:
                terminate(failure_code or "WORKER_DID_NOT_EXIT")
                returncode = child.poll()
            assert returncode is not None
            if feeder_started:
                feeder_thread.join(timeout=10)
                if feeder_thread.is_alive():
                    child.terminate_tree()
                    raise LayoutRunnerError("archive feeder did not terminate")
            control_thread.join(timeout=10)
            log_thread.join(timeout=10)
            if control_thread.is_alive() or log_thread.is_alive():
                child.terminate_tree()
                raise LayoutRunnerError("supervisor drain thread did not terminate")
            if infrastructure_errors:
                raise LayoutRunnerError("supervisor thread failed") from infrastructure_errors[0]
            extra_control: list[bytes] = []
            while True:
                try:
                    queued = control_queue.get_nowait()
                except queue.Empty:
                    break
                if queued is not None:
                    extra_control.append(queued)
            if extra_control and failure_code is None:
                failure_code = "MULTIPLE_TERMINAL_MESSAGES"
            log_stream.flush()
            os.fsync(log_stream.fileno())

            with supplied_lock:
                observed_bytes = supplied_bytes
                observed_sha = supplied_hash.hexdigest().upper() if supplied_bytes else None
            finished_at = time.monotonic()
            if finished_at > deadline and failure_code is None:
                failure_code = "WORKER_TIMEOUT"
            complete = (
                failure_code is None
                and returncode == 0
                and terminal is not None
                and _terminal_is_complete(terminal)
                and observed_bytes == expected_bytes
                and observed_sha == expected_sha256
                and terminal["summary"]["compressed_bytes"] == observed_bytes  # type: ignore[index]
                and terminal["summary"]["compressed_sha256"] == observed_sha  # type: ignore[index]
            )
            if not complete and failure_code is None:
                if terminal is not None and terminal.get("event") == "ERROR":
                    if (
                        set(terminal) == {"code", "event", "schema_version"}
                        and terminal.get("code") in WORKER_ERROR_CODES
                    ):
                        code = terminal.get("code")
                        failure_code = (
                            code if type(code) is str else "INVALID_ERROR_TERMINAL"
                        )
                    else:
                        failure_code = "INVALID_ERROR_TERMINAL"
                else:
                    failure_code = "WORKER_COMPLETION_MISMATCH"
            return WorkerRunObservation(
                complete=complete,
                ready=ready,
                returncode=returncode,
                failure_code=None if complete else failure_code,
                supplied_bytes=observed_bytes,
                supplied_sha256=observed_sha,
                log_bytes=log_written,
                terminal=terminal,
                elapsed_seconds=finished_at - started,
                formally_contained=child.formally_contained,
            )
        except BaseException:
            child.terminate_tree()
            raise
        finally:
            child.close()
