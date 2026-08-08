from __future__ import annotations

import hashlib
import json

import pytest

from arsc_eval.round13_synthetic_mtmm import (
    ATTRIBUTION_AGGREGATION,
    BASELINES,
    BOUNDARY_CONTROLS,
    DOSES,
    FINAL_VERDICTS,
    FORMAL_ARTIFACT_ALLOWLIST,
    FORMAL_HASH_CLOSURE,
    FORMAL_INDEX_NAME,
    FORMULAS,
    GATES,
    GENERATORS,
    MANIPULATIONS,
    METRICS,
    ONE_SHOT,
    ESTIMANDS,
    RANKING_REPORTS,
    ROW_CONFIDENCE_CONTRACT,
    ROWS_PER_WORLD,
    build_contract,
    build_worlds,
)
from scripts.freeze_round13_synthetic_mtmm_protocol import canonical_json_bytes, publish_exclusive


def test_worlds_are_exhaustive_partitioned_unique_and_deterministic() -> None:
    worlds = build_worlds()
    assert worlds == build_worlds()
    assert len(worlds) == 32
    assert {world["row_count"] for world in worlds} == {1024}
    assert len({world["seed_sha256"] for world in worlds}) == 32
    mappings = set()
    for world in worlds:
        roles = world["feature_roles"]
        assert [len(roles[name]) for name in ("causal", "proxy", "nuisance")] == [4, 3, 3]
        flat = roles["causal"] + roles["proxy"] + roles["nuisance"]
        assert sorted(flat) == list(range(10))
        mappings.add(tuple(flat))
    assert len(mappings) == 32


def test_frozen_design_vocabulary_and_metric_definitions() -> None:
    assert tuple(GENERATORS) == (
        "oracle_causal", "sparse_causal", "diffuse_causal_plus_decoy",
        "proxy_shortcut", "random_matched_sparsity", "anti_causal_adversarial",
    )
    assert tuple(MANIPULATIONS) == (
        "action_correctness_degradation", "rationale_correctness_degradation",
        "selective_ranking_degradation", "nuisance_consistency_degradation",
    )
    assert DOSES == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert METRICS["A"]["definition"].startswith("macro-F1")
    assert METRICS["R"]["definition"].startswith("macro-F1")
    assert "negative tie-aware" in METRICS["S"]["definition"]
    assert set(METRICS) == {"A", "R", "S", "C1_action", "C1_rationale"}
    assert BASELINES == {
        "support_f1": "higher", "deletion_auc": "lower", "insertion_auc": "higher",
        "infidelity": "lower", "max_sensitivity": "lower",
    }


def test_exact_gates_controls_verdicts_and_one_shot_semantics() -> None:
    assert GATES["bootstrap"]["unit"] == "world"
    assert GATES["bootstrap"]["draws"] == 10_000
    assert GATES["bootstrap"]["shared_draws"] is True
    assert GATES["bootstrap"]["bonferroni_q"] == 0.0125
    assert "intersection" in GATES["bootstrap"]["ci1_components"]
    assert "max_statistic" in GATES["bootstrap"]["ci1_components"]
    assert GATES["kendall_tau_b"] == {"point_min": 0.70, "corrected_lower_strict_min": 0.50}
    assert GATES["high_low_auroc"] == {"point_min": 0.80, "corrected_lower_strict_min": 0.70}
    assert GATES["mtmm_gap"] == {"point_min": 0.30, "corrected_lower_strict_min": 0.20}
    assert GATES["leave_one_world_out_incremental_delta_r2"]["point_min"] == 0.15
    assert GATES["leave_one_world_out_incremental_delta_r2"]["corrected_lower_strict_min"] == 0.10
    assert GATES["oracle_destroyed_standardized_difference"]["point_min"] == 0.50
    assert "recompute the action and rationale truth" in BOUNDARY_CONTROLS["causal_recomputation"]["definition"]
    assert FINAL_VERDICTS == (
        "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS",
        "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED",
    )
    assert ONE_SHOT["formal_claim_is_permanent"] is True
    assert ONE_SHOT["infrastructure_failure_consumes_claim"] is True
    assert ONE_SHOT["retry_allowed"] is False
    assert ONE_SHOT["delete_or_recover_claim_allowed"] is False
    assert ONE_SHOT["attempt"] == "round13_attempt01"
    assert ONE_SHOT["claim_path"].endswith("round13_synthetic_mtmm_formal_claim.json")
    assert ONE_SHOT["preclaim_refusal"]["claim_consumed"] is False
    assert ONE_SHOT["postclaim_failure"]["claim_consumed"] is True
    assert ONE_SHOT["infrastructure_status"] == {
        "value": "IMPLEMENTATION_FAILURE",
        "is_a_scientific_verdict": False,
    }


def test_replacement_orders_have_complete_coverage_and_stable_digests() -> None:
    contract = build_contract(include_replacement_orders=True)
    orders = contract["design"]["replacement_orders"]
    assert len(orders) == 32 * 6 * 4 * 4
    first = orders[0]
    assert sorted(first["permutation"]) == list(range(ROWS_PER_WORLD))
    payload = b"".join(value.to_bytes(4, "big") for value in first["permutation"])
    assert hashlib.sha256(payload).hexdigest().upper() == first["permutation_sha256"]
    assert orders == build_contract(include_replacement_orders=True)["design"]["replacement_orders"]


def test_contract_is_result_blind_and_canonical_encoding_is_compact() -> None:
    contract = build_contract(include_replacement_orders=False)
    encoded = canonical_json_bytes(contract)
    assert encoded.endswith(b"\n") and b"\n" not in encoded[:-1]
    assert encoded == canonical_json_bytes(json.loads(encoded))
    forbidden = {"observed", "estimate", "confidence_interval", "gate_pass", "verdict"}
    assert not forbidden.intersection(contract)
    assert contract["evaluation"]["formulas"] == FORMULAS
    assert contract["evaluation"]["estimands"] == ESTIMANDS
    assert contract["evaluation"]["ranking_reports"] == RANKING_REPORTS
    assert contract["design"]["row_confidence_contract"] == ROW_CONFIDENCE_CONTRACT
    assert contract["design"]["attribution_aggregation"] == ATTRIBUTION_AGGREGATION
    assert contract["formal_execution"]["artifact_allowlist"] == list(FORMAL_ARTIFACT_ALLOWLIST)


def test_estimands_endpoints_and_hash_closure_are_noncontradictory() -> None:
    assert "mean_a(F1_a)" in FORMULAS["A_formula"]["formula"]
    assert "define F1_a=1" in FORMULAS["A_formula"]["tie_handling"]
    assert "metric_f,quality_f" in ESTIMANDS["mtmm"]["definition"]
    assert "self correlation" not in ESTIMANDS["mtmm"]["definition"]
    assert ESTIMANDS["leave_one_world_out"]["target"].startswith("latent scalar quality=1-dose")
    assert "four adjacent transitions" in RANKING_REPORTS["reversal_rate"]
    assert "ground-truth-best generator" in RANKING_REPORTS["top1_regret"]
    assert "fixed-error ranking fixture" in ROW_CONFIDENCE_CONTRACT["fixture"]
    assert set(ROW_CONFIDENCE_CONTRACT["generator_quality"]) == set(GENERATORS)
    assert MANIPULATIONS["action_correctness_degradation"]["admissible_generators"] == [
        name for name in GENERATORS if name != "anti_causal_adversarial"
    ]
    assert "clean_output only" in MANIPULATIONS["nuisance_consistency_degradation"]["channel_separation"]
    assert FORMAL_HASH_CLOSURE["index_self_excluded"] is True
    assert FORMAL_INDEX_NAME not in FORMAL_HASH_CLOSURE["index_records"]
    assert "round13_synthetic_mtmm_formal_claim.json" not in FORMAL_HASH_CLOSURE["index_records"]
    assert FORMAL_HASH_CLOSURE["claim_is_not_rewritten"] is True
    assert ESTIMANDS["auroc"]["dose_groups"].endswith("dose 0.5 is excluded")
    assert ESTIMANDS["mtmm"]["constant_series"].endswith("input series is constant")
    assert ESTIMANDS["shuffle_unit"]["permutations"] == 10_000
    assert "radius is exactly 1" in FORMULAS["max_sensitivity"]["max_sensitivity_neighborhood"]
    assert "four-action macro-F1" in FORMULAS["deletion_auc"]["formula"]
    assert "f_scalar is the arithmetic mean" in FORMULAS["infidelity"]["formula"]
    assert "tie group" in ROW_CONFIDENCE_CONTRACT["tie_aware_aurc"]
    assert "no jitter" in ROW_CONFIDENCE_CONTRACT["clean_scalar"]
    assert "first 8 SHA-256 digest bytes" in ROW_CONFIDENCE_CONTRACT["sha_uint64_rule"]
    assert ATTRIBUTION_AGGREGATION["formula"].startswith("g_aggregate[j]=(1/4)*sum")
    assert "no random mask order" in FORMULAS["deletion_auc"]["reference"]


def test_exclusive_publication_refuses_overwrite(tmp_path) -> None:
    target = tmp_path / "protocol.json"
    publish_exclusive(target, b"first\n")
    with pytest.raises(FileExistsError):
        publish_exclusive(target, b"second\n")
    assert target.read_bytes() == b"first\n"
