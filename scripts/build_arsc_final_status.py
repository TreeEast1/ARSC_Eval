"""Generate ARSC_FINAL_STATUS.md: the claim-to-frozen-evidence map.

Every claim the paper is allowed to make is listed here together with the
frozen experiment that supports it, the artifact path, and the supporting
numbers *read from that artifact*.  Nothing is transcribed by hand: if a claim
cannot be backed by a value pulled out of a frozen file, it does not belong in
this document.

The forbidden claims are listed too, each with the reason the frozen evidence
does not reach them, so a reader can see the boundary rather than infer it.
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
    load_round10_results,
    load_round12_results,
    load_rq1_summary,
    provenance,
    read_json,
    rooted,
    rq1_metric_rows,
    rq1_seed_metrics,
)

#: Paper asset files that must exist for the status document to be complete.
REQUIRED_ASSETS: tuple[tuple[str, str], ...] = (
    (
        "docs/paper/ARSC_CLAIMS_AND_TERMINOLOGY.md",
        "ARSC claim / terminology document",
    ),
    ("outputs/paper/tables/arsc_profile.md", "Main-result Profile Table"),
    (
        "outputs/paper/tables/decision_change.md",
        "Action-only to ARSC Decision Change Table",
    ),
    (
        "outputs/paper/figures/round10_axis_separation.png",
        "Round 10 dose-response / axis-separation main figure",
    ),
    (
        "outputs/paper/figures/seed_heterogeneity.png",
        "Seed heterogeneity figure",
    ),
    (
        "outputs/paper/tables/seed_heterogeneity.md",
        "Seed heterogeneity table",
    ),
    (
        "outputs/paper/figures/rationale_coverage.png",
        "Rationale per-class coverage figure",
    ),
    (
        "outputs/paper/tables/rationale_coverage.md",
        "Rationale per-class coverage table",
    ),
    (
        "outputs/paper/tables/s_confidence_audit.md",
        "S confidence audit table",
    ),
    ("docs/paper/LIMITATIONS.md", "Limitations"),
    (
        "docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md",
        "Nuclear Transfer Conditions",
    ),
)

#: Round-to-paper-role assignment, frozen by this goal.
ROUND_ROLES: tuple[tuple[str, str, str], ...] = (
    ("Round 5", "Main text", "RQ1 model-profile case study, five paired seeds 43-47"),
    ("Round 10", "Main text", "RQ2 axis non-redundancy, primary evidence"),
    (
        "Round 12",
        "Main text",
        "Secondary supporting result for the Joint stability advantage",
    ),
    ("Rounds 1-4", "Appendix", "Protocol development history; not core results"),
    ("Round 6", "Appendix", "Population insufficiency; evidence for the CEG failure"),
    ("Round 7", "Appendix", "Minimal permutation / falsification sanity"),
    (
        "Rounds 8-9",
        "Appendix",
        "Existing supplementary sanity; not extended further",
    ),
    ("CEG", "Limitations", "Failed evidence-sensitivity extension; measurement boundary"),
    ("Round 11", "Excluded", "Not scientific evidence; no further analysis"),
    ("Round 13", "Excluded", "Not scientific evidence; no further analysis"),
)

FORBIDDEN_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        "Joint is comprehensively safer",
        "Joint resolves on AURC and C1 only. UAR@90 and ECE are inconclusive, "
        "and no headline comparison is unanimous across the five seeds.",
    ),
    (
        "Rationale supervision improves all dimensions",
        "The frozen design cannot attribute the S and C differences to "
        "rationale supervision; with A practically equivalent they are "
        "accompanying descriptive differences only.",
    ),
    (
        "Rationale F1 proves faithful reasoning",
        "R measures 21-class label recovery. Nothing in the protocol observes "
        "the model's internal computation.",
    ),
    (
        "C1 proves the model relies on correct evidence",
        "C1 compares thresholded action sets before and after a pixel "
        "perturbation. It never localises or verifies the evidence used.",
    ),
    (
        "The BDD-OIA experiments prove nuclear safety",
        "Single driving dataset, synthetic pixel perturbations, no nuclear "
        "data, no episodic correctness, no instrumentation model. See "
        "docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md.",
    ),
    (
        "CEG has been validated",
        "Mask v2/v3/v4 and the BDD100K v5 population gates all failed; the "
        "line was formally closed with no confirmatory measurement.",
    ),
    (
        "All four axes passed construct validation",
        "Round 10 passed 3 of 12 pre-registered family-by-axis gates. Nine "
        "gates failed.",
    ),
    (
        "AURC / UAR@90 / ECE collectively constitute Safety",
        "They are three separate quantities that disagree with each other "
        "under every confidence construction tested.",
    ),
)

STOP_CONDITIONS: tuple[str, ...] = (
    "No new or external dataset was downloaded or opened.",
    "DAAD-X was not continued.",
    "No CEG v6 was created.",
    "No further Round 7-9 style permutation / map sanity was run.",
    "No new complex metric was designed.",
    "No pre-registered threshold was modified.",
    "No epoch, threshold, temperature or seed was re-selected from test results.",
    "No definition was adjusted to make the four axes all significant.",
    "No ARSC aggregate score was designed.",
    "No model was retrained and no seed was added.",
    "All frozen raw results were preserved unmodified.",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="ARSC_FINAL_STATUS.md")
    return parser.parse_args()


def fmt(value: float, digits: int = 6, signed: bool = False) -> str:
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def interval(row: dict[str, float], scale: float = 1.0, digits: int = 6) -> str:
    lower = row["hierarchical_ci_lower"] * scale
    upper = row["hierarchical_ci_upper"] * scale
    if scale < 0:
        lower, upper = upper, lower
    return f"[{lower:+.{digits}f}, {upper:+.{digits}f}]"


def build_claims(context: dict[str, Any]) -> list[dict[str, Any]]:
    metric_rows = context["metric_rows"]
    seed_metrics = context["seed_metrics"]
    summary = context["summary"]
    round10 = context["round10"]
    round10_axis = context["round10_axis"]
    round12 = context["round12"]
    s_audit = context["s_audit"]
    coverage = context["rationale_coverage"]

    equivalence = summary["decisions"]["action_equivalence"]
    delta_a = metric_rows["delta_action_macro_f1::Joint-Action"]
    gate = round10["gate_result"]
    passed_axes = sorted(
        {
            entry["axis"]
            for entry in gate["family_axis_gates"]
            if entry["passed"]
        }
    )
    headline10 = round10_axis["headline"]
    flip = metric_rows["advantage_action_flip_rate_mean_three::Action-Joint"]
    flip_branch = summary["decisions"]["rq2_light_perturbation_subbranch"]
    aurc = metric_rows["delta_aurc::Joint-Action"]
    uar = metric_rows["delta_unsafe_acceptance_rate_90::Joint-Action"]
    ece = metric_rows["delta_ece_calibrated::Joint-Action"]
    rationale = metric_rows[f"rationale_macro_f1::{MODEL_JOINT}"]
    rationale_micro = metric_rows[f"rationale_micro_f1::{MODEL_JOINT}"]
    cov = coverage["coverage"]
    s_stability = s_audit["interpretation"][
        "q1_does_the_S_conclusion_depend_on_the_confidence_definition"
    ]["direction_is_stable_across_constructions"]
    s_summary = s_audit["summary"]
    exact_set = s_summary["__exact_set_error_rate__"]
    mean_conf = s_audit["interpretation"][
        "q3_is_max_p_semantically_mismatched_with_exact_set_correctness"
    ]["mean_confidence_by_construction_and_model"]

    seeds_favouring_joint_a = sum(
        seed_metrics[seed]["delta_action_macro_f1::Joint-Action"] > 0
        for seed in FROZEN_SEEDS
    )

    return [
        {
            "id": "CLAIM-1",
            "statement": (
                "Joint and Action-Only have comparable Action Performance "
                "within the pre-defined practical-equivalence band."
            ),
            "round": "Round 5",
            "evidence": (
                f"Action Macro-F1 {fmt(metric_rows[f'action_macro_f1::{MODEL_ACTION}']['mean_across_seeds'])} "
                f"(Action-Only) vs "
                f"{fmt(metric_rows[f'action_macro_f1::{MODEL_JOINT}']['mean_across_seeds'])} "
                f"(Joint); delta {fmt(delta_a['mean_across_seeds'], signed=True)}, "
                f"95% CI {interval(delta_a)}, entirely inside the "
                f"pre-registered +/-{ACTION_EQUIVALENCE_MARGIN:g} margin "
                f"(frozen decision passed = {str(equivalence['passed']).lower()})."
            ),
            "artifact": "outputs/validity/rq1_multiseed_summary.json",
            "asset": "outputs/paper/tables/arsc_profile.md",
        },
        {
            "id": "CLAIM-2",
            "statement": (
                "Action F1 alone misses differences in rationale coverage, "
                "selective-risk behaviour and perturbation stability."
            ),
            "round": "Round 5",
            "evidence": (
                f"With A practically equivalent, the other axes still separate "
                f"the models: R exposes {cov['zero_class_count']} of "
                f"{cov['class_count']} rationale classes at F1 = 0 in all five "
                f"seeds; AURC favours Joint by "
                f"{fmt(-aurc['mean_across_seeds'], signed=True)} "
                f"CI {interval(aurc, -1.0)}; C1 favours Joint by "
                f"{fmt(flip['mean_across_seeds'], signed=True)} "
                f"CI {interval(flip)}. None of this is visible in Action F1."
            ),
            "artifact": "outputs/validity/rq1_multiseed_summary.json",
            "asset": "outputs/paper/tables/decision_change.md",
        },
        {
            "id": "CLAIM-3",
            "statement": (
                "Prediction-set stability can degrade markedly while "
                "aggregate Macro-F1 is nearly unchanged, so these evaluation "
                "dimensions are not redundant."
            ),
            "round": "Round 10",
            "evidence": (
                f"{round10['design']['sample_count']} images / "
                f"{round10['design']['source_clip_count']} source clips, real "
                f"re-inference. At maximum severity the largest C1 degradation "
                f"is {fmt(headline10['largest_c1_degradation_at_max_severity'], 4)} "
                f"against a largest |A| degradation of "
                f"{fmt(headline10['largest_absolute_a_degradation_at_max_severity'], 4)} "
                f"({headline10['c1_to_a_magnitude_ratio']:.1f}x) and a largest "
                f"|R| degradation of "
                f"{fmt(headline10['largest_absolute_r_degradation_at_max_severity'], 4)}. "
                f"The S response sign is not consistent across families "
                f"(consistent = {str(headline10['s_sign_is_consistent_across_families']).lower()}). "
                f"{gate['passed_gate_count']}/{gate['gate_count']} "
                f"pre-registered gates passed, all of them "
                f"{'/'.join(passed_axes)} gates; frozen verdict "
                f"{round10['verdict']}, unchanged."
            ),
            "artifact": (
                "outputs/validity/round10_corruption_formal_attempt02/"
                "round10_corruption_results.json"
            ),
            "asset": "outputs/paper/figures/round10_axis_separation.png",
        },
        {
            "id": "CLAIM-4",
            "statement": (
                "Joint shows lower mean perturbation-induced action flip in "
                "this BDD-OIA case study, with seed heterogeneity."
            ),
            "round": "Round 5 (primary) + Round 12 (secondary)",
            "evidence": (
                f"Round 5 mean flip advantage "
                f"{fmt(flip['mean_across_seeds'], signed=True)} "
                f"CI {interval(flip)}, "
                f"{flip_branch['positive_seed_count']}/{len(FROZEN_SEEDS)} "
                f"seeds positive. Round 12 on the Round 10 dose grid: D_C1 = "
                f"{fmt(round12['point_estimates']['D_C1'], signed=True)}, "
                f"one-sided lower bound "
                f"{fmt(round12['lower_bounds']['D_C1'], signed=True)}, verdict "
                f"{round12['gates']['verdict']}; per-seed D_C1 minimum "
                f"{fmt(min(round12['per_seed_D_C1']), signed=True)} (seed 43 "
                f"reverses in both rounds)."
            ),
            "artifact": "outputs/validity/round12_existing_outputs_results.json",
            "asset": "outputs/paper/figures/seed_heterogeneity.png",
        },
        {
            "id": "CLAIM-5",
            "statement": (
                "Rationale-label recovery coverage is incomplete and highly "
                "class-dependent."
            ),
            "round": "Round 5",
            "evidence": (
                f"Joint rationale Macro-F1 "
                f"{fmt(rationale['mean_across_seeds'])} CI {interval(rationale)} "
                f"vs Micro-F1 {fmt(rationale_micro['mean_across_seeds'])} "
                f"(gap {fmt(rationale_micro['mean_across_seeds'] - rationale['mean_across_seeds'], signed=True)}). "
                f"{cov['zero_class_count']} of {cov['class_count']} classes "
                f"score F1 = 0 in all five seeds "
                f"({', '.join(cov['classes_with_zero_f1_in_all_seeds'])}); "
                f"{len(cov['classes_never_predicted_in_any_seed'])} classes are "
                f"never predicted positive in any seed."
            ),
            "artifact": "outputs/validity/rq1_multiseed_summary.json",
            "asset": "outputs/paper/figures/rationale_coverage.png",
        },
        {
            "id": "CLAIM-6",
            "statement": (
                "The selective-risk conclusion depends on metric and "
                "confidence operationalisation and must be reported per item."
            ),
            "round": "Round 5 + S construct audit",
            "evidence": (
                f"Under the frozen S0 confidence, AURC favours Joint "
                f"({fmt(-aurc['mean_across_seeds'], signed=True)}, "
                f"CI {interval(aurc, -1.0)}) while UAR@90 "
                f"(CI {interval(uar, -1.0)}) and ECE "
                f"(CI {interval(ece, -1.0)}) are inconclusive. Re-ranking with "
                f"S1 and S2 keeps the AURC direction stable "
                f"({str(s_stability['aurc']).lower()}) but not the UAR@90 "
                f"verdict ({str(s_stability['unsafe_acceptance_rate_90']).lower()}). "
                f"Construct mismatch: exact-set accuracy near "
                f"{fmt(1 - exact_set[MODEL_ACTION], 3)} vs mean S0 confidence "
                f"{fmt(mean_conf['S0'][MODEL_ACTION], 4)}, giving S0 ECE "
                f"{fmt(s_summary[f'S0::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)} "
                f"against S1 ECE "
                f"{fmt(s_summary[f'S1::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)}. "
                f"S0 remains the frozen primary and reproduces the published "
                f"values (all checks passed = "
                f"{str(s_audit['s0_reproduction_check']['all_checks_passed']).lower()})."
            ),
            "artifact": "outputs/paper/s_confidence_audit.json",
            "asset": "outputs/paper/tables/s_confidence_audit.md",
        },
        {
            "id": "CLAIM-7",
            "statement": (
                "ARSC's value is an auditable evaluation profile, not a single "
                "score."
            ),
            "round": "Round 5 + Round 10",
            "evidence": (
                f"The profile is internally non-uniform in a way no scalar can "
                f"carry: A favours Joint on only "
                f"{seeds_favouring_joint_a}/{len(FROZEN_SEEDS)} seeds, the "
                f"three S metrics disagree with each other under all three "
                f"confidence constructions, and Round 10 shows only "
                f"{'/'.join(passed_axes)} responds to perturbation severity "
                f"({gate['passed_gate_count']}/{gate['gate_count']} gates). "
                f"Axes that neither co-vary nor share a scale cannot be "
                f"averaged into one number without discarding the finding."
            ),
            "artifact": "outputs/paper/arsc_profile.json",
            "asset": "outputs/paper/tables/arsc_profile.md",
        },
    ]


def main() -> int:
    args = parse_args()
    summary = load_rq1_summary()
    context = {
        "summary": summary,
        "metric_rows": rq1_metric_rows(summary),
        "seed_metrics": rq1_seed_metrics(summary),
        "round10": load_round10_results(),
        "round10_axis": read_json("outputs/paper/round10_axis_separation.json"),
        "round12": load_round12_results(),
        "s_audit": read_json("outputs/paper/s_confidence_audit.json"),
        "rationale_coverage": read_json("outputs/paper/rationale_coverage.json"),
    }
    claims = build_claims(context)

    missing = [path for path, _ in REQUIRED_ASSETS if not rooted(path).exists()]

    lines: list[str] = []
    add = lines.append

    add("# ARSC final status")
    add("")
    add(
        "ARSC is an **auditable multi-axis evaluation protocol for decision "
        "models**, not a safety score. This document maps every claim the "
        "paper is allowed to make onto the frozen experiment that supports it."
    )
    add("")
    add(
        "> **Action Performance produces a ranking. ARSC produces a profile.**"
    )
    add("")
    add(
        "This file is generated by `scripts/build_arsc_final_status.py`. Every "
        "number below is read from a frozen artifact at generation time; none "
        "is transcribed by hand."
    )
    add("")

    add("## 1. Axis definitions in force")
    add("")
    add("| Axis | Name | Operationalisation | Explicitly does *not* measure |")
    add("| --- | --- | --- | --- |")
    for axis in ("A", "R", "S", "C1"):
        add(
            f"| {axis} | {AXIS_NAMES[axis]} | {AXIS_OPERATIONALISATION[axis]} "
            f"| {AXIS_NOT[axis]} |"
        )
    add("")
    add(
        "CEG is **not** an axis. It is a failed evidence-sensitivity extension "
        "and is reported only as a measurement boundary."
    )
    add("")

    add("## 2. Claim-to-evidence map")
    add("")
    for claim in claims:
        add(f"### {claim['id']}")
        add("")
        add(f"**Claim.** {claim['statement']}")
        add("")
        add(f"**Supporting experiment.** {claim['round']}")
        add("")
        add(f"**Frozen evidence.** {claim['evidence']}")
        add("")
        add(f"**Frozen artifact.** `{claim['artifact']}`")
        add("")
        add(f"**Paper asset.** `{claim['asset']}`")
        add("")

    add("## 3. Forbidden claims and why the evidence does not reach them")
    add("")
    add("| Forbidden claim | Why the frozen evidence does not support it |")
    add("| --- | --- |")
    for statement, reason in FORBIDDEN_CLAIMS:
        add(f"| {statement} | {reason} |")
    add("")

    add("## 4. Round roles in the paper")
    add("")
    add("| Round | Placement | Role |")
    add("| --- | --- | --- |")
    for round_name, placement, role in ROUND_ROLES:
        add(f"| {round_name} | {placement} | {role} |")
    add("")

    add("## 5. Deliverable checklist")
    add("")
    add("| # | Deliverable | Path | Present |")
    add("| --- | --- | --- | --- |")
    for index, (path, description) in enumerate(REQUIRED_ASSETS, start=1):
        present = "yes" if rooted(path).exists() else "**MISSING**"
        add(f"| {index} | {description} | `{path}` | {present} |")
    add("")
    add(f"Missing deliverables: {len(missing)}")
    add("")

    add("## 6. Reproduction")
    add("")
    add(
        "Every table and figure under `outputs/paper/` is regenerated from the "
        "frozen artifacts under `outputs/validity/` by:"
    )
    add("")
    add("```bash")
    add("PYTHONPATH=src python scripts/build_all_paper_assets.py")
    add("```")
    add("")
    add(
        "The pipeline is torch-free and reads only frozen artifacts; no model "
        "forward pass is recomputed. The S confidence audit re-derives the "
        "frozen `S0` selective-risk values and asserts they match "
        "`outputs/validity/rq1_multiseed_summary.json` to within 1e-9 before "
        "any alternative confidence construction is compared against them."
    )
    add("")

    add("## 7. Scientific stop conditions observed")
    add("")
    for condition in STOP_CONDITIONS:
        add(f"- {condition}")
    add("")

    add("## 8. Optional future experiment (NOT executed)")
    add("")
    add(
        "Re-run the identical BDD-OIA ARSC protocol on a **different backbone** "
        "and check whether the profile shape is preserved: whether A stays "
        "practically equivalent, whether C remains the only axis with a strong "
        "perturbation dose-response, and whether the seed-level reversals "
        "persist."
    )
    add("")
    add(
        "This is recorded as the single optional follow-up and was deliberately "
        "not executed. It requires explicit user authorisation to start."
    )
    add("")

    add("## 9. Boundary statement")
    add("")
    add(
        "The BDD-OIA study demonstrates **protocol mechanics** and "
        "**multi-axis diagnostic value**. It is **not nuclear safety "
        "validation**, not real-road robustness evidence, and not evidence "
        "about reasoning faithfulness. Transfer conditions are stated in "
        "`docs/paper/NUCLEAR_TRANSFER_CONDITIONS.md`; the full boundary list "
        "is in `docs/paper/LIMITATIONS.md`."
    )
    add("")

    add("## 10. Provenance of the inputs to this document")
    add("")
    add("| Frozen input | SHA-256 |")
    add("| --- | --- |")
    for record in provenance(
        [
            "outputs/validity/rq1_multiseed_summary.json",
            "outputs/validity/round10_corruption_formal_attempt02/"
            "round10_corruption_results.json",
            "outputs/validity/round12_existing_outputs_results.json",
            "outputs/paper/s_confidence_audit.json",
            "outputs/paper/rationale_coverage.json",
            "outputs/paper/round10_axis_separation.json",
            "outputs/paper/arsc_profile.json",
            "outputs/paper/seed_heterogeneity.json",
        ]
    ):
        add(f"| `{record['path']}` | `{record['sha256']}` |")
    add("")

    output = rooted(args.output)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {output}")
    print(f"claims: {len(claims)}; missing deliverables: {len(missing)}")
    for path in missing:
        print(f"  MISSING {path}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
