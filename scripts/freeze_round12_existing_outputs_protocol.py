"""Freeze the result-blind Round 12 existing-outputs pre-result protocol.

This command implements ONLY the Round 12 pre-result protocol-freezing layer
authorized by ``outputs/validity/round12_existing_outputs_reviewer_decision.json``.

Contract / boundaries enforced here:

* Result-blind: no new axis effect is computed, no bootstrap is executed, and
  no metric value is read from the NPZ inputs.  The two NPZ archives are
  inspected *structurally only* (key set, shape, dtype) and by hash so the
  exact allowlist can be frozen before any outcome is computed.
* No forbidden access: DAAD-X, model/checkpoint/inference and image code paths
  are never imported or touched.
* Fail closed: a SHA256, schema, or unexpected-NPZ-key mismatch raises and
  writes nothing.
* One-shot: if a reserved formal result artifact already exists, or the target
  frozen protocol exists with a different payload, this command refuses.
* Atomic JSON write: the frozen protocol is staged to a ``.tmp`` sibling and
  ``os.replace``d into place only after successful validation.
* Only ``outputs/validity/round12_existing_outputs_frozen_protocol.json`` is
  created, and only when this module is invoked explicitly (``__main__``).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.lib.format as npy_format


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = (
    ROOT / "outputs/validity/round12_existing_outputs_reviewer_decision.json"
)
MEMO_PATH = ROOT / "outputs/research_review_memo_round12_existing_outputs_direction.md"
DEFAULT_OUTPUT = ROOT / "outputs/validity/round12_existing_outputs_frozen_protocol.json"

# Exact paths and SHA-256 bindings taken from the reviewer decision, validated
# against the on-disk files before anything is written.
EXPECTED_DECISION_SCHEMA = "ARSC_ROUND12_EXISTING_OUTPUTS_REVIEWER_DECISION_V1"
EXPECTED_DECISION = "GO_FREEZE_ONE_ANALYSIS"
EXPECTED_ANALYSIS_ID = "ROUND12_PAIRED_MULTIAXIS_SUPERVISION_DOSE_INTERACTION"

# NPZ archives that are inspected structurally (key/shape/dtype only).  Their
# content hashes are bound exactly; values are never loaded for metrics.
PRIMITIVES_PATH = (
    ROOT
    / "outputs/validity/round10_corruption_formal_attempt02"
    / "round10_corruption_primitives.npz"
)
BOOTSTRAP_DRAWS_PATH = (
    ROOT
    / "outputs/validity/round10_corruption_formal_attempt02"
    / "round10_corruption_bootstrap_draws.npz"
)

# Reserved future formal-run artifact names.  This freeze step may create ONLY
# the frozen protocol JSON; any of the reserved result artifacts must be absent.
RESERVED_FORMAL_ARTIFACTS = (
    "outputs/validity/round12_existing_outputs_frozen_protocol.json",
    "outputs/validity/round12_existing_outputs_results.json",
    "outputs/validity/round12_existing_outputs_point_diagnostics.csv",
    "outputs/validity/round12_existing_outputs_component_draws.npz",
    "outputs/validity/round12_existing_outputs_artifact_index.json",
    "outputs/validity/round12_existing_outputs_protocol.log",
)

# The output allowlist: exactly one file may be created by this freeze step.
OUTPUT_ALLOWLIST = ("outputs/validity/round12_existing_outputs_frozen_protocol.json",)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    require(path.is_file(), f"required file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def generated_at_from(decision: Mapping[str, Any]) -> str:
    """Return a deterministic timestamp normalized from the reviewer decision.

    The reviewer decision carries a fixed ``generated_at_utc`` date that is
    defined once at review time.  We re-emit that date normalized to an exact
    UTC midnight so the frozen protocol bytes are fully reproducible and never
    depend on the wall clock or subprocess output.
    """
    raw = str(decision.get("generated_at_utc") or "")
    require(bool(raw), "reviewer decision missing generated_at_utc")
    date_part = raw[:10]
    require(
        len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-",
        "reviewer decision generated_at_utc is not ISO yyyy-MM-dd",
    )
    return f"{date_part}T00:00:00Z"


def npz_schema(path: Path) -> dict[str, Any]:
    """Return the structural schema (keys/shape/dtype) of an NPZ archive.

    The archive is opened as a ZIP and every ``.npy`` member is parsed
    header-only via ``numpy.lib.format.read_magic`` plus either
    ``read_array_header_1_0`` or ``read_array_header_2_0``.  The validators
    consume only the fixed magic bytes and the length-prefixed header; array
    payload bytes are never read into this process, so this stays result-blind
    and never materializes any metric value.

    The following malformed archives are rejected (fail closed):

    * duplicate member names,
    * any member that is not a ``.npy`` file,
    * object-dtype arrays (a latent pickle/arbitrary-byte path),
    * unsupported NumPy file-format versions (anything other than 1.0 / 2.0),
    * and, downstream in :func:`verify_npz_allowlist`, unexpected key names.
    """
    require(path.is_file(), f"NPZ file missing: {path}")
    require(
        not path.is_symlink() and path.is_file(),
        f"NPZ input must be a regular file, not a symlink/link: {path}",
    )
    items: list[dict[str, Any]] = []
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        require(
            len(names) == len(set(names)),
            "duplicate NPZ archive member name in structural inspection",
        )
        seen: set[str] = set()
        for name in names:
            require(
                name.endswith(".npy"),
                f"non-.npy entry in NPZ archive: {name}",
            )
            key = name[: -len(".npy")]
            require(key not in seen, f"duplicate NPZ key in structural inspection: {key}")
            seen.add(key)
            with archive.open(name) as member:
                try:
                    major, minor = npy_format.read_magic(member)
                except Exception as exc:  # malformed magic / short read
                    raise ValueError(f"invalid NPY magic for {name}: {exc}") from exc
                require(
                    (major, minor) in ((1, 0), (2, 0)),
                    f"unsupported NPY format version for {name}: {major}.{minor}",
                )
                if major == 1:
                    shape, _fortran, dtype = npy_format.read_array_header_1_0(member)
                else:
                    shape, _fortran, dtype = npy_format.read_array_header_2_0(member)
                require(
                    not getattr(dtype, "hasobject", False),
                    f"object dtype not allowed in NPZ structural scan: {name}",
                )
            items.append(
                {
                    "key": key,
                    "shape": [int(dim) for dim in shape],
                    "dtype": str(dtype),
                }
            )
    items.sort(key=lambda item: item["key"])
    return {
        "path": relative(path),
        "sha256": sha256_file(path),
        "key_count": len(items),
        "items": items,
    }


def items_map(schema: dict[str, Any]) -> dict[str, tuple[list[int], str]]:
    return {
        item["key"]: (list(item["shape"]), str(item["dtype"]))
        for item in schema["items"]
    }


def verify_npz_allowlist(
    schema: dict[str, Any],
    expected_allowlist: dict[str, tuple[list[int], str]],
    *,
    expected_sha256: str,
    expected_key_count: int,
) -> None:
    """Fail closed unless keys, shapes, dtypes, key count, and hash are exact."""
    require(
        schema["sha256"] == expected_sha256.upper(),
        f"NPZ sha256 mismatch for {schema['path']}: {schema['sha256']}",
    )
    observed = items_map(schema)
    require(
        set(observed) == set(expected_allowlist),
        f"unexpected NPZ key set for {schema['path']}: "
        f"{sorted(set(observed) ^ set(expected_allowlist))}",
    )
    require(
        schema["key_count"] == expected_key_count,
        f"NPZ key count mismatch for {schema['path']}",
    )
    for key, (shape, dtype) in expected_allowlist.items():
        require(
            observed[key][0] == list(shape),
            f"NPZ shape mismatch for {schema['path']}::{key}: {observed[key][0]}",
        )
        require(
            observed[key][1] == dtype,
            f"NPZ dtype mismatch for {schema['path']}::{key}: {observed[key][1]}",
        )


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_decision(decision: Mapping[str, Any]) -> None:
    require(
        decision.get("schema_version") == EXPECTED_DECISION_SCHEMA,
        "unexpected reviewer decision schema",
    )
    require(
        decision.get("decision") == EXPECTED_DECISION,
        "reviewer decision does not authorize freezing",
    )
    require(
        decision.get("implementation_authorized_by_this_decision") is False,
        "reviewer decision must not itself authorize implementation execution",
    )
    analysis = decision.get("main_analysis") or {}
    require(
        analysis.get("analysis_id") == EXPECTED_ANALYSIS_ID,
        "reviewer decision does not authorize the expected single analysis",
    )
    require(
        analysis.get("new_inference_required") is False,
        "reviewer decision must not require new inference",
    )
    recommend = decision.get("recommended_analysis_count")
    require(recommend == 1, "reviewer decision must recommend exactly one analysis")


def verify_input_hashes(decision: Mapping[str, Any]) -> list[dict[str, str]]:
    """Verify and return the seven input-evidence SHA bindings."""
    evidence = decision.get("input_evidence") or []
    require(len(evidence) == 7, "unexpected input-evidence item count")
    bindings: list[dict[str, str]] = []
    for item in evidence:
        path_text = item.get("path")
        expected = str(item.get("sha256", "")).upper()
        require(path_text and expected, "input-evidence missing path or sha256")
        path = ROOT / path_text
        digest = sha256_file(path)
        require(
            digest == expected,
            f"input SHA256 mismatch for {path_text}: {digest}",
        )
        bindings.append({"path": path_text, "sha256": digest})
    return bindings


def expected_r12_npz_allowlists() -> dict[str, dict[str, tuple[list[int], str]]]:
    """Exact structural allowlists asserted from the two Round 10 NPZ archives.

    These are pure key/shape/dtype expectations established by structural
    inspection only of the frozen Round 10 outputs; no metric values appear.
    """
    primitives = {
        "schema_version": ([], "<U26"),
        "seeds": ([5], "int16"),
        "families": ([3], "<U10"),
        "levels": ([5], "int8"),
        "models": ([2], "<U11"),
        "axes": ([4], "<U2"),
        "endpoint_components": ([8], "<U27"),
        "safety_diagnostic_names": ([8], "<U36"),
        "clip_id_by_image": ([4557], "int32"),
        "clip_keys": ([3904], "<U17"),
        "clip_sizes": ([3904], "int32"),
        "action_targets": ([4557, 4], "uint8"),
        "rationale_targets": ([4557, 21], "uint8"),
        "action_predictions": ([5, 3, 5, 2, 4557, 4], "bool"),
        "rationale_predictions": ([5, 3, 5, 4557, 21], "bool"),
        "confidence": ([5, 3, 5, 2, 4557], "float64"),
        "errors": ([5, 3, 5, 2, 4557], "uint8"),
        "group_ids": ([5, 3, 5, 2, 4557], "int32"),
        "group_counts": ([5, 3, 5, 2], "int32"),
        "A_tp": ([5, 3, 5, 2, 3904, 4], "uint16"),
        "A_fp": ([5, 3, 5, 2, 3904, 4], "uint16"),
        "A_fn": ([5, 3, 5, 2, 3904, 4], "uint16"),
        "R_tp": ([5, 3, 5, 3904, 21], "uint16"),
        "R_fp": ([5, 3, 5, 3904, 21], "uint16"),
        "R_fn": ([5, 3, 5, 3904, 21], "uint16"),
        "C1_action_clip_sums": ([5, 3, 5, 2, 3904], "uint16"),
        "C1_rationale_clip_sums": ([5, 3, 5, 3904], "float64"),
        "curve_A": ([5, 3, 2, 5], "float64"),
        "curve_R": ([5, 3, 1, 5], "float64"),
        "curve_S": ([5, 3, 2, 5], "float64"),
        "curve_C1": ([5, 3, 3, 5], "float64"),
        "family_axis_bottlenecks": ([5, 3, 4], "float64"),
        "endpoint_effects": ([5, 3, 8], "float64"),
        "action_per_class_f1": ([5, 3, 5, 2, 4], "float64"),
        "action_target_positive": ([5, 3, 5, 2, 4], "int64"),
        "action_predicted_positive": ([5, 3, 5, 2, 4], "int64"),
        "rationale_per_class_f1": ([5, 3, 5, 21], "float64"),
        "rationale_target_positive": ([5, 3, 5, 21], "int64"),
        "rationale_predicted_positive": ([5, 3, 5, 21], "int64"),
        "safety_diagnostics": ([5, 3, 5, 2, 8], "float64"),
    }
    draws = {
        "schema_version": ([], "<U31"),
        "seed_position_draws": ([5000, 5], "uint8"),
        "clip_position_draws": ([5000, 3904], "uint16"),
        "expanded_image_counts": ([5000], "int32"),
        "family_axis_gate_draws": ([5000, 12], "float64"),
        "endpoint_draws": ([5000, 24], "float64"),
    }
    return {
        relative(PRIMITIVES_PATH): primitives,
        relative(BOOTSTRAP_DRAWS_PATH): draws,
    }


def ensure_no_reserved_formal_artifacts(output: Path) -> None:
    for path_text in RESERVED_FORMAL_ARTIFACTS:
        path = ROOT / path_text
        if path == output:
            if path.exists() and output.exists():
                continue  # idempotent re-freeze is handled separately below
            continue
        require(
            not path.exists(),
            f"refusing freeze: reserved formal artifact exists: {path_text}",
        )


def build_protocol(
    decision: Mapping[str, Any],
    input_bindings: Sequence[Mapping[str, str]],
    primitives_schema: dict[str, Any],
    draws_schema: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Assemble the result-blind frozen protocol (no computed effects)."""
    memo = decision.get("memo") or {}
    memo_sha = str(memo.get("sha256", "")).upper()
    require(memo_sha, "reviewer decision missing memo sha256")
    require(
        sha256_file(MEMO_PATH) == memo_sha,
        "reviewer memo SHA256 differs from decision binding",
    )
    analysis = decision["main_analysis"]
    bootstrap = analysis["bootstrap"]
    multiplicity = analysis["multiplicity_control"]
    return {
        "schema_version": "ARSC_ROUND12_EXISTING_OUTPUTS_FROZEN_PROTOCOL_V1",
        "generated_at_utc": generated_at,
        "status": "FROZEN_RESULT_BLIND_PROTOCOL_ONLY",
        "result_blind": True,
        "execution": {
            "formal_run": False,
            "attempt": "attempt01",
            "new_inference": False,
            "training": False,
            "outcome_computed": False,
            "bootstrap_executed": False,
        },
        "authorization": {
            "decision_path": relative(DECISION_PATH),
            "decision_sha256": sha256_file(DECISION_PATH),
            "decision_schema": decision.get("schema_version"),
            "decision": decision.get("decision"),
            "implementation_authorized_by_this_decision": False,
            "implementation_authorized": False,
            "execution_authorized": False,
            "memo_path": relative(MEMO_PATH),
            "memo_sha256": memo_sha,
        },
        "analysis": {
            "analysis_id": analysis["analysis_id"],
            "title": analysis["title"],
            "scope": analysis["scope"],
            "cell_weighting": analysis["scope"]["cell_weighting"],
            "clean_baseline": analysis["scope"]["clean_baseline"],
            "effect_definitions": analysis["effect_definitions"],
            "directions": {
                "positive_is_favorable": True,
                "D_A": "larger D_A = stronger joint action-quality retention relative to action_only across the 12 corruption cells",
                "D_R": "larger D_R = less within-joint rationale-quality drop from clean; retention guardrail only",
                "D_S": "larger D_S = smaller joint selective-risk (tie-averaged AURC) increase relative to action_only",
                "D_C1": "larger D_C1 = fewer action flips under joint supervision relative to action_only at the nonzero cell",
            },
            "hypothesis": analysis["hypothesis"],
            "r_axis_limitation": analysis["r_axis_limitation"],
            "unit_of_analysis": analysis["unit_of_analysis"],
            "nonredundancy": analysis["nonredundancy"],
            "paper_consequence": analysis["paper_consequence"],
            "new_inference_required": False,
        },
        "margins_and_guardrails": {
            "practical_margin": 0.01,
            "c1_point_minimum": 0.01,
            "c1_lower_bound_strict_positive": True,
            "c1_minimum_positive_seeds": 4,
            "c1_family_guardrail_floor": -0.01,
            "ar_s_non_inferiority_floor": -0.01,
        },
        "gates": {
            "PASS": [
                "D_C1 grand point estimate >= 0.01 (raw float64)",
                "D_C1 q=0.0125 lower bound > 0.0 (raw float64)",
                "at least four of five seed-specific D_C1 values > 0.0",
                "each of three family-specific D_C1 values >= -0.01",
                "D_A q=0.0125 lower bound > -0.01",
                "D_R q=0.0125 lower bound > -0.01",
                "D_S q=0.0125 lower bound > -0.01",
            ],
            "PARTIAL": "all three C1 guardrails pass (point, C1 lower bound, seed count, family floor) but at least one A/R/S non-inferiority lower bound fails",
            "FAIL": "any C1 point estimate, C1 q=0.0125 lower bound, seed-count, or family guardrail fails",
        },
        "bootstrap": {
            "replicates": int(bootstrap["replicates"]),
            "draw_source": bootstrap["draw_source"],
            "seed_draw_shape": list(bootstrap["seed_draw_shape"]),
            "clip_draw_shape": list(bootstrap["clip_draw_shape"]),
            "pairing": bootstrap["pairing"],
            "metric_recomputation": bootstrap["metric_recomputation"],
            "replicate_statistic": (
                "For each replicate use the single shared seed-position and "
                "single shared clip-position draw. For every selected seed "
                "position, recompute macro-F1, tie-averaged AURC, and flip rate "
                "from the expanded clip sample for all 12 cells and both models, "
                "then form that selected seed's four D values as equal cell means; "
                "average each D over the five selected seed positions."
            ),
            "quantile": {
                "method": "linear",
                "dtype": "float64",
                "lower_quantile": 0.0125,
                "multiplicity_control": {
                    "co_primary_components": int(multiplicity["co_primary_components"]),
                    "familywise_alpha": multiplicity["familywise_alpha"],
                    "method": multiplicity["method"],
                    "lower_quantile": multiplicity["lower_quantile"],
                },
            },
            "never_bootstrap_aggregated_cell_means_only": True,
        },
        "numeric_policy": {
            "dtype": "float64",
            "nonfinite_input_or_result": "ROUND12_INCONCLUSIVE_STOP",
            "zero_denominator_macro_f1": 0.0,
            "per_class_target_and_prediction_both_empty_f1": 0.0,
            "tie_averaged_aurc_is_exact_tie_averaged_round10_semantics": True,
            "empty_metric_input": "ROUND12_INCONCLUSIVE_STOP",
            "comparison_operator": "raw float64 unrounded; >= passes margin, >0.0 is strict positive, no rounding in gates",
        },
        "clean_level0_equality": {
            "requirement": (
                "Every seed's level-0 (clean) cell must be exact across all three "
                "families for each model; a single clean baseline per seed and "
                "model is counted. Any mismatch is ROUND12_INCONCLUSIVE_STOP."
            ),
            "evaluated_before_effects": True,
        },
        "inputs": {
            "input_evidence": list(input_bindings),
            "npz_allowlists": {
                primitives_schema["path"]: {
                    "sha256": primitives_schema["sha256"],
                    "key_count": primitives_schema["key_count"],
                    "items": primitives_schema["items"],
                },
                draws_schema["path"]: {
                    "sha256": draws_schema["sha256"],
                    "key_count": draws_schema["key_count"],
                    "items": draws_schema["items"],
                },
            },
        },
        "independent_review": {
            "direction_decision": relative(DECISION_PATH),
            "direction_decision_sha256": sha256_file(DECISION_PATH),
            "direction_memo": relative(MEMO_PATH),
            "direction_memo_sha256": memo_sha,
            "reviewer_role": "independent_existing_outputs_scientific_direction_reviewer",
            "reviewer_decision": decision.get("decision"),
        },
        "output_allowlist": list(OUTPUT_ALLOWLIST),
        "forbidden_actions": [
            "no DAAD-X data access",
            "no model or checkpoint loading",
            "no inference and no new training",
            "no computation of new axis effects",
            "no bootstrap execution",
            "no selection of seeds/families/levels/models/components after seeing effects",
            "no modification of existing artifacts",
            "no metric or effect value read into this freeze",
        ],
        "one_shot_stopping": (
            "This freeze computes no outcomes. A future formal attempt must be "
            "separately authorized and must itself fail closed on one-shot "
            "stopping with exactly one execution before any results are frozen."
        ),
        "state": {"result_blind": True, "execution": False, "formal_run": False},
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse invocation arguments.

    There is deliberately no ``--output`` option: this command always writes
    the one canonical frozen protocol at ``DEFAULT_OUTPUT`` so a caller cannot
    redirect an un-validated artifact to an arbitrary path.
    """
    parser = argparse.ArgumentParser()
    return parser.parse_args(argv)


def require_regular_or_absent(path: Path) -> None:
    """Fail closed unless ``path`` is absent, or an existing regular file.

    Symlinks and special files (FIFOs, devices, directories) are rejected so
    a hostile or accidental path object can never be replaced or followed.
    """
    if not path.exists():
        require(not path.is_symlink(), f"output must not be a dangling symlink: {path}")
        return
    require(not path.is_symlink(), f"output must not be a symlink: {path}")
    require(path.is_file(), f"output must be an existing regular file: {path}")


def fsync_parent_directory(path: Path) -> None:
    """Best-effort durable flush of the output's parent directory.

    ``os.replace`` guarantees visibility but not durability; fsyncing the
    parent directory moves the rename to stable storage.  Some platforms
    (notably Windows) do not permit opening a directory for fsync, so this is
    best-effort and never re-raises.
    """
    try:
        if hasattr(os, "O_DIRECTORY"):
            flags = os.O_RDONLY | os.O_DIRECTORY
        else:
            flags = os.O_RDONLY
        dir_fd = os.open(str(path.parent), flags)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # Directory fsync is unsupported on this platform; the file-level
        # fsync above still applies. This is non-fatal here.
        pass


def main(argv: Sequence[str] | None = None) -> int:
    parse_args(argv)
    output = DEFAULT_OUTPUT

    require_regular_or_absent(output)
    require(not output.is_dir(), "output path must not be a directory")
    ensure_no_reserved_formal_artifacts(output)

    require(DECISION_PATH.is_file(), "reviewer decision missing")
    decision = read_json(DECISION_PATH)
    verify_decision(decision)
    input_bindings = verify_input_hashes(decision)

    primitives_schema = npz_schema(PRIMITIVES_PATH)
    draws_schema = npz_schema(BOOTSTRAP_DRAWS_PATH)
    allowlists = expected_r12_npz_allowlists()
    verify_npz_allowlist(
        primitives_schema,
        allowlists[relative(PRIMITIVES_PATH)],
        expected_sha256=decision["input_evidence"][0]["sha256"],
        expected_key_count=len(allowlists[relative(PRIMITIVES_PATH)]),
    )
    verify_npz_allowlist(
        draws_schema,
        allowlists[relative(BOOTSTRAP_DRAWS_PATH)],
        expected_sha256=decision["input_evidence"][1]["sha256"],
        expected_key_count=len(allowlists[relative(BOOTSTRAP_DRAWS_PATH)]),
    )

    protocol = build_protocol(
        decision,
        input_bindings,
        primitives_schema,
        draws_schema,
        generated_at=generated_at_from(decision),
    )
    payload = json_bytes(protocol)

    if output.exists():
        existing = output.read_bytes()
        if existing != payload:
            raise ValueError(
                f"existing frozen protocol differs; refusing overwrite: {output}"
            )
        print(f"UNCHANGED {output.relative_to(ROOT)}")
        print(f"SHA256 {sha256_file(output)}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    require_regular_or_absent(output)
    temporary = output.with_name(output.name + ".tmp")
    require(not temporary.exists(), "temporary output already exists")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        fsync_parent_directory(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f"WROTE {output.relative_to(ROOT)}")
    print(f"SHA256 {sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
