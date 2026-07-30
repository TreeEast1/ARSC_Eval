"""Validate a completed C1 semantic audit CSV and apply the frozen gate."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import write_json


KINDS = ("brightness", "blur", "noise")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=(
            "outputs/validity/perturbation_semantic_audit/"
            "audit_manifest.csv"
        ),
    )
    parser.add_argument(
        "--output",
        default=(
            "outputs/validity/perturbation_semantic_audit/"
            "audit_summary.json"
        ),
    )
    parser.add_argument("--minimum-rate", type=float, default=0.95)
    return parser.parse_args()


def rooted(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_decision(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "unchanged"}:
        return True
    if normalized in {"0", "false", "no", "changed"}:
        return False
    raise ValueError(f"invalid or missing audit decision: {value!r}")


def main() -> int:
    args = parse_args()
    with rooted(args.manifest).open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 100:
        raise ValueError("semantic audit requires at least 100 samples")
    counts = {}
    all_decisions = []
    for kind in KINDS:
        decisions = [
            parse_decision(row[f"{kind}_semantic_unchanged"])
            for row in rows
        ]
        all_decisions.extend(decisions)
        counts[kind] = {
            "unchanged": sum(decisions),
            "reviewed": len(decisions),
            "rate": sum(decisions) / len(decisions),
        }
    overall_rate = sum(all_decisions) / len(all_decisions)
    result = {
        "status": "completed_model_output_blind_visual_review",
        "reviewed_unique_images": len(rows),
        "reviewed_pairs": len(all_decisions),
        "by_perturbation": counts,
        "overall_semantic_unchanged_rate": overall_rate,
        "minimum_rate": args.minimum_rate,
        "gate_passed": bool(
            overall_rate >= args.minimum_rate
            and all(
                value["rate"] >= args.minimum_rate
                for value in counts.values()
            )
        ),
        "notes": sorted(
            {
                row["review_notes"].strip()
                for row in rows
                if row["review_notes"].strip()
            }
        ),
    }
    write_json(rooted(args.output), result)
    print(json.dumps(result, indent=2))
    return 0 if result["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
