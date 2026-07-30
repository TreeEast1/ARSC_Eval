"""Record the completed 108-pair manual masks_v2 audit.

The audit IDs correspond exactly to the deterministic ordering emitted by
``audit_masks_v2.py``.  This script makes the human decisions reproducible and
updates the audit summary without changing the mask population.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import write_json


AUDIT_DIR = PROJECT_ROOT / "outputs" / "validity" / "mask_audit_v2"

# A pass requires the selected object instance and, for traffic lights, its
# visible state/direction to be credibly consistent with the localized BDD-OIA
# rationale. Merely detecting the generic COCO class is insufficient.
CRITICAL_PASS_IDS = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 18, 19,
    22, 23, 26, 29, 30,
    36, 38,
    41,
    47, 51, 52, 53, 54, 57, 59, 61, 65,
    72, 73, 74, 82, 83, 84, 94, 97, 100,
    101, 102, 106,
}

# These controls contain an obvious undetected object/sign/signal that could
# itself carry decision-relevant evidence. All others were visibly clear at
# the audited resolution.
CONTROL_FAIL_IDS = {5, 19, 35, 53, 85}


def main() -> int:
    review_path = AUDIT_DIR / "manual_review.csv"
    with review_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 108:
        raise ValueError(f"expected 108 audit rows, found {len(rows)}")

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
                    "generic detector box does not reliably match the "
                    "annotated light state/direction"
                )
            else:
                notes.append(
                    "class is visible but the selected instance is not "
                    "credibly action-inducing (or is a false detection)"
                )
        if not control_pass:
            notes.append(
                "control contains an undetected potentially critical object"
            )
        row["Notes"] = "; ".join(notes) if notes else "manual audit pass"

    columns = list(rows[0])
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    critical_rate = len(CRITICAL_PASS_IDS) / len(rows)
    control_contamination_rate = len(CONTROL_FAIL_IDS) / len(rows)
    summary_path = AUDIT_DIR / "audit_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["manual_status"] = "completed_fail"
    summary["manual_results"] = {
        "reviewed_pairs": len(rows),
        "critical_binding_correct": len(CRITICAL_PASS_IDS),
        "critical_binding_correct_rate": critical_rate,
        "control_contaminated": len(CONTROL_FAIL_IDS),
        "control_critical_evidence_contamination_rate": (
            control_contamination_rate
        ),
        "semantic_label_unchanged": len(rows),
        "semantic_label_unchanged_rate": 1.0,
        "critical_binding_threshold_passed": (
            critical_rate
            >= summary["acceptance_thresholds"][
                "critical_binding_correct_rate_minimum"
            ]
        ),
        "control_contamination_threshold_passed": (
            control_contamination_rate
            <= summary["acceptance_thresholds"][
                "control_critical_evidence_contamination_rate_maximum"
            ]
        ),
        "semantic_threshold_passed": True,
        "overall_gate_passed": False,
    }
    summary["decision"] = (
        "FAIL for causal-faithfulness claims. Retain only as a "
        "detector-localized occlusion-sensitivity diagnostic."
    )
    write_json(summary_path, summary)

    generation_path = (
        PROJECT_ROOT / "outputs" / "validity" / "masks_v2_generation.json"
    )
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation["audit_status"] = "completed_fail"
    generation["audit_summary"] = str(summary_path.relative_to(PROJECT_ROOT))
    generation["validity_scope"] = (
        "detector-localized occlusion sensitivity only; generic detections "
        "did not pass rationale/action binding audit"
    )
    write_json(generation_path, generation)
    print(json.dumps(summary["manual_results"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
