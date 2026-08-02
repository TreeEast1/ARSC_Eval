from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from arsc_eval import round11_layout_worker as worker  # noqa: E402


def test_ready_message_is_fixed_canonical_and_path_free() -> None:
    value = json.loads(worker.READY_MESSAGE)
    assert value == {"event": "READY", "schema_version": worker.CONTROL_SCHEMA}
    assert worker.READY_MESSAGE == worker._canonical(value)
    assert b"/" not in worker.READY_MESSAGE and b"\\" not in worker.READY_MESSAGE


def test_worker_argv_contract_is_exact() -> None:
    parsed = worker._parse_argv(
        ["--control-fd", "7", "--expected-bytes", "123", "--expected-sha256", "A" * 64]
    )
    assert parsed == ("--control-fd", "7", 123, "A" * 64)
    with pytest.raises(ValueError):
        worker._parse_argv(
            ["--control-fd", "7", "--expected-bytes", "0123", "--expected-sha256", "A" * 64]
        )


def test_terminal_error_allowlist_has_no_dynamic_text() -> None:
    for code in ("PARSER_REJECTED", "WORKER_CONTROL_FAILURE"):
        value = worker._terminal_error(code)
        assert value == worker._canonical(
            {"code": code, "event": "ERROR", "schema_version": worker.CONTROL_SCHEMA}
        )
        assert b"/" not in value and b"\\" not in value
    with pytest.raises(ValueError, match="error code"):
        worker._terminal_error("PRIVATE/PATH")
