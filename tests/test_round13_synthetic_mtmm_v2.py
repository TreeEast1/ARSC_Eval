"""Focused tests for the Round 13 V2 protocol draft (result-blind preclaim supersession).

These tests prove that V2:

* reuses V1 worlds, feature roles, rule selections, replacement orders, seeds,
  and qualities byte-for-byte (no resampling);
* freezes the exact random-action seed bytes and SHA-256 digest[31]&1 XOR rule;
* freezes exact Boolean semantics including 2-way and 4-way MAJORITY ties
  (ties false) and AND/OR/XOR/PARITY;
* carries the immutable lineage binding V1 path / exact V1 SHA-256 / V1 schema /
  round13_attempt01 / PRECLAIM_RESULT_BLIND / formal_claim_absent / SUPERSEDED_PRECLAIM,
  with the two unpinned reason codes;
* uses V2 paths (round13_synthetic_mtmm_v2_*), attempt round13_attempt02, and
  claim schema ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V2, and refuses when any legacy
  V1 or any V2 formal artifact exists;
* keeps exactly two unchanged scientific verdict strings; process statuses are
  never scientific verdicts;
* canonical exclusive publication is proven only in pytest-temp output; and
* contains no outcomes (result-blind).

It never issues GO_FREEZE or GO_RUN.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

import arsc_eval.round13_synthetic_mtmm as v1
import arsc_eval.round13_synthetic_mtmm_v2 as v2
from scripts.freeze_round13_synthetic_mtmm_v2_protocol import (
    build_frozen_protocol,
    canonical_json_bytes,
    publish_exclusive,
    refuse_if_formal_artifacts,
)

ROOT = Path(__file__).resolve().parents[1]
V1_PROTOCOL_PATH = ROOT / v2.V1_PROTOCOL_REL
V1_RAW = V1_PROTOCOL_PATH.read_bytes()
assert hashlib.sha256(V1_RAW).hexdigest().upper() == v2.V1_PROTOCOL_SHA256
V1_FROZEN = json.loads(V1_RAW.decode("utf-8"))


# ---------------------------------------------------------------------------
# No resampling over V1 (requirement "reuse ... byte-for-byte; do not resample").
# ---------------------------------------------------------------------------
def test_v2_worlds_and_orders_are_byte_identical_to_v1() -> None:
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    assert contract["design"]["worlds"] == V1_FROZEN["design"]["worlds"]
    assert contract["design"]["replacement_orders"] == V1_FROZEN["design"]["replacement_orders"]
    assert contract["evaluation"] == V1_FROZEN["evaluation"]


def test_v2_contract_reuses_v1_generator_qualities_and_namespace() -> None:
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    assert contract["design"]["row_confidence_contract"]["generator_quality"] == (
        v1.ROW_CONFIDENCE_CONTRACT["generator_quality"]
    )
    assert contract["random_action"]["namespace"] == v1.NAMESPACE
    assert contract["design"]["doses"] == list(v1.DOSES)


# ---------------------------------------------------------------------------
# Exact random-action seed bytes and digest bit (requirement 3).
# ---------------------------------------------------------------------------
def test_example_random_action_seed_bytes_exact() -> None:
    expected = (
        b"ARSC_ROUND13_SYNTHETIC_MTMM_V1:generator_seed:random_matched_sparsity:action:0:0000:0"
    )
    assert v2.random_action_seed_bytes(0, 0, 0) == expected
    assert v2.EXAMPLE_RANDOM_ACTION_SEED == expected


def test_example_seed_digest_bit_and_xor() -> None:
    digest = hashlib.sha256(v2.EXAMPLE_RANDOM_ACTION_SEED).digest()
    expected_bit = digest[31] & 1
    assert v2.random_action_lsb(v2.EXAMPLE_RANDOM_ACTION_SEED) == expected_bit == 1
    # truth XOR bit: truth 0 -> 1, truth 1 -> 0 for the example.
    assert v2.random_matched_sparsity_action_bit("world_00", 0, 0, 0) == 1
    assert v2.random_matched_sparsity_action_bit("world_00", 0, 0, 1) == 0


# ---------------------------------------------------------------------------
# Frozen Boolean semantics including ties (requirement 2).
# ---------------------------------------------------------------------------
def test_majority_two_way_tie_is_false() -> None:
    # 2-input MAJORITY threshold = 2//2+1 = 2; ties (1,1 / 0,0) are strict.
    assert v2.majority([1, 1]) == 1
    assert v2.majority([1, 0]) == 0  # tie -> false
    assert v2.majority([0, 1]) == 0  # tie -> false
    assert v2.majority([0, 0]) == 0


def test_majority_four_input_threshold_is_three_ties_false() -> None:
    assert v2.BOOLEAN_SEMANTICS["FOUR_INPUT_THRESHOLD"] == 3
    assert v2.majority([1, 1, 0, 0]) == 0  # 2 < 3 -> false (even tie)
    assert v2.majority([1, 1, 1, 0]) == 1  # 3 >= 3 -> true
    assert v2.majority([1, 1, 1, 1]) == 1
    assert v2.majority([0, 0, 0, 1]) == 0


def test_boolean_and_or_xor_parity_semantics() -> None:
    assert v2.and_op(1, 1) == 1 and v2.and_op(1, 0) == 0
    assert v2.or_op(0, 0) == 0 and v2.or_op(0, 1) == 1
    assert v2.xor_op(1, 1) == 0 and v2.xor_op(0, 1) == 1
    assert v2.parity([1, 0, 1]) == 0
    assert v2.parity([1, 0, 0]) == 1
    assert v2.BOOLEAN_SEMANTICS["MAJORITY_TIES"] is False
    assert "floor(n/2)+1" in v2.BOOLEAN_SEMANTICS["MAJORITY_THRESHOLD"]


# ---------------------------------------------------------------------------
# Immutable lineage (requirement 4).
# ---------------------------------------------------------------------------
def test_lineage_binds_v1_exactly() -> None:
    lineage = v2.LINEAGE["supersedes"]
    assert lineage["path"] == "outputs/validity/round13_synthetic_mtmm_frozen_protocol.json"
    assert lineage["schema"] == "arsc-round13-synthetic-mtmm-protocol-v1"
    assert lineage["prior_attempt"] == "round13_attempt01"
    assert lineage["phase"] == "PRECLAIM_RESULT_BLIND"
    assert lineage["formal_claim_absent"] is True
    assert lineage["status"] == "SUPERSEDED_PRECLAIM"
    assert set(lineage["reason_codes"]) == {
        "UNPINNED_EVEN_MAJORITY_THRESHOLD",
        "RANDOM_ACTION_SEED_BYTES",
    }


def test_lineage_binds_exact_v1_sha256() -> None:
    assert v2.V1_PROTOCOL_SHA256 == (
        "7C32F1DB779B1D99FA7118E496196DD325930E169055637639AE66806DF4890C"
    )
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    assert contract["lineage"]["supersedes"]["sha256"] == v2.V1_PROTOCOL_SHA256


# ---------------------------------------------------------------------------
# V2 paths / attempt / schema / preflight refusal (requirements 1 & 5).
# ---------------------------------------------------------------------------
def test_v2_schema_path_attempt_and_claim_schema() -> None:
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    assert contract["schema_version"] == "arsc-round13-synthetic-mtmm-protocol-v2"
    assert v2.FROZEN_PROTOCOL_OUTPUT == (
        "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
    )
    formal = contract["formal_execution"]["one_shot"]
    assert formal["attempt"] == "round13_attempt02"
    assert formal["claim_schema"] == "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V2"
    assert formal["claim_path"] == "outputs/validity/round13_synthetic_mtmm_v2_formal_claim.json"
    execution = contract["formal_execution"]
    assert execution["artifact_allowlist"] == list(v2.V2_ARTIFACT_ALLOWLIST)
    assert execution["preclaim_forbidden_artifacts"] == list(v2.V2_PREFORMAL_ARTIFACT_RELS)
    assert execution["hash_closure"] == v2.V2_HASH_CLOSURE
    assert v2.V2_PROTOCOL_NAME in execution["hash_closure"]["index_records"]
    assert execution["hash_closure"]["index_self_excluded"] is True
    assert execution["hash_closure"]["claim_cycle_excluded"] is True
    assert execution["hash_closure"]["claim_is_not_rewritten"] is True
    assert contract["prior_protocol_status"] == "SUPERSEDED_PRECLAIM"


def test_v2_formal_artifact_paths_use_v2_prefix() -> None:
    assert v2.FORMAL_CLAIM_NAME.startswith("round13_synthetic_mtmm_v2_")
    assert v2.FORMAL_RESULTS_NAME.startswith("round13_synthetic_mtmm_v2_")
    assert v2.FORMAL_VERDICT_NAME.startswith("round13_synthetic_mtmm_v2_")
    assert v2.FORMAL_INDEX_NAME.startswith("round13_synthetic_mtmm_v2_")
    for rel in v2.V2_PREFORMAL_ARTIFACT_RELS:
        assert rel.startswith("round13_synthetic_mtmm_v2_")


def test_preflight_refuses_legacy_v1_formal_artifact(tmp_path) -> None:
    (tmp_path / "outputs/validity").mkdir(parents=True, exist_ok=True)
    legacy = tmp_path / "outputs/validity/round13_synthetic_mtmm_formal_claim.json"
    legacy.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="legacy V1 or V2 formal artifact"):
        v2.run_preflight(tmp_path)


def test_preflight_refuses_v2_formal_artifact(tmp_path) -> None:
    (tmp_path / "outputs/validity").mkdir(parents=True, exist_ok=True)
    v2art = tmp_path / "outputs/validity/round13_synthetic_mtmm_v2_verdict.json"
    v2art.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="legacy V1 or V2 formal artifact"):
        v2.refuse_if_formal_artifacts_exist(tmp_path)


def test_preflight_passes_and_is_result_blind(tmp_path) -> None:
    target = tmp_path / v2.V1_PROTOCOL_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(V1_RAW)
    result = v2.run_preflight(tmp_path)
    assert result["status"] == "PREFLIGHT_V2_PASS"
    assert result["status_is_not_go_run"] is True
    assert result["status_is_not_a_scientific_verdict"] is True
    assert result["worlds_resampled"] is False
    assert result["replacement_orders_resampled"] is False
    assert result["legacy_or_v2_formal_artifacts_present"] is False
    assert result["result_blind"] is True


# ---------------------------------------------------------------------------
# Exactly two scientific verdicts unchanged (requirement 6).
# ---------------------------------------------------------------------------
def test_exactly_two_scientific_verdicts_unchanged() -> None:
    assert v2.FINAL_VERDICTS == (
        "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS",
        "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED",
    )
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    assert contract["formal_execution"]["possible_scientific_verdicts"] == list(
        v2.FINAL_VERDICTS
    )
    # Process statuses are not scientific verdicts.
    for status in (
        v2.SUPERSEDED_STATUS,
        v2.PRECLAIM_PHASE,
        "PREFORMAL_REFUSAL_V2",
        "POSTCLAIM_INFRASTRUCTURE_FAILURE_V2",
        "GO_RUN_V2",
        "PREFLIGHT_V2_PASS",
    ):
        assert status not in v2.FINAL_VERDICTS


# ---------------------------------------------------------------------------
# Absence of outcomes (result-blind).
# ---------------------------------------------------------------------------
def test_v2_contract_has_no_outcomes() -> None:
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    forbidden = {
        "observed", "estimate", "confidence_interval", "gate_pass",
        "verdict", "p_value", "effect_size", "result",
    }
    assert not forbidden.intersection(contract)
    # There is no claim/result/verdict/index artifact payload inside the contract.
    assert "formal_claim" not in contract
    assert "results" not in contract
    assert "verdict" not in contract


def test_v2_contract_is_canonical_compact() -> None:
    contract = v2.build_contract(V1_FROZEN, include_replacement_orders=False)
    encoded = canonical_json_bytes(contract)
    assert encoded.endswith(b"\n") and b"\n" not in encoded[:-1]
    assert encoded == canonical_json_bytes(json.loads(encoded))


# ---------------------------------------------------------------------------
# Canonical exclusive publication to pytest temp only (requirement 7).
# ---------------------------------------------------------------------------
def test_exclusive_publication_refuses_overwrite(tmp_path) -> None:
    target = tmp_path / "protocol.json"
    publish_exclusive(target, b"first\n", root=tmp_path)
    with pytest.raises(FileExistsError):
        publish_exclusive(target, b"second\n", root=tmp_path)
    assert target.read_bytes() == b"first\n"


def test_v1_frozen_bytes_sha_binds_lineage_when_present(tmp_path) -> None:
    # A temp V1 file whose own SHA differs from the awaited lineage digest must
    # be rejected by build_frozen_protocol (the guard, not the bytes).
    (tmp_path / "outputs/validity").mkdir(parents=True, exist_ok=True)
    fake_v1 = tmp_path / v2.V1_PROTOCOL_REL
    fake_v1.parent.mkdir(parents=True, exist_ok=True)
    fake_v1.write_bytes(b"not-the-real-v1-bytes\n")
    with pytest.raises(ValueError, match="V1 frozen bytes SHA-256 differs"):
        build_frozen_protocol(tmp_path)


def test_refuse_on_v2_or_legacy_formal_artifact_for_freezer(tmp_path) -> None:
    (tmp_path / "outputs/validity").mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "outputs/validity/round13_synthetic_mtmm_results.json"
    artifact.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="formal artifact"):
        refuse_if_formal_artifacts(tmp_path)


def test_freezer_canonical_publication_to_pytest_temp(tmp_path) -> None:
    """Prove canonical compact JSON + exclusive publication in a pytest temp dir."""
    protocol = v2.build_contract(V1_FROZEN, include_replacement_orders=True)
    payload = canonical_json_bytes(protocol)
    out = tmp_path / "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    publish_exclusive(out, payload, root=tmp_path)
    # Exclusive/no-overwrite.
    with pytest.raises(FileExistsError):
        publish_exclusive(out, payload, root=tmp_path)
    written = out.read_bytes()
    assert written == payload
    # Canonical compact JSON round-trip.
    assert canonical_json_bytes(json.loads(written)) == written


def test_interrupted_publication_never_creates_final(tmp_path, monkeypatch) -> None:
    out = tmp_path / "outputs/validity/protocol.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    real_write = os.write
    calls = 0

    def interrupted(descriptor, payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_write(descriptor, payload[:1])
        raise OSError("simulated interruption")

    monkeypatch.setattr(os, "write", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        publish_exclusive(out, b"complete-payload\n", root=tmp_path)
    assert not out.exists()
    candidate = out.with_name(f".{out.name}.candidate.tmp")
    assert candidate.exists()


def test_preflight_rejects_dangling_formal_symlink_when_available(tmp_path) -> None:
    parent = tmp_path / "outputs/validity"
    parent.mkdir(parents=True, exist_ok=True)
    artifact = parent / "round13_synthetic_mtmm_v2_formal_claim.json"
    try:
        os.symlink(parent / "missing-target.json", artifact)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    with pytest.raises(FileExistsError, match="formal artifact"):
        v2.refuse_if_formal_artifacts_exist(tmp_path)


# ---------------------------------------------------------------------------
# Focused provenance verifier tests (verify_v2_frozen_bytes) in pytest temp.
# ---------------------------------------------------------------------------
def _build_temp_v2_root(tmp_path: Path) -> Path:
    """Populate a pytest-temp workspace with exact copies of the frozen V1
    protocol and the four V2 bound sources (identical bytes), then return root."""
    for relative in v2.V2_BOUND_SOURCE_RELS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    v1_target = tmp_path / v2.V1_PROTOCOL_REL
    v1_target.parent.mkdir(parents=True, exist_ok=True)
    v1_target.write_bytes(V1_RAW)
    return tmp_path


def _expected_v2_protocol(root: Path) -> dict[str, Any]:
    """Rebuild the expected full V2 frozen protocol over the temp-root copies,
    mirroring the verifier's bound-source and schema-hash computation."""
    v1_raw = (root / v2.V1_PROTOCOL_REL).read_bytes()
    v1_obj = json.loads(v1_raw.decode("utf-8"))
    expected = v2.build_contract(v1_obj, include_replacement_orders=True)
    bound_sources = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest().upper()
        for relative in v2.V2_BOUND_SOURCE_RELS
    }
    expected["provenance"] = {
        "bound_sources": bound_sources,
        "v1_frozen_bytes_sha256": hashlib.sha256(v1_raw).hexdigest().upper(),
        "v2_protocol_schema_sha256": hashlib.sha256(
            canonical_json_bytes(v2.build_contract(v1_obj, include_replacement_orders=False))
        ).hexdigest().upper(),
    }
    return expected


def _write_v2_frozen(root: Path, mutator=None) -> None:
    protocol = _expected_v2_protocol(root)
    if mutator is not None:
        mutator(protocol)
    out = root / v2.FROZEN_PROTOCOL_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    publish_exclusive(out, canonical_json_bytes(protocol), root=root)


def test_verify_v2_frozen_bytes_accepts_valid_expected(tmp_path) -> None:
    root = _build_temp_v2_root(tmp_path)
    expected = _expected_v2_protocol(root)
    payload = canonical_json_bytes(expected)
    _write_v2_frozen(root)
    assert v2.verify_v2_frozen_bytes(root) == payload


def test_verify_v2_frozen_bytes_rejects_missing_source_hash(tmp_path) -> None:
    root = _build_temp_v2_root(tmp_path)

    def mutate(protocol):
        protocol["provenance"]["bound_sources"].pop(v2.V2_BOUND_SOURCE_RELS[0])

    _write_v2_frozen(root, mutate)
    with pytest.raises(ValueError, match="rebuilt expected provenance"):
        v2.verify_v2_frozen_bytes(root)


def test_verify_v2_frozen_bytes_rejects_extra_source_hash(tmp_path) -> None:
    root = _build_temp_v2_root(tmp_path)

    def mutate(protocol):
        protocol["provenance"]["bound_sources"]["src/arsc_eval/extra_bound.py"] = "0" * 64

    _write_v2_frozen(root, mutate)
    with pytest.raises(ValueError, match="rebuilt expected provenance"):
        v2.verify_v2_frozen_bytes(root)


def test_verify_v2_frozen_bytes_rejects_wrong_source_hash(tmp_path) -> None:
    root = _build_temp_v2_root(tmp_path)

    def mutate(protocol):
        protocol["provenance"]["bound_sources"][v2.V2_BOUND_SOURCE_RELS[1]] = "A" * 64

    _write_v2_frozen(root, mutate)
    with pytest.raises(ValueError, match="rebuilt expected provenance"):
        v2.verify_v2_frozen_bytes(root)


def test_verify_v2_frozen_bytes_rejects_wrong_schema_hash(tmp_path) -> None:
    root = _build_temp_v2_root(tmp_path)

    def mutate(protocol):
        protocol["provenance"]["v2_protocol_schema_sha256"] = "B" * 64

    _write_v2_frozen(root, mutate)
    with pytest.raises(ValueError, match="rebuilt expected provenance"):
        v2.verify_v2_frozen_bytes(root)
