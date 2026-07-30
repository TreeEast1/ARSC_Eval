"""Record the completed independent 102-pair masks_v3 audit.

The audit IDs correspond to the deterministic, v2-disjoint sample emitted by
``audit_masks_v2.py`` for ``masks_v3``.  The decisions below were made from
the rendered audit pages without consulting model counterfactual outputs.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import write_json


AUDIT_DIR = PROJECT_ROOT / "outputs" / "validity" / "mask_audit_v3"

# Passing requires a credibly action-inducing instance. For traffic lights,
# the visible state must also agree with the localized red/green rationale.
CRITICAL_PASS_IDS = {
    # bicycle
    1, 2, 3, 5, 6, 7,
    # car
    9, 10, 12, 13, 14, 15, 16, 17, 18, 20,
    # motorcycle
    21, 22,
    # person
    29,
    # traffic light
    33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 48, 49, 50,
    51, 52, 53, 55, 56, 57, 59, 60, 61, 62, 66, 67, 68, 69, 70, 71,
    73, 74, 75, 76, 78, 79, 81, 82, 83, 84, 85, 87, 89, 90, 91, 93,
    94, 95, 96, 97, 98, 99, 100, 101, 102,
}

# Controls in these rows visibly cover another potentially action-relevant
# object or signal head. Border-adjacent but visibly empty controls pass.
CONTROL_FAIL_IDS = {12, 14, 19, 20, 28, 29, 70, 86, 88, 98}


def main() -> int:
    review_path = AUDIT_DIR / "manual_review.csv"
    with review_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 102:
        raise ValueError(f"expected 102 audit rows, found {len(rows)}")

    by_class: dict[str, Counter[str]] = {}
    for row in rows:
        audit_id = int(row["Audit_ID"])
        critical_pass = audit_id in CRITICAL_PASS_IDS
        control_pass = audit_id not in CONTROL_FAIL_IDS
        row["Critical_Binding_Correct"] = "yes" if critical_pass else "no"
        row["Control_Free_Of_Critical_Evidence"] = (
            "yes" if control_pass else "no"
        )
        row["Semantic_Label_Unchanged"] = "yes"
        notes = []
        if not critical_pass:
            if row["Detected_Class"] == "traffic light":
                notes.append(
                    "visible signal state is inconsistent/ambiguous, the "
                    "box is a false detection, or the signal is not "
                    "credibly action-inducing"
                )
            else:
                notes.append(
                    "detected instance is not credibly action-inducing or "
                    "is a false detection"
                )
        if not control_pass:
            notes.append(
                "control contains another potentially action-relevant object"
            )
        row["Notes"] = "; ".join(notes) if notes else "manual audit pass"

        counts = by_class.setdefault(row["Detected_Class"], Counter())
        counts["reviewed"] += 1
        counts["critical_pass"] += int(critical_pass)
        counts["control_fail"] += int(not control_pass)

    columns = list(rows[0])
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    critical_count = len(CRITICAL_PASS_IDS)
    control_fail_count = len(CONTROL_FAIL_IDS)
    critical_rate = critical_count / len(rows)
    control_contamination_rate = control_fail_count / len(rows)
    strata = {}
    for class_name, counts in sorted(by_class.items()):
        reviewed = counts["reviewed"]
        strata[class_name] = {
            "reviewed_pairs": reviewed,
            "critical_binding_correct": counts["critical_pass"],
            "critical_binding_correct_rate": counts["critical_pass"] / reviewed,
            "control_contaminated": counts["control_fail"],
            "control_critical_evidence_contamination_rate": (
                counts["control_fail"] / reviewed
            ),
        }

    summary_path = AUDIT_DIR / "audit_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    critical_threshold = summary["acceptance_thresholds"][
        "critical_binding_correct_rate_minimum"
    ]
    control_threshold = summary["acceptance_thresholds"][
        "control_critical_evidence_contamination_rate_maximum"
    ]
    summary["manual_status"] = "completed_fail"
    summary["manual_results"] = {
        "reviewed_pairs": len(rows),
        "critical_binding_correct": critical_count,
        "critical_binding_correct_rate": critical_rate,
        "control_contaminated": control_fail_count,
        "control_critical_evidence_contamination_rate": (
            control_contamination_rate
        ),
        "semantic_label_unchanged": len(rows),
        "semantic_label_unchanged_rate": 1.0,
        "critical_binding_threshold_passed": (
            critical_rate >= critical_threshold
        ),
        "control_contamination_threshold_passed": (
            control_contamination_rate <= control_threshold
        ),
        "semantic_threshold_passed": True,
        "overall_gate_passed": False,
        "by_detected_class": strata,
    }
    summary["decision"] = (
        "FAIL for causal-faithfulness claims. State-aware filtering improved "
        "traffic-light binding but did not meet the preregistered audit gate; "
        "controls also exceeded the contamination limit."
    )
    write_json(summary_path, summary)

    generation_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v3_generation.json"
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation["audit_status"] = "completed_fail"
    generation["audit_summary"] = str(summary_path.relative_to(PROJECT_ROOT))
    generation["validity_scope"] = (
        "measurement-development diagnostic only; do not use for causal "
        "faithfulness claims"
    )
    write_json(generation_path, generation)
    print(json.dumps(summary["manual_results"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
