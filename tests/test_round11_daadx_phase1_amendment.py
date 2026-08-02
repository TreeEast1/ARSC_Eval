from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/freeze_round11_daadx_phase1_amendment.py"
SPEC = importlib.util.spec_from_file_location("round11_phase1_amendment", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _protocol() -> tuple[bytes, str]:
    value = {
        "schema_version": MODULE.PROTOCOL_SCHEMA,
        "result_blind": True,
        "attempt": "attempt01",
        "training_authorized": False,
        "authorization": "DAADX_DOWNLOAD_AND_GROUP_INTEGRITY_PREFLIGHT_ONLY",
        "formal_output": {
            "staging": "outputs/validity/formal.staging",
            "final": "outputs/validity/formal",
            "log": "outputs/validity/formal.log",
            "artifact_index": "outputs/validity/formal.index.json",
        },
    }
    payload = json.dumps(value, separators=(",", ":")).encode()
    return payload, hashlib.sha256(payload).hexdigest().upper()


def _build():
    payload, digest = _protocol()
    return MODULE.build_amendment(payload, expected_protocol_sha256=digest)


def test_repository_protocol_exact_hash_and_generated_amendment() -> None:
    protocol = ROOT / MODULE.PROTOCOL_PATH
    assert MODULE.sha256_bytes(protocol.read_bytes()) == MODULE.EXPECTED_PROTOCOL_SHA256
    expected = MODULE.build_amendment(protocol.read_bytes())
    output = ROOT / MODULE.AMENDMENT_PATH
    if output.exists():
        assert json.loads(output.read_text(encoding="utf-8")) == expected


def test_exact_top_level_contract_and_determinism() -> None:
    amendment = _build()
    assert set(amendment) == {
        "schema_version", "generated_at_utc", "additive_only", "result_blind",
        "phase", "attempt", "training_authorized", "original_protocol", "scope",
        "execution_control", "output_topology", "artifact_contract", "outcomes",
        "independent_closure_review", "prohibited_effects",
    }
    assert amendment["schema_version"] == MODULE.SCHEMA
    assert amendment["additive_only"] is True
    assert amendment["result_blind"] is True
    assert amendment["training_authorized"] is False
    assert MODULE.canonical_json_bytes(amendment) == MODULE.canonical_json_bytes(_build())


def test_scope_outcomes_and_artifact_allowlist_are_exact() -> None:
    amendment = _build()
    assert amendment["scope"]["gates_executed"] == ["G0", "G1", "G2", "G3"]
    assert set(amendment["scope"]["deferred_gate_status"]) == {"G4", "G5", "G6", "G7"}
    assert set(amendment["scope"]["deferred_gate_status"].values()) == {
        "DEFERRED_NOT_RUN_PHASE1"
    }
    assert amendment["scope"]["g8_status_field_allowed"] is False
    assert set(amendment["outcomes"]) == set(MODULE.LEGAL_OUTCOMES)
    assert all(not item["is_formal_g0_g8_verdict"] for item in amendment["outcomes"].values())
    assert all(item["publish_hash_closed_phase1_evidence"] for item in amendment["outcomes"].values())
    contract = amendment["artifact_contract"]
    assert contract["exact_files"] == list(MODULE.ARTIFACTS)
    assert len(contract["exact_files"]) == len(set(contract["exact_files"])) == 16
    assert contract["artifact_index"] == MODULE.ARTIFACTS[-1]
    assert contract["console_only_pass_allowed"] is False


def test_claim_and_phase_paths_do_not_overlap_original_formal_paths() -> None:
    amendment = _build()
    topology = amendment["output_topology"]
    phase = {
        amendment["execution_control"]["claim_path"],
        topology["staging"], topology["final"], MODULE.AMENDMENT_PATH,
    }
    assert len(phase) == 4
    assert not phase.intersection(topology["original_formal_paths"].values())
    assert amendment["execution_control"]["persist_after_every_exit_or_exception"] is True
    assert amendment["execution_control"]["automatic_deletion_or_reuse_allowed"] is False


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda p: p.__setitem__("schema_version", "WRONG"), "schema"),
        (lambda p: p.__setitem__("result_blind", False), "result-blind"),
        (lambda p: p.__setitem__("attempt", "attempt02"), "attempt"),
        (lambda p: p.__setitem__("training_authorized", True), "training"),
        (lambda p: p.__setitem__("authorization", "TRAIN"), "authorization"),
    ],
)
def test_protocol_semantic_changes_fail_closed(mutation, message: str) -> None:
    payload, _digest = _protocol()
    value = json.loads(payload)
    mutation(value)
    changed = json.dumps(value, separators=(",", ":")).encode()
    with pytest.raises(ValueError, match=message):
        MODULE.build_amendment(
            changed, expected_protocol_sha256=MODULE.sha256_bytes(changed)
        )


def test_protocol_hash_change_fails_closed() -> None:
    payload, digest = _protocol()
    with pytest.raises(ValueError, match="SHA256"):
        MODULE.build_amendment(payload + b" ", expected_protocol_sha256=digest)


def test_atomic_publish_no_overwrite_and_competitor_preserved(tmp_path: Path) -> None:
    amendment = _build()
    output = tmp_path / "amendment.json"
    MODULE.publish_no_overwrite(amendment, output)
    first = output.read_bytes()
    assert first == MODULE.canonical_json_bytes(amendment)
    assert not output.with_name(output.name + ".tmp").exists()
    with pytest.raises(ValueError, match="already exists"):
        MODULE.publish_no_overwrite(amendment, output)
    assert output.read_bytes() == first

    competitor = tmp_path / "competitor.json"
    def competitor_link(source: Path, target: Path) -> None:
        target.write_bytes(b"competitor")
        raise FileExistsError("competitor won")

    with pytest.raises(FileExistsError, match="competitor won"):
        MODULE.publish_no_overwrite(amendment, competitor, link_func=competitor_link)
    assert competitor.read_bytes() == b"competitor"
    assert not competitor.with_name(competitor.name + ".tmp").exists()


def test_preexisting_temp_is_preserved(tmp_path: Path) -> None:
    output = tmp_path / "amendment.json"
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(b"other owner")
    with pytest.raises(ValueError, match="temp already exists"):
        MODULE.publish_no_overwrite(_build(), output)
    assert temporary.read_bytes() == b"other owner"


def test_symlink_output_rejected_when_supported(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"target")
    output = tmp_path / "link"
    try:
        output.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="already exists"):
        MODULE.publish_no_overwrite(_build(), output)
