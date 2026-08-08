"""Tests for the Round 13 stage-1 read-only preflight.

Covers: all eight frozen rule templates and the hand-written evaluator; the
full 32-world compile to four action truth bits per world; the exact
deterministic summary; bad protocol SHA-256, bad canonical encoding, bad
bound-source hash, bad schema/result-blind, and present-formal-artifact
failures; and the static absence of forbidden data paths / write APIs in the
two preflight source files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

import arsc_eval.round13_preflight as preflight

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / preflight.PROTOCOL_REL
CORE_PATH = ROOT / "src/arsc_eval/round13_preflight.py"
CLI_PATH = ROOT / "scripts/preflight_round13_protocol.py"


# ---------------------------------------------------------------------------
# Rule-template evaluator coverage.
# ---------------------------------------------------------------------------
def test_evaluator_covers_all_frozen_rule_templates() -> None:
    assert set(preflight.RULE_BANK) == {
        "x0 AND x1",
        "x0 OR x1",
        "x0 XOR x1",
        "MAJORITY(x0,x1,x2)",
        "x0 AND (x1 OR x2)",
        "(x0 AND x1) OR (x2 AND x3)",
        "PARITY(x0,x1,x2)",
        "MAJORITY(x0,x1,x2,x3)",
    }


@pytest.mark.parametrize(
    ("template", "values", "expected"),
    [
        ("x0 AND x1", [True, True], True),
        ("x0 AND x1", [True, False], False),
        ("x0 OR x1", [False, False], False),
        ("x0 OR x1", [False, True], True),
        ("x0 XOR x1", [True, True], False),
        ("x0 XOR x1", [False, True], True),
        ("MAJORITY(x0,x1,x2)", [True, False, False], False),
        ("MAJORITY(x0,x1,x2)", [True, True, False], True),
        ("x0 AND (x1 OR x2)", [True, True, False], True),
        ("x0 AND (x1 OR x2)", [True, False, False], False),
        ("(x0 AND x1) OR (x2 AND x3)", [True, False, True, True], True),
        ("(x0 AND x1) OR (x2 AND x3)", [True, False, False, True], False),
        ("PARITY(x0,x1,x2)", [True, False, True], False),
        ("PARITY(x0,x1,x2)", [True, False, False], True),
        ("MAJORITY(x0,x1,x2,x3)", [True, True, False, False], False),
        ("MAJORITY(x0,x1,x2,x3)", [True, True, False, True], True),
    ],
)
def test_evaluator_and_compiled_match(
    template: str, values: list[bool], expected: bool
) -> None:
    assert preflight.evaluate_template(template, values) is expected
    assert preflight.compile_template(template)(values) is expected


def test_rule_templates_used_across_worlds_are_all_frozen() -> None:
    protocol = json.loads(PROTOCOL_PATH.read_bytes().decode("utf-8"))
    seen: set[str] = set()
    for world in protocol["design"]["worlds"]:
        seen.update(world["action_rule_templates"])
    assert seen == set(preflight.RULE_BANK)


# ---------------------------------------------------------------------------
# Full 32-world compile.
# ---------------------------------------------------------------------------
def test_full_32_world_compile_and_deterministic_summary() -> None:
    summary = preflight.run_preflight(ROOT)
    assert summary["world_count"] == 32
    assert summary["total_rows"] == 32 * 1024
    assert summary["action_bits_total"] == 4 * 32 * 1024
    assert summary["rule_templates_all_frozen"] is True
    assert summary["instantiated_expressions_verified"] is True
    assert summary["rationale_supports_verified"] is True
    # Determinism: running twice must give the identical summary.
    assert summary == preflight.run_preflight(ROOT)


def test_exact_deterministic_summary() -> None:
    summary = preflight.run_preflight(ROOT)
    assert summary["status"] == "PREFLIGHT_STAGE1_PASS"
    assert summary["protocol_sha256"] == preflight.EXPECTED_PROTOCOL_SHA256
    assert summary["schema_version"] == preflight.EXPECTED_PROTOCOL_SCHEMA
    assert summary["result_blind"] is True
    assert summary["replacement_cells"] == 3072
    assert summary["bound_source_count"] == 3
    assert summary["bound_sources_match"] is True
    assert summary["formal_artifacts_present"] is False
    assert summary["rule_templates_covered"] == 8
    assert summary["total_rows"] == 32768
    assert summary["action_bits_total"] == 131072
    assert summary["action_ones_total"] == 61568
    assert summary["action_prevalence"] == pytest.approx(0.469726562)
    assert summary["per_action_ones"] == [15808, 15616, 14784, 15360]
    assert summary["per_action_prevalence"] == [
        pytest.approx(0.482421875),
        pytest.approx(0.4765625),
        pytest.approx(0.451171875),
        pytest.approx(0.46875),
    ]
    assert summary["preflight_status_is_only_stage1"] is True
    # Stage-1 status is neither GO_RUN nor a scientific verdict.
    assert summary["status"] != "GO_RUN"
    assert summary["status"] not in (
        "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS",
        "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED",
    )


# ---------------------------------------------------------------------------
# Failure paths (bad hash / canonical / source hash / schema / formal artifact).
# ---------------------------------------------------------------------------
def test_bad_protocol_sha256_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="SHA-256 differs"):
        monkeypatch.setattr(
            preflight, "EXPECTED_PROTOCOL_SHA256", "0" * 64
        )
        preflight.run_preflight(ROOT)


def test_bad_canonical_encoding_fails(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Non-canonical but valid JSON (embedded whitespace) in a temp file whose
    # digest we pin so only the canonical round-trip check fails.
    noncanonical = b'{"a": 1, "b": [1, 2, 3]}\n'
    target = tmp_path / "protocol.json"
    target.write_bytes(noncanonical)
    monkeypatch.setattr(
        preflight,
        "EXPECTED_PROTOCOL_SHA256",
        hashlib.sha256(noncanonical).hexdigest().upper(),
    )
    with pytest.raises(ValueError, match="canonical JSON"):
        preflight.verify_protocol_bytes(target)


def test_bad_bound_source_hash_fails() -> None:
    one_source = preflight.BOUND_SOURCES_REL[0]
    protocol_path = ROOT / preflight.PROTOCOL_REL
    fake_protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    fake_protocol["provenance"]["bound_sources"][one_source.as_posix()] = "0" * 64
    with pytest.raises(ValueError, match="bound source SHA-256 differs"):
        preflight.verify_bound_sources(fake_protocol, ROOT)


def test_bad_schema_and_result_blind_fail() -> None:
    with pytest.raises(ValueError, match="schema version differs"):
        preflight.verify_protocol_header({"schema_version": "wrong", "result_blind": True})
    with pytest.raises(ValueError, match="result-blind"):
        preflight.verify_protocol_header(
            {
                "schema_version": preflight.EXPECTED_PROTOCOL_SCHEMA,
                "result_blind": False,
            }
        )


def test_present_formal_artifact_fails(tmp_path) -> None:
    artifact = (
        tmp_path
        / "outputs/validity/round13_synthetic_mtmm_formal_claim.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="formal artifact already present"):
        preflight.verify_formal_artifacts_absent(tmp_path)


def test_dangling_formal_symlink_fails(tmp_path) -> None:
    artifact = tmp_path / "outputs/validity/round13_synthetic_mtmm_formal_claim.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(artifact.parent / "missing-target.json", artifact)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    assert artifact.is_symlink() and not artifact.exists()
    with pytest.raises(ValueError, match="formal artifact already present"):
        preflight.verify_formal_artifacts_absent(tmp_path)


# ---------------------------------------------------------------------------
# Static absence of forbidden data paths / write APIs.
# ---------------------------------------------------------------------------
_FORBIDDEN_PATTERNS = (
    re.compile(r"data/external"),
    re.compile(r"DAAD"),
    re.compile(r"daadx"),
    re.compile(r"download"),
    re.compile(r"requests\."),
    re.compile(r"urllib"),
    re.compile(r"torch"),
    re.compile(r"numpy"),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"open\([^\n]*['](?:w|w\+|wb|ab|r\+)[']"),
    re.compile(r"open\([^\n]*[\"](?:w|w\+|wb|ab|r\+)[\"]"),
    re.compile(r"\.write_bytes\("),
    re.compile(r"\.write_text\("),
    re.compile(r"os\.write\("),
    re.compile(r"os\.makedirs\("),
    re.compile(r"subprocess"),
    re.compile(r"shutil"),
    re.compile(r"tempfile"),
)


def _assert_statically_clean(path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        assert pattern.search(text) is None, (
            f"{path.name} contains forbidden pattern {pattern.pattern}"
        )


def test_core_module_has_no_forbidden_paths_or_write_apis() -> None:
    _assert_statically_clean(CORE_PATH)


def test_cli_has_no_forbidden_paths_or_write_apis() -> None:
    _assert_statically_clean(CLI_PATH)


def test_protocol_is_compact_canonical_and_authentic() -> None:
    raw = PROTOCOL_PATH.read_bytes()
    assert preflight.canonical_json_bytes(json.loads(raw.decode("utf-8"))) == raw
    assert hashlib.sha256(raw).hexdigest().upper() == (
        "7C32F1DB779B1D99FA7118E496196DD325930E169055637639AE66806DF4890C"
    )
