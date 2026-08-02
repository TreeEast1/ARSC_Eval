"""Pure Phase-2C output serializers for the Round 12 existing-outputs run.

This module is the **pure byte-production layer** for the Round 12 formal
attempt-01 outputs.  It deliberately contains NO file transactions, NO runner,
and NO ``main`` connection: every function accepts in-memory values and returns
``bytes`` or a JSON-native ``dict``.  Nothing is written to disk anywhere, no
wall-clock time is embedded, and no canonical Round 12 core / metrics module is
imported or called.  The round-trip and determinism guarantees therefore rest
entirely on the deterministic bytes these helpers produce.

Frozen contract
---------------
The five formal output names are fixed exactly by the Round 12 protocol and
live flat under ``outputs/validity``:

* ``round12_existing_outputs_results.json``          -- :func:`build_result_document`
* ``round12_existing_outputs_point_diagnostics.csv``  -- :func:`diagnostics_csv_bytes`
* ``round12_existing_outputs_component_draws.npz``    -- :func:`deterministic_npz_bytes`
* ``round12_existing_outputs_artifact_index.json``    -- built inside :func:`build_formal_payloads`
* ``round12_existing_outputs_protocol.log``           -- :func:`deterministic_log_jsonl`

Determinism rules
-----------------
* ``json_bytes`` uses ``allow_nan=False`` and ``sort_keys=True`` so identical
  documents serialize to identical UTF-8 bytes and non-finite floats fail.
* The NPZ payload holds exactly four arrays ``D_A``, ``D_R``, ``D_S``, ``D_C1``
  as ``float64`` shape ``(5000,)`` written in that fixed member order with a
  fixed 1980-01-01 member timestamp and no compression (``ZIP_STORED``), using
  ``numpy.lib.format.write_array`` so the byte stream is fully deterministic.
* The log is a JSONL with a fixed ordered sequence of named events and no
  wall-clock timestamps.
* ``build_formal_payloads`` hashes the four non-index payload bytes (result,
  CSV, NPZ, log) plus caller-supplied input/provenance bindings into
  ``artifact_index.json``.  It does **not** self-hash.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Frozen naming / schema / structural constants.
# ---------------------------------------------------------------------------

# The exact five formal output base names (in the canonical write order except
# artifact_index.json, which is produced last by build_formal_payloads and
# references the other four).  These are the frozen flat outputs/validity
# filenames from the Round 12 protocol.
FORMAL_OUTPUT_NAMES: tuple[str, ...] = (
    "round12_existing_outputs_results.json",
    "round12_existing_outputs_point_diagnostics.csv",
    "round12_existing_outputs_component_draws.npz",
    "round12_existing_outputs_artifact_index.json",
    "round12_existing_outputs_protocol.log",
)

# Frozen Round 12 formal-01 output directory: the five files live flat here.
FORMAL_OUTPUT_DIR = Path("outputs/validity")

FORMAL_OUTPUT_PATHS: Mapping[str, Path] = {
    name: FORMAL_OUTPUT_DIR / name for name in FORMAL_OUTPUT_NAMES
}

RESULT_SCHEMA = "ARSC_ROUND12_EXISTING_OUTPUTS_FORMAL_RESULTS_V1"
INDEX_SCHEMA = "ARSC_ROUND12_EXISTING_OUTPUTS_ARTIFACT_INDEX_V1"
LOG_SCHEMA = "ARSC_ROUND12_EXISTING_OUTPUTS_FORMAL_LOG_V1"

# Frozen Round 12 analysis identity (from the frozen protocol / reviewer
# decision).  The result document and log bind these; they are never clock- or
# run-derived so determinism is preserved.
ANALYSIS_ID = "ROUND12_PAIRED_MULTIAXIS_SUPERVISION_DOSE_INTERACTION"
ATTEMPT = "attempt01"

# Exact key set of the ``statistics`` document produced by
# round12_existing_outputs.round12_statistics.  The bootstrap component arrays
# are deliberately included here so they are validated exactly, but they only
# ever appear inside the NPZ payload (never in any JSON/CSV/log payload).
EXACT_STATISTICS_KEYS: tuple[str, ...] = (
    "point_estimates",
    "per_seed_D_C1",
    "per_family_D_C1",
    "lower_bounds",
    "gates",
    "bootstrap_draws",
)

D_AXES: tuple[str, ...] = ("D_A", "D_R", "D_S", "D_C1")
REPLICATES = 5000
SEED_COUNT = 5
FAMILY_COUNT = 3

# The frozen 7 gate check names produced by round12_existing_outputs.assess_gate.
EXPECTED_GATE_KEYS: tuple[str, ...] = (
    "D_C1 point >= 0.01",
    "D_C1 q=0.0125 lower bound > 0.0",
    ">= 4 of 5 seed-specific D_C1 > 0.0",
    "each family D_C1 >= -0.01",
    "D_A q=0.0125 lower bound > -0.01",
    "D_R q=0.0125 lower bound > -0.01",
    "D_S q=0.0125 lower bound > -0.01",
)

# Log event names in the fixed order they are emitted.
LOG_EVENT_NAMES: tuple[str, ...] = (
    "start",
    "statistics_validated",
    "point_statistics",
    "component_draws",
    "lower_bounds",
    "gates_assessed",
    "result_document_built",
    "diagnostics_serialized",
    "npz_serialized",
    "log_serialized",
    "artifact_index_built",
    "done",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


# ---------------------------------------------------------------------------
# JSON bytes helper (deterministic, non-finite rejecting).
# ---------------------------------------------------------------------------


def require_no_json_arrays(value: Any) -> None:
    """Fail closed if ``value`` still contains any NumPy array or scalar.

    Guardrail for the result document: everything that is meant to reach a JSON
    file must already be a JSON-native value (``int``/``float``/``str``/``bool``/
    ``None``/list/dict).  Lists are recursive; numpy arrays and scalars are
    rejected outright so a stray in-memory array cannot leak into a JSON file.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            require(isinstance(k, str), "JSON object key must be text")
            require_no_json_arrays(v)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            require_no_json_arrays(item)
        return
    require(
        not isinstance(value, np.ndarray) and not isinstance(value, np.generic),
        "NumPy array/scalar is not allowed inside a JSON payload",
    )


def json_bytes(value: Mapping[str, Any] | Sequence[Any] | Any) -> bytes:
    """Return deterministic newline-terminated UTF-8 JSON bytes with
    ``allow_nan=False`` and ``sort_keys=True``.  NumPy arrays inside the value
    are rejected first so the caller cannot accidentally leak a non-JSON-native
    array.  A single trailing ``\\n`` is appended so every formal JSON payload
    is newline terminated."""
    require_no_json_arrays(value)
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


# ---------------------------------------------------------------------------
# NPZ bytes helper (deterministic component draws).
# ---------------------------------------------------------------------------


def validate_draws(draws: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Validate the four component draw arrays.

    Requires exactly the four keys ``D_A/D_R/D_S/D_C1``, each an **already
    ``float64`` ndarray** of exactly shape ``(REPLICATES,)`` with all finite
    values.  This is a strict fail-closed check: inputs are *rejected* (never
    coerced) unless they are already ``numpy.ndarray`` with ``dtype ==
    numpy.float64`` and ``shape == (REPLICATES,)``, so a caller cannot smuggle
    an integer/int32/float32 payload past the gate and rely on silent coercion.
    """
    require(set(draws) == set(D_AXES), "draws must contain exactly D_A/D_R/D_S/D_C1")
    validated: dict[str, np.ndarray] = {}
    for axis in D_AXES:
        array = draws[axis]
        require(
            isinstance(array, np.ndarray),
            f"{axis} draws must already be a numpy.ndarray (no coercion)",
        )
        require(array.dtype == np.float64, f"{axis} draws dtype must be exactly float64")
        require(
            array.shape == (REPLICATES,),
            f"{axis} draws must be shape ({REPLICATES},)",
        )
        require(np.all(np.isfinite(array)), f"{axis} draws contain nonfinite values")
        validated[axis] = array
    return validated


def deterministic_npz_bytes(draws: Mapping[str, Any]) -> bytes:
    """Serialize exactly D_A/D_R/D_S/D_C1, float64 (5000,), to deterministic
    NPZ bytes.

    Uses ``io.BytesIO`` + ``zipfile.ZipFile`` with a fixed 1980-01-01 member
    timestamp and a fixed member order, each member written with
    ``numpy.lib.format.write_array`` into a ``.npy`` member.  Compression is
    ``ZIP_STORED`` so the archive bytes are stable across zlib versions.
    """
    validated = validate_draws(draws)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for axis in D_AXES:
            info = zipfile.ZipInfo(axis + ".npy")
            info.date_time = (1980, 1, 1, 0, 0, 0)  # fixed frozen timestamp
            info.compress_type = zipfile.ZIP_STORED
            member = io.BytesIO()
            np.lib.format.write_array(member, validated[axis], allow_pickle=False)
            archive.writestr(info, member.getvalue())
    return buffer.getvalue()


def roundtrip_npz_bytes(data: bytes) -> dict[str, np.ndarray]:
    """Decode deterministic NPZ bytes back into the four arrays (test helper /
    validation-only).  In-memory only; never opens a file."""
    with zipfile.ZipFile(io.BytesIO(data), mode="r") as archive:
        names = archive.namelist()
        require(names == [axis + ".npy" for axis in D_AXES], "unexpected NPZ member order")
        result: dict[str, np.ndarray] = {}
        for axis in D_AXES:
            member_name = axis + ".npy"
            info = archive.getinfo(member_name)
            # Fixed 1980-01-01 timestamp is part of the byte determinism.
            require(
                info.date_time == (1980, 1, 1, 0, 0, 0),
                "NPZ member timestamp is not the frozen 1980 value",
            )
            with archive.open(member_name, mode="r") as stream:
                result[axis] = np.lib.format.read_array(stream, allow_pickle=False)
    return result


# ---------------------------------------------------------------------------
# Point-diagnostics CSV bytes helper.
# ---------------------------------------------------------------------------


def diagnostics_csv_bytes(
    point_estimates: Mapping[str, float],
    lower_bounds: Mapping[str, float],
    per_seed_dc1: Any,
    per_family_dc1: Any,
    gates: Mapping[str, Any],
) -> bytes:
    """Serialize a fixed UTF-8 diagnostics CSV.

    The header is fixed and rows are emitted in this order:
      4 ``point`` records (D_A,D_R,D_S,D_C1),
      4 ``lower_bound`` records (same axes),
      5 ``seed`` records (per-seed D_C1),
      3 ``family`` records (per-family D_C1),
      7 ``gate`` records (the frozen check names).
    """
    points = {
        axis: float(point_estimates[axis]) for axis in D_AXES
    }
    lowers = {axis: float(lower_bounds[axis]) for axis in D_AXES}
    seeds = [float(x) for x in np.asarray(per_seed_dc1, dtype=np.float64).reshape(-1)]
    families = [float(x) for x in np.asarray(per_family_dc1, dtype=np.float64).reshape(-1)]
    require(len(seeds) == SEED_COUNT, f"per-seed D_C1 must have {SEED_COUNT} values")
    require(
        len(families) == FAMILY_COUNT,
        f"per-family D_C1 must have {FAMILY_COUNT} values",
    )
    require(
        set(gates["checks"]) == set(EXPECTED_GATE_KEYS),
        "gate checks do not match the frozen 7 keys exactly",
    )
    for value in (*points.values(), *lowers.values(), *seeds, *families):
        require(np.isfinite(value), "diagnostics CSV contains a nonfinite value")

    header = "record_type,axis,index,value,check_name,passed"
    lines = [header]

    def _fmt(value: float) -> str:
        # repr-based formatting keeps full float64 precision deterministically,
        # avoiding locale-sensitive str().
        return repr(float(value))

    for axis in D_AXES:
        lines.append(f"point,{axis},,{_fmt(points[axis])},,")
    for axis in D_AXES:
        lines.append(f"lower_bound,{axis},,{_fmt(lowers[axis])},,")
    for seed_index, value in enumerate(seeds):
        lines.append(f"seed,D_C1,{seed_index},{_fmt(value)},,")
    for family_index, value in enumerate(families):
        lines.append(f"family,D_C1,{family_index},{_fmt(value)},,")
    for name in EXPECTED_GATE_KEYS:
        passed = gates["checks"][name]
        require(isinstance(passed, bool), f"gate check {name!r} must be boolean")
        passed_text = "True" if passed else "False"
        lines.append(f"gate,,,,{name},{passed_text}")

    payload = ("\n".join(lines) + "\n").encode("utf-8")
    return payload


def _validated_statistics(statistics: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact public output of ``round12_statistics``.

    This deliberately performs no statistical recomputation.  It only checks
    structure, finiteness, and internal gate consistency before serialization.
    """
    require(isinstance(statistics, Mapping), "statistics must be a mapping")
    require(
        set(statistics) == set(EXACT_STATISTICS_KEYS),
        "statistics keys do not match the frozen contract",
    )

    points_raw = statistics["point_estimates"]
    lowers_raw = statistics["lower_bounds"]
    require(isinstance(points_raw, Mapping), "point_estimates must be a mapping")
    require(isinstance(lowers_raw, Mapping), "lower_bounds must be a mapping")
    require(set(points_raw) == set(D_AXES), "point-estimate axes mismatch")
    require(set(lowers_raw) == set(D_AXES), "lower-bound axes mismatch")
    for axis in D_AXES:
        require(type(points_raw[axis]) is float, f"{axis} point estimate must be float")
        require(type(lowers_raw[axis]) is float, f"{axis} lower bound must be float")
    points = {axis: points_raw[axis] for axis in D_AXES}
    lowers = {axis: lowers_raw[axis] for axis in D_AXES}
    require(
        all(np.isfinite(value) for value in (*points.values(), *lowers.values())),
        "point estimates and lower bounds must be finite",
    )

    seeds_raw = statistics["per_seed_D_C1"]
    families_raw = statistics["per_family_D_C1"]
    require(
        isinstance(seeds_raw, np.ndarray)
        and seeds_raw.dtype == np.float64
        and seeds_raw.shape == (SEED_COUNT,),
        "per_seed_D_C1 must be float64 shape (5,)",
    )
    require(
        isinstance(families_raw, np.ndarray)
        and families_raw.dtype == np.float64
        and families_raw.shape == (FAMILY_COUNT,),
        "per_family_D_C1 must be float64 shape (3,)",
    )
    require(
        np.all(np.isfinite(seeds_raw)) and np.all(np.isfinite(families_raw)),
        "seed/family D_C1 values must be finite",
    )

    gates_raw = statistics["gates"]
    require(isinstance(gates_raw, Mapping), "gates must be a mapping")
    require(
        set(gates_raw) == {"verdict", "checks", "c1_pass", "ars_pass"},
        "gate keys mismatch",
    )
    checks_raw = gates_raw["checks"]
    require(isinstance(checks_raw, Mapping), "gate checks must be a mapping")
    require(set(checks_raw) == set(EXPECTED_GATE_KEYS), "gate check names mismatch")
    checks: dict[str, bool] = {}
    for name in EXPECTED_GATE_KEYS:
        require(isinstance(checks_raw[name], bool), f"gate check {name!r} must be bool")
        checks[name] = checks_raw[name]
    require(isinstance(gates_raw["c1_pass"], bool), "c1_pass must be bool")
    require(isinstance(gates_raw["ars_pass"], bool), "ars_pass must be bool")
    expected_c1 = all(checks[name] for name in EXPECTED_GATE_KEYS[:4])
    expected_ars = all(checks[name] for name in EXPECTED_GATE_KEYS[4:])
    require(gates_raw["c1_pass"] == expected_c1, "c1_pass is inconsistent")
    require(gates_raw["ars_pass"] == expected_ars, "ars_pass is inconsistent")
    expected_verdict = "PASS" if expected_c1 and expected_ars else (
        "PARTIAL" if expected_c1 else "FAIL"
    )
    require(gates_raw["verdict"] == expected_verdict, "gate verdict is inconsistent")

    draws = validate_draws(statistics["bootstrap_draws"])
    return {
        "point_estimates": points,
        "lower_bounds": lowers,
        "per_seed_D_C1": seeds_raw.copy(),
        "per_family_D_C1": families_raw.copy(),
        "gates": {
            "verdict": expected_verdict,
            "checks": checks,
            "c1_pass": expected_c1,
            "ars_pass": expected_ars,
        },
        "bootstrap_draws": {axis: draws[axis].copy() for axis in D_AXES},
    }


def build_result_document(
    statistics: Mapping[str, Any], provenance: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the JSON-native formal result document (component draws excluded)."""
    validated = _validated_statistics(statistics)
    require(isinstance(provenance, Mapping), "provenance must be a mapping")
    require_no_json_arrays(provenance)
    return {
        "schema_version": RESULT_SCHEMA,
        "analysis_id": ANALYSIS_ID,
        "attempt": ATTEMPT,
        "replicates": REPLICATES,
        "point_estimates": validated["point_estimates"],
        "lower_bounds": validated["lower_bounds"],
        "per_seed_D_C1": validated["per_seed_D_C1"].tolist(),
        "per_family_D_C1": validated["per_family_D_C1"].tolist(),
        "gates": validated["gates"],
        "provenance": dict(provenance),
    }


def deterministic_log_jsonl(statistics: Mapping[str, Any]) -> bytes:
    """Create a fixed-sequence, clock-free JSONL audit log."""
    validated = _validated_statistics(statistics)
    event_details: dict[str, Mapping[str, Any]] = {
        "start": {"analysis_id": ANALYSIS_ID, "attempt": ATTEMPT},
        "statistics_validated": {"status": "ok"},
        "point_statistics": {"axes": list(D_AXES)},
        "component_draws": {"axes": list(D_AXES), "replicates": REPLICATES},
        "lower_bounds": {"quantile": 0.0125},
        "gates_assessed": {"verdict": validated["gates"]["verdict"]},
        "result_document_built": {"schema_version": RESULT_SCHEMA},
        "diagnostics_serialized": {"format": "csv"},
        "npz_serialized": {"format": "npz"},
        "log_serialized": {"schema_version": LOG_SCHEMA},
        "artifact_index_built": {"schema_version": INDEX_SCHEMA},
        "done": {"status": "complete"},
    }
    lines = [
        json.dumps(
            {"schema_version": LOG_SCHEMA, "sequence": sequence, "event": name, **event_details[name]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        for sequence, name in enumerate(LOG_EVENT_NAMES)
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_formal_payloads(
    statistics: Mapping[str, Any],
    provenance: Mapping[str, Any],
    input_bindings: Mapping[str, Any],
) -> dict[Path, bytes]:
    """Build exactly the five frozen formal payloads, entirely in memory."""
    validated = _validated_statistics(statistics)
    require(isinstance(input_bindings, Mapping), "input_bindings must be a mapping")
    require_no_json_arrays(input_bindings)

    result_document = build_result_document(statistics, provenance)
    result_payload = json_bytes(result_document)
    csv_payload = diagnostics_csv_bytes(
        validated["point_estimates"],
        validated["lower_bounds"],
        validated["per_seed_D_C1"],
        validated["per_family_D_C1"],
        validated["gates"],
    )
    npz_payload = deterministic_npz_bytes(validated["bootstrap_draws"])
    log_payload = deterministic_log_jsonl(statistics)

    non_index: tuple[tuple[str, bytes], ...] = (
        (FORMAL_OUTPUT_NAMES[0], result_payload),
        (FORMAL_OUTPUT_NAMES[1], csv_payload),
        (FORMAL_OUTPUT_NAMES[2], npz_payload),
        (FORMAL_OUTPUT_NAMES[4], log_payload),
    )
    index_document = {
        "schema_version": INDEX_SCHEMA,
        "analysis_id": ANALYSIS_ID,
        "attempt": ATTEMPT,
        "artifacts": [
            {"path": str(FORMAL_OUTPUT_PATHS[name]).replace("\\", "/"),
             "sha256": sha256_bytes(payload), "bytes": len(payload)}
            for name, payload in non_index
        ],
        "provenance": dict(provenance),
        "input_bindings": dict(input_bindings),
        "self_hash_excluded": True,
    }
    index_payload = json_bytes(index_document)
    return {
        FORMAL_OUTPUT_PATHS[FORMAL_OUTPUT_NAMES[0]]: result_payload,
        FORMAL_OUTPUT_PATHS[FORMAL_OUTPUT_NAMES[1]]: csv_payload,
        FORMAL_OUTPUT_PATHS[FORMAL_OUTPUT_NAMES[2]]: npz_payload,
        FORMAL_OUTPUT_PATHS[FORMAL_OUTPUT_NAMES[3]]: index_payload,
        FORMAL_OUTPUT_PATHS[FORMAL_OUTPUT_NAMES[4]]: log_payload,
    }
