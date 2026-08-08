"""Result-blind specification for the Round 13 synthetic MTMM study.

This module freezes design inputs only.  It deliberately contains no observed
metric values, confidence intervals, gate decisions, or scientific verdict.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

SCHEMA_VERSION = "arsc-round13-synthetic-mtmm-protocol-v1"
NAMESPACE = "ARSC_ROUND13_SYNTHETIC_MTMM_V1"
WORLD_COUNT = 32
FEATURE_COUNT = 10
ROWS_PER_WORLD = 1 << FEATURE_COUNT
DOSES = (0.0, 0.25, 0.5, 0.75, 1.0)
NONZERO_DOSES = DOSES[1:]

# Four q = 0.0125 evaluation families (0.05 / 4).  C1 is a single family formed
# by the intersection of its two components through a max-statistic /
# shared-bootstrap correction, so the family count stays four.
FAMILIES = ("A", "R", "S", "C1")
FAMILY_Q = 0.0125
FAMILY_Q_DERIVATION = "0.05 / 4 families (A, R, S, C1)"
BOOTSTRAP_SEED = 20260813
BOOTSTRAP_DRAWS = 10_000

# Canonical row enumeration: every world enumerates the same 1024 binary rows
# as ascending integers 0..1023 where feature index k is bit k (feature 0 is
# the least-significant bit, feature 9 the most-significant bit).  Row truth
# and every per-row output are indexed by this canonical integer.
ROW_ENUMERATION = {
    "order": "ascending binary integers 0..1023 (exactly 1024 rows)",
    "feature_0": "least-significant bit",
    "feature_9": "most-significant bit",
    "bit_of_feature_k": "bit k of the row integer is feature k",
    "row_ids": list(range(ROWS_PER_WORLD)),
}

# Infrastructure status used only for the one-shot formal execution bookkeeping.
# It is never a third scientific verdict.
INFRASTRUCTURE_STATUS = "IMPLEMENTATION_FAILURE"
PREFORMAL_REFUSAL = "PREFORMAL_REFUSAL"
POSTCLAIM_INFRASTRUCTURE_FAILURE = "POSTCLAIM_INFRASTRUCTURE_FAILURE"

GENERATORS: dict[str, dict[str, Any]] = {
    "oracle_causal": {
        "action_generation": "predict each action exactly from the world ground-truth causal rule row-truth vector.",
        "rationale_generation": "per action predict exactly the instantiated support set frozen in world.action_rationale_supports.",
        "confidence_generation": "feature score is 1-r/10 for support rank r=0..9 and 0 for non-support; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "resolve confidence ties by ascending feature index, then ascending canonical row integer.",
        "empty_rationale_behavior": "not reachable: every action rule has a nonempty causal support.",
        "proxy_decoy_mapping": "none used; only causal features are ever ranked.",
        "sparsity_rounding": "exact supports; nothing is rounded.",
        "hash_seeds": {
            "confidence": f"{NAMESPACE}:generator_seed:oracle_causal:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:oracle_causal:tiebreak:{{world_index}}",
        },
    },
    "sparse_causal": {
        "action_generation": "predict each action as for oracle_causal (exact ground-truth action).",
        "rationale_generation": "keep the highest hash-tie-broken ceil(|support|/2) active causal rationale features, at least one when the support is nonempty.",
        "confidence_generation": "feature score is 1-r/10 for retained rank r and 0 otherwise; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "retain the top ceil(|support|/2) features by the frozen rationale hash order; ties in rank resolved by feature index.",
        "empty_rationale_behavior": "if an action support were empty, retain no feature; in practice every support is nonempty.",
        "proxy_decoy_mapping": "dropped causal features are never replaced by proxy/decoys; the retained set is a strict subset of causal.",
        "sparsity_rounding": "ceil(x/2) rounding of the retained cardinality.",
        "hash_seeds": {
            "rationale": f"{NAMESPACE}:generator_seed:sparse_causal:rationale:{{world_index}}",
            "confidence": f"{NAMESPACE}:generator_seed:sparse_causal:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:sparse_causal:tiebreak:{{world_index}}",
        },
    },
    "diffuse_causal_plus_decoy": {
        "action_generation": "predict each action as for oracle_causal (exact ground-truth action).",
        "rationale_generation": "keep all causal rationale features, then append equal-mass proxy features, then nuisance decoy features as lower-ranked distractors.",
        "confidence_generation": "feature scores are 1.0-r/100 for causal ranks, 0.6-r/100 for proxy ranks, and 0.2-r/100 for nuisance ranks; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "resolve ties by ascending feature index within the same mass band.",
        "empty_rationale_behavior": "causal support never empty; decoy features still appended.",
        "proxy_decoy_mapping": "decoys are exactly world.decoy_features = proxy plus nuisance feature indices; proxy partners from world.proxy_partners.",
        "sparsity_rounding": "no sparsity rounding; cardinality equals the full feature extent (causal+proxy+nuisance).",
        "hash_seeds": {
            "decoy_order": f"{NAMESPACE}:generator_seed:diffuse:decoy_order:{{world_index}}",
            "confidence": f"{NAMESPACE}:generator_seed:diffuse:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:diffuse:tiebreak:{{world_index}}",
        },
    },
    "proxy_shortcut": {
        "action_generation": "predict each action as for oracle_causal (exact ground-truth action).",
        "rationale_generation": "map each causal rationale position to its frozen proxy partner (world.proxy_partners) and rank only the proxy features.",
        "confidence_generation": "mapped proxy rank r receives 1-r/10 and every non-proxy receives 0; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "resolve ties by ascending proxy feature index.",
        "empty_rationale_behavior": "if a causal support were empty, no proxy is ranked; in practice nonempty.",
        "proxy_decoy_mapping": "proxy_partners: causal feature c -> world.proxy_partners[c]; decoys/nuisance are never ranked.",
        "sparsity_rounding": "cardinality equals the number of distinct proxy partners (mapped support size).",
        "hash_seeds": {
            "proxy_partner": f"{NAMESPACE}:generator_seed:proxy_shortcut:proxy_partner:{{world_index}}",
            "confidence": f"{NAMESPACE}:generator_seed:proxy_shortcut:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:proxy_shortcut:tiebreak:{{world_index}}",
        },
    },
    "random_matched_sparsity": {
        "action_generation": "for action a on row i, predict truth XOR (SHA256(generator action seed:world:i:a) least-significant bit); this output is independent of later manipulations.",
        "rationale_generation": "select a frozen hash-ranked subset of all features with cardinality matched to the oracle rationale and rank only those features.",
        "confidence_generation": "selected rank r receives 1-r/10 and unselected features receive 0; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "resolve ties by the frozen hash rank, then ascending feature index.",
        "empty_rationale_behavior": "if the matched cardinality is zero, rank nothing (empty prediction).",
        "proxy_decoy_mapping": "selection draws uniformly over all 10 features (causal, proxy, and nuisance) with no role preference.",
        "sparsity_rounding": "matched cardinality := |oracle support| rounded to the nearest integer (ties toward larger).",
        "hash_seeds": {
            "selection": f"{NAMESPACE}:generator_seed:random_matched_sparsity:selection:{{world_index}}",
            "confidence": f"{NAMESPACE}:generator_seed:random_matched_sparsity:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:random_matched_sparsity:tiebreak:{{world_index}}",
        },
    },
    "anti_causal_adversarial": {
        "action_generation": "predict the four-action vector and then bitwise-complement every action bit on every row.",
        "rationale_generation": "rank the noncausal features before the causal rationale features (anti-causal ordering).",
        "confidence_generation": "noncausal rank r receives 1-r/20 and causal rank r receives 0.2-r/100; row confidence follows ROW_CONFIDENCE_CONTRACT.",
        "tie_breaking": "resolve ties by ascending feature index.",
        "empty_rationale_behavior": "not reachable for rationale; the complement action is always well-defined.",
        "proxy_decoy_mapping": "noncausal set = world.decoy_features (proxy + nuisance); these lead causality in the ranking.",
        "sparsity_rounding": "no rounding; the entire feature set participates.",
        "hash_seeds": {
            "noncausal_order": f"{NAMESPACE}:generator_seed:anti_causal:noncausal_order:{{world_index}}",
            "confidence": f"{NAMESPACE}:generator_seed:anti_causal:confidence:{{world_index}}",
            "tiebreak": f"{NAMESPACE}:generator_seed:anti_causal:tiebreak:{{world_index}}",
        },
    },
}

ROW_CONFIDENCE_CONTRACT = {
    "fixture": "S uses an independent fixed-error ranking fixture shared by all six generators: error_i=1 iff SHA256(NAMESPACE:S_fixture:world:i) mod 5 equals 0; flip action 0 only on error rows, giving nonconstant 20-percent deterministic loss.",
    "generator_quality": {"oracle_causal": 1.0, "sparse_causal": 0.8, "diffuse_causal_plus_decoy": 0.6, "proxy_shortcut": 0.4, "random_matched_sparsity": 0.2, "anti_causal_adversarial": 0.0},
    "clean_scalar": "for generator quality q and row error e in {0,1}, clean_confidence=(1-e)*q+e*(1-q); no jitter enters AURC",
    "selective_destroyed_endpoint": "destroyed_confidence=error_i, ranking error rows first",
    "tie_aware_aurc": "group rows by exact scalar confidence and order groups descending. For a tie group of size m with z errors, after p earlier rows with u errors, define expected risk at within-group position k=1..m as (u+k*z/m)/(p+k). AURC is the arithmetic mean of these expected risks over all N=1024 accepted-row positions; S=-AURC.",
    "tie_rule": "ties are averaged analytically by tie_aware_aurc; hash jitter and row order never enter AURC",
    "sha_uint64_rule": "where any generator seed needs epsilon outside AURC, use the first 8 SHA-256 digest bytes interpreted unsigned big-endian and divide by 2^64",
    "admissibility": "all six generators are reported; dose-response gates use generators with q>0, while q=0 is the preregistered destroyed endpoint",
}

ATTRIBUTION_AGGREGATION = {
    "input": "four action-specific 10-feature score vectors g[a,j]",
    "formula": "g_aggregate[j]=(1/4)*sum_{a=0..3} abs(g[a,j]) for j=0..9",
    "ranking": "sort features by descending g_aggregate[j], breaking exact ties by ascending feature index",
    "use": "deletion AUC, insertion AUC, infidelity, and max sensitivity all use this same aggregate vector and ranking",
}

MANIPULATIONS: dict[str, dict[str, Any]] = {
    "action_correctness_degradation": {
        "target": "A",
        "quality": "1 - dose",
        "affected_channel": "action vector (the four predicted binary action bits)",
        "replacement_algorithm": "on the frozen nested prefix of floor(dose*1024) rows, replace action by the fixed destroyed endpoint bitwise-complement of ground-truth action; never complement generator output.",
        "admissible_generators": [name for name in GENERATORS if name != "anti_causal_adversarial"],
        "dose_zero_is_identity": True,
        "unchanged_channels": ["rationale support (R)", "confidence ranking (S)", "nuisance consistency (C1)"],
        "invariants_other_channels": [
            "predicted rationale support set is byte-identical to the pre-manipulation row output on every row",
            "per-action confidence/ranking order and ties are copied unchanged from the pre-manipulation row output",
            "nuisance-consistency pairing identity and all un-perturbed rows are unchanged",
        ],
    },
    "rationale_correctness_degradation": {
        "target": "R",
        "quality": "1 - dose",
        "affected_channel": "predicted rationale support (per-action feature membership)",
        "replacement_algorithm": "on the frozen nested prefix, replace rationale by the fixed destroyed endpoint: complement of ground-truth 10-feature membership; preserve clean action and row confidence.",
        "admissibility": "exclude cells whose baseline rationale already equals the destroyed endpoint on every row",
        "dose_zero_is_identity": True,
        "unchanged_channels": ["action vector (A)", "confidence ranking (S)", "nuisance consistency (C1)"],
        "invariants_other_channels": [
            "predicted action vector is unchanged on every row",
            "per-action ranking/confidence scores are unchanged on every row",
            "nuisance-consistency pairing and un-perturbed rows are unchanged",
        ],
    },
    "selective_ranking_degradation": {
        "target": "S",
        "quality": "1 - dose",
        "affected_channel": "confidence/ranking order",
        "replacement_algorithm": "on the frozen nested prefix, replace clean_confidence_i by ROW_CONFIDENCE_CONTRACT.destroyed_confidence_i; preserve actions and rationale.",
        "admissibility": "dose-response gates use q>0 generators; all six including q=0 destroyed endpoint remain in rankings",
        "dose_zero_is_identity": True,
        "unchanged_channels": ["action vector (A)", "rationale support (R)", "nuisance consistency (C1)"],
        "invariants_other_channels": [
            "predicted action vector unchanged on every row",
            "predicted rationale support unchanged on every row",
            "nuisance-consistency pairing and un-perturbed rows unchanged",
        ],
    },
    "nuisance_consistency_degradation": {
        "target": "C1",
        "quality": "1 - dose",
        "affected_channel": "C1 nuisance consistency (clean-vs-nuisance paired action flip rate and rationale Jaccard)",
        "replacement_algorithm": "A/R/S consume immutable clean_output. On the nuisance-paired C1 channel and frozen nested prefix, set paired action=complement(clean action) and paired rationale=complement(clean membership).",
        "channel_separation": "A/R/S consume clean_output only; C1 consumes (clean_output,nuisance_paired_output) only",
        "dose_zero_is_identity": True,
        "unchanged_channels": ["action vector (A)", "rationale support (R)", "confidence ranking (S)"],
        "invariants_other_channels": [
            "predicted action vector unchanged except the exactly targeted nuisance-injected flip rows",
            "predicted rationale unchanged except the exactly targeted disjoint replacement rows",
            "confidence/ranking order unchanged on every row",
        ],
    },
}

METRICS: dict[str, dict[str, str]] = {
    "A": {
        "definition": "macro-F1 over the four binary action labels, scored against the (recomputed) action truth",
        "direction": "higher",
    },
    "R": {
        "definition": "macro-F1 over the ten binary rationale-membership labels, scored against the (recomputed) rationale truth",
        "direction": "higher",
    },
    "S": {
        "definition": "negative tie-aware area under the selective-risk curve (AURC) over the confidence-ranked rows",
        "direction": "higher",
    },
    "C1_action": {
        "definition": "clean-vs-nuisance-paired estimate of one minus the action flip rate over nuisance-only world pairs",
        "direction": "higher",
    },
    "C1_rationale": {
        "definition": "clean-vs-nuisance-paired rowwise Jaccard of rationale supports over nuisance-only world pairs",
        "direction": "higher",
    },
}

BASELINES: dict[str, str] = {
    "support_f1": "higher",
    "deletion_auc": "lower",
    "insertion_auc": "higher",
    "infidelity": "lower",
    "max_sensitivity": "lower",
}

# Frozen formulas, edge cases, tie handling, and directions for A/R/S/C1 and the
# five baselines.  All formulas are result-blind (they specify computation, not
# observed outputs).
FORMULAS: dict[str, dict[str, str]] = {
    "A_formula": {
        "formula": "macro-F1=mean_a(F1_a)=(1/4)*sum_a(F1_a), F1_a=2*TP_a/(2*TP_a+FP_a+FN_a), with counts over 1024 rows",
        "truth": "against the recomputed action truth vector for the world/dose (causal changes recompute truth; semantically correct changes are not errors)",
        "tie_handling": "when 2*TP+FP+FN is zero (prediction and truth both empty), define F1_a=1; otherwise use the stated fraction",
        "direction": "higher is better",
        "edge_cases": "if an action label and its ground truth are both empty in a family, that action contributes macro-F1 = 1.0",
    },
    "R_formula": {
        "formula": "macro-F1 over the ten binary rationale-membership labels, macro-averaged per action as in A",
        "truth": "against the recomputed per-action causal support membership (instantiated Boolean expressions) for the world/dose",
        "tie_handling": "same zero-denominator rule as A_formula",
        "direction": "higher is better",
        "edge_cases": "empty support vs empty truth counts 1.0; empty support vs nonempty truth counts 0.0",
    },
    "S_formula": {
        "formula": "S = -AURC where AURC is the tie-aware area under the selective-risk curve computed over rows sorted by per-row ranking confidence",
        "tie_handling": "ties in confidence are broken by the frozen tie-break (ascending feature index then ascending row integer) before AURC integration",
        "direction": "higher is better (more negative AURC)",
        "edge_cases": "constant-conference ranking collapses to a single AURC value (area of the identity selective curve)",
    },
    "C1_action_formula": {
        "formula": "1 - flip_rate, where flip_rate = (# nuisance-only world-paired rows whose predicted action changed) / (total nuisance-only paired rows)",
        "truth": "nuisance-only pairs never recompute truth (nuisance features are not causal); a changed prediction is a genuine C1 violation",
        "tie_handling": "an action change is binary; no ties",
        "direction": "higher is better (fewer flips)",
        "edge_cases": "if there are zero nuisance-only paired rows in a family, C1_action is excluded from that family's gate",
    },
    "C1_rationale_formula": {
        "formula": "clean-vs-nuisance-paired rowwise Jaccard = mean_row Jaccard(support_clean, support_nuisance)",
        "truth": "Jaccard=|A intersection B|/|A union B|; empty-vs-empty counts 1.0",
        "tie_handling": "no ties",
        "direction": "higher is better",
        "edge_cases": "|A union B|=0 implies both sets are empty and gives 1.0",
    },
    "support_f1": {
        "formula": "macro-F1 between predicted rationale support and the recomputed ground-truth causal support, identical to R_formula",
        "direction": "higher",
        "tie_handling": "same as R_formula",
        "edge_cases": "same as R_formula",
    },
    "deletion_auc": {
        "formula": "for k=0..10 zero the top-k ranked bits, compute four-action macro-F1 over 1024 rows, then trapezoid-integrate the 11 values on grid k/10",
        "reference": "deletion order is exactly ATTRIBUTION_AGGREGATION.ranking; no random mask order is used",
        "mask": "deletion mask zeroes the top-k ranked features across all 10 feature bits for the ranked population",
        "direction": "lower is better (performance should collapse faster)",
        "tie_handling": "ties in deletion rank follow the frozen tie-break order",
    },
    "insertion_auc": {
        "formula": "for k=0..10 restore the top-k ranked bits from an all-zero input, compute four-action macro-F1 over 1024 rows, then trapezoid-integrate on grid k/10",
        "reference": "insertion uses exactly ATTRIBUTION_AGGREGATION.ranking and adds top-k features back from a zeroed baseline",
        "mask": "insertion mask restores features in frozen rank order for the ranked population",
        "direction": "higher is better",
        "tie_handling": "ties in insertion rank follow the frozen tie-break order",
    },
    "infidelity": {
        "formula": "mean_mask((dot(mask,g)-(f_scalar(x)-f_scalar(x XOR mask)))^2); f_scalar is the arithmetic mean of the four binary action outputs",
        "distribution": "all 1024 binary masks with uniform weight 1/1024 in canonical integer order",
        "direction": "lower is better",
        "tie_handling": "none",
        "edge_cases": "the all-zero mask contributes zero",
    },
    "max_sensitivity": {
        "formula": "max over exactly ten Hamming-distance-1 neighbors of max_feature |g_j(x)-g_j(neighbor)|, averaged over 1024 rows",
        "max_sensitivity_neighborhood": "radius is exactly 1 and the neighborhood is all ten single-bit flips in ascending feature order; no random sampling",
        "direction": "lower is better (attribution is robust)",
        "tie_handling": "maximum over neighborhood ties is irrelevant (a max)",
        "edge_cases": "degenerate neighborhood (radius 0) gives max_sensitivity = 0",
    },
}

# Frozen estimands for the family gates and the incremental regression.
ESTIMANDS: dict[str, dict[str, Any]] = {
    "kendall_tau_b": {
        "definition": "Kendall tau-b between per-world quality and per-world metric value",
        "quality_axis": "quality = 1 - dose (higher dose => lower quality => the manipulation is expected to lower a valid metric)",
        "positive_direction_quality": "quality = 1 - dose so that higher quality corresponds to higher valid metric",
        "unit": "world (32 worlds)",
    },
    "auroc": {
        "definition": "area under the ROC curve discriminating high-quality (intact) rows from low-quality (degraded) rows",
        "positive_class": "high quality / intact output",
        "dose_groups": "positive/high-quality doses={0,0.25}; negative/low-quality doses={0.75,1.0}; dose 0.5 is excluded",
        "quality_axis": "quality = 1 - dose applied to row-level intactness",
        "unit": "world",
    },
    "standardized_slope": {
        "definition": "standardized linear slope of valid metric vs quality (quality = 1 - dose)",
        "denominator": "the standard deviation of the metric across worlds (formula-level standardized unit) so slopes are comparable across metrics",
    },
    "mtmm": {
        "definition": "for family f, gap_f=tau_b(metric_f,quality_f)-max_{g!=f}|tau_b(metric_f,quality_g)| on matched cells",
        "convergent": "Kendall tau-b with the corresponding manipulation quality=1-dose; take mean tau across admissible generators within each world",
        "non_target": "maximum absolute Kendall tau-b with the other three manipulation-quality axes on matched cells",
        "c1_components": "compute separately for C1_action and C1_rationale; C1 family value is their minimum and uses shared-bootstrap max-statistic inference",
        "matched_cells": "match identical world and generator across manipulation axes; compare the same five dose positions after applying each axis-specific admissibility rule",
        "constant_series": "define Kendall tau-b association as 0 when either input series is constant",
    },
    "nuisance_unit": {
        "definition": "nuisance perturbation unit is a single feature 1-bit flip of a nuisance feature; nuisance-only pairs differ only in nuisance features",
    },
    "shuffle_unit": {
        "definition": "within each shared world-bootstrap replicate, permute high-vs-low AUROC labels across matched cells 10000 times using SHA256(NAMESPACE:shuffle:replicate:permutation) hash order; recompute AUROC; dose 0.5 remains excluded",
        "positive_label": "1 for doses 0 and 0.25; 0 for doses 0.75 and 1.0",
        "permutations": 10000,
    },
    "leave_one_world_out": {
        "model": "fixed OLS baseline-only versus baseline-plus-ARSC",
        "target": "latent scalar quality=1-dose for each admissible world x generator x manipulation x dose cell",
        "matrices": "one row per admissible cell; baseline X contains five direction-aligned baselines; augmented X appends A,R,S,C1_action,C1_rationale; y is latent quality",
        "standardization": "within each training fold, z-score nonconstant predictors and y; apply training mean/scale to held-out rows; constant columns become zero",
        "intercept": "fit includes an intercept",
        "aggregation": "concatenate held-out predictions from all 32 folds; compute SSE-based R2 once per model; delta-R2=R2_augmented-R2_baseline",
        "rank_deficiency": "if a fold's design matrix is rank-deficient, use the pseudoinverse (numpy.linalg.lstsq)",
        "negative_r2": "negative R2 values are allowed and preserved (do not clip), reflecting worse-than-intercept fit",
    },
}

# Required ranking reports frozen at the protocol level.
RANKING_REPORTS: dict[str, str] = {
    "full_rankings": "mean generator-by-metric ranking averaged across the 32 worlds for every metric",
    "concordance": "Kendall concordance among the per-world generator rankings",
    "top1_regret": "latent quality of the ground-truth-best generator minus latent quality of the metric-selected top generator; ties use frozen generator order",
    "reversal_rate": "generator-pair rank swaps across the four adjacent transitions among five doses, divided by four",
}

GATES: dict[str, Any] = {
    "family_count": len(FAMILIES),
    "family_names": list(FAMILIES),
    "family_q": FAMILY_Q,
    "family_q_derivation": FAMILY_Q_DERIVATION,
    "bootstrap": {
        "seed": BOOTSTRAP_SEED,
        "unit": "world",
        "draws": BOOTSTRAP_DRAWS,
        "shared_draws": True,
        "quantile_method": "numpy.quantile(method='linear') over the shared world-bootstrap replicate distribution",
        "bonferroni_q": FAMILY_Q,
        "ci1_components": {
            "intersection": "the C1 family gate statistic is the minimum (intersection) over the C1_action gate and the C1_rationale gate",
            "max_statistic": "max-statistic / shared-bootstrap correction over the C1_action and C1_rationale components keeps C1 one of the four q=0.0125 families",
            "shared_draws_applies": "the same 10,000 shared world-bootstrap draws are reused across all four families and across the two C1 components",
        },
    },
    "kendall_tau_b": {"point_min": 0.70, "corrected_lower_strict_min": 0.50},
    "high_low_auroc": {"point_min": 0.80, "corrected_lower_strict_min": 0.70},
    "mtmm_gap": {"point_min": 0.30, "corrected_lower_strict_min": 0.20},
    "nuisance_negative_control": {
        "non_target_abs_change_corrected_upper_strict_max": 0.10,
        "shuffled_mapping_auroc_closed_interval": [0.45, 0.55],
    },
    "leave_one_world_out_incremental_delta_r2": {
        "model": "fixed OLS baseline-only versus baseline-plus-ARSC",
        "point_min": 0.15,
        "corrected_lower_strict_min": 0.10,
    },
    "required_ranking_reports": ["full_rankings", "concordance", "top1_regret", "reversal_rate"],
    "oracle_destroyed_standardized_difference": {
        "point_min": 0.50,
        "failure_class": "IMPLEMENTATION_FAILURE",
        "status_note": "IMPLEMENTATION_FAILURE is an infrastructure/implementation status, never a third scientific verdict; the only two scientific verdicts are the FINAL_VERDICTS.",
    },
}

BOUNDARY_CONTROLS = {
    "nuisance_invariance": {
        "applies_to": "C1 only",
        "definition": "flip only nuisance features; ground-truth causal rules are untouched so truth is unchanged across the pair; both C1 components measure output invariance under nuisance-only world perturbation.",
        "raw_response_change_descriptors": "record the unlabeled response change (action flip rate, rationale Jaccard) separately from any semantic-correctness judgment.",
        "semantic_correctness": "semantic correctness is judged independently of raw response change; a semantically correct response to a causal change is NOT a C1 nuisance violation.",
        "c1_scope": "C1 is applied only to nuisance-only pairs; causal-boundary pairs never feed the C1 gate.",
    },
    "causal_recomputation": {
        "applies_to": "A/R/S semantic scoring; C1 raw descriptor only and never the C1 nuisance gate",
        "definition": "flip causally relevant features, recompute the action and rationale truth, and score the oracle against the recomputed truth so an appropriate oracle response is not penalized.",
        "perturbation_order": "for world w and row i, causal features are flipped in SHA256(NAMESPACE:causal_boundary:w:i:feature) order; enumerate all nonempty prefixes of the four causal features",
        "recompute_truth": "after any causal change, recompute truth from the frozen rules; semantically correct changes are scored against the recomputed truth.",
        "semantic_correctness": "record raw action/rationale response changes descriptively, but causal pairs never enter the C1 gate; A/R/S score against recomputed truth.",
    },
}

FINAL_VERDICTS = (
    "ROUND13_SYNTHETIC_METRIC_FAMILY_PASS",
    "ROUND13_SYNTHETIC_METRIC_FAMILY_NOT_VALIDATED",
)

# Formal one-shot execution contract.  The permanent claim path, schema, unique
# attempt label, artifact allowlist/index and hash-closure rules are frozen.
FORMAL_EXECUTION_SCHEMA = "ARSC_ROUND13_SYNTHETIC_MTMM_CLAIM_V1"
FORMAL_ATTEMPT = "round13_attempt01"
FORMAL_CLAIM_NAME = "round13_synthetic_mtmm_formal_claim.json"
FORMAL_RESULTS_NAME = "round13_synthetic_mtmm_results.json"
FORMAL_VERDICT_NAME = "round13_synthetic_mtmm_verdict.json"
FORMAL_INDEX_NAME = "round13_synthetic_mtmm_artifact_index.json"
FORMAL_CLAIM_PATH = "outputs/validity/round13_synthetic_mtmm_formal_claim.json"
FORMAL_PROTOCOL_NAME = "round13_synthetic_mtmm_frozen_protocol.json"

# Complete artifact allowlist for the formal execution hash closure (relative
# to the outputs root), plus the index that seals every artifact's SHA-256.
FORMAL_ARTIFACT_ALLOWLIST = (
    FORMAL_PROTOCOL_NAME,
    FORMAL_CLAIM_NAME,
    FORMAL_RESULTS_NAME,
    FORMAL_VERDICT_NAME,
    FORMAL_INDEX_NAME,
)
FORMAL_HASH_CLOSURE = {
    "index": FORMAL_INDEX_NAME,
    "allowlist": list(FORMAL_ARTIFACT_ALLOWLIST),
    "index_records_sha256_of_every_allowlisted_artifact": False,
    "index_self_excluded": True,
    "index_records": [name for name in FORMAL_ARTIFACT_ALLOWLIST if name not in {FORMAL_INDEX_NAME, FORMAL_CLAIM_NAME}],
    "claim_is_not_rewritten": True,
    "closure_rule": "index hashes protocol, results, and verdict only; index and permanent claim are self/cycle-excluded and their hashes are bound by the subsequent Git commit plus independent H3 closure record",
    "claim_consumed_on_postclaim_infrastructure_failure": True,
}

# Preclaim refusal vs postclaim infrastructure failure are distinct control
# points.  A preformal refusal refuses the run before any claim is made and
# leaves the claim unsaturated; a postclaim infrastructure failure happens after
# the durable claim and consumes the one-attempt claim.  In neither case is
# IMPLEMENTATION_FAILURE a third scientific verdict.
ONE_SHOT = {
    "formal_claim_is_permanent": True,
    "infrastructure_failure_consumes_claim": True,
    "retry_allowed": False,
    "delete_or_recover_claim_allowed": False,
    "attempt": FORMAL_ATTEMPT,
    "claim_path": FORMAL_CLAIM_PATH,
    "claim_schema": FORMAL_EXECUTION_SCHEMA,
    "preclaim_refusal": {
        "status": PREFORMAL_REFUSAL,
        "claim_consumed": False,
        "kind": "preformal refusal before any durable claim is acquired",
    },
    "postclaim_failure": {
        "status": POSTCLAIM_INFRASTRUCTURE_FAILURE,
        "claim_consumed": True,
        "kind": "postclaim infrastructure failure consumes the one-attempt claim",
    },
    "infrastructure_status": {
        "value": INFRASTRUCTURE_STATUS,
        "is_a_scientific_verdict": False,
    },
    "scientific_verdict_count": 2,
}

RULE_BANK = (
    "x0 AND x1",
    "x0 OR x1",
    "x0 XOR x1",
    "MAJORITY(x0,x1,x2)",
    "x0 AND (x1 OR x2)",
    "(x0 AND x1) OR (x2 AND x3)",
    "PARITY(x0,x1,x2)",
    "MAJORITY(x0,x1,x2,x3)",
)


def _digest(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8")).digest()


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _hash_order(key: str, size: int) -> list[int]:
    return sorted(range(size), key=lambda value: _digest(f"{key}:{value:04d}"))


def _order_digest(order: list[int]) -> str:
    payload = b"".join(value.to_bytes(4, "big") for value in order)
    return hashlib.sha256(payload).hexdigest().upper()


def _rule_variables(template: str) -> list[int]:
    """Return the placeholder variable indices (x0,x1,...) referenced by a rule template."""
    return [int(index) for index in re.findall(r"x(\d+)", template)]


def _instantiate_expression(template: str, causal: list[int]) -> str:
    """Instantiate a rule template over the world's causal feature indices."""
    return re.sub(r"x(\d+)", lambda match: f"f_{causal[int(match.group(1))]}", template)


def _expression_support(expression: str) -> list[int]:
    """Return the sorted feature indices referenced by an instantiated expression."""
    return sorted({int(index) for index in re.findall(r"f_(\d+)", expression)})


def _proxy_partners(world_index: int, causal: list[int], proxy: list[int]) -> dict[str, int]:
    """Deterministic hash-order pairing of each causal feature to a proxy partner."""
    partners: dict[str, int] = {}
    for feature in causal:
        inside = _hash_order(f"{NAMESPACE}:proxypartner:{world_index}:{feature}", len(proxy))
        partners[str(feature)] = proxy[inside[0]]
    return partners


def build_worlds() -> list[dict[str, Any]]:
    worlds: list[dict[str, Any]] = []
    for world_index in range(WORLD_COUNT):
        world_id = f"world_{world_index:02d}"
        seed_sha256 = _hex(f"{NAMESPACE}:world:{world_index}")
        order = _hash_order(f"{NAMESPACE}:roles:{world_index}", FEATURE_COUNT)
        causal = order[:4]
        proxy = order[4:7]
        nuisance = order[7:]
        rule_indices = [
            int.from_bytes(_digest(f"{NAMESPACE}:rule:{world_index}:{action}")[:4], "big") % len(RULE_BANK)
            for action in range(4)
        ]
        templates = [RULE_BANK[index] for index in rule_indices]
        expressions = [_instantiate_expression(template, causal) for template in templates]
        supports = [_expression_support(expression) for expression in expressions]
        worlds.append(
            {
                "world_id": world_id,
                "seed_sha256": seed_sha256,
                "row_count": ROWS_PER_WORLD,
                "feature_roles": {
                    "causal": causal,
                    "proxy": proxy,
                    "nuisance": nuisance,
                },
                "feature_role_map_sha256": _hex(f"{NAMESPACE}:roles:{world_index}"),
                "row_enumeration": ROW_ENUMERATION,
                "action_rule_templates": templates,
                "rule_indices": rule_indices,
                "action_expressions": expressions,
                "action_rationale_supports": supports,
                "action_supports_match_expressions": [
                    _expression_support(expression) == support
                    for expression, support in zip(expressions, supports)
                ],
                "proxy_partners": _proxy_partners(world_index, causal, proxy),
                "decoy_features": proxy + nuisance,
                "truth_evaluation": "Evaluate all 1024 canonical binary rows (integers 0..1023, feature k = bit k); action truth is each Boolean action rule evaluated over its causal features; action rationale is the instantiated causal support of each action rule.",
            }
        )
    return worlds


def build_replacement_orders() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for world_index in range(WORLD_COUNT):
        for generator in GENERATORS:
            for manipulation in MANIPULATIONS:
                for dose in NONZERO_DOSES:
                    affected_count = int(math.floor(dose * ROWS_PER_WORLD))
                    key = f"{NAMESPACE}:replacement:{world_index}:{generator}:{manipulation}:{dose:.2f}"
                    order = _hash_order(key, ROWS_PER_WORLD)
                    affected_row_ids = order[:affected_count]
                    records.append(
                        {
                            "world_id": f"world_{world_index:02d}",
                            "generator": generator,
                            "manipulation": manipulation,
                            "target": MANIPULATIONS[manipulation]["target"],
                            "dose": dose,
                            "affected_count": affected_count,
                            "affected_row_ids": affected_row_ids,
                            "replacement_function": MANIPULATIONS[manipulation]["replacement_algorithm"],
                            "replacement_seed_sha256": _hex(f"{key}:replacement"),
                            "permutation": order,
                            "permutation_sha256": _order_digest(order),
                            "dose_zero_is_identity": MANIPULATIONS[manipulation]["dose_zero_is_identity"],
                            "invariants_other_channels": MANIPULATIONS[manipulation]["invariants_other_channels"],
                        }
                    )
    return records


def build_contract(*, include_replacement_orders: bool = True) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "result_blind": True,
        "design": {
            "world_count": WORLD_COUNT,
            "feature_count": FEATURE_COUNT,
            "rows_per_world": ROWS_PER_WORLD,
            "feature_role_counts": {"causal": 4, "proxy": 3, "nuisance": 3},
            "doses": list(DOSES),
            "worlds": build_worlds(),
            "generators": GENERATORS,
            "manipulations": MANIPULATIONS,
            "boundary_controls": BOUNDARY_CONTROLS,
            "row_confidence_contract": ROW_CONFIDENCE_CONTRACT,
            "attribution_aggregation": ATTRIBUTION_AGGREGATION,
        },
        "evaluation": {
            "metrics": METRICS,
            "formulas": FORMULAS,
            "baselines": BASELINES,
            "estimands": ESTIMANDS,
            "ranking_reports": RANKING_REPORTS,
            "gates": GATES,
        },
        "formal_execution": {
            "one_shot": ONE_SHOT,
            "artifact_allowlist": list(FORMAL_ARTIFACT_ALLOWLIST),
            "hash_closure": FORMAL_HASH_CLOSURE,
            "possible_scientific_verdicts": list(FINAL_VERDICTS),
        },
    }
    if include_replacement_orders:
        contract["design"]["replacement_orders"] = build_replacement_orders()
    validate_contract(contract, require_orders=include_replacement_orders)
    return contract


def validate_contract(contract: dict[str, Any], *, require_orders: bool = True) -> None:
    if contract.get("result_blind") is not True:
        raise ValueError("protocol must remain result-blind")
    design = contract["design"]
    worlds = design["worlds"]
    if len(worlds) != WORLD_COUNT or any(world["row_count"] != ROWS_PER_WORLD for world in worlds):
        raise ValueError("world count or exhaustive row count mismatch")
    seeds = {world["seed_sha256"] for world in worlds}
    mappings = set()
    for world in worlds:
        roles = world["feature_roles"]
        flattened = roles["causal"] + roles["proxy"] + roles["nuisance"]
        if len(roles["causal"]) != 4 or len(roles["proxy"]) != 3 or len(roles["nuisance"]) != 3:
            raise ValueError("invalid 4/3/3 role counts")
        if sorted(flattened) != list(range(FEATURE_COUNT)):
            raise ValueError("feature roles must be a disjoint partition")
        if world["row_enumeration"] != ROW_ENUMERATION:
            raise ValueError("world row enumeration contract changed")
        if len(world["rule_indices"]) != 4 or len(world["action_rule_templates"]) != 4:
            raise ValueError("world must freeze four action rules")
        if not world["action_supports_match_expressions"] or any(
            not ok for ok in world["action_supports_match_expressions"]
        ):
            raise ValueError("rule supports must match the instantiated expressions")
        if len(world["action_expressions"]) != 4 or len(world["action_rationale_supports"]) != 4:
            raise ValueError("world must freeze four action expressions and four supports")
        if len(world["proxy_partners"]) != 4:
            raise ValueError("proxy partner map must cover the four causal features")
        mappings.add(tuple(flattened))
    if len(seeds) != WORLD_COUNT or len(mappings) != WORLD_COUNT:
        raise ValueError("world seeds and role mappings must be unique")
    if tuple(design["generators"]) != tuple(GENERATORS):
        raise ValueError("generator contract changed")
    if not all(
        isinstance(spec, dict) and {"action_generation", "rationale_generation", "confidence_generation",
                                    "tie_breaking", "empty_rationale_behavior", "proxy_decoy_mapping",
                                    "sparsity_rounding", "hash_seeds"} <= set(spec)
        for spec in GENERATORS.values()
    ):
        raise ValueError("generator records must be structured declarative records")
    if tuple(design["manipulations"]) != tuple(MANIPULATIONS):
        raise ValueError("manipulation contract changed")
    if tuple(design["doses"]) != DOSES:
        raise ValueError("dose contract changed")
    for manipulation, spec in MANIPULATIONS.items():
        if spec["dose_zero_is_identity"] is not True:
            raise ValueError("dose 0 must be identity for every manipulation")
        if not spec["unchanged_channels"] or not spec["invariants_other_channels"]:
            raise ValueError("manipulation must freeze unchanged channels and invariants")
        if spec.get("quality") != "1 - dose":
            raise ValueError("positive-direction quality must be 1 - dose")
    # Bootstrap / family-count contract.
    gates = contract["evaluation"]["gates"]
    if gates["family_count"] != len(FAMILIES) or gates["family_count"] != 4:
        raise ValueError("family count must be exactly four")
    if gates["family_q"] != FAMILY_Q or gates["family_q"] != 0.05 / 4:
        raise ValueError("family q must be 0.05/4 = 0.0125")
    if gates["bootstrap"]["seed"] != BOOTSTRAP_SEED or gates["bootstrap"]["draws"] != BOOTSTRAP_DRAWS:
        raise ValueError("bootstrap seed or draw count contract changed")
    if gates["bootstrap"]["shared_draws"] is not True:
        raise ValueError("bootstrap draws must be shared across families")
    if "intersection" not in gates["bootstrap"]["ci1_components"] or \
       "max_statistic" not in gates["bootstrap"]["ci1_components"]:
        raise ValueError("C1 must freeze its intersection/max-statistic family correction")
    # Formal execution invariants.
    formal = contract["formal_execution"]["one_shot"]
    if tuple(contract["formal_execution"]["possible_scientific_verdicts"]) != FINAL_VERDICTS:
        raise ValueError("scientific verdict contract changed")
    if len(contract["formal_execution"]["possible_scientific_verdicts"]) != 2:
        raise ValueError("exactly two scientific verdicts are required")
    if formal["infrastructure_status"]["is_a_scientific_verdict"] is not False:
        raise ValueError("IMPLEMENTATION_FAILURE must never be a scientific verdict")
    if formal["infrastructure_status"]["value"] != "IMPLEMENTATION_FAILURE":
        raise ValueError("infrastructure status value changed")
    if formal["attempt"] != "round13_attempt01":
        raise ValueError("unique attempt label changed")
    if formal["claim_path"] != "outputs/validity/round13_synthetic_mtmm_formal_claim.json":
        raise ValueError("formal claim path changed")
    if formal["postclaim_failure"]["claim_consumed"] is not True:
        raise ValueError("postclaim infrastructure failure must consume the claim")
    if formal["preclaim_refusal"]["claim_consumed"] is not False:
        raise ValueError("preformal refusal must not consume the claim")
    if require_orders:
        orders = design.get("replacement_orders", [])
        expected = WORLD_COUNT * len(GENERATORS) * len(MANIPULATIONS) * len(NONZERO_DOSES)
        if len(orders) != expected:
            raise ValueError("replacement order coverage mismatch")
        for record in orders:
            order = record["permutation"]
            if sorted(order) != list(range(ROWS_PER_WORLD)) or _order_digest(order) != record["permutation_sha256"]:
                raise ValueError("invalid replacement permutation or digest")
            expected_count = int(math.floor(record["dose"] * ROWS_PER_WORLD))
            if record["affected_count"] != expected_count:
                raise ValueError("replacement affected count must be floor(dose*rows)")
            if record["affected_row_ids"] != order[:expected_count]:
                raise ValueError("replacement affected row ids must be the frozen permutation prefix")
            if record["dose_zero_is_identity"] is not True:
                raise ValueError("replacement record must be identity at dose 0")
            if not record["invariants_other_channels"]:
                raise ValueError("replacement record must freeze the other-channel invariants")


__all__ = [
    "BASELINES", "BOOTSTRAP_DRAWS", "BOOTSTRAP_SEED", "BOUNDARY_CONTROLS",
    "DOSES", "ESTIMANDS", "FAMILIES", "FAMILY_Q", "FAMILY_Q_DERIVATION",
    "FINAL_VERDICTS", "FORMAL_ARTIFACT_ALLOWLIST", "FORMAL_ATTEMPT",
    "FORMAL_CLAIM_NAME", "FORMAL_CLAIM_PATH", "FORMAL_EXECUTION_SCHEMA",
    "FORMAL_HASH_CLOSURE", "FORMAL_INDEX_NAME", "FORMAL_PROTOCOL_NAME",
    "FORMAL_RESULTS_NAME", "FORMAL_VERDICT_NAME", "FORMULAS", "GATES",
    "GENERATORS", "INFRASTRUCTURE_STATUS", "MANIPULATIONS", "METRICS",
    "NAMESPACE", "NONZERO_DOSES", "ONE_SHOT", "POSTCLAIM_INFRASTRUCTURE_FAILURE",
    "PREFORMAL_REFUSAL", "RANKING_REPORTS", "ROW_ENUMERATION", "ROWS_PER_WORLD",
    "RULE_BANK", "SCHEMA_VERSION", "WORLD_COUNT", "build_contract",
    "build_replacement_orders", "build_worlds", "validate_contract",
]
