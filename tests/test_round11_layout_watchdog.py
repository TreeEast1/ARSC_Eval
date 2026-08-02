from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from arsc_eval.round11_layout_watchdog import (  # noqa: E402
    LayoutWatchdogError,
    run_worker_with_watchdog,
)


def _log(root: Path) -> Path:
    return (root / "round11_daadx_layout_inventory.log").resolve()


def test_successful_worker_is_logged_without_shell(tmp_path: Path) -> None:
    outcome = run_worker_with_watchdog(
        [sys.executable, "-c", "print('synthetic-ok')"],
        cwd=tmp_path.resolve(),
        log_path=_log(tmp_path),
        timeout_seconds=5,
    )
    assert outcome.returncode == 0
    assert outcome.log_bytes == len(b"synthetic-ok\r\n") or outcome.log_bytes == len(
        b"synthetic-ok\n"
    )
    assert _log(tmp_path).read_text(encoding="utf-8").strip() == "synthetic-ok"


def test_parent_watchdog_kills_blocked_worker(tmp_path: Path) -> None:
    started = time.monotonic()
    with pytest.raises(LayoutWatchdogError, match="elapsed-time"):
        run_worker_with_watchdog(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=tmp_path.resolve(),
            log_path=_log(tmp_path),
            timeout_seconds=0.05,
            poll_seconds=0.005,
        )
    assert time.monotonic() - started < 3
    assert _log(tmp_path).is_file()


def test_child_exit_after_deadline_cannot_win_poll_race(tmp_path: Path) -> None:
    with pytest.raises(LayoutWatchdogError, match="elapsed-time"):
        run_worker_with_watchdog(
            [sys.executable, "-c", "import time; time.sleep(0.07)"],
            cwd=tmp_path.resolve(),
            log_path=_log(tmp_path),
            timeout_seconds=0.05,
            poll_seconds=0.2,
        )


def test_noisy_worker_is_killed_and_log_never_exceeds_cap(tmp_path: Path) -> None:
    with pytest.raises(LayoutWatchdogError, match="execution-log cap"):
        run_worker_with_watchdog(
            [
                sys.executable,
                "-c",
                "import sys,time; sys.stdout.buffer.write(b'x'*100000); sys.stdout.flush(); time.sleep(10)",
            ],
            cwd=tmp_path.resolve(),
            log_path=_log(tmp_path),
            timeout_seconds=5,
            max_log_bytes=64,
            poll_seconds=0.005,
        )
    assert _log(tmp_path).stat().st_size == 64


def test_nonzero_worker_fails_closed_and_preserves_log(tmp_path: Path) -> None:
    with pytest.raises(LayoutWatchdogError, match="exited nonzero: 7"):
        run_worker_with_watchdog(
            [sys.executable, "-c", "print('failed'); raise SystemExit(7)"],
            cwd=tmp_path.resolve(),
            log_path=_log(tmp_path),
            timeout_seconds=5,
        )
    assert "failed" in _log(tmp_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", ["timeout", "log"])
def test_watchdog_caps_cannot_be_raised_before_log_creation(
    tmp_path: Path, kind: str
) -> None:
    kwargs = {
        "timeout_seconds": 21_601 if kind == "timeout" else 1,
        "max_log_bytes": 16_777_217 if kind == "log" else 1,
    }
    with pytest.raises(LayoutWatchdogError, match="frozen range"):
        run_worker_with_watchdog(
            [sys.executable, "-c", "raise AssertionError('must not run')"],
            cwd=tmp_path.resolve(),
            log_path=_log(tmp_path),
            **kwargs,
        )
    assert not _log(tmp_path).exists()
