"""Apply reviewed page decisions and evaluate the frozen Round 10 gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit"
)
BUILD_PATH = AUDIT_DIR / "build_summary.json"
MANIFEST_PATH = AUDIT_DIR / "audit_manifest.csv"
DECISION_PATH = AUDIT_DIR / "review_decision.json"
SUMMARY_PATH = AUDIT_DIR / "audit_summary.json"


def parse_args() -> argparse.Namespace:
    return argparse.ArgumentParser(description=__doc__).parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parse_args()
    if SUMMARY_PATH.exists():
        raise RuntimeError(f"audit summary already exists: {SUMMARY_PATH}")
    build = read_json(BUILD_PATH)
    decision = read_json(DECISION_PATH)
    expected_pages = {
        item["path"]: item["sha256"] for item in build["pages"]
    }
    if decision["reviewed_page_sha256"] != expected_pages:
        raise RuntimeError("reviewed page hash binding is incomplete or differs")
    if (
        decision["default_decisions"]
        != {
            "action_and_rationale_labels_still_applicable": True,
            "scene_semantics_preserved": True,
        }
    ):
        raise RuntimeError("unexpected default decision schema")
    overrides = {
        (
            int(item["audit_index"]),
            str(item["family"]),
            int(item["level"]),
        ): item
        for item in decision["overrides"]
    }
    with MANIFEST_PATH.open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
        fieldnames = list(rows[0]) if rows else []
    if len(rows) != 1200:
        raise RuntimeError("semantic manifest must contain 1200 rows")
    by_stratum: dict[tuple[str, int], list[tuple[bool, bool]]] = (
        defaultdict(list)
    )
    for row in rows:
        key = (
            int(row["audit_index"]),
            row["family"],
            int(row["level"]),
        )
        item = overrides.get(key, {})
        labels = bool(
            item.get(
                "action_and_rationale_labels_still_applicable",
                True,
            )
        )
        scene = bool(item.get("scene_semantics_preserved", True))
        row[
            "action_and_rationale_labels_still_applicable"
        ] = str(labels).lower()
        row["scene_semantics_preserved"] = str(scene).lower()
        row["review_notes"] = str(item.get("review_notes", ""))
        by_stratum[(row["family"], int(row["level"]))].append(
            (labels, scene)
        )
    with MANIFEST_PATH.open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    threshold = 0.95
    strata = {}
    for (family, level), values in sorted(by_stratum.items()):
        labels_rate = sum(item[0] for item in values) / len(values)
        scene_rate = sum(item[1] for item in values) / len(values)
        joint_rate = sum(
            item[0] and item[1] for item in values
        ) / len(values)
        strata[f"{family}::level{level}"] = {
            "reviewed": len(values),
            "labels_still_applicable_rate": labels_rate,
            "scene_semantics_preserved_rate": scene_rate,
            "joint_pass_rate": joint_rate,
            "passed": bool(
                labels_rate >= threshold
                and scene_rate >= threshold
                and joint_rate >= threshold
            ),
        }
    manual_pass = all(item["passed"] for item in strata.values())
    status = (
        "PASS_MODEL_OUTPUT_BLIND_SEMANTIC_GATE"
        if manual_pass and build["technical_gate"]["passed"]
        else "STOP_SEMANTIC_OR_TECHNICAL_GATE"
    )
    summary = {
        "status": status,
        "outcomes_read_or_computed": False,
        "reviewer": decision["reviewer"],
        "review_completed_at_utc": decision[
            "review_completed_at_utc"
        ],
        "reviewed_unique_images": 100,
        "reviewed_pairs": 1200,
        "reviewed_decisions": 2400,
        "strata": strata,
        "manual_gate_passed": manual_pass,
        "technical_gate": build["technical_gate"],
        "manifest": str(
            MANIFEST_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "review_decision": str(
            DECISION_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "review_decision_sha256": sha256_file(DECISION_PATH),
        "complete_grid_passed": bool(
            manual_pass and build["technical_gate"]["passed"]
        ),
        "failure_rule": (
            "Any failed stratum stops the entire Round 10 grid; "
            "no family or level replacement is permitted."
        ),
    }
    with SUMMARY_PATH.open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps(summary, indent=2))
    return 0 if summary["complete_grid_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
