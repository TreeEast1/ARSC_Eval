"""Process-level watchdog for the data-agnostic Round 11 layout worker."""

from __future__ import annotations

import os
import stat
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .round11_layout_inventory import DEFAULT_LIMITS


class LayoutWatchdogError(RuntimeError):
    """The isolated layout worker failed a watchdog invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LayoutWatchdogError(message)


@dataclass(frozen=True)
class WorkerOutcome:
    returncode: int
    elapsed_seconds: float
    log_bytes: int


def _terminate_exact(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as error:
        raise LayoutWatchdogError("isolated worker did not terminate after kill") from error


def run_worker_with_watchdog(
    argv: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    timeout_seconds: float,
    max_log_bytes: int = DEFAULT_LIMITS.max_execution_log_output_bytes,
    poll_seconds: float = 0.02,
) -> WorkerOutcome:
    """Run one exact non-shell worker with a hard parent-process deadline.

    Output is drained by a dedicated thread so a noisy worker cannot deadlock
    on a full pipe.  At most ``max_log_bytes`` are written to the owned log;
    overflow and timeout both kill the exact child and fail closed.
    """

    require(
        isinstance(argv, Sequence)
        and not isinstance(argv, (str, bytes))
        and bool(argv)
        and all(isinstance(item, str) and item != "" for item in argv),
        "worker argv is invalid",
    )
    require(cwd.is_absolute() and cwd.is_dir() and not cwd.is_symlink(), "worker cwd is invalid")
    require(log_path.is_absolute(), "worker log path must be absolute")
    require(log_path.parent == cwd, "worker log must be owned directly by cwd")
    require(log_path.name == "round11_daadx_layout_inventory.log", "worker log name differs")
    require(not log_path.exists() and not log_path.is_symlink(), "worker log already exists")
    require(
        isinstance(timeout_seconds, (int, float))
        and 0 < timeout_seconds <= DEFAULT_LIMITS.max_elapsed_seconds,
        "worker timeout exceeds frozen range",
    )
    require(
        isinstance(max_log_bytes, int)
        and 0 < max_log_bytes <= DEFAULT_LIMITS.max_execution_log_output_bytes,
        "worker log cap exceeds frozen range",
    )
    require(isinstance(poll_seconds, (int, float)) and 0 < poll_seconds <= 1, "poll interval is invalid")

    overflow = threading.Event()
    reader_error: list[BaseException] = []
    written = 0
    started = time.monotonic()
    with log_path.open("xb", buffering=0) as log_stream:
        metadata = os.fstat(log_stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "worker log is not owned regular file")
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=False,
            bufsize=0,
        )
        assert process.stdout is not None

        def drain() -> None:
            nonlocal written
            try:
                while True:
                    block = process.stdout.read(65_536)
                    if not block:
                        return
                    remaining = max_log_bytes - written
                    if remaining > 0:
                        kept = block[:remaining]
                        view = memoryview(kept)
                        offset = 0
                        while offset < len(view):
                            count = log_stream.write(view[offset:])
                            if not isinstance(count, int) or count <= 0:
                                raise LayoutWatchdogError("short or invalid worker-log write")
                            offset += count
                        written += offset
                    if len(block) > remaining:
                        overflow.set()
            except BaseException as error:
                reader_error.append(error)

        reader = threading.Thread(target=drain, name="round11-layout-log-drain", daemon=True)
        reader.start()
        timed_out = False
        try:
            while True:
                if overflow.is_set():
                    _terminate_exact(process)
                    break
                elapsed = time.monotonic() - started
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    timed_out = True
                    _terminate_exact(process)
                    break
                try:
                    process.wait(timeout=min(poll_seconds, remaining))
                except subprocess.TimeoutExpired:
                    continue
                # A child that exits after the deadline must not become a
                # success merely because poll()/wait() now reports completion.
                if time.monotonic() - started > timeout_seconds:
                    timed_out = True
                break
        except BaseException:
            _terminate_exact(process)
            raise
        finally:
            reader.join(timeout=10)
            if reader.is_alive():
                _terminate_exact(process)
                process.stdout.close()
                reader.join(timeout=1)
                raise LayoutWatchdogError("worker log drain did not terminate")
            process.stdout.close()
            log_stream.flush()
            os.fsync(log_stream.fileno())

    elapsed = time.monotonic() - started
    require(not reader_error, "worker log drain failed")
    require(not timed_out, "isolated worker exceeded elapsed-time cap")
    require(not overflow.is_set(), "isolated worker exceeded execution-log cap")
    require(process.returncode == 0, f"isolated worker exited nonzero: {process.returncode}")
    return WorkerOutcome(
        returncode=process.returncode,
        elapsed_seconds=elapsed,
        log_bytes=written,
    )
