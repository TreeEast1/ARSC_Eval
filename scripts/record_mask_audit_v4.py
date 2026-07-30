"""Record the full, model-output-blind audit of 113 confirmatory v4 pairs."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import write_json


AUDIT_DIR = PROJECT_ROOT / "outputs" / "validity" / "mask_audit_v4"

# All seven binding failures are in the red-light stratum: amber/incorrect
# signal state, vertical illuminated signs, or an unidentifiable night blob.
CRITICAL_FAIL_IDS = {25, 27, 32, 37, 41, 82, 90}

# These controls visibly include a road sign or another signal head.
CONTROL_FAIL_IDS = {50, 65, 71, 79, 91, 108}


def main() -> int:
    review_path = AUDIT_DIR / "manual_review.csv"
    with review_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 113:
        raise ValueError(f"expected 113 audit rows, found {len(rows)}")

    strata: dict[str, Counter[str]] = {}
    for row in rows:
        audit_id = int(row["Audit_ID"])
        critical_pass = audit_id not in CRITICAL_FAIL_IDS
        control_pass = audit_id not in CONTROL_FAIL_IDS
        row["Critical_Binding_Correct"] = "yes" if critical_pass else "no"
        row["Control_Free_Of_Critical_Evidence"] = (
            "yes" if control_pass else "no"
        )
        row["Semantic_Label_Unchanged"] = "yes"
        state = (
            "red"
            if row["Localized_Rationales"] == "red_light"
            else "green"
        )
        counts = strata.setdefault(state, Counter())
        counts["reviewed"] += 1
        counts["critical_pass"] += int(critical_pass)
        counts["control_fail"] += int(not control_pass)
        notes = []
        if not critical_pass:
            notes.append(
                "state/binding failure: amber or wrong signal head, "
                "illuminated sign false detection, or unidentifiable red blob"
            )
        if not control_pass:
            notes.append(
                "control contains another signal head or road sign"
            )
        row["Notes"] = "; ".join(notes) if notes else "manual audit pass"

    columns = list(rows[0])
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    critical_pass_count = len(rows) - len(CRITICAL_FAIL_IDS)
    control_fail_count = len(CONTROL_FAIL_IDS)
    by_state = {}
    for state, counts in sorted(strata.items()):
        reviewed = counts["reviewed"]
        by_state[state] = {
            "reviewed_pairs": reviewed,
            "critical_binding_correct": counts["critical_pass"],
            "critical_binding_correct_rate": counts["critical_pass"] / reviewed,
            "control_contaminated": counts["control_fail"],
            "control_critical_evidence_contamination_rate": (
                counts["control_fail"] / reviewed
            ),
            "critical_binding_threshold_passed": (
                counts["critical_pass"] / reviewed >= 0.90
            ),
            "control_contamination_threshold_passed": (
                counts["control_fail"] / reviewed <= 0.05
            ),
        }

    summary_path = AUDIT_DIR / "audit_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    critical_rate = critical_pass_count / len(rows)
    contamination_rate = control_fail_count / len(rows)
    summary["manual_status"] = "completed_fail"
    summary["manual_results"] = {
        "reviewed_pairs": len(rows),
        "population_review_rate": 1.0,
        "model_output_blind": True,
        "critical_binding_correct": critical_pass_count,
        "critical_binding_correct_rate": critical_rate,
        "control_contaminated": control_fail_count,
        "control_critical_evidence_contamination_rate": contamination_rate,
        "semantic_label_unchanged": len(rows),
        "semantic_label_unchanged_rate": 1.0,
        "overall_critical_binding_threshold_passed": critical_rate >= 0.90,
        "overall_control_contamination_threshold_passed": (
            contamination_rate <= 0.05
        ),
        "semantic_threshold_passed": True,
        "by_light_state": by_state,
        "all_state_specific_thresholds_passed": all(
            item["critical_binding_threshold_passed"]
            and item["control_contamination_threshold_passed"]
            for item in by_state.values()
        ),
        "overall_gate_passed": False,
    }
    summary["decision"] = (
        "FAIL confirmatory gate. Overall binding exceeds 90%, but the red "
        "stratum is below 90%; overall controls also slightly exceed 5%. "
        "Do not run confirmatory CEG with v4."
    )
    write_json(summary_path, summary)

    generation_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v4_generation.json"
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation["audit_status"] = "completed_fail"
    generation["audit_summary"] = str(summary_path.relative_to(PROJECT_ROOT))
    generation["confirmatory_population_manifest"] = (
        "data\\processed\\masks_v4\\manifest_confirmatory.jsonl"
    )
    generation["validity_scope"] = (
        "measurement-development only; red-light binding and control "
        "contamination did not pass state-specific confirmatory gates"
    )
    write_json(generation_path, generation)
    print(json.dumps(summary["manual_results"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
