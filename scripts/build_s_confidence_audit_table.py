"""Render the S confidence-construct audit table from the frozen audit result.

``scripts/run_s_confidence_audit.py`` does the expensive work: it re-derives
AURC, UAR@90 and ECE for three pre-registered confidence constructions and runs
the hierarchical seed-then-image bootstrap.  This script only formats that
frozen JSON into the paper table, so the table can be regenerated without
repeating the bootstrap.

The table's purpose is narrow and must stay narrow.  ``S0`` (``conf = max_i
p_i``) is the frozen primary result and is not replaced.  ``S1`` and ``S2``
exist to answer three questions:

1. Does the Joint vs Action-Only S conclusion depend on the confidence
   definition?
2. Do AURC, UAR@90 and ECE still disagree with each other?
3. Is ``max(p)`` semantically mismatched with the exact-set correctness event
   it is scored against?

If the constructions disagree, the disagreement is reported as the finding.  No
construction is promoted, and no fourth construction is added.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.paper_assets import (
    FROZEN_SEEDS,
    MODEL_ACTION,
    MODEL_JOINT,
    read_json,
    write_markdown_table,
)
from arsc_eval.selective_confidence import (
    CONFIDENCE_FORMULAS,
    CONFIDENCE_IDS,
    CONFIDENCE_LABELS,
    CONFIDENCE_ROLES,
)

METRICS = (
    ("aurc", "AURC", "lower"),
    ("unsafe_acceptance_rate_90", "UAR@90", "lower"),
    ("ece", "ECE", "lower"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", default="outputs/paper/s_confidence_audit.json")
    parser.add_argument(
        "--output-markdown", default="outputs/paper/tables/s_confidence_audit.md"
    )
    return parser.parse_args()


def fmt(value: float, digits: int = 6, signed: bool = False) -> str:
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def interval(record: dict[str, float], digits: int = 6) -> str:
    return (
        f"[{record['hierarchical_ci_lower']:+.{digits}f}, "
        f"{record['hierarchical_ci_upper']:+.{digits}f}]"
    )


def verdict(record: dict[str, float]) -> str:
    """Reading of the paired interval for a lower-is-better S metric.

    The delta is Joint minus Action-Only, so a wholly negative interval means
    Joint has the lower (better) value.
    """

    if record["hierarchical_ci_upper"] < 0.0:
        return "Joint better"
    if record["hierarchical_ci_lower"] > 0.0:
        return "Action-Only better"
    return "inconclusive"


def main() -> int:
    args = parse_args()
    audit = read_json(args.audit_json)
    summary = audit["summary"]
    interpretation = audit["interpretation"]
    reproduction = audit["s0_reproduction_check"]
    exact_set = summary["__exact_set_error_rate__"]
    mismatch = interpretation[
        "q3_is_max_p_semantically_mismatched_with_exact_set_correctness"
    ]
    mean_confidence = mismatch["mean_confidence_by_construction_and_model"]

    rows = []
    for construction in CONFIDENCE_IDS:
        for metric_key, metric_label, _ in METRICS:
            action = summary[f"{construction}::{metric_key}::{MODEL_ACTION}"]
            joint = summary[f"{construction}::{metric_key}::{MODEL_JOINT}"]
            delta = summary[
                f"{construction}::{metric_key}::delta_joint_minus_action"
            ]
            rows.append(
                [
                    construction,
                    CONFIDENCE_ROLES[construction].replace("_", " "),
                    metric_label,
                    f"{fmt(action['mean_across_seeds'])}<br>{interval(action)}",
                    f"{fmt(joint['mean_across_seeds'])}<br>{interval(joint)}",
                    f"{fmt(delta['mean_across_seeds'], signed=True)}<br>{interval(delta)}",
                    verdict(delta),
                ]
            )

    stability = interpretation[
        "q1_does_the_S_conclusion_depend_on_the_confidence_definition"
    ]["direction_is_stable_across_constructions"]
    agreement = interpretation["q2_do_aurc_uar90_and_ece_still_disagree"][
        "all_three_metrics_agree_within_construction"
    ]

    preamble = [
        "**Sensitivity / construct audit of the selective-risk "
        "operationalisation.** This is not a replacement primary result. "
        f"`S0` remains the frozen primary S axis "
        f"({CONFIDENCE_FORMULAS['S0']}) exactly as published in "
        "`outputs/validity/rq1_multiseed_summary.json`.",
        "",
        "Motivation: the frozen S axis scores an *exact-set* error (any of the "
        "four thresholded action bits wrong) using a *single-bit* confidence "
        "(`max_i p_i`). Those two constructs do not match. The audit measures "
        "how much that matters instead of arguing about it.",
        "",
        "Nothing was retrained. The audit reuses the frozen test logits, the "
        f"frozen temperature scaling, threshold 0.5, seeds "
        f"{', '.join(str(seed) for seed in FROZEN_SEEDS)}, and the frozen "
        "hierarchical seed-then-image bootstrap "
        f"({audit['bootstrap']['replicates']} replicates, seed "
        f"{audit['bootstrap']['seed']}). Because the threshold and the "
        "temperature are unchanged, the predicted action set -- and therefore "
        "the exact-set error vector -- is identical across all three "
        "constructions. Only the *ranking* of test images changes.",
        "",
        "| Construction | Formula | Role |",
        "| --- | --- | --- |",
        *(
            f"| `{construction}` {CONFIDENCE_LABELS[construction].split(' ', 1)[1]} "
            f"| `{CONFIDENCE_FORMULAS[construction]}` "
            f"| {CONFIDENCE_ROLES[construction].replace('_', ' ')} |"
            for construction in CONFIDENCE_IDS
        ),
        "",
        f"`S0` reproduces the frozen published values to within "
        f"{reproduction['tolerance']:g} on every checked field "
        f"({len(reproduction['checks'])} checks, all passed = "
        f"{str(reproduction['all_checks_passed']).lower()}), which is what "
        "licenses comparing `S1` and `S2` against it.",
    ]

    write_markdown_table(
        args.output_markdown,
        "S confidence-construct audit (Round 5 test set, seeds 43-47)",
        preamble,
        [
            "Construction",
            "Role",
            "Metric",
            "Action-Only",
            "Joint",
            "Joint - Action-Only",
            "Verdict",
        ],
        rows,
        notes=[
            "All three metrics are lower-is-better, so a wholly negative "
            "`Joint - Action-Only` interval means Joint is better.",
            f"**Q1 - does the S conclusion depend on the confidence "
            f"definition?** "
            f"{interpretation['q1_does_the_S_conclusion_depend_on_the_confidence_definition']['answer'].replace('_', ' ')}. "
            f"The AURC direction is stable across constructions "
            f"(stable = {str(stability['aurc']).lower()}), but the UAR@90 "
            f"verdict is not "
            f"(stable = {str(stability['unsafe_acceptance_rate_90']).lower()}): "
            f"it is inconclusive under S0 and S1 and resolves in Joint's "
            f"favour only under S2. So the S conclusion is partly "
            f"construct-dependent.",
            f"**Q2 - do AURC, UAR@90 and ECE still disagree?** "
            f"{interpretation['q2_do_aurc_uar90_and_ece_still_disagree']['answer'].replace('_', ' ')}. "
            f"The three metrics fail to agree within every construction "
            f"(agreement by construction: "
            f"{', '.join(f'{key} = {str(value).lower()}' for key, value in agreement.items())}). "
            f"Changing the confidence definition does not make the S metrics "
            f"converge, so they must be reported separately.",
            f"**Q3 - is `max(p)` mismatched with exact-set correctness?** Yes, "
            f"measurably. The empirical exact-set error rate is "
            f"{fmt(exact_set[MODEL_ACTION], 4)} for Action-Only and "
            f"{fmt(exact_set[MODEL_JOINT], 4)} for Joint, i.e. exact-set "
            f"accuracy near {fmt(1 - exact_set[MODEL_ACTION], 3)}. Mean S0 "
            f"confidence is {fmt(mean_confidence['S0'][MODEL_ACTION], 4)} -- "
            f"far above that accuracy -- and the resulting S0 ECE is "
            f"{fmt(summary[f'S0::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)}. "
            f"The exact-set proxy S1 has mean confidence "
            f"{fmt(mean_confidence['S1'][MODEL_ACTION], 4)} and ECE "
            f"{fmt(summary[f'S1::ece::{MODEL_ACTION}']['mean_across_seeds'], 4)}. "
            f"`max(p)` is scoring a different event from the one the error "
            f"definition counts.",
            "The constructions disagree and that disagreement is the reported "
            "finding. No further confidence definitions were tried, no "
            "construction was promoted to primary, and no threshold, "
            "temperature, seed or bootstrap setting was changed to reduce the "
            "disagreement.",
            "This audit varies only how test images are *ranked* for selective "
            "prediction. It does not measure safety, and it does not show that "
            "any construction is the correct one.",
        ],
    )
    print(f"wrote {args.output_markdown} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
