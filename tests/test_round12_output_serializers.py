"""Synthetic contract tests for the pure Round 12 output serializers.

These tests exercise ``src/arsc_eval/round12_output_serializers.py`` exclusively
through synthetic, in-memory fixtures.  No formal/real statistics document,
bootstrap archive, or reviewer decision is ever read: every statistic is a small
deterministic synthetic fixture with the exact frozen key structure, float64
``(5000,)`` bootstrap arrays for the four axes ``D_A/D_R/D_S/D_C1``, float64
``(5,)`` / ``(3,)`` seed/family arrays, and a mutually consistent all-PASS gate
set.

Covered behaviour
-----------------
* the exact five flat frozen output names/paths (including ``protocol.log``);
* repeated byte determinism for every serializer;
* newline termination of the JSON and JSONL payloads;
* the result document carries every scalar / list / gate / provenance field and
  deliberately excludes the bootstrap arrays;
* non-finite and NumPy values are rejected from JSON payloads;
* strict *original* ``float64``/shape validation of the draw arrays (no coercion);
* NPZ fixed member order, frozen 1980-01-01 member timestamp, ``float64`` shape
  ``(5000,)`` and an exact in-memory round-trip;
* CSV row count and record order;
* inconsistent gate rejection;
* the artifact index has / byte-counts all four non-index payloads and performs
  no self-entry / self-hash;
* malformed statistics key sets are rejected;
* all pure calls create no files under ``tmp_path``.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

import arsc_eval.round12_output_serializers as serializers

RNG = np.random.default_rng(20240601)


# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------


def make_draws() -> dict[str, np.ndarray]:
    """Four float64 (5000,) arrays, all finite, deterministic per build."""
    draws: dict[str, np.ndarray] = {}
    for axis in serializers.D_AXES:
        base = np.arange(serializers.REPLICATES, dtype=np.float64)
        draws[axis] = (base / (serializers.REPLICATES + 1)) + float(hash(axis) % 10)
    return draws


def make_gates(*, all_pass: bool = True) -> dict:
    checks = {name: bool(all_pass) for name in serializers.EXPECTED_GATE_KEYS}
    c1 = all(checks[name] for name in serializers.EXPECTED_GATE_KEYS[:4])
    ars = all(checks[name] for name in serializers.EXPECTED_GATE_KEYS[4:])
    verdict = "PASS" if (c1 and ars) else ("PARTIAL" if c1 else "FAIL")
    return {"verdict": verdict, "checks": checks, "c1_pass": c1, "ars_pass": ars}


def make_statistics(*, all_pass: bool = True) -> dict:
    """Small synthetic, mutually-consistent PASS statistics fixture."""
    seeds = (np.arange(serializers.SEED_COUNT, dtype=np.float64) + 1) / 10.0
    families = (np.arange(serializers.FAMILY_COUNT, dtype=np.float64) + 1) / 100.0
    return {
        "point_estimates": {axis: float(i) + 0.5 for i, axis in enumerate(serializers.D_AXES)},
        "per_seed_D_C1": seeds,
        "per_family_D_C1": families,
        "lower_bounds": {axis: float(i) - 0.25 for i, axis in enumerate(serializers.D_AXES)},
        "gates": make_gates(all_pass=all_pass),
        "bootstrap_draws": make_draws(),
    }


def make_provenance() -> dict:
    return {
        "run_id": "synthetic-run-0001",
        "author": "test-only",
        "environment": {"python": "3.12", "numpy": "stable"},
        "tag": "synthetic",
    }


def make_input_bindings() -> dict:
    return {
        "statistics_source": "synthetic/fixture",
        "notes": ["no formal data"],
        "n_axes": 4,
    }


def _sha256_upper(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest().upper()


# ---------------------------------------------------------------------------
# Frozen output names / paths
# ---------------------------------------------------------------------------


def test_exact_five_flat_frozen_output_paths() -> None:
    assert serializers.FORMAL_OUTPUT_NAMES == (
        "round12_existing_outputs_results.json",
        "round12_existing_outputs_point_diagnostics.csv",
        "round12_existing_outputs_component_draws.npz",
        "round12_existing_outputs_artifact_index.json",
        "round12_existing_outputs_protocol.log",
    )
    assert serializers.FORMAL_OUTPUT_DIR == Path("outputs/validity")
    expected_paths = {
        "round12_existing_outputs_results.json": Path("outputs/validity/round12_existing_outputs_results.json"),
        "round12_existing_outputs_point_diagnostics.csv": Path(
            "outputs/validity/round12_existing_outputs_point_diagnostics.csv"
        ),
        "round12_existing_outputs_component_draws.npz": Path(
            "outputs/validity/round12_existing_outputs_component_draws.npz"
        ),
        "round12_existing_outputs_artifact_index.json": Path(
            "outputs/validity/round12_existing_outputs_artifact_index.json"
        ),
        "round12_existing_outputs_protocol.log": Path(
            "outputs/validity/round12_existing_outputs_protocol.log"
        ),
    }
    assert dict(serializers.FORMAL_OUTPUT_PATHS) == expected_paths
    # All five live flat (single filename component) directly under
    # outputs/validity -- no deeper nesting.
    for name, path in serializers.FORMAL_OUTPUT_PATHS.items():
        assert len(path.parts) == 3
        assert path.parent == serializers.FORMAL_OUTPUT_DIR
        assert path.name == name
        assert path.parts[-2:] == ("validity", name)


# ---------------------------------------------------------------------------
# Repeated byte determinism
# ---------------------------------------------------------------------------


def test_all_serializers_are_byte_deterministic() -> None:
    stats = make_statistics()
    prov = make_provenance()
    binds = make_input_bindings()

    result = serializers.build_result_document(stats, prov)
    assert serializers.json_bytes(result) == serializers.json_bytes(result)

    assert serializers.diagnostics_csv_bytes(
        stats["point_estimates"],
        stats["lower_bounds"],
        stats["per_seed_D_C1"],
        stats["per_family_D_C1"],
        stats["gates"],
    ) == serializers.diagnostics_csv_bytes(
        stats["point_estimates"],
        stats["lower_bounds"],
        stats["per_seed_D_C1"],
        stats["per_family_D_C1"],
        stats["gates"],
    )

    assert serializers.deterministic_npz_bytes(
        stats["bootstrap_draws"]
    ) == serializers.deterministic_npz_bytes(stats["bootstrap_draws"])

    assert serializers.deterministic_log_jsonl(stats) == serializers.deterministic_log_jsonl(stats)

    first = serializers.build_formal_payloads(stats, prov, binds)
    second = serializers.build_formal_payloads(stats, prov, binds)
    assert list(first) == list(second)  # same key paths
    for path in first:
        assert first[path] == second[path]


# ---------------------------------------------------------------------------
# Newline JSON / JSONL
# ---------------------------------------------------------------------------


def test_json_and_log_are_newline_terminated() -> None:
    stats = make_statistics()
    result = serializers.build_result_document(stats, make_provenance())
    json_b = serializers.json_bytes(result)
    assert json_b.endswith(b"\n")
    assert not json_b.endswith(b"\n\n")
    # Each reserialization remains newline-terminated and is valid JSON.
    assert json.loads(json_b.decode("utf-8"))["analysis_id"] == serializers.ANALYSIS_ID

    log_b = serializers.deterministic_log_jsonl(stats)
    assert log_b.endswith(b"\n")
    lines = log_b.decode("utf-8").splitlines()
    assert len(lines) == len(serializers.LOG_EVENT_NAMES)
    # Each line is its own JSON object (JSONL).
    sequences = [json.loads(line)["sequence"] for line in lines]
    assert sequences == list(range(len(serializers.LOG_EVENT_NAMES)))
    names = [json.loads(line)["event"] for line in lines]
    assert names == list(serializers.LOG_EVENT_NAMES)


# ---------------------------------------------------------------------------
# Result document field coverage; bootstrap arrays excluded
# ---------------------------------------------------------------------------


def test_result_document_fields_present_and_bootstrap_excluded() -> None:
    stats = make_statistics()
    prov = make_provenance()
    result = serializers.build_result_document(stats, prov)

    # Scalars / identity fields.
    assert result["schema_version"] == serializers.RESULT_SCHEMA
    assert result["analysis_id"] == serializers.ANALYSIS_ID
    assert result["attempt"] == serializers.ATTEMPT
    assert result["replicates"] == serializers.REPLICATES

    # Scalar per-axis estimates / bounds (no arrays).
    assert set(result["point_estimates"]) == set(serializers.D_AXES)
    assert set(result["lower_bounds"]) == set(serializers.D_AXES)
    for axis in serializers.D_AXES:
        assert isinstance(result["point_estimates"][axis], float)
        assert isinstance(result["lower_bounds"][axis], float)

    # List-covered seed / family arrays.
    assert result["per_seed_D_C1"] == stats["per_seed_D_C1"].tolist()
    assert result["per_family_D_C1"] == stats["per_family_D_C1"].tolist()
    assert isinstance(result["per_seed_D_C1"], list)
    assert isinstance(result["per_family_D_C1"], list)

    # Gate coverage.
    gates = result["gates"]
    assert gates["verdict"] == "PASS"
    assert gates["c1_pass"] is True
    assert gates["ars_pass"] is True
    assert set(gates["checks"]) == set(serializers.EXPECTED_GATE_KEYS)

    # Provenance passthrough.
    assert result["provenance"] == prov

    # Bootstrap array axis keys must never appear in the JSON result.
    assert "bootstrap_draws" not in result
    for axis in serializers.D_AXES:
        assert axis not in result
        assert axis not in gates

    # The result document serializes to valid deterministic JSON bytes.
    payload = serializers.json_bytes(result)
    assert json.loads(payload.decode("utf-8")) == result


# ---------------------------------------------------------------------------
# Non-finite / numpy JSON rejection
# ---------------------------------------------------------------------------


def test_json_rejects_nonfinite_floats() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            serializers.json_bytes({"value": bad})
        with pytest.raises(ValueError):
            serializers.json_bytes({"nested": {"list": [0.0, bad]}})


def test_json_and_result_reject_numpy_values() -> None:
    with pytest.raises(ValueError, match="NumPy"):
        serializers.json_bytes({"array": np.zeros(3)})
    with pytest.raises(ValueError, match="NumPy"):
        serializers.json_bytes({"scalar": np.float64(1.0)})
    with pytest.raises(ValueError, match="NumPy"):
        serializers.json_bytes({"nested": [1, np.arange(2)]})
    # Result documents also refuse a stray numpy array even when statistics are valid.
    bad_prov = dict(make_provenance())
    bad_prov["stray"] = np.zeros(2)
    with pytest.raises(ValueError, match="NumPy"):
        serializers.build_result_document(make_statistics(), bad_prov)


# ---------------------------------------------------------------------------
# Strict original ndarray float64 / shape validation
# ---------------------------------------------------------------------------


def test_validate_draws_requires_original_float64_ndarray_shape() -> None:
    good = make_draws()
    validated = serializers.validate_draws(good)
    assert list(validated) == list(serializers.D_AXES)

    # Wrong shape.
    wrong_shape = copy.deepcopy(good)
    wrong_shape["D_A"] = np.zeros(serializers.REPLICATES + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="shape"):
        serializers.validate_draws(wrong_shape)

    # Wrong dtype (int64) — no silent coercion.
    wrong_dtype = copy.deepcopy(good)
    wrong_dtype["D_R"] = np.zeros(serializers.REPLICATES, dtype=np.int64)
    with pytest.raises(ValueError, match="dtype"):
        serializers.validate_draws(wrong_dtype)

    # float32 is still not the exact float64 required.
    wrong_dtype32 = copy.deepcopy(good)
    wrong_dtype32["D_S"] = np.zeros(serializers.REPLICATES, dtype=np.float32)
    with pytest.raises(ValueError, match="dtype"):
        serializers.validate_draws(wrong_dtype32)

    # A plain list (never an ndarray) is rejected.
    as_list = copy.deepcopy(good)
    as_list["D_C1"] = good["D_C1"].tolist()
    with pytest.raises(ValueError, match="ndarray"):
        serializers.validate_draws(as_list)

    # Non-finite rejection.
    nonfinite = copy.deepcopy(good)
    nonfinite["D_A"] = good["D_A"].copy()
    nonfinite["D_A"][0] = np.nan
    with pytest.raises(ValueError, match="nonfinite"):
        serializers.validate_draws(nonfinite)


# ---------------------------------------------------------------------------
# NPZ: member order, 1980 timestamp, shape, roundtrip
# ---------------------------------------------------------------------------


def test_npz_fixed_member_order_timestamp_and_dtype_shape() -> None:
    stats = make_statistics()
    payload = serializers.deterministic_npz_bytes(stats["bootstrap_draws"])
    with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
        names = archive.namelist()
        assert names == [axis + ".npy" for axis in serializers.D_AXES]
        for axis in serializers.D_AXES:
            info = archive.getinfo(axis + ".npy")
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED


def test_npz_exact_roundtrip() -> None:
    stats = make_statistics()
    payload = serializers.deterministic_npz_bytes(stats["bootstrap_draws"])
    decoded = serializers.roundtrip_npz_bytes(payload)
    assert list(decoded) == list(serializers.D_AXES)
    for axis in serializers.D_AXES:
        assert decoded[axis].dtype == np.float64
        assert decoded[axis].shape == (serializers.REPLICATES,)
        assert np.array_equal(decoded[axis], stats["bootstrap_draws"][axis])


def test_npz_rejects_unexpected_member_order() -> None:
    good = make_draws()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for axis in reversed(serializers.D_AXES):
            info = zipfile.ZipInfo(axis + ".npy")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            member = io.BytesIO()
            np.lib.format.write_array(member, good[axis], allow_pickle=False)
            archive.writestr(info, member.getvalue())
    with pytest.raises(ValueError, match="member order"):
        serializers.roundtrip_npz_bytes(buffer.getvalue())


# ---------------------------------------------------------------------------
# CSV row count / order
# ---------------------------------------------------------------------------


def test_diagnostics_csv_row_count_and_order() -> None:
    stats = make_statistics()
    csv_b = serializers.diagnostics_csv_bytes(
        stats["point_estimates"],
        stats["lower_bounds"],
        stats["per_seed_D_C1"],
        stats["per_family_D_C1"],
        stats["gates"],
    )
    lines = csv_b.decode("utf-8").splitlines()
    # header + 4 point + 4 lower_bound + 5 seed + 3 family + 7 gate
    assert lines[0] == "record_type,axis,index,value,check_name,passed"
    assert len(lines) == 1 + 4 + 4 + 5 + 3 + 7

    rows = [next(csv.reader([line])) for line in lines[1:]]

    record_types = [row[0] for row in rows]
    assert record_types == (
        ["point"] * 4
        + ["lower_bound"] * 4
        + ["seed"] * 5
        + ["family"] * 3
        + ["gate"] * 7
    )

    # point records follow D_A,D_R,D_S,D_C1 order.
    point_axes = [row[1] for row in rows[:4]]
    assert point_axes == list(serializers.D_AXES)
    lower_axes = [row[1] for row in rows[4:8]]
    assert lower_axes == list(serializers.D_AXES)

    # seed / family counts and indices.
    seed_rows = rows[8:13]
    assert [row[2] for row in seed_rows] == ["0", "1", "2", "3", "4"]
    assert all(row[1] == "D_C1" for row in seed_rows)
    family_rows = rows[13:16]
    assert [row[2] for row in family_rows] == ["0", "1", "2"]
    assert all(row[1] == "D_C1" for row in family_rows)

    # gate records carry the frozen check names and PASS booleans.
    gate_rows = rows[16:]
    assert [row[4] for row in gate_rows] == list(serializers.EXPECTED_GATE_KEYS)
    assert all(row[3] == "" for row in gate_rows)
    assert all(row[5] == "True" for row in gate_rows)


# ---------------------------------------------------------------------------
# Inconsistent gate rejection
# ---------------------------------------------------------------------------


def test_inconsistent_gate_rejection() -> None:
    stats = make_statistics()
    gates = stats["gates"]
    # Mutate verdict so it disagrees with the c1/ars booleans.
    bad = copy.deepcopy(stats)
    bad["gates"] = dict(gates)
    bad["gates"]["verdict"] = "FAIL" if gates["verdict"] == "PASS" else "PASS"
    with pytest.raises(ValueError, match="verdict"):
        serializers._validated_statistics(bad)

    bad2 = copy.deepcopy(stats)
    bad2["gates"] = dict(gates)
    bad2["gates"]["c1_pass"] = not gates["c1_pass"]
    with pytest.raises(ValueError, match="c1_pass"):
        serializers._validated_statistics(bad2)

    bad3 = copy.deepcopy(stats)
    bad3["gates"] = dict(gates)
    bad3["gates"]["ars_pass"] = not gates["ars_pass"]
    with pytest.raises(ValueError, match="ars_pass"):
        serializers._validated_statistics(bad3)

    # A gate check that is not a bool is rejected.
    bad4 = copy.deepcopy(stats)
    bad4["gates"] = dict(gates)
    bad4["gates"]["checks"] = dict(gates["checks"])
    bad4["gates"]["checks"][serializers.EXPECTED_GATE_KEYS[0]] = "yes"
    with pytest.raises(ValueError, match="bool"):
        serializers._validated_statistics(bad4)


# ---------------------------------------------------------------------------
# Artifact index: hashes + byte counts, no self entry / self hash
# ---------------------------------------------------------------------------


def test_artifact_index_hashes_all_four_non_index_payloads_no_self() -> None:
    stats = make_statistics()
    prov = make_provenance()
    binds = make_input_bindings()
    payloads = serializers.build_formal_payloads(stats, prov, binds)

    index_path = serializers.FORMAL_OUTPUT_PATHS["round12_existing_outputs_artifact_index.json"]
    index_bytes = payloads[index_path]
    index_doc = json.loads(index_bytes.decode("utf-8"))

    assert index_doc["schema_version"] == serializers.INDEX_SCHEMA
    assert index_doc["analysis_id"] == serializers.ANALYSIS_ID
    assert index_doc["attempt"] == serializers.ATTEMPT
    assert index_doc["provenance"] == prov
    assert index_doc["input_bindings"] == binds
    assert index_doc["self_hash_excluded"] is True

    artifacts = index_doc["artifacts"]
    non_index_names = [
        "round12_existing_outputs_results.json",
        "round12_existing_outputs_point_diagnostics.csv",
        "round12_existing_outputs_component_draws.npz",
        "round12_existing_outputs_protocol.log",
    ]
    # Exactly the four non-index payloads, no artifact-index self entry.
    assert len(artifacts) == 4
    assert {a["path"] for a in artifacts} == {
        "outputs/validity/" + name for name in non_index_names
    }

    for artifact in artifacts:
        rel_name = artifact["path"].rsplit("/", 1)[1]
        assert rel_name != "round12_existing_outputs_artifact_index.json"
        expected = payloads[serializers.FORMAL_OUTPUT_PATHS[rel_name]]
        assert artifact["sha256"] == _sha256_upper(expected) == serializers.sha256_bytes(expected)
        assert artifact["bytes"] == len(expected)

    # No self-hash / self-entry under any field.
    assert "artifact_index" not in {a["path"] for a in artifacts}
    joined = json.dumps(index_doc, sort_keys=True)
    assert "artifact_index.json" not in artifacts[0]["path"]


# ---------------------------------------------------------------------------
# Malformed statistics keys
# ---------------------------------------------------------------------------


def test_malformed_statistics_keys_rejected() -> None:
    base = make_statistics()
    # Missing a key.
    missing = {k: v for k, v in base.items() if k != "gates"}
    with pytest.raises(ValueError, match="keys"):
        serializers._validated_statistics(missing)

    # Extra unknown key.
    extra = dict(base)
    extra["sneaky"] = 1
    with pytest.raises(ValueError, match="keys"):
        serializers._validated_statistics(extra)

    # A statistics non-mapping.
    with pytest.raises(ValueError, match="mapping"):
        serializers._validated_statistics([1, 2, 3])


# ---------------------------------------------------------------------------
# Pure calls never touch the filesystem
# ---------------------------------------------------------------------------


def test_pure_calls_create_no_files_under_tmp_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    stats = make_statistics()
    prov = make_provenance()
    binds = make_input_bindings()

    serializers.build_result_document(stats, prov)
    serializers.json_bytes(serializers.build_result_document(stats, prov))
    serializers.diagnostics_csv_bytes(
        stats["point_estimates"],
        stats["lower_bounds"],
        stats["per_seed_D_C1"],
        stats["per_family_D_C1"],
        stats["gates"],
    )
    serializers.deterministic_npz_bytes(stats["bootstrap_draws"])
    payload = serializers.deterministic_npz_bytes(stats["bootstrap_draws"])
    serializers.roundtrip_npz_bytes(payload)
    serializers.deterministic_log_jsonl(stats)
    serializers.build_formal_payloads(stats, prov, binds)

    # Nothing anywhere (including nested dirs) was created.
    assert list(tmp_path.rglob("*")) == []
