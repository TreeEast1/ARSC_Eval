"""Focused synthetic tests for the Round 12 protocol-freezing layer.

These tests drive the corrected **canonical-only** freeze script.  That script
has no ``--output``/``git_value`` indirection: it always writes the one frozen
protocol to the canonical ``DEFAULT_OUTPUT`` path.  Here that path (and
``ROOT``, ``DECISION_PATH``, ``MEMO_PATH``, ``PRIMITIVES_PATH``,
``BOOTSTRAP_DRAWS_PATH``) are redirected to a synthetic temporary root with
matching synthetic inputs, so no real artifact is produced or touched.

What is verified:
  * ``main([])`` is deterministic and idempotent;
  * arbitrary CLI arguments are rejected (no ``--output`` escape hatch);
  * SHA / decision-schema / unexpected-NPZ-key mismatches silently write nothing;
  * ``npz_schema`` is header-only: it works even when ``np.load`` is made to
    fail, yet it still rejects duplicate / non-``.npy`` / object / unsupported-
    version archives;
  * a symlink or non-regular output path fails closed (where portable);
  * the frozen protocol carries the exact margins, gates, lower-quantile and
    ``authorization: False`` fields;
  * the executable freeze source makes no forbidden imports/calls (only the
    frozen policy *strings* mention DAAD-X/model/checkpoint boundaries, which
    are data, not executable paths).
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import subprocess  # noqa: F401  (kept for parity with the legacy harness layout)
import sys
import tokenize
import warnings
import zipfile
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_round12_existing_outputs_protocol as freeze  # noqa: E402

_REAL_DECISION_PATH = (
    ROOT / "outputs/validity/round12_existing_outputs_reviewer_decision.json"
)
_REAL_DECISION = json.loads(_REAL_DECISION_PATH.read_text(encoding="utf-8"))


class Env(NamedTuple):
    root: Path
    decision: dict[str, Any]
    primitives: Path
    draws: Path
    decision_path: Path
    memo_path: Path
    default_output: Path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_allowlist_npz(path: Path, allowlist: dict[str, tuple[list[int], str]]) -> Path:
    """Write an NPZ whose key/shape/dtype exactly match an allowlist."""
    arrays: dict[str, np.ndarray] = {}
    for key, (shape, dtype) in allowlist.items():
        if shape == []:  # 0-d scalar arrays (schema_version entries)
            arrays[key] = np.zeros((), dtype=dtype)
        else:
            arrays[key] = np.zeros(tuple(shape), dtype=dtype)
    np.savez(path, **arrays)
    return path


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    extra_primitives_keys: bool = False,
    tamper_input_sha: bool = False,
    wrong_schema: bool = False,
    authorize_execution: bool = False,
    memo_mismatch: bool = False,
) -> Env:
    """Create synthetic inputs and redirect the script's module globals.

    The two NPZ archives are built to satisfy :func:`expected_r12_npz_allowlists`
    so that ``main([])`` can actually complete when nothing is tampered.
    """
    allowlists = freeze.expected_r12_npz_allowlists()
    prim_allow = dict(allowlists[freeze.relative(freeze.PRIMITIVES_PATH)])
    draw_allow = dict(allowlists[freeze.relative(freeze.BOOTSTRAP_DRAWS_PATH)])
    if extra_primitives_keys:
        prim_allow["sneaky_extra"] = ([1], "float64")

    primitives = tmp_path / "round10_corruption_primitives.npz"
    draws = tmp_path / "round10_corruption_bootstrap_draws.npz"
    decision_path = tmp_path / "round12_existing_outputs_reviewer_decision.json"
    # Keep the memo at the same ROOT-relative path as the real binding
    # (outputs/...), so relative(MEMO_PATH) matches decision["memo"]["path"].
    memo_path = (
        tmp_path / "outputs" / "research_review_memo_round12_existing_outputs_direction.md"
    )
    default_output = (
        tmp_path / "outputs" / "validity" / "round12_existing_outputs_frozen_protocol.json"
    )

    _write_allowlist_npz(primitives, prim_allow)
    _write_allowlist_npz(draws, draw_allow)

    # Five dummy evidence files (they only need to exist and hash-match).
    dummy_contents: dict[str, bytes] = {
        "outputs/validity/round10_corruption_results.json": b"{}",
        "outputs/validity/round10_corruption_dose_response_protocol_amendment01.json": b"{}",
        "outputs/validity/rq1_multiseed_frozen_protocol.json": b"{}",
        "outputs/validity/rq1_multiseed_summary.json": b"{}",
        "outputs/validity/round10_postresult_reviewer_decision.json": b"{}",
    }
    dummy_paths: list[Path] = []
    for rel, content in dummy_contents.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        dummy_paths.append(p)

    memo_path.parent.mkdir(parents=True, exist_ok=True)
    memo_path.write_bytes(b"MEMO CONTENT")
    memo_sha = _sha256_file(memo_path)

    decision = copy.deepcopy(_REAL_DECISION)
    evidence = [
        {
            "path": str(primitives.relative_to(tmp_path)),
            "sha256": _sha256_file(primitives),
            "sufficiency": "synthetic primitives",
        },
        {
            "path": str(draws.relative_to(tmp_path)),
            "sha256": _sha256_file(draws),
            "sufficiency": "synthetic draws",
        },
    ] + [
        {
            "path": str(p.relative_to(tmp_path)),
            "sha256": _sha256_file(p),
            "sufficiency": "synthetic evidence",
        }
        for p in dummy_paths
    ]
    decision["input_evidence"] = evidence
    decision["memo"]["sha256"] = memo_sha

    if tamper_input_sha:
        decision["input_evidence"][0]["sha256"] = "0" * 64
    if wrong_schema:
        decision["schema_version"] = "WRONG"
    if authorize_execution:
        decision["implementation_authorized_by_this_decision"] = True
    if memo_mismatch:
        # Decision still references its bound memo sha, but the file on disk is
        # different, so build_protocol must fail closed on the memo hash.
        decision["memo"]["sha256"] = "1" * 64

    # Persist the (possibly mutated) synthetic decision to the redirected
    # DECISION_PATH so main([]) reads exactly what each test intends.
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "PRIMITIVES_PATH", primitives)
    monkeypatch.setattr(freeze, "BOOTSTRAP_DRAWS_PATH", draws)
    monkeypatch.setattr(freeze, "DECISION_PATH", decision_path)
    monkeypatch.setattr(freeze, "MEMO_PATH", memo_path)
    monkeypatch.setattr(freeze, "DEFAULT_OUTPUT", default_output)

    return Env(
        root=tmp_path,
        decision=decision,
        primitives=primitives,
        draws=draws,
        decision_path=decision_path,
        memo_path=memo_path,
        default_output=default_output,
    )


def _code_without_strings_and_comments(source: str) -> str:
    """Return only executable tokens (drop string literals and comments)."""
    tokens: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            continue
        tokens.append(tok.string)
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Canonical-only invocation contract
# ---------------------------------------------------------------------------


def test_main_is_deterministic_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)

    assert freeze.main([]) == 0
    assert env.default_output.exists()
    first = env.default_output.read_bytes()

    # Re-invoking leaves identical bytes (idempotent) and returns success.
    assert freeze.main([]) == 0
    assert env.default_output.read_bytes() == first

    # A third invocation is still stable and byte-identical.
    assert freeze.main([]) == 0
    assert env.default_output.read_bytes() == first


def test_arbitrary_args_are_rejected(tmp_path: Path) -> None:
    # The corrected script has no --output escape hatch; any argv is rejected.
    with pytest.raises(SystemExit):
        freeze.parse_args(["--output", str(tmp_path / "elsewhere.json")])
    with pytest.raises(SystemExit):
        freeze.main(["--output", str(tmp_path / "elsewhere.json")])


# ---------------------------------------------------------------------------
# Fail-closed correctness: nothing is written on mismatch
# ---------------------------------------------------------------------------


def test_input_sha_mismatch_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch, tamper_input_sha=True)
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        freeze.main([])
    assert not env.default_output.exists()


def test_decision_schema_mismatch_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch, wrong_schema=True)
    with pytest.raises(ValueError, match="reviewer decision schema"):
        freeze.main([])
    assert not env.default_output.exists()


def test_unexpected_npz_key_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch, extra_primitives_keys=True)
    with pytest.raises(ValueError, match="unexpected NPZ key set"):
        freeze.main([])
    assert not env.default_output.exists()


def test_upholds_decision_boundary_not_authorizing_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A decision that tries to self-authorize implementation must be rejected.
    env = _setup_env(tmp_path, monkeypatch, authorize_execution=True)
    with pytest.raises(ValueError, match="must not itself authorize"):
        freeze.main([])
    assert not env.default_output.exists()


def test_memo_hash_mismatch_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch, memo_mismatch=True)
    with pytest.raises(ValueError, match="memo SHA256 differs"):
        freeze.main([])
    assert not env.default_output.exists()


# ---------------------------------------------------------------------------
# Structural (header-only) NPZ inspection
# ---------------------------------------------------------------------------


def test_npz_schema_is_header_only_even_when_np_load_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    small = tmp_path / "small.npz"
    np.savez(small, a=np.zeros(3), b=np.array("z", dtype="U4"))

    # npz_schema ends by computing a ROOT-relative path; redirect ROOT so the
    # header-only result resolves under the synthetic tmp root.
    monkeypatch.setattr(freeze, "ROOT", tmp_path)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("np.load must never be called during schema inspection")

    monkeypatch.setattr(np, "load", _boom)

    schema = freeze.npz_schema(small)
    assert schema["key_count"] == 2
    observed = freeze.items_map(schema)
    assert observed["a"] == ([3], "float64")
    assert observed["b"] == ([], "<U4")


def test_duplicate_npz_member_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.npz"
    payload = b"\x93NUMPY\x01\x00" + b"\x00\x00"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("k.npy", payload)
            archive.writestr("k.npy", payload)
    with pytest.raises(ValueError, match="duplicate NPZ"):
        freeze.npz_schema(path)


def test_non_npy_member_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "nonnpy.npz"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", b"not an array")
    with pytest.raises(ValueError, match="non-\\.npy entry"):
        freeze.npz_schema(path)


def test_object_dtype_fails_closed(tmp_path: Path) -> None:
    buf = io.BytesIO()
    np.lib.format.write_array(buf, np.array([object()], dtype=object), allow_pickle=True)
    obj_npy = buf.getvalue()
    path = tmp_path / "object.npz"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("k.npy", obj_npy)
    with pytest.raises(ValueError, match="object dtype not allowed"):
        freeze.npz_schema(path)


def test_unsupported_npy_version_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.npz"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        # Magic prefix + major=1, minor=3 (neither 1.0 nor 2.0).
        archive.writestr("k.npy", b"\x93NUMPY" + bytes([1, 3]) + b"xxxx")
    with pytest.raises(ValueError, match="unsupported NPY format version"):
        freeze.npz_schema(path)


# ---------------------------------------------------------------------------
# Symlink / non-regular output handling (portable)
# ---------------------------------------------------------------------------


def test_symlink_output_fails_closed_if_portable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"{}")
    link = tmp_path / "frozen.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")

    monkeypatch.setattr(freeze, "DEFAULT_OUTPUT", link)
    with pytest.raises(ValueError, match="symlink"):
        freeze.main([])


def test_nonregular_output_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "outdir"
    directory.mkdir()
    monkeypatch.setattr(freeze, "DEFAULT_OUTPUT", directory)
    with pytest.raises(ValueError, match="regular file"):
        freeze.main([])


def test_os_replace_failure_leaves_no_output_or_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)

    def _boom(src: Any, dst: Any) -> Any:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="simulated replace failure"):
        freeze.main([])

    # Atomic write must fail closed: neither the canonical output nor the
    # staged .tmp sibling may remain behind.
    assert not env.default_output.exists()
    assert not env.default_output.with_name(env.default_output.name + ".tmp").exists()


# ---------------------------------------------------------------------------
# Exact frozen policy
# ---------------------------------------------------------------------------


def _built_protocol(env: Env) -> dict[str, Any]:
    return freeze.build_protocol(
        env.decision,
        freeze.verify_input_hashes(env.decision),
        freeze.npz_schema(env.primitives),
        freeze.npz_schema(env.draws),
        generated_at=freeze.generated_at_from(env.decision),
    )


def test_exact_margins_gates_q_and_authorization_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    protocol = _built_protocol(env)

    margins = protocol["margins_and_guardrails"]
    assert margins["practical_margin"] == 0.01
    assert margins["c1_point_minimum"] == 0.01
    assert margins["c1_lower_bound_strict_positive"] is True
    assert margins["c1_minimum_positive_seeds"] == 4
    assert margins["c1_family_guardrail_floor"] == -0.01
    assert margins["ar_s_non_inferiority_floor"] == -0.01

    gates = protocol["gates"]
    assert len(gates["PASS"]) == 7
    assert "q=0.0125 lower bound > 0.0" in gates["PASS"][1]
    assert "at least four of five seed-specific D_C1 values > 0.0" in gates["PASS"][2]
    assert "each of three family-specific D_C1 values >= -0.01" in gates["PASS"][3]
    assert "D_A" in gates["PASS"][4] and "-0.01" in gates["PASS"][4]
    assert "PARTIAL" in gates and "FAIL" in gates

    quantile = protocol["bootstrap"]["quantile"]
    assert quantile["lower_quantile"] == 0.0125
    assert quantile["method"] == "linear"
    assert protocol["bootstrap"]["replicates"] == 5000

    auth = protocol["authorization"]
    assert auth["implementation_authorized_by_this_decision"] is False
    assert auth["implementation_authorized"] is False
    assert auth["execution_authorized"] is False

    # Canonical-only: the output allowlist is exactly the single frozen file.
    assert protocol["output_allowlist"] == [
        "outputs/validity/round12_existing_outputs_frozen_protocol.json"
    ]
    assert protocol["execution"]["outcome_computed"] is False
    assert protocol["execution"]["bootstrap_executed"] is False
    assert protocol["state"]["result_blind"] is True


def test_frozen_protocol_parameters_round_trip_via_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    assert freeze.main([]) == 0
    written = json.loads(env.default_output.read_text(encoding="utf-8"))
    assert written["margins_and_guardrails"]["practical_margin"] == 0.01
    assert written["bootstrap"]["quantile"]["lower_quantile"] == 0.0125
    assert written["authorization"]["execution_authorized"] is False


# ---------------------------------------------------------------------------
# Forbidden executable access only — not the frozen policy strings
# ---------------------------------------------------------------------------


def test_forbidden_executable_imports_and_calls_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The frozen protocol (data) may and should mention the boundary policy.
    env = _setup_env(tmp_path, monkeypatch)
    protocol = _built_protocol(env)
    forbidden_text = " ".join(protocol["forbidden_actions"]).lower()
    assert "no daad-x data access" in forbidden_text
    assert "no model or checkpoint loading" in forbidden_text
    assert "no bootstrap execution" in forbidden_text

    # But the executable source must contain no forbidden import or call.
    source = (ROOT / "scripts/freeze_round12_existing_outputs_protocol.py").read_text(
        encoding="utf-8"
    )
    executable = _code_without_strings_and_comments(source)
    forbidden_patterns = [
        r"import\s+torch\b",
        r"^\s*from\s+torch\b",
        r"\btorch\.",
        r"\bdaadx\b",
        r"Image\.open\(",
        r"\bcheckpoint\b",
        r"\.pth\b",
        r"\.pt\b",
        r"\bmodels\b",
        r"model\.eval\(",
        r"\.train\(",
        r"np\.load\(",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, executable), (
            f"forbidden executable reference in freeze source: {pattern!r}"
        )
