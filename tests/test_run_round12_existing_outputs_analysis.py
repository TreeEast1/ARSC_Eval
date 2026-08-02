"""Focused authorization-gate tests for the Round 12 existing-outputs runner.

These tests drive ``scripts/run_round12_existing_outputs_analysis.py`` as a
pure gate: nothing is imported from NumPy and no real artifact is read or
written.  Every canonical path binding (:data:`~runner.BINDING_PATHS`) is
temporarily monkeypatched to a synthetic tree rooted under ``tmp_path``, and
a matching synthetic GO_RUN JSON, frozen protocol, direction decision and
protocol prereview decision are produced so the gate can be exercised exactly
as :func:`~runner.authorize_before_data_access` expects it to be enforced.

Coverage (all fail-closed paths plus the one authorized path):

* missing GO_RUN document;
* valid GO_RUN -> gate passes, then ``main`` stops with
  ``NOT_IMPLEMENTED_AFTER_GATE``;
* duplicate binding key;
* wrong on-disk SHA-256;
* wrong binding path / schema / decision;
* protocol state (status, result-blind, formal-run/outcome/bootstrap fields);
* direction decision and protocol prereview decision validation;
* symlink and non-regular binding path rejection;
* extra CLI argv rejection;
* no NumPy source: ``authorize_before_data_access`` never imports numpy and
  never calls ``numpy.load``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_round12_existing_outputs_analysis as runner  # noqa: E402
import arsc_eval.round12_existing_outputs as round12_core  # noqa: E402
import arsc_eval.round12_output_serializers as output_serializers  # noqa: E402
from arsc_eval.round12_existing_outputs import REQUIRED_INPUT_KEYS  # noqa: E402


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


class Env:
    """Synthetic tree plus the relative paths the gate will hash-bind."""

    def __init__(self, root: Path):
        self.root = root
        # Canonical ROOT-relative file locations for every binding key.
        self.paths: dict[str, Path] = {
            "runner": root / "scripts" / "run_round12_existing_outputs_analysis.py",
            "round12-core": root / "src" / "arsc_eval" / "round12_existing_outputs.py",
            "canonical-metrics": root / "src" / "arsc_eval" / "corruption_statistics.py",
            "runner-tests": root / "tests" / "test_run_round12_existing_outputs_analysis.py",
            "core-tests": root / "tests" / "test_round12_existing_outputs.py",
            "output-serializer": root / "src" / "arsc_eval" / "round12_output_serializers.py",
            "output-serializer-tests": root / "tests" / "test_round12_output_serializers.py",
            "frozen-protocol": (
                root / "outputs" / "validity" / "round12_existing_outputs_frozen_protocol.json"
            ),
            "direction-decision": (
                root / "outputs" / "validity" / "round12_existing_outputs_reviewer_decision.json"
            ),
            "protocol-prereview": (
                root / "outputs" / "validity" / "round12_frozen_protocol_reviewer_decision.json"
            ),
            "primitives": (
                root
                / "outputs"
                / "validity"
                / "round10_corruption_formal_attempt02"
                / "round10_corruption_primitives.npz"
            ),
            "draws": (
                root
                / "outputs"
                / "validity"
                / "round10_corruption_formal_attempt02"
                / "round10_corruption_bootstrap_draws.npz"
            ),
        }


_KEY_TO_ATTR = {
    "runner": "RUNNER_PATH",
    "round12-core": "ROUND12_CORE_PATH",
    "canonical-metrics": "CANONICAL_METRICS_PATH",
    "runner-tests": "RUNNER_TESTS_PATH",
    "core-tests": "CORE_TESTS_PATH",
    "output-serializer": "OUTPUT_SERIALIZER_PATH",
    "output-serializer-tests": "OUTPUT_SERIALIZER_TESTS_PATH",
    "frozen-protocol": "PROTOCOL_PATH",
    "direction-decision": "DIRECTION_DECISION_PATH",
    "protocol-prereview": "PROTOCOL_PREREVIEW_PATH",
    "primitives": "PRIMITIVES_PATH",
    "draws": "DRAWS_PATH",
}


def _attr_for_key(key: str) -> str:
    return _KEY_TO_ATTR[key]


def _write_file(path: Path, content: bytes | str) -> Path:
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_object_document(path: Path, payload: dict) -> Path:
    _write_file(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + os.linesep,
    )
    return path


def _write_binding_files(env: Env) -> None:
    """Materialize every hash-bound synthetic file under the temp tree."""
    for key, path in env.paths.items():
        if key in {"frozen-protocol", "direction-decision", "protocol-prereview"}:
            # JSON payloads are written by the caller (they must be valid JSON
            # read by the gate), so leave their raw bytes to _setup_env.
            continue
        if key in {"primitives", "draws"}:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(path, z=np.zeros((1,), dtype=np.float64))
        else:
            _write_file(path, f"synthetic {key} content\n")


def _build_directory_decision(env: Env) -> dict:
    return {
        "schema_version": "ARSC_ROUND12_EXISTING_OUTPUTS_REVIEWER_DECISION_V1",
        "decision": runner.DIRECTION_DECISION,  # GO_FREEZE_ONE_ANALYSIS
        "reviewer_role": "independent_existing_outputs_scientific_direction_reviewer",
        "implementation_authorized_by_this_decision": False,
    }


def _build_frozen_protocol(env: Env, directory_decision: dict) -> dict:
    dir_sha = _sha256_file(env.paths["direction-decision"])
    npz_allowlists = {}
    for key in ("primitives", "draws"):
        path = env.paths[key]
        npz_allowlists[path.relative_to(env.root).as_posix()] = {
            "sha256": _sha256_file(path),
            "key_count": 1,
            "items": [{"key": "z", "shape": [1], "dtype": "float64"}],
        }
    return {
        "schema_version": "ARSC_ROUND12_EXISTING_OUTPUTS_FROZEN_PROTOCOL_V1",
        "status": runner.PROTOCOL_STATUS,  # FROZEN_RESULT_BLIND_PROTOCOL_ONLY
        "result_blind": True,
        "execution": {
            "formal_run": False,
            "outcome_computed": False,
            "bootstrap_executed": False,
        },
        "authorization": {
            "decision_path": env.paths["direction-decision"].relative_to(
                env.root
            ).as_posix(),
            "decision_sha256": dir_sha,
        },
        "inputs": {"npz_allowlists": npz_allowlists},
    }


def _build_prereview(env: Env) -> dict:
    return {
        "schema_version": "ARSC_ROUND12_FROZEN_PROTOCOL_PRERESULT_REVIEWER_DECISION_V1",
        "decision": runner.PROTOCOL_PREREVIEW_DECISION,  # GO_IMPLEMENT_...
        "reviewer_role": "independent_result_blind_round12_frozen_protocol_reviewer",
    }


def _build_go_run(
    env: Env,
    *,
    schema_version: str | None = None,
    decision: str | None = None,
    bindings: list | None = None,
) -> dict:
    if bindings is None:
        bindings = []
        for key in runner.BINDING_KEYS:
            path = env.paths[key]
            bindings.append(
                {
                    "key": key,
                    "path": path.relative_to(env.root).as_posix(),
                    "sha256": _sha256_file(path),
                }
            )
    return {
        "schema_version": schema_version or runner.GO_RUN_SCHEMA,
        "decision": decision or runner.GO_RUN_DECISION,
        "result_blind": True,
        "execution_scope": {
            "attempt": "attempt01",
            "maximum_formal_executions": 1,
            "formal_run_authorized": True,
        },
        "bindings": bindings,
    }


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    go_run: dict | None = None,
    protocol: dict | None = None,
    directory_decision: dict | None = None,
    prereview: dict | None = None,
    write_go_run: bool = True,
) -> Env:
    """Redirect all canonical bindings to synthetic files and wire the gate."""
    env = Env(tmp_path)
    _write_binding_files(env)

    direction = directory_decision or _build_directory_decision(env)
    _write_object_document(env.paths["direction-decision"], direction)

    proto = protocol or _build_frozen_protocol(env, direction)
    _write_object_document(env.paths["frozen-protocol"], proto)

    prereiv = prereview or _build_prereview(env)
    _write_object_document(env.paths["protocol-prereview"], prereiv)

    if write_go_run:
        _write_object_document(env.paths["frozen-protocol"].with_name(".go_run_tmp.json"), {})
        go = go_run or _build_go_run(env)
        go_run_path = tmp_path / "outputs" / "validity" / (
            "round12_analysis_runner_reviewer_decision.json"
        )
        _write_object_document(go_run_path, go)

    # Redirect every canonical path constant plus ROOT and BINDING_PATHS.
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "GO_RUN_PATH", go_run_path if write_go_run else tmp_path / "absent_go_run.json")
    monkeypatch.setattr(runner, "PROTOCOL_PATH", env.paths["frozen-protocol"])
    monkeypatch.setattr(
        runner, "DIRECTION_DECISION_PATH", env.paths["direction-decision"]
    )
    monkeypatch.setattr(
        runner, "PROTOCOL_PREREVIEW_PATH", env.paths["protocol-prereview"]
    )
    monkeypatch.setattr(runner, "PRIMITIVES_PATH", env.paths["primitives"])
    monkeypatch.setattr(runner, "DRAWS_PATH", env.paths["draws"])
    monkeypatch.setattr(runner, "ROUND12_CORE_PATH", env.paths["round12-core"])
    monkeypatch.setattr(
        runner, "CANONICAL_METRICS_PATH", env.paths["canonical-metrics"]
    )
    monkeypatch.setattr(runner, "RUNNER_TESTS_PATH", env.paths["runner-tests"])
    monkeypatch.setattr(runner, "CORE_TESTS_PATH", env.paths["core-tests"])
    monkeypatch.setattr(runner, "OUTPUT_SERIALIZER_PATH", env.paths["output-serializer"])
    monkeypatch.setattr(
        runner, "OUTPUT_SERIALIZER_TESTS_PATH", env.paths["output-serializer-tests"]
    )
    monkeypatch.setattr(runner, "RUNNER_PATH", env.paths["runner"])
    monkeypatch.setattr(runner, "BINDING_PATHS", dict(env.paths))
    return env


# ---------------------------------------------------------------------------
# Valid authorization and post-gate orchestration
# ---------------------------------------------------------------------------


def test_authorization_passes_then_main_runs_post_gate_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    # The gate itself, when invoked directly, does not raise.
    runner.authorize_before_data_access()
    events: list[str] = []
    bundle = {
        "raw": np.asarray([1]),
        "seed_position_draws": np.asarray([[0]], dtype=np.uint8),
        "clip_position_draws": np.asarray([[0]], dtype=np.uint16),
        "expanded_image_counts": np.asarray([1], dtype=np.int32),
    }
    def synthetic_loader(protocol):
        assert (tmp_path / runner.ATTEMPT_CLAIM_RELATIVE_PATH).is_file()
        events.append("load")
        return dict(bundle)

    monkeypatch.setattr(runner, "load_formal_inputs_after_authorization", synthetic_loader)
    monkeypatch.setattr(
        round12_core,
        "round12_statistics",
        lambda inputs, seed_draws, clip_draws, **kwargs: events.append("statistics")
        or {"synthetic": True},
    )
    expected_payloads = {path: b"x" for path in runner.FORMAL_OUTPUT_RELATIVE_PATHS}
    monkeypatch.setattr(
        output_serializers,
        "build_formal_payloads",
        lambda statistics, provenance, input_bindings: events.append("serialize")
        or expected_payloads,
    )
    monkeypatch.setattr(
        runner,
        "publish_formal_payloads_transaction",
        lambda payloads, **kwargs: events.append("publish") or None,
    )
    assert runner.main([]) == 0
    assert events == ["load", "statistics", "serialize", "publish"]


# ---------------------------------------------------------------------------
# Missing GO_RUN
# ---------------------------------------------------------------------------


def test_missing_go_run_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch, write_go_run=False)
    with pytest.raises(ValueError, match="missing|required regular file"):
        runner.authorize_before_data_access()


def test_missing_go_run_main_never_loads_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch, write_go_run=False)
    called = False

    def forbidden_loader(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("loader must not be called")

    monkeypatch.setattr(runner, "load_formal_inputs_after_authorization", forbidden_loader)
    with pytest.raises(ValueError, match="missing|required regular file"):
        runner.main([])
    assert called is False


def test_existing_formal_target_stops_main_before_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(tmp_path, monkeypatch)
    existing = tmp_path / runner.FORMAL_OUTPUT_RELATIVE_PATHS[0]
    existing.write_bytes(b"prior formal result")
    called = False

    def forbidden_loader(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("loader must not be called")

    monkeypatch.setattr(runner, "load_formal_inputs_after_authorization", forbidden_loader)
    with pytest.raises(ValueError, match="formal target already exists"):
        runner.main([])
    assert called is False
    assert existing.read_bytes() == b"prior formal result"


# ---------------------------------------------------------------------------
# Duplicate binding key
# ---------------------------------------------------------------------------


def test_duplicate_binding_key_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = Env(tmp_path)
    _write_binding_files(start)
    direction = _build_directory_decision(start)
    _write_object_document(start.paths["direction-decision"], direction)
    _write_object_document(start.paths["frozen-protocol"], _build_frozen_protocol(start, direction))
    _write_object_document(start.paths["protocol-prereview"], _build_prereview(start))
    go = _build_go_run(start)
    # Swap one real entry out and put a duplicate of the runner entry in so the
    # list stays exactly len(BINDING_KEYS) but contains a duplicate key.
    go["bindings"].pop(1)
    go["bindings"].append(dict(go["bindings"][0]))
    go_run_path = tmp_path / "outputs" / "validity" / (
        "round12_analysis_runner_reviewer_decision.json"
    )
    _write_object_document(go_run_path, go)
    for key, path in start.paths.items():
        monkeypatch.setattr(runner, _attr_for_key(key), path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "BINDING_PATHS", dict(start.paths))
    monkeypatch.setattr(runner, "GO_RUN_PATH", go_run_path)
    with pytest.raises(ValueError, match="duplicate GO_RUN binding key"):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Wrong hash, wrong path, wrong schema, wrong decision
# ---------------------------------------------------------------------------


def test_wrong_sha256_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env)
    go["bindings"][0]["sha256"] = "0" * 64
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        runner.authorize_before_data_access()


def test_protocol_npz_sha_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    protocol = json.loads(env.paths["frozen-protocol"].read_text(encoding="utf-8"))
    primitive_key = env.paths["primitives"].relative_to(env.root).as_posix()
    protocol["inputs"]["npz_allowlists"][primitive_key]["sha256"] = "0" * 64
    _setup_env(tmp_path, monkeypatch, protocol=protocol)
    with pytest.raises(ValueError, match="NPZ SHA differs from frozen protocol"):
        runner.authorize_before_data_access()


def test_wrong_binding_path_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env)
    # Point the runner binding at another canonical path's relative value.
    runner_item = next(b for b in go["bindings"] if b["key"] == "runner")
    core_item = next(b for b in go["bindings"] if b["key"] == "round12-core")
    runner_item["path"] = core_item["path"]
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="differs from canonical"):
        runner.authorize_before_data_access()


def test_wrong_go_run_schema_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env, schema_version="WRONG_SCHEMA")
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="unexpected GO_RUN schema"):
        runner.authorize_before_data_access()


def test_wrong_go_run_decision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env, decision="GO_RUN_SOMETHING_ELSE")
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="does not authorize"):
        runner.authorize_before_data_access()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda go: go.update(result_blind=False),
        lambda go: go.pop("result_blind"),
    ],
)
def test_go_run_must_be_explicitly_result_blind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env)
    mutation(go)
    _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="result_blind"):
        runner.authorize_before_data_access()


@pytest.mark.parametrize(
    "scope",
    [
        None,
        {"attempt": "attempt02", "maximum_formal_executions": 1, "formal_run_authorized": True},
        {"attempt": "attempt01", "maximum_formal_executions": 2, "formal_run_authorized": True},
        {"attempt": "attempt01", "maximum_formal_executions": 1, "formal_run_authorized": False},
    ],
)
def test_go_run_scope_is_exactly_one_attempt01(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env)
    if scope is None:
        go.pop("execution_scope")
    else:
        go["execution_scope"] = scope
    _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="execution_scope"):
        runner.authorize_before_data_access()


def test_binding_length_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    go = _build_go_run(env)
    go["bindings"] = list(go["bindings"])[:5]
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="exactly"):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Protocol state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda p: p.update(status="ALREADY_RUN"),
            "not the frozen result-blind protocol",
        ),
        (lambda p: p.update(result_blind=False), "result-blind"),
        (lambda p: p["execution"].update(formal_run=True), "formal run"),
        (lambda p: p["execution"].update(outcome_computed=True), "outcome"),
        (lambda p: p["execution"].update(bootstrap_executed=True), "bootstrap"),
        (lambda p: p.pop("execution"), "execution record"),
    ],
)
def test_protocol_state_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    message: str,
) -> None:
    env = Env(tmp_path)
    _write_binding_files(env)
    direction = _build_directory_decision(env)
    _write_object_document(env.paths["direction-decision"], direction)
    _write_object_document(env.paths["protocol-prereview"], _build_prereview(env))
    proto = _build_frozen_protocol(env, direction)
    mutate(proto)
    _write_object_document(env.paths["frozen-protocol"], proto)
    go_run_path = tmp_path / "outputs" / "validity" / (
        "round12_analysis_runner_reviewer_decision.json"
    )
    _write_object_document(go_run_path, _build_go_run(env))
    for key, path in env.paths.items():
        monkeypatch.setattr(runner, _attr_for_key(key), path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "BINDING_PATHS", dict(env.paths))
    monkeypatch.setattr(runner, "GO_RUN_PATH", go_run_path)
    with pytest.raises(ValueError, match=message):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Direction decision
# ---------------------------------------------------------------------------


def test_wrong_direction_decision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(
        tmp_path,
        monkeypatch,
        directory_decision={
            "schema_version": "ARSC_ROUND12_EXISTING_OUTPUTS_REVIEWER_DECISION_V1",
            "decision": "GO_FREEZE_TWO_ANALYSES",
        },
    )
    with pytest.raises(ValueError, match="not the expected GO_FREEZE"):
        runner.authorize_before_data_access()


def test_missing_direction_schema_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(
        tmp_path,
        monkeypatch,
        directory_decision={
            "decision": runner.DIRECTION_DECISION,
        },
    )
    with pytest.raises(ValueError, match="not the expected GO_FREEZE"):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Protocol prereview
# ---------------------------------------------------------------------------


def test_wrong_prereview_decision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(
        tmp_path,
        monkeypatch,
        prereview={
            "schema_version": "ARSC_ROUND12_FROZEN_PROTOCOL_PRERESULT_REVIEWER_DECISION_V1",
            "decision": "GO_IMPLEMENT_SOMETHING_ELSE",
        },
    )
    with pytest.raises(ValueError, match="not the expected GO_IMPLEMENT"):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Symlink / non-regular binding path
# ---------------------------------------------------------------------------


def test_binding_symlink_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlink support unavailable")
    env = _setup_env(tmp_path, monkeypatch)
    runner_path = env.paths["runner"]
    target = tmp_path / "real_runner.py"
    _write_file(target, "synthetic runner content\n")
    try:
        runner_path.unlink()
        os.symlink(target, runner_path)
    except OSError:
        pytest.skip("cannot create symlink on this host")
    go = _build_go_run(env)
    env = _setup_env(tmp_path, monkeypatch, go_run=go)
    with pytest.raises(ValueError, match="must not be a symlink"):
        runner.authorize_before_data_access()


# ---------------------------------------------------------------------------
# Extra argv
# ---------------------------------------------------------------------------


def test_extra_argv_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    with pytest.raises(SystemExit):
        runner.parse_args(["--unexpected"])


# ---------------------------------------------------------------------------
# No numpy source on the authoritarian path
# ---------------------------------------------------------------------------


def test_authorize_never_imports_numpy_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _setup_env(tmp_path, monkeypatch)
    calls: list[str] = []

    original_load = np.load

    def _forbidden(*args, **kwargs):
        calls.append("np.load")
        return original_load(*args, **kwargs)

    monkeypatch.setattr(np, "load", _forbidden)
    runner.authorize_before_data_access()
    assert calls == []


class _RecordingArchive:
    def __init__(self, values: dict[str, np.ndarray]):
        self.values = values
        self.files = list(values)
        self.accessed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def __getitem__(self, key: str) -> np.ndarray:
        self.accessed.append(key)
        return self.values[key]


def _loader_protocol(root: Path, primitives: Path, draws: Path,
                     primitive_keys: list[str], draw_keys: list[str]) -> dict:
    return {
        "inputs": {
            "npz_allowlists": {
                primitives.relative_to(root).as_posix(): {
                    "items": [{"key": key} for key in primitive_keys]
                },
                draws.relative_to(root).as_posix(): {
                    "items": [{"key": key} for key in draw_keys]
                },
            }
        }
    }


def test_selective_loader_never_reads_aggregate_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primitives_path = tmp_path / "primitives.npz"
    draws_path = tmp_path / "draws.npz"
    forbidden_primitives = ["curve_A", "endpoint_effects", "safety_diagnostics"]
    forbidden_draws = ["family_axis_gate_draws", "endpoint_draws"]
    primitive_values = {
        key: np.asarray([index], dtype=np.int64)
        for index, key in enumerate((*REQUIRED_INPUT_KEYS, *forbidden_primitives))
    }
    draw_allowed = [
        "seed_position_draws",
        "clip_position_draws",
        "expanded_image_counts",
    ]
    draw_values = {
        key: np.asarray([index], dtype=np.int64)
        for index, key in enumerate((*draw_allowed, *forbidden_draws))
    }
    primitives = _RecordingArchive(primitive_values)
    draws = _RecordingArchive(draw_values)
    calls: list[tuple[Path, bool]] = []

    def fake_load(path, *, allow_pickle):
        resolved = Path(path)
        calls.append((resolved, allow_pickle))
        return primitives if resolved == primitives_path else draws

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "validate_npz_headers_after_authorization", lambda *args: None)
    monkeypatch.setattr(np, "load", fake_load)
    protocol = _loader_protocol(
        tmp_path,
        primitives_path,
        draws_path,
        list(primitive_values),
        list(draw_values),
    )
    bundle = runner.load_formal_inputs_after_authorization(
        protocol, primitives_path, draws_path
    )

    assert calls == [(primitives_path, False), (draws_path, False)]
    assert primitives.accessed == list(REQUIRED_INPUT_KEYS)
    assert draws.accessed == draw_allowed
    assert not (set(forbidden_primitives) | set(forbidden_draws)) & set(bundle)
    for key in REQUIRED_INPUT_KEYS:
        assert bundle[key] is not primitive_values[key]
    for key in draw_allowed:
        assert bundle[key] is not draw_values[key]


def test_selective_loader_rejects_archive_key_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primitives_path = tmp_path / "primitives.npz"
    draws_path = tmp_path / "draws.npz"
    primitive_values = {
        key: np.asarray([0], dtype=np.int64) for key in REQUIRED_INPUT_KEYS
    }
    draw_keys = [
        "seed_position_draws",
        "clip_position_draws",
        "expanded_image_counts",
    ]
    primitives = _RecordingArchive(primitive_values)
    draws = _RecordingArchive(
        {key: np.asarray([0], dtype=np.int64) for key in draw_keys}
    )

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "validate_npz_headers_after_authorization", lambda *args: None)
    monkeypatch.setattr(
        np,
        "load",
        lambda path, *, allow_pickle: primitives
        if Path(path) == primitives_path
        else draws,
    )
    protocol = _loader_protocol(
        tmp_path,
        primitives_path,
        draws_path,
        list(primitive_values) + ["unexpected_key"],
        draw_keys,
    )
    with pytest.raises(ValueError, match="primitives archive key set"):
        runner.load_formal_inputs_after_authorization(
            protocol, primitives_path, draws_path
        )
    assert primitives.accessed == []


def test_header_only_npz_validation_accepts_exact_shape_dtype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "header_only.npz"
    np.savez(
        archive_path,
        matrix=np.zeros((2, 3), dtype=np.float32),
        scalar=np.asarray(7, dtype=np.int16),
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    entry = {
        "items": [
            {"key": "matrix", "shape": [2, 3], "dtype": "float32"},
            {"key": "scalar", "shape": [], "dtype": "int16"},
        ]
    }
    monkeypatch.setattr(np, "load", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("np.load must not be used for header validation")
    ))
    runner.validate_npz_headers_after_authorization(archive_path, entry)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"items": [{"key": "matrix", "shape": [3, 2], "dtype": "float32"}]}, "shape"),
        ({"items": [{"key": "matrix", "shape": [2, 3], "dtype": "float64"}]}, "dtype"),
        ({"items": [{"key": "other", "shape": [2, 3], "dtype": "float32"}]}, "member set"),
    ],
)
def test_header_only_npz_validation_rejects_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: dict, message: str
) -> None:
    archive_path = tmp_path / "header_mismatch.npz"
    np.savez(archive_path, matrix=np.zeros((2, 3), dtype=np.float32))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=message):
        runner.validate_npz_headers_after_authorization(archive_path, entry)


# ---------------------------------------------------------------------------
# One-shot transaction publication
# ---------------------------------------------------------------------------


def _transaction_payloads() -> dict[Path, bytes]:
    return {
        path: ("payload:" + path.name).encode("utf-8")
        for path in runner.FORMAL_OUTPUT_RELATIVE_PATHS
    }


def _prepare_transaction_root(tmp_path: Path) -> None:
    (tmp_path / "outputs" / "validity").mkdir(parents=True)


def _transaction_claim(tmp_path: Path) -> str:
    return runner.acquire_attempt_claim(root=tmp_path)


def test_attempt_claim_is_atomic_and_stale_claim_fails_closed(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    token = runner.acquire_attempt_claim(root=tmp_path)
    claim = tmp_path / runner.ATTEMPT_CLAIM_RELATIVE_PATH
    assert claim.read_bytes() == (token + "\n").encode("ascii")
    with pytest.raises(ValueError, match="claim already exists"):
        runner.acquire_attempt_claim(root=tmp_path)
    assert claim.read_bytes() == (token + "\n").encode("ascii")


def test_transaction_publishes_exact_bytes_and_index_last(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    payloads = _transaction_payloads()
    observed: list[str] = []

    def recording_replace(source: Path, target: Path) -> None:
        observed.append(target.name)
        os.replace(source, target)

    runner.publish_formal_payloads_transaction(
        payloads, root=tmp_path, claim_token=claim_token, replace_func=recording_replace
    )
    for relative_path, payload in payloads.items():
        assert (tmp_path / relative_path).read_bytes() == payload
    assert observed[-1] == "round12_existing_outputs_artifact_index.json"
    assert not list((tmp_path / "outputs" / "validity").glob("*.tmp.round12_attempt01.*"))
    assert (tmp_path / runner.ATTEMPT_CLAIM_RELATIVE_PATH).read_text().strip() == claim_token


def test_transaction_default_atomic_no_overwrite_publish(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    payloads = _transaction_payloads()
    runner.publish_formal_payloads_transaction(
        payloads, root=tmp_path, claim_token=claim_token
    )
    assert {
        relative_path: (tmp_path / relative_path).read_bytes()
        for relative_path in runner.FORMAL_OUTPUT_RELATIVE_PATHS
    } == payloads


def test_transaction_refuses_preexisting_target_without_changes(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    payloads = _transaction_payloads()
    existing_relative = runner.FORMAL_OUTPUT_RELATIVE_PATHS[1]
    existing = tmp_path / existing_relative
    existing.write_bytes(b"keep-me")
    with pytest.raises(ValueError, match="already exists"):
        runner.publish_formal_payloads_transaction(
            payloads, root=tmp_path, claim_token=claim_token
        )
    assert existing.read_bytes() == b"keep-me"
    for relative_path in runner.FORMAL_OUTPUT_RELATIVE_PATHS:
        if relative_path != existing_relative:
            assert not (tmp_path / relative_path).exists()


def test_transaction_replace_failure_rolls_back_targets_and_temps(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    calls = 0

    def failing_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("injected replace failure")
        os.replace(source, target)

    with pytest.raises(OSError, match="injected replace failure"):
        runner.publish_formal_payloads_transaction(
            _transaction_payloads(), root=tmp_path, claim_token=claim_token,
            replace_func=failing_replace
        )
    for relative_path in runner.FORMAL_OUTPUT_RELATIVE_PATHS:
        target = tmp_path / relative_path
        assert not target.exists()
        assert not target.with_name(
            target.name + ".tmp.round12_attempt01." + claim_token
        ).exists()
    assert (tmp_path / runner.ATTEMPT_CLAIM_RELATIVE_PATH).is_file()


def test_transaction_rollback_never_deletes_competitor_target(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    calls = 0
    competitor_target: Path | None = None
    unrelated_temp = (
        tmp_path / runner.FORMAL_OUTPUT_RELATIVE_PATHS[-1]
    ).with_name(
        runner.FORMAL_OUTPUT_RELATIVE_PATHS[-1].name
        + ".tmp.round12_attempt01."
        + "f" * 32
    )
    unrelated_temp.write_bytes(b"other owner")

    def competitor_then_fail(source: Path, target: Path) -> None:
        nonlocal calls, competitor_target
        calls += 1
        if calls == 2:
            competitor_target = target
            target.write_bytes(b"competitor")
            raise FileExistsError("competitor won target")
        os.link(source, target)

    with pytest.raises(FileExistsError, match="competitor won"):
        runner.publish_formal_payloads_transaction(
            _transaction_payloads(), root=tmp_path, claim_token=claim_token,
            replace_func=competitor_then_fail
        )
    assert competitor_target is not None
    assert competitor_target.read_bytes() == b"competitor"
    first_target = tmp_path / runner.FORMAL_PUBLISH_ORDER[0]
    assert not first_target.exists()
    assert unrelated_temp.read_bytes() == b"other owner"
    owned = list((tmp_path / "outputs" / "validity").glob(
        "*.tmp.round12_attempt01." + claim_token
    ))
    assert owned == []


def test_transaction_rejects_unexpected_path(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    payloads = _transaction_payloads()
    payloads[Path("outputs/validity/unexpected.bin")] = b"bad"
    with pytest.raises(ValueError, match="exact frozen output set"):
        runner.publish_formal_payloads_transaction(
            payloads, root=tmp_path, claim_token=claim_token
        )


def test_transaction_rejects_symlink_target_when_supported(tmp_path: Path) -> None:
    _prepare_transaction_root(tmp_path)
    claim_token = _transaction_claim(tmp_path)
    target = tmp_path / runner.FORMAL_OUTPUT_RELATIVE_PATHS[0]
    backing = tmp_path / "backing.bin"
    backing.write_bytes(b"keep")
    try:
        target.symlink_to(backing)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="already exists"):
        runner.publish_formal_payloads_transaction(
            _transaction_payloads(), root=tmp_path, claim_token=claim_token
        )
    assert backing.read_bytes() == b"keep"
