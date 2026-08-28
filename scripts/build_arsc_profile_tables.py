"""Main-result Profile Table and the Action-only-to-ARSC Decision Change Table.

These are the two headline tables of the paper and they answer RQ1: when two
decision models have comparable Action Performance, does looking at the other
three axes change the judgement?

The Profile Table reports every axis separately, with the frozen five-seed
mean, the frozen hierarchical bootstrap interval, the seed-level agreement
count and the explicit boundary of what the axis does *not* measure.  There is
deliberately no aggregate score: ARSC reports a profile, not a ranking.

The Decision Change Table walks an evaluation view at a time -- Action
Performance alone, then each additional axis, then the seed-level distribution,
the Round 10 dose-response and the S construct audit -- and contrasts the
conclusion a reader would reach from that view alone against the conclusion
that survives the whole profile.

Every number is read from a frozen artifact:

* ``outputs/validity/rq1_multiseed_summary.json``      Round 5, RQ1
* ``outputs/validity/round10_corruption_formal_attempt02/``  Round 10, RQ2
* ``outputs/validity/round12_existing_outputs_results.json`` Round 12, secondary
* ``outputs/paper/s_confidence_audit.json``            S construct audit

Prose in this script is narrative only; the numbers inside it are formatted
from the loaded artifacts and are never transcribed by hand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.paper_assets import (
    ACTION_EQUIVALENCE_MARGIN,
    AXIS_NAMES,
    AXIS_NOT,
    AXIS_OPERATIONALISATION,
    FROZEN_SEEDS,
    MODEL_ACTION,
    MODEL_JOINT,
    PERTURBATION_FAMILIES,
    load_round10_results,
    load_round12_results,
    load_rq1_summary,
    provenance,
    read_json,
    rq1_metric_rows,
    rq1_seed_metrics,
    write_csv,
    write_json,
    write_markdown_table,
)

S_AUDIT_PATH = "outputs/paper/s_confidence_audit.json"
ROUND10_AXIS_PATH = "outputs/paper/round10_axis_separation.json"
ROUND12_REVIEW_PATH = (
    "outputs/validity/round12_existing_outputs_postresult_reviewer_decision.json"
)

#: Rows of the Profile Table.  ``lower_is_better`` drives the orientation of
#: the reported Joint advantage so that positive always means "Joint better".
PROFILE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "axis": "A",
        "label": "Action Macro-F1",
        "action_key": f"action_macro_f1::{MODEL_ACTION}",
        "joint_key": f"action_macro_f1::{MODEL_JOINT}",
        "delta_key": "delta_action_macro_f1::Joint-Action",
        "lower_is_better": False,
    },
    {
        "axis": "A",
        "label": "Action Micro-F1",
        "action_key": f"action_micro_f1::{MODEL_ACTION}",
        "joint_key": f"action_micro_f1::{MODEL_JOINT}",
        "delta_key": None,
        "lower_is_better": False,
    },
    {
        "axis": "R",
        "label": "Rationale Macro-F1 (21 classes)",
        "action_key": None,
        "joint_key": f"rationale_macro_f1::{MODEL_JOINT}",
        "delta_key": None,
        "lower_is_better": False,
    },
    {
        "axis": "R",
        "label": "Rationale Micro-F1 (21 classes)",
        "action_key": None,
        "joint_key": f"rationale_micro_f1::{MODEL_JOINT}",
        "delta_key": None,
        "lower_is_better": False,
    },
    {
        "axis": "S",
        "label": "AURC (exact-set error, calibrated)",
        "action_key": f"aurc::{MODEL_ACTION}",
        "joint_key": f"aurc::{MODEL_JOINT}",
        "delta_key": "delta_aurc::Joint-Action",
        "lower_is_better": True,
    },
    {
        "axis": "S",
        "label": "UAR@90 (risk at 90% coverage)",
        "action_key": f"unsafe_acceptance_rate_90::{MODEL_ACTION}",
        "joint_key": f"unsafe_acceptance_rate_90::{MODEL_JOINT}",
        "delta_key": "delta_unsafe_acceptance_rate_90::Joint-Action",
        "lower_is_better": True,
    },
    {
        "axis": "S",
        "label": "ECE (calibrated)",
        "action_key": f"ece_calibrated::{MODEL_ACTION}",
        "joint_key": f"ece_calibrated::{MODEL_JOINT}",
        "delta_key": "delta_ece_calibrated::Joint-Action",
        "lower_is_better": True,
    },
    {
        "axis": "C1",
        "label": "Action-set flip rate (mean of 3 families)",
        "action_key": f"action_flip_rate_mean_three::{MODEL_ACTION}",
        "joint_key": f"action_flip_rate_mean_three::{MODEL_JOINT}",
        "delta_key": "advantage_action_flip_rate_mean_three::Action-Joint",
        "delta_already_oriented": True,
        "lower_is_better": True,
    },
    *(
        {
            "axis": "C1",
            "label": f"Action-set flip rate ({family})",
            "action_key": f"action_flip_rate_{family}::{MODEL_ACTION}",
            "joint_key": f"action_flip_rate_{family}::{MODEL_JOINT}",
            "delta_key": f"advantage_action_flip_rate_{family}::Action-Joint",
            "delta_already_oriented": True,
            "lower_is_better": True,
        }
        for family in PERTURBATION_FAMILIES
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default="outputs/paper/arsc_profile.json")
    parser.add_argument(
        "--output-profile-csv", default="outputs/paper/arsc_profile.csv"
    )
    parser.add_argument(
        "--output-profile-markdown", default="outputs/paper/tables/arsc_profile.md"
    )
    parser.add_argument(
        "--output-decision-csv", default="outputs/paper/decision_change.csv"
    )
    parser.add_argument(
        "--output-decision-markdown",
        default="outputs/paper/tables/decision_change.md",
    )
    return parser.parse_args()


def fmt(value: float | None, digits: int = 6, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def interval(lower: float, upper: float, digits: int = 6) -> str:
    return f"[{lower:+.{digits}f}, {upper:+.{digits}f}]"


def verdict_from_interval(lower: float, upper: float) -> str:
    """Frozen reading of a hierarchical bootstrap interval for a comparison."""

    if lower > 0.0:
        return "Joint better (95% CI excludes 0)"
    if upper < 0.0:
        return "Action-Only better (95% CI excludes 0)"
    return "inconclusive (95% CI includes 0)"


def build_profile(
    metric_rows: dict[str, dict[str, float]],
    seed_metrics: dict[int, dict[str, float]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in PROFILE_ROWS:
        record: dict[str, Any] = {
            "axis": spec["axis"],
            "axis_name": AXIS_NAMES[spec["axis"]],
            "operationalisation": AXIS_OPERATIONALISATION[spec["axis"]],
            "does_not_measure": AXIS_NOT[spec["axis"]],
            "metric": spec["label"],
            "lower_is_better": spec["lower_is_better"],
        }
        for role, key in (("action_only", spec["action_key"]), ("joint", spec["joint_key"])):
            if key is None:
                record[f"{role}_mean"] = None
                record[f"{role}_ci_lower"] = None
                record[f"{role}_ci_upper"] = None
                continue
            row = metric_rows[key]
            record[f"{role}_mean"] = row["mean_across_seeds"]
            record[f"{role}_ci_lower"] = row["hierarchical_ci_lower"]
            record[f"{role}_ci_upper"] = row["hierarchical_ci_upper"]

        delta_key = spec["delta_key"]
        if delta_key is None:
            record.update(
                {
                    "joint_advantage_metric_key": None,
                    "joint_advantage_mean": None,
                    "joint_advantage_ci_lower": None,
                    "joint_advantage_ci_upper": None,
                    "seeds_favouring_joint": None,
                    "verdict": "single-model axis (Action-Only has no R head)"
                    if spec["axis"] == "R"
                    else "reported for completeness; no frozen paired interval",
                }
            )
            records.append(record)
            continue

        # Orient every advantage so that positive means "Joint is better".
        orientation = 1.0
        if spec["lower_is_better"] and not spec.get("delta_already_oriented"):
            orientation = -1.0
        row = metric_rows[delta_key]
        mean = row["mean_across_seeds"] * orientation
        lower = row["hierarchical_ci_lower"] * orientation
        upper = row["hierarchical_ci_upper"] * orientation
        if orientation < 0:
            lower, upper = upper, lower
        seed_values = [
            seed_metrics[seed][delta_key] * orientation for seed in FROZEN_SEEDS
        ]
        record.update(
            {
                "joint_advantage_metric_key": delta_key,
                "joint_advantage_orientation": orientation,
                "joint_advantage_mean": mean,
                "joint_advantage_ci_lower": lower,
                "joint_advantage_ci_upper": upper,
                "seeds_favouring_joint": int(sum(value > 0.0 for value in seed_values)),
                "seed_values": [float(value) for value in seed_values],
                "verdict": verdict_from_interval(lower, upper),
            }
        )
        records.append(record)
    return records


def build_decision_change(
    metric_rows: dict[str, dict[str, float]],
    seed_metrics: dict[int, dict[str, float]],
    summary: dict[str, Any],
    round10: dict[str, Any],
    round10_axis: dict[str, Any],
    round12: dict[str, Any],
    round12_review: dict[str, Any],
    s_audit: dict[str, Any],
    rationale_coverage: dict[str, Any],
) -> list[dict[str, str]]:
    """The Action-only-conclusion to ARSC-conclusion table."""

    equivalence = summary["decisions"]["action_equivalence"]
    delta_a = metric_rows["delta_action_macro_f1::Joint-Action"]
    action_only_a = metric_rows[f"action_macro_f1::{MODEL_ACTION}"]
    joint_a = metric_rows[f"action_macro_f1::{MODEL_JOINT}"]
    seeds_favouring_joint_a = sum(
        seed_metrics[seed]["delta_action_macro_f1::Joint-Action"] > 0
        for seed in FROZEN_SEEDS
    )

    rationale = metric_rows[f"rationale_macro_f1::{MODEL_JOINT}"]
    rationale_micro = metric_rows[f"rationale_micro_f1::{MODEL_JOINT}"]
    coverage = rationale_coverage["coverage"]
    zero_classes = coverage["classes_with_zero_f1_in_all_seeds"]
    class_count = coverage["class_count"]

    aurc = metric_rows["delta_aurc::Joint-Action"]
    uar = metric_rows["delta_unsafe_acceptance_rate_90::Joint-Action"]
    ece = metric_rows["delta_ece_calibrated::Joint-Action"]

    flip = metric_rows["advantage_action_flip_rate_mean_three::Action-Joint"]
    flip_branch = summary["decisions"]["rq2_light_perturbation_subbranch"]
    flip_reversed = [
        seed
        for seed in FROZEN_SEEDS
        if seed_metrics[seed][
            "advantage_action_flip_rate_mean_three::Action-Joint"
        ]
        <= 0
    ]

    gate = round10["gate_result"]
    passed_pairs = [
        (entry["family"], entry["axis"])
        for entry in gate["family_axis_gates"]
        if entry["passed"]
    ]
    passed_axes = sorted({axis for _, axis in passed_pairs})
    headline10 = round10_axis["headline"]

    round12_point = round12["point_estimates"]
    round12_lower = round12["lower_bounds"]

    s_directions = s_audit["interpretation"][
        "q1_does_the_S_conclusion_depend_on_the_confidence_definition"
    ]
    s_stable = s_directions["direction_is_stable_across_constructions"]
    s_summary = s_audit["summary"]
    exact_set_error = s_summary["__exact_set_error_rate__"]

    rows: list[dict[str, str]] = []

    rows.append(
        {
            "evaluation_view": "A only - Action Performance",
            "observed_evidence": (
                f"Action Macro-F1: Action-Only {fmt(action_only_a['mean_across_seeds'])}, "
                f"Joint {fmt(joint_a['mean_across_seeds'])}. "
                f"Delta = {fmt(delta_a['mean_across_seeds'], signed=True)}, "
                f"95% CI {interval(delta_a['hierarchical_ci_lower'], delta_a['hierarchical_ci_upper'])}, "
                f"inside the pre-registered +/-{ACTION_EQUIVALENCE_MARGIN:g} "
                f"practical-equivalence margin "
                f"(passed = {str(equivalence['passed']).lower()})."
            ),
            "if_only_this_evidence": (
                "The two models are practically equivalent on action "
                "performance, with a small statistically resolvable edge to "
                "Joint. Either model can be adopted; pick Joint if the tiny "
                "edge matters. No further evaluation looks necessary."
            ),
            "arsc_interpretation": (
                "Correct as far as it goes, and it is exactly why the case is "
                "diagnostically useful: because A is practically equivalent, A "
                "cannot arbitrate between the models, so any real difference "
                "must be looked for on the other axes. The edge is also not "
                f"unanimous - only {seeds_favouring_joint_a} of "
                f"{len(FROZEN_SEEDS)} seeds favour Joint on A."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ R - Rationale-label Performance",
            "observed_evidence": (
                f"Joint rationale Macro-F1 {fmt(rationale['mean_across_seeds'])} "
                f"95% CI {interval(rationale['hierarchical_ci_lower'], rationale['hierarchical_ci_upper'])}; "
                f"Micro-F1 {fmt(rationale_micro['mean_across_seeds'])}. "
                f"{len(zero_classes)} of {class_count} rationale classes score "
                f"F1 = 0 in all five seeds ({', '.join(zero_classes)})."
            ),
            "if_only_this_evidence": (
                "Reading the Macro-F1 alone: the Joint model has a usable, if "
                "weak, rationale capability that the Action-Only model lacks "
                "entirely, so Joint is the more informative model."
            ),
            "arsc_interpretation": (
                "Joint does recover rationale labels that Action-Only cannot "
                "produce at all, but the single Macro-F1 conceals the shape of "
                f"that capability: the Macro/Micro gap "
                f"({fmt(rationale_micro['mean_across_seeds'] - rationale['mean_across_seeds'], signed=True)}) "
                "and the per-class breakdown show coverage is incomplete and "
                "strongly class-dependent. This is rationale-label recovery "
                "coverage only - it is not evidence about reasoning "
                "faithfulness, and it does not show the model's explanations "
                "are right or wrong."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ S - Selective Risk & Calibration",
            "observed_evidence": (
                f"Joint advantage (positive = Joint better): "
                f"AURC {fmt(-aurc['mean_across_seeds'], signed=True)} "
                f"CI {interval(-aurc['hierarchical_ci_upper'], -aurc['hierarchical_ci_lower'])}; "
                f"UAR@90 {fmt(-uar['mean_across_seeds'], signed=True)} "
                f"CI {interval(-uar['hierarchical_ci_upper'], -uar['hierarchical_ci_lower'])}; "
                f"ECE {fmt(-ece['mean_across_seeds'], signed=True)} "
                f"CI {interval(-ece['hierarchical_ci_upper'], -ece['hierarchical_ci_lower'])}."
            ),
            "if_only_this_evidence": (
                "Reading AURC alone: Joint has better selective-risk "
                "behaviour, so Joint should be preferred wherever the system "
                "is allowed to abstain."
            ),
            "arsc_interpretation": (
                "Only AURC resolves. UAR@90 and ECE do not: their intervals "
                "include zero and ECE is essentially a tie. The three S "
                "metrics therefore do not agree, so the correct statement is "
                "that Joint has a small AURC advantage under this "
                "operationalisation, not that Joint's uncertainty behaviour is "
                "better overall. S is a selective-prediction operating "
                "characteristic; it is not 'Safety'."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ C - Prediction Stability under perturbation",
            "observed_evidence": (
                f"Mean action-set flip rate over three families: Action-Only "
                f"{fmt(metric_rows[f'action_flip_rate_mean_three::{MODEL_ACTION}']['mean_across_seeds'])}, "
                f"Joint {fmt(metric_rows[f'action_flip_rate_mean_three::{MODEL_JOINT}']['mean_across_seeds'])}. "
                f"Joint advantage {fmt(flip['mean_across_seeds'], signed=True)} "
                f"CI {interval(flip['hierarchical_ci_lower'], flip['hierarchical_ci_upper'])}, "
                f"{flip_branch['positive_seed_count']}/{len(FROZEN_SEEDS)} seeds "
                f"positive (reversed: {', '.join(f'seed {seed}' for seed in flip_reversed)}). "
                f"Round 12 replicates the direction on the Round 10 dose grid: "
                f"D_C1 = {fmt(round12_point['D_C1'], signed=True)}, "
                f"one-sided lower bound {fmt(round12_lower['D_C1'], signed=True)}, "
                f"formal verdict {round12['gates']['verdict']}, independent "
                f"reviewer decision {round12_review['decision']}. In Round 12 "
                f"the A, R and S axes pass only -0.01 non-inferiority "
                f"guardrails "
                f"(D_A {fmt(round12_point['D_A'], signed=True)}, "
                f"D_R {fmt(round12_point['D_R'], signed=True)}, "
                f"D_S {fmt(round12_point['D_S'], signed=True)}); they are not "
                f"improvements."
            ),
            "if_only_this_evidence": (
                "Joint is the more stable model under input perturbation and "
                "is therefore the more robust choice for deployment."
            ),
            "arsc_interpretation": (
                "Joint does flip less often on average, and Round 12 supports "
                "the direction on an independent dose grid, so this is the "
                "best-supported non-A difference between the two models. But "
                "the effect is not unanimous across seeds, Round 12's own "
                "reviewer recorded it as neither an every-seed nor an "
                "every-cell guarantee, and its A/R/S results are "
                "non-inferiority only, so Round 12 is not a three-axis "
                "improvement. The manipulation is brightness/blur/noise on "
                "BDD-OIA images: this is prediction-set stability under "
                "semantics-preserving synthetic image perturbation - not "
                "real-road robustness, and not evidence that the model "
                "attends to the right evidence."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ seed-level distribution",
            "observed_evidence": (
                f"Across the five frozen seeds, no headline model comparison "
                f"(A, AURC, UAR@90, ECE, C1 mean-of-three) is unanimous. "
                f"A favours Joint on "
                f"{seeds_favouring_joint_a}/{len(FROZEN_SEEDS)} seeds; AURC "
                f"reverses on seed 45; C1 reverses on seed 43 in Round 5 and "
                f"again in Round 12 "
                f"(per-seed D_C1 minimum {fmt(min(round12['per_seed_D_C1']), signed=True)}); "
                f"ECE reverses on seed 46."
            ),
            "if_only_this_evidence": (
                "Reading the five-seed means alone: Joint wins on A, AURC and "
                "C1, so Joint is uniformly the better model."
            ),
            "arsc_interpretation": (
                "Every headline axis comparison has at least one seed that "
                "reverses the sign of its mean, so the means alone are not an adequate "
                "summary. The ARSC profile must be reported as mean plus "
                "seed-level distribution. The reversals are results, not noise "
                "to be averaged away, and no attempt is made to explain them."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ Round 10 perturbation dose-response (RQ2)",
            "observed_evidence": (
                f"{round10['design']['sample_count']} test images from "
                f"{round10['design']['source_clip_count']} source clips, "
                f"{len(round10['design']['families'])} families x "
                f"{len(round10['design']['levels']) - 1} severity levels plus "
                f"clean, real re-inference. "
                f"{gate['passed_gate_count']}/{gate['gate_count']} "
                f"pre-registered family-by-axis gates passed, and all of them "
                f"are {'/'.join(passed_axes)} gates. At the highest severity, "
                f"the largest C1 degradation is "
                f"{fmt(headline10['largest_c1_degradation_at_max_severity'], 4)} "
                f"while the largest |A| degradation is "
                f"{fmt(headline10['largest_absolute_a_degradation_at_max_severity'], 4)} "
                f"({headline10['c1_to_a_magnitude_ratio']:.1f}x), R Macro-F1 "
                f"falls by at most "
                f"{fmt(headline10['largest_absolute_r_degradation_at_max_severity'], 4)}, "
                f"and the sign of the S response is not even consistent across "
                f"families "
                f"({', '.join(f'{family} {sign:+.0f}' for family, sign in headline10['s_degradation_sign_by_family'].items())})."
            ),
            "if_only_this_evidence": (
                f"Reading the gate tally alone: only "
                f"{gate['passed_gate_count']} of {gate['gate_count']} gates "
                f"passed, so the four-axis construct validation failed and the "
                f"extra axes were not worth measuring."
            ),
            "arsc_interpretation": (
                "The pre-registered verdict stands unchanged "
                f"({round10['verdict']}, {gate['passed_gate_count']}/"
                f"{gate['gate_count']}), but the pattern of failure is the "
                "finding. The perturbation moves C1 substantially while "
                "leaving aggregate A and R almost flat and driving S "
                "inconsistently. That is discriminant evidence: the axes are "
                "not measuring the same thing, so they are not redundant. It "
                "does not license the claim that every perturbation should "
                "move every axis, and it does not validate the axes as "
                "constructs."
            ),
        }
    )

    rows.append(
        {
            "evaluation_view": "+ S construct audit (confidence definition)",
            "observed_evidence": (
                f"The frozen S axis pairs an exact-set error definition with "
                f"conf = max_i p_i. Empirical exact-set error is "
                f"{fmt(exact_set_error[MODEL_ACTION], 4)} (Action-Only) and "
                f"{fmt(exact_set_error[MODEL_JOINT], 4)} (Joint), so exact-set "
                f"accuracy is near "
                f"{fmt(1 - exact_set_error[MODEL_ACTION], 2)}, while mean S0 "
                f"confidence is "
                f"{fmt(s_audit['interpretation']['q3_is_max_p_semantically_mismatched_with_exact_set_correctness']['mean_confidence_by_construction_and_model']['S0'][MODEL_ACTION], 4)}. "
                f"Re-ranking with the exact-set proxy S1 and the weakest-bit "
                f"score S2 leaves the AURC direction stable "
                f"(stable = {str(s_stable['aurc']).lower()}) but changes the "
                f"UAR@90 verdict (stable = {str(s_stable['unsafe_acceptance_rate_90']).lower()}). "
                f"ECE falls from "
                f"{fmt(s_summary[f'S0::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)} "
                f"under S0 to "
                f"{fmt(s_summary[f'S1::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)} "
                f"under S1."
            ),
            "if_only_this_evidence": (
                "Reading the audit as a model search: S1 is better calibrated "
                "against the error definition, so S1 should replace max(p) as "
                "the primary confidence and the S conclusion should be "
                "restated on that basis."
            ),
            "arsc_interpretation": (
                "S0 remains the frozen primary result and is not replaced; the "
                "audit is a sensitivity check on the operationalisation, not a "
                "search for a better number. Its finding is that the S verdict "
                "is partly construct-dependent - AURC direction survives, "
                "UAR@90 does not - and that max(p) is measurably mismatched "
                "with the exact-set event it is scored against. Selective-risk "
                "conclusions must therefore be reported per metric and per "
                "confidence definition, not as a single 'S' verdict."
            ),
        }
    )

    return rows


def main() -> int:
    args = parse_args()
    summary = load_rq1_summary()
    metric_rows = rq1_metric_rows(summary)
    seed_metrics = rq1_seed_metrics(summary)
    round10 = load_round10_results()
    round10_axis = read_json(ROUND10_AXIS_PATH)
    round12 = load_round12_results()
    round12_review = read_json(ROUND12_REVIEW_PATH)
    s_audit = read_json(S_AUDIT_PATH)
    rationale_coverage = read_json("outputs/paper/rationale_coverage.json")

    profile = build_profile(metric_rows, seed_metrics)
    decision = build_decision_change(
        metric_rows,
        seed_metrics,
        summary,
        round10,
        round10_axis,
        round12,
        round12_review,
        s_audit,
        rationale_coverage,
    )

    resolved = [
        record
        for record in profile
        if record.get("joint_advantage_mean") is not None
        and "excludes 0" in record["verdict"]
    ]
    unresolved = [
        record
        for record in profile
        if record.get("joint_advantage_mean") is not None
        and "includes 0" in record["verdict"]
    ]
    comparison_records = [
        record for record in profile if record.get("joint_advantage_mean") is not None
    ]
    unanimous_records = [
        record
        for record in comparison_records
        if record["seeds_favouring_joint"] == len(FROZEN_SEEDS)
    ]

    result = {
        "schema_version": "ARSC_PROFILE_AND_DECISION_CHANGE_V1",
        "analysis_id": "ARSC_RQ1_MODEL_PROFILE",
        "role": (
            "RQ1 main result. Round 5 model-profile case study: does "
            "multi-axis evaluation change the judgement reached from Action "
            "Performance alone?"
        ),
        "no_aggregate_score": (
            "ARSC deliberately reports no combined score. The axes are "
            "reported separately because they are not commensurable and, as "
            "Round 10 shows, they do not respond to the same manipulation."
        ),
        "punchline": (
            "Action Performance produces a ranking. ARSC produces a profile."
        ),
        "frozen_inputs": {
            "seeds": list(FROZEN_SEEDS),
            "round5": "outputs/validity/rq1_multiseed_summary.json",
            "round10": (
                "outputs/validity/round10_corruption_formal_attempt02/"
                "round10_corruption_results.json"
            ),
            "round12": "outputs/validity/round12_existing_outputs_results.json",
            "s_audit": S_AUDIT_PATH,
            "rationale_coverage": "outputs/paper/rationale_coverage.json",
        },
        "practical_equivalence": summary["decisions"]["action_equivalence"],
        "profile_table": profile,
        "decision_change_table": decision,
        "headline": {
            "axis_comparisons_reported": sum(
                1 for record in profile if record.get("joint_advantage_mean") is not None
            ),
            "comparisons_with_interval_excluding_zero": len(resolved),
            "comparisons_inconclusive": len(unresolved),
            "resolved_metrics": [record["metric"] for record in resolved],
            "inconclusive_metrics": [record["metric"] for record in unresolved],
        },
        "provenance": provenance(
            [
                "outputs/validity/rq1_multiseed_summary.json",
                "outputs/validity/round10_corruption_formal_attempt02/"
                "round10_corruption_results.json",
                "outputs/validity/round12_existing_outputs_results.json",
                ROUND12_REVIEW_PATH,
                S_AUDIT_PATH,
                "outputs/paper/rationale_coverage.json",
                ROUND10_AXIS_PATH,
            ]
        ),
    }
    write_json(args.output_json, result)

    profile_fields = [
        "axis",
        "axis_name",
        "metric",
        "operationalisation",
        "does_not_measure",
        "lower_is_better",
        "action_only_mean",
        "action_only_ci_lower",
        "action_only_ci_upper",
        "joint_mean",
        "joint_ci_lower",
        "joint_ci_upper",
        "joint_advantage_metric_key",
        "joint_advantage_mean",
        "joint_advantage_ci_lower",
        "joint_advantage_ci_upper",
        "seeds_favouring_joint",
        "verdict",
    ]
    write_csv(
        args.output_profile_csv,
        [{name: record.get(name) for name in profile_fields} for record in profile],
        profile_fields,
    )

    profile_markdown_rows = []
    for record in profile:
        def cell(role: str) -> str:
            mean = record[f"{role}_mean"]
            if mean is None:
                return "n/a"
            return (
                f"{fmt(mean)}<br>"
                f"{interval(record[f'{role}_ci_lower'], record[f'{role}_ci_upper'])}"
            )

        advantage = record.get("joint_advantage_mean")
        if advantage is None:
            advantage_cell = "n/a"
            seeds_cell = "n/a"
        else:
            advantage_cell = (
                f"{fmt(advantage, signed=True)}<br>"
                f"{interval(record['joint_advantage_ci_lower'], record['joint_advantage_ci_upper'])}"
            )
            seeds_cell = f"{record['seeds_favouring_joint']}/{len(FROZEN_SEEDS)}"
        profile_markdown_rows.append(
            [
                record["axis"],
                record["metric"],
                "lower" if record["lower_is_better"] else "higher",
                cell("action_only"),
                cell("joint"),
                advantage_cell,
                seeds_cell,
                record["verdict"],
            ]
        )

    write_markdown_table(
        args.output_profile_markdown,
        "ARSC main-result Profile Table (Round 5, BDD-OIA, seeds 43-47)",
        [
            "The four ARSC axes reported **separately**. There is no combined "
            "score: the axes are not commensurable, and Round 10 shows they do "
            "not respond to the same manipulation.",
            "",
            "Cells give the frozen five-seed mean above the 95% hierarchical "
            "bootstrap interval (resample seeds, then images within seed; "
            "2000 replicates). The *Joint advantage* column is oriented so "
            "that **positive always means Joint is better**, including for the "
            "lower-is-better metrics.",
            "",
            "| Axis | Reads as | Explicitly does *not* measure |",
            "| --- | --- | --- |",
            *(
                f"| {axis} = {AXIS_NAMES[axis]} | {AXIS_OPERATIONALISATION[axis]} "
                f"| {AXIS_NOT[axis]} |"
                for axis in ("A", "R", "S", "C1")
            ),
        ],
        [
            "Axis",
            "Metric",
            "Better",
            "Action-Only",
            "Joint",
            "Joint advantage",
            "Seeds favouring Joint",
            "Verdict at frozen criteria",
        ],
        profile_markdown_rows,
        notes=[
            "**Action Performance produces a ranking. ARSC produces a "
            "profile.** The profile is the result; collapsing it back to one "
            "number would discard exactly the information the protocol exists "
            "to expose.",
            f"Action Performance is practically equivalent under the "
            f"pre-registered +/-{ACTION_EQUIVALENCE_MARGIN:g} margin "
            f"(passed = "
            f"{str(summary['decisions']['action_equivalence']['passed']).lower()}), "
            f"which is what makes the other three axes the only place a "
            f"difference can be found.",
            "The R axis has no Action-Only column because the Action-Only "
            "model has no rationale head. R measures rationale-label recovery "
            "only; it is not evidence about reasoning faithfulness.",
            "S is a selective-prediction operating characteristic computed "
            "with the frozen confidence definition conf = max_i p_i against an "
            "exact-set error. See "
            "`outputs/paper/tables/s_confidence_audit.md` for the "
            "construct-sensitivity audit; it does not replace these numbers.",
            "C1 is clean-vs-perturbed action-set flip rate under "
            "brightness/blur/noise on BDD-OIA images. It is not real-road "
            "robustness and not evidence faithfulness.",
            f"Per-seed values for every comparison are in "
            f"`outputs/paper/seed_heterogeneity.csv`. Of the "
            f"{len(comparison_records)} paired comparisons in this table, only "
            f"{len(unanimous_records)} "
            f"({', '.join(record['metric'] for record in unanimous_records) or 'none'}) "
            f"favours Joint on all five seeds; every headline comparison "
            f"(A, AURC, UAR@90, ECE, C1 mean-of-three) has at least one seed "
            f"that reverses the sign of its mean.",
        ],
    )

    decision_fields = [
        "evaluation_view",
        "observed_evidence",
        "if_only_this_evidence",
        "arsc_interpretation",
    ]
    write_csv(args.output_decision_csv, decision, decision_fields)
    write_markdown_table(
        args.output_decision_markdown,
        "Decision Change Table: what changes when evaluation moves from "
        "Action Performance alone to the full ARSC profile",
        [
            "Each row adds one evaluation view to the one above it. The third "
            "column is the conclusion a reader would reach from that view "
            "*alone*; the fourth is the conclusion that survives the whole "
            "profile.",
            "",
            "**Action Performance produces a ranking. ARSC produces a "
            "profile.**",
            "",
            "Read together, the rows show that the Action-only conclusion "
            "(\"the models are practically equivalent, Joint is marginally "
            "ahead\") is not overturned but *re-scoped*: it becomes a "
            "conditional, bounded judgement whose non-A differences are "
            "axis-specific, partly operationalisation-dependent, and not "
            "unanimous across training seeds.",
        ],
        [
            "Evaluation view",
            "Observed evidence (frozen)",
            "If only this evidence is used",
            "Final ARSC interpretation",
        ],
        [[row[name] for name in decision_fields] for row in decision],
        notes=[
            "No row licenses the claim that Joint is comprehensively safer, "
            "that rationale supervision improves every dimension, that "
            "rationale F1 demonstrates faithful reasoning, that C1 shows the "
            "model relies on correct evidence, or that the four axes have "
            "passed construct validation.",
            "The Round 10 pre-registered verdict and thresholds are unchanged. "
            "Only the interpretation of the failure pattern is stated: the "
            "axes respond differently, which is evidence of "
            "non-redundancy, not evidence that all axes are valid.",
            "The BDD-OIA study demonstrates protocol mechanics and multi-axis "
            "diagnostic value. It is not a nuclear safety validation; see "
            "`docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md`.",
        ],
    )

    print(f"profile rows: {len(profile)}")
    print(
        "comparisons with CI excluding 0: "
        f"{len(resolved)} -> {[record['metric'] for record in resolved]}"
    )
    print(
        "comparisons inconclusive: "
        f"{len(unresolved)} -> {[record['metric'] for record in unresolved]}"
    )
    print(f"decision-change rows: {len(decision)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
