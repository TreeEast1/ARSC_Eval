"""Result-blind tests for the Round 13 synthetic MTMM V3 protocol draft.

These tests prove that V3:

* binds the exact committed V2 frozen protocol bytes via SHA-256
  (``38AF...32E5``) and builds/validates the V3 contract from those exact
  parsed bytes (no resampling);
* freezes the deterministic 640-cell canonical matched-cell manifest with a
  *symmetric* 320/320 integer ``canonical_label`` split and an exact first
  matched-cell ID;
* keeps the V3 result-blind schema, prior ``SUPERSEDED_PRECLAIM`` status, and
  exact V3 lineage binding the V2 path / exact V2 SHA-256 / V2 schema / frozen
  Git commit ``ba00c2e`` / ``round13_attempt02``;
* freezes exactly two unchanged scientific verdict strings and the V3
  one-shot attempt / claim schema;
* freezes the deterministic shuffle golden evidence (640 cells, canonical
  label counts, dose-0.5 exclusion, and the fixed permutation draws
  ``q=0,1,9999``).

The module is intentionally result-blind; these tests contain no observed
metric value, confidence interval, gate decision, or scientific verdict.  They
never issue GO_FREEZE or GO_RUN and perform no filesystem writes.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import arsc_eval.round13_synthetic_mtmm_v3 as v3

V2_RAW = (ROOT / v3.V2_PROTOCOL_REL).resolve().read_bytes()
V2_PROTOCOL = json.loads(V2_RAW.decode("utf-8"))


def _contract():
    return v3.build_contract(V2_PROTOCOL, include_replacement_orders=True)


def _load_freezer():
    """Load the V3 freezer protocol script as a module without executing main()."""
    spec = importlib.util.spec_from_file_location(
        "_frozen_v3_freezer_module",
        ROOT / "scripts" / "freeze_round13_synthetic_mtmm_v3_protocol.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create module spec for the V3 freezer script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# (1) Exact V2 frozen bytes SHA, JSON load, build_contract, validate_contract.
# ---------------------------------------------------------------------------
def test_v2_bytes_sha_binds_contract_build_and_validate() -> None:
    assert v3.V2_PROTOCOL_SHA256 == (
        "38AF706B42B0CECCED97D3A5925CDE1360ED2C79FB3AE36680DC02E83DB432E5"
    )
    assert hashlib.sha256(V2_RAW).hexdigest().upper() == v3.V2_PROTOCOL_SHA256
    assert V2_PROTOCOL["schema_version"] == v3.V2_SCHEMA
    assert V2_PROTOCOL.get("result_blind") is True
    contract = _contract()
    assert contract["schema_version"] == v3.SCHEMA_VERSION
    # validate_contract must accept the exact built contract (raises otherwise).
    v3.validate_contract(contract, V2_PROTOCOL, require_orders=True)


# ---------------------------------------------------------------------------
# (2) Deterministic canonical matched-cell manifest for replicate 0.
# ---------------------------------------------------------------------------
def test_canonical_matched_cells_zero_is_640_with_symmetric_labels() -> None:
    cells = v3.canonical_matched_cells(0)
    assert len(cells) == v3.MATCHED_CELL_COUNT == 640
    assert all(type(c["canonical_label"]) is int for c in cells)
    ones = sum(1 for c in cells if c["canonical_label"] == 1)
    zeros = sum(1 for c in cells if c["canonical_label"] == 0)
    assert ones == 320 and zeros == 320
    assert ones + zeros == 640
    first = cells[0]
    expected_id = v3.matched_cell_id(
        0,
        v3.bootstrap_replicate_world(0, 0),
        v3.COMMON_GENERATORS[0],
        v3.MATCHED_DOSES[0],
    )
    assert first["matched_cell_id"] == expected_id == "00:09:oracle_causal:0.00"
    assert first["bootstrap_position"] == 0
    assert first["source_world"] == 9
    assert first["generator"] == "oracle_causal"
    assert first["dose"] == 0.0


# ---------------------------------------------------------------------------
# (3) V3 result-blind schema, prior status, and no outcomes.
# ---------------------------------------------------------------------------
def test_v3_contract_is_result_blind_schema_and_prior_status() -> None:
    contract = _contract()
    assert contract["result_blind"] is True
    assert contract["schema_version"] == "arsc-round13-synthetic-mtmm-protocol-v3"
    assert contract["prior_protocol_status"] == "SUPERSEDED_PRECLAIM"
    forbidden = {
        "observed",
        "estimate",
        "confidence_interval",
        "gate_pass",
        "verdict",
        "p_value",
        "effect_size",
        "result",
    }
    assert not forbidden.intersection(contract)


# ---------------------------------------------------------------------------
# (4) Immutable V3 lineage binds the exact committed V2 protocol.
# ---------------------------------------------------------------------------
def test_lineage_binds_v2_exactly() -> None:
    lineage = v3.LINEAGE["supersedes"]
    contract = _contract()
    bound = contract["lineage"]["supersedes"]
    assert bound == lineage
    assert bound["path"] == v3.V2_PROTOCOL_REL == (
        "outputs/validity/round13_synthetic_mtmm_v2_frozen_protocol.json"
    )
    assert bound["sha256"] == v3.V2_PROTOCOL_SHA256
    assert bound["schema"] == v3.V2_SCHEMA == "arsc-round13-synthetic-mtmm-protocol-v2"
    assert bound["commit"] == v3.V2_COMMIT == "ba00c2e88b22a3fd503955f8f39c4e1548a18d31"
    assert bound["prior_attempt"] == "round13_attempt02"
    assert bound["phase"] == "PRECLAIM_RESULT_BLIND"
    assert bound["formal_claim_absent"] is True
    assert bound["status"] == "SUPERSEDED_PRECLAIM"
    assert bound["no_resampling_of_worlds_or_orders"] is True


# ---------------------------------------------------------------------------
# (5) Exactly two unchanged scientific verdicts and the V3 one-shot contract.
# ---------------------------------------------------------------------------
def test_only_two_scientific_verdicts_with_v3_attempt_and_claim() -> None:
    assert v3.FINAL_VERDICTS == (
        "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS",
        "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED",
    )
    contract = _contract()
    formal = contract["formal_execution"]
    assert formal["possible_scientific_verdicts"] == list(v3.FINAL_VERDICTS)
    assert formal["scientific_verdict_count"] == 2
    one_shot = formal["one_shot"]
    assert one_shot["attempt"] == "round13_attempt03"
    assert one_shot["claim_schema"] == "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V3"
    assert one_shot["retry_allowed"] is False
    assert one_shot["claim_path"] == (
        "outputs/validity/round13_synthetic_mtmm_v3_formal_claim.json"
    )


# ---------------------------------------------------------------------------
# (6) Frozen shuffle golden evidence (deterministic, dose-0.5 excluded).
# ---------------------------------------------------------------------------
def test_shuffle_golden_evidence_is_frozen() -> None:
    contract = _contract()
    shuffle = contract["resampling"]["shuffle"]
    assert shuffle["matched_cell_count"] == 640
    assert shuffle["count_labels_ones"] == 320
    assert shuffle["count_labels_zeros"] == 320
    assert shuffle["golden_evidence"]["dose_0_5_excluded"] is True
    assert shuffle["matched_doses"] == [0.0, 0.25, 0.75, 1.0]
    assert shuffle["family_absent_from_permutation_identity"] is True
    golden = shuffle["golden_evidence"]
    assert golden["replicate"] == 0
    assert golden["matched_cell_count"] == 640
    assert golden["permutation_draws"] == [0, 1, 9999]
    assert len(golden["permutation_payload_sha256"]) == 3
    # Live recomputation must match the frozen golden evidence binding.
    live = v3.shuffle_golden_evidence()
    assert golden["canonical_skeleton_sha256"] == live["canonical_skeleton_sha256"]
    assert golden["permutation_payload_sha256"] == live["permutation_payload_sha256"]


# ---------------------------------------------------------------------------
# (7) Tampering with a fresh contract's frozen fields is rejected, and the
#     module-level constants are never polluted by caller mutation.
# ---------------------------------------------------------------------------
def test_alias_tampering_is_rejected_without_constant_pollution() -> None:
    # r_tensor shape tampering must be rejected.
    c = _contract()
    c["r_tensor"]["shape"][0] = 999
    with pytest.raises(ValueError):
        v3.validate_contract(c, V2_PROTOCOL, require_orders=True)

    # one_shot approval_marker tampering must be rejected.
    c = _contract()
    c["formal_execution"]["one_shot"]["approval_marker"] = "TAMPER"
    with pytest.raises(ValueError):
        v3.validate_contract(c, V2_PROTOCOL, require_orders=True)

    # hash_closure closure_rule tampering must be rejected.
    c = _contract()
    c["formal_execution"]["hash_closure"]["closure_rule"] = "TAMPER"
    with pytest.raises(ValueError):
        v3.validate_contract(c, V2_PROTOCOL, require_orders=True)

    # The module-level constants must remain pristine after all tampering.
    assert v3.R_TENSOR_SHAPE == [1024, 4, 10]
    assert v3.V3_ONE_SHOT["approval_marker"] == (
        "independent GO_RUN_V3 approval required"
    )
    assert v3.V3_HASH_CLOSURE["closure_rule"] != "TAMPER"


# ---------------------------------------------------------------------------
# (8) The freezer must rely on the verified V3 spec module exclusively (no
#     direct ``arsc_eval`` import chain) and must publish exclusively with no
#     residual temporary candidate file.
# ---------------------------------------------------------------------------
def test_freezer_static_import_order_and_exclusive_publish(tmp_path) -> None:
    freezer_path = ROOT / "scripts" / "freeze_round13_synthetic_mtmm_v3_protocol.py"
    source = freezer_path.read_bytes()
    tree = ast.parse(source.decode("utf-8"), filename=str(freezer_path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("arsc_eval"), (
                    "freezer must not import the arsc_eval package directly, got "
                    f"{alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("arsc_eval"):
                assert False, (
                    "freezer must not import from the arsc_eval package directly, "
                    f"got {node.module!r}"
                )

    freezer = _load_freezer()

    outputs = tmp_path / "outputs"
    validity = outputs / "validity"
    outputs.mkdir()
    validity.mkdir()

    final = validity / "round13_synthetic_mtmm_v3_freezer_probe.json"
    payload = b"{}\n"
    freezer.publish_exclusive(final, payload, root=tmp_path)

    assert final.read_bytes() == payload
    with pytest.raises(FileExistsError):
        freezer.publish_exclusive(final, payload, root=tmp_path)

    candidate = validity / ".round13_synthetic_mtmm_v3_freezer_probe.json.candidate.tmp"
    assert not candidate.exists()


# ---------------------------------------------------------------------------
# (9) publish_exclusive failure must clean up the dot-candidate (and, once
#     created, the final artifact) so no residual outputs survive a raise.
# ---------------------------------------------------------------------------
def test_freezer_publish_failure_cleans_candidate_and_created_final(
    tmp_path, monkeypatch
) -> None:
    freezer = _load_freezer()
    payload = b"{}\n"

    # --- Case A: refuse_if_formal_artifacts raises at the pre-link re-check.
    # The dot-candidate is written first, so a raise must clean it up and leave
    # the final untouched (never created).
    root_a = tmp_path / "a"
    validity_a = root_a / "outputs" / "validity"
    validity_a.mkdir(parents=True)
    final_a = validity_a / "round13_synthetic_mtmm_v3_prelink_probe.json"

    def raise_at_refuse(*_args, **_kwargs):
        raise RuntimeError("prelink")

    monkeypatch.setattr(freezer, "refuse_if_formal_artifacts", raise_at_refuse)
    with pytest.raises(RuntimeError, match="prelink"):
        freezer.publish_exclusive(final_a, payload, root=root_a)
    assert not final_a.exists()
    assert not final_a.with_name(f".{final_a.name}.candidate.tmp").exists()

    # Restore the Case A monkeypatch before the Case B stable_read patch.
    monkeypatch.undo()

    # --- Case B: stable_read raises after the final has been hard-linked, so
    # publish_exclusive must remove both the created final and the dot-candidate.
    root_b = tmp_path / "b"
    validity_b = root_b / "outputs" / "validity"
    validity_b.mkdir(parents=True)
    final_b = validity_b / "round13_synthetic_mtmm_v3_postlink_probe.json"

    real_stable_read = freezer.stable_read

    def raise_at_final(path, root, *_args, **_kwargs):
        if os.path.abspath(path) == os.path.abspath(final_b):
            raise RuntimeError("postlink")
        return real_stable_read(path, root)

    monkeypatch.setattr(freezer, "stable_read", raise_at_final)
    with pytest.raises(RuntimeError, match="postlink"):
        freezer.publish_exclusive(final_b, payload, root=root_b)
    assert not final_b.exists()
    assert not final_b.with_name(f".{final_b.name}.candidate.tmp").exists()


# ---------------------------------------------------------------------------
# (10) load_verified_v3_module must restore all prior sys.modules entries for
#      the four exact names it rebinds, both after a successful exact-byte load
#      and after a failure (tampered V2 provenance bound-source SHA-256), so no
#      caller state is polluted.
# ---------------------------------------------------------------------------
def test_freezer_exact_byte_loader_restores_modules(monkeypatch) -> None:
    freezer = _load_freezer()
    names = (
        'arsc_eval',
        'arsc_eval.round13_synthetic_mtmm',
        'arsc_eval.round13_synthetic_mtmm_v2',
        'arsc_eval.round13_synthetic_mtmm_v3',
    )
    before = {n: sys.modules.get(n) for n in names}
    loaded = freezer.load_verified_v3_module(ROOT)
    assert loaded.SCHEMA_VERSION == v3.SCHEMA_VERSION
    assert all(sys.modules.get(n) is before[n] for n in names)

    real = freezer.verify_expected_shas

    def bad(root):
        v2_raw, v3_raw = real(root)
        parsed = json.loads(v2_raw)
        parsed['provenance']['bound_sources'][
            'src/arsc_eval/round13_synthetic_mtmm.py'
        ] = '0' * 64
        return freezer.canonical_json_bytes(parsed), v3_raw

    monkeypatch.setattr(freezer, 'verify_expected_shas', bad)
    with pytest.raises(ValueError):
        freezer.load_verified_v3_module(ROOT)
    assert all(sys.modules.get(n) is before[n] for n in names)


# ---------------------------------------------------------------------------
# (11) An external hardlink to the dot-candidate (created outside the freezer
#      during the pre-link re-check) must be rejected via the nlink identity
#      closure, and never leave the final or dot-candidate behind.
# ---------------------------------------------------------------------------
def test_freezer_rejects_extra_candidate_hardlink(tmp_path, monkeypatch) -> None:
    freezer = _load_freezer()
    outputs = tmp_path / "outputs"
    validity = outputs / "validity"
    validity.mkdir(parents=True)

    final = validity / "round13_synthetic_mtmm_v3_alias_probe.json"
    candidate = final.with_name(f".{final.name}.candidate.tmp")
    alias = tmp_path / "external_alias"
    payload = b"{}\\n"

    real_refuse = freezer.refuse_if_formal_artifacts
    injected = {"done": False}

    def inject(root):
        if not injected["done"]:
            os.link(candidate, alias)
            injected["done"] = True
        return real_refuse(root)

    monkeypatch.setattr(freezer, "refuse_if_formal_artifacts", inject)

    with pytest.raises((ValueError, RuntimeError)):
        freezer.publish_exclusive(final, payload, root=tmp_path)

    assert not final.exists()
    assert not candidate.exists()
    assert alias.exists()
    assert alias.read_bytes() == payload
    alias.unlink()


# ---------------------------------------------------------------------------
# (12) main() must remove the created final and the dot-candidate when the
#      post-write rebuild verification raises, so no residual output survives.
#      This is a temp-dir-only check of the main post-write cleanup path.
# ---------------------------------------------------------------------------
def test_freezer_main_removes_created_final_on_postwrite_rebuild_failure(
    tmp_path, monkeypatch
) -> None:
    freezer = _load_freezer()

    validity = tmp_path / "outputs" / "validity"
    validity.mkdir(parents=True)
    output = validity / Path(freezer.FROZEN_PROTOCOL_OUTPUT).name
    candidate = output.with_name(f".{output.name}.candidate.tmp")

    monkeypatch.setattr(freezer, "ROOT", tmp_path)
    monkeypatch.setattr(freezer, "DEFAULT_OUTPUT", output)
    monkeypatch.setattr(
        freezer,
        "build_frozen_protocol",
        lambda root: {"schema_version": "probe"},
    )
    # leave the real publish_exclusive in place

    def raise_postwrite(*_args, **_kwargs):
        raise RuntimeError("postwrite rebuild failure")

    monkeypatch.setattr(freezer, "verify_frozen_protocol", raise_postwrite)
    monkeypatch.setattr(sys, "argv", ["freeze_v3"])

    with pytest.raises(RuntimeError, match="postwrite"):
        freezer.main()

    assert not output.exists()
    assert not candidate.exists()


# ---------------------------------------------------------------------------
# (13) If the candidate leaf is replaced (different inode/bytes) at the link
#      step, publish_exclusive must fail closed (linked identity mismatch) and
#      its failure cleanup must leave neither the final nor the candidate.
#      os.link is monkeypatched with a platform-neutral fake that creates the
#      destination as a distinct regular file (different bytes/inode) instead
#      of a hardlink to the source, leaving the still-open candidate (src)
#      completely unchanged -- no unlink or mutation of the open candidate,
#      so the simulation works on Windows too.
# ---------------------------------------------------------------------------
def test_freezer_post_link_identity_mismatch_leaves_no_residual(
    tmp_path, monkeypatch
) -> None:
    freezer = _load_freezer()
    outputs = tmp_path / "outputs"
    validity = outputs / "validity"
    validity.mkdir(parents=True)

    final = validity / "round13_synthetic_mtmm_v3_replaced_candidate_probe.json"
    candidate = final.with_name(f".{final.name}.candidate.tmp")
    payload = b"original-payload\n"

    def link_with_distinct_leaf(src, dst, *_args, **_kwargs):
        # Simulate a post-link identity mismatch: create dst as a distinct
        # regular file (new inode, different bytes) and return success while
        # leaving the open candidate (src) untouched.  The created dst then
        # differs from the opened_candidate identity that publish_exclusive
        # anchored before the link, triggering its fail-closed identity check.
        with open(dst, "wb") as fh:
            fh.write(b"replaced-candidate-bytes\n")

    monkeypatch.setattr(freezer.os, "link", link_with_distinct_leaf)

    with pytest.raises(RuntimeError, match="linked identity mismatch"):
        freezer.publish_exclusive(final, payload, root=tmp_path)

    # The failure cleanup must leave neither the created final nor the
    # candidate behind.
    assert not final.exists()
    assert not candidate.exists()


# ---------------------------------------------------------------------------
# (14) main() postverify cleanup runs the final and candidate cleanup attempts
#      independently: a first cleanup OSError (on the final) must not prevent
#      the second cleanup attempt (the candidate), and both failures are
#      aggregated/reported after both attempts.
# ---------------------------------------------------------------------------
def test_freezer_main_first_cleanup_oserror_does_not_prevent_second(
    tmp_path, monkeypatch
) -> None:
    freezer = _load_freezer()

    validity = tmp_path / "outputs" / "validity"
    validity.mkdir(parents=True)
    output = validity / Path(freezer.FROZEN_PROTOCOL_OUTPUT).name
    candidate = output.with_name(f".{output.name}.candidate.tmp")

    monkeypatch.setattr(freezer, "ROOT", tmp_path)
    monkeypatch.setattr(freezer, "DEFAULT_OUTPUT", output)
    monkeypatch.setattr(
        freezer,
        "build_frozen_protocol",
        lambda root: {"schema_version": "probe"},
    )

    def raise_postwrite(*_args, **_kwargs):
        # Re-create a lingering candidate so the second cleanup attempt has a
        # real file to remove (proving it genuinely runs after the first fails).
        candidate.write_bytes(b"lingering-candidate\n")
        raise RuntimeError("postwrite rebuild failure")

    monkeypatch.setattr(freezer, "verify_frozen_protocol", raise_postwrite)
    monkeypatch.setattr(sys, "argv", ["freeze_v3"])

    attempts = []
    real_safe_unlink = freezer.safe_unlink_exact

    def fail_on_final(path, root, *_args, **_kwargs):
        attempts.append(os.path.abspath(path))
        if os.path.abspath(path) == os.path.abspath(output):
            raise OSError("simulated unlink OSError on final")
        return real_safe_unlink(path, root)

    monkeypatch.setattr(freezer, "safe_unlink_exact", fail_on_final)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        freezer.main()

    # Both cleanup attempts were made independently even though the final
    # cleanup raised OSError, and the aggregated failure names the OSError.
    assert [
        os.path.abspath(p) for p in attempts
    ] == [os.path.abspath(output), os.path.abspath(candidate)]
    # The second attempt (candidate) actually removed the lingering candidate.
    assert not candidate.exists()
    # The first attempt's final survived its deliberate OSError.
    assert output.exists()
    output.unlink()


# ---------------------------------------------------------------------------
# (15) Gate evaluator boundaries and infrastructure fail-closed semantics.
#      A passing values container is rebuilt purely from the frozen gate specs,
#      then each boundary and failure mode is asserted against the exact
#      evaluator verdicts.
# ---------------------------------------------------------------------------
def _gate_value(gate_id):
    """Resolve the gate spec and return a value that makes the gate pass."""
    if gate_id in v3.GLOBAL_GATE_SPECS:
        spec = v3.GLOBAL_GATE_SPECS[gate_id]
    else:
        family, metric, gate_op = gate_id.split(".")
        spec = v3.FAMILY_GATE_SPECS[family][metric][gate_op]

    kind = spec.get("kind")
    if kind == "boolean":
        return spec["expected"]
    if kind == "interval":
        return (spec["lower"] + spec["upper"]) / 2.0

    operator = spec["operator"]
    threshold = spec["threshold"]
    if operator in (">=", "<=", "=="):
        # Exact threshold satisfies inclusive / equality operators.
        return threshold
    if operator == ">":
        return threshold + 0.01
    if operator == "<":
        return threshold - 0.01
    raise AssertionError(f"unhandled operator {operator!r}")


def test_gate_evaluator_boundaries_and_infrastructure_fail_closed() -> None:
    # Build a fully passing values dict from the exact frozen specs.
    values = {gate_id: _gate_value(gate_id) for gate_id in v3.REQUIRED_GATE_IDS}
    assert set(values) == set(v3.REQUIRED_GATE_IDS)
    assert v3.evaluate_gate_values(values) == v3.PASS_VERDICT

    # Ordinary family numeric gate below its threshold => NOT_VALIDATED (an
    # ordinary numeric failure, never a third scientific verdict).
    nv = copy.deepcopy(values)
    nv["A.kendall_tau_b.point"] = 0.69  # below >= 0.70 threshold
    assert v3.evaluate_gate_values(nv) == v3.NOT_VALIDATED_VERDICT

    # Engineering gate below its bound => INFRASTRUCTURE_STATUS.
    infra = copy.deepcopy(values)
    infra["oracle_destroyed_standardized_difference"] = 0.49  # below >= 0.50
    assert v3.evaluate_gate_values(infra) == v3.INFRASTRUCTURE_STATUS

    # Infrastructure fail-closed cases: missing a required key, an extra key, a
    # boolean supplied where a number is required, and a non-finite value.
    missing = copy.deepcopy(values)
    pop_key = next(iter(missing))
    del missing[pop_key]
    assert v3.evaluate_gate_values(missing) == v3.INFRASTRUCTURE_STATUS

    extra = copy.deepcopy(values)
    extra["extra.gate"] = 1.0
    assert v3.evaluate_gate_values(extra) == v3.INFRASTRUCTURE_STATUS

    bool_as_number = copy.deepcopy(values)
    bool_as_number["A.kendall_tau_b.point"] = True
    assert v3.evaluate_gate_values(bool_as_number) == v3.INFRASTRUCTURE_STATUS

    nonfinite = copy.deepcopy(values)
    nonfinite["A.kendall_tau_b.point"] = float("nan")
    assert v3.evaluate_gate_values(nonfinite) == v3.INFRASTRUCTURE_STATUS

    # The closed nuisance_shuffle_auroc interval boundaries remain passing when
    # substituted individually.
    low = copy.deepcopy(values)
    low["nuisance_shuffle_auroc"] = 0.45
    assert v3.evaluate_gate_values(low) == v3.PASS_VERDICT

    high = copy.deepcopy(values)
    high["nuisance_shuffle_auroc"] = 0.55
    assert v3.evaluate_gate_values(high) == v3.PASS_VERDICT

