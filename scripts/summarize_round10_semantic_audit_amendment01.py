"""Strictly validate and summarize the repaired Round 10 semantic audit."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.round10_protocol_validation import (
    expected_sample_indices,
    semantic_key_sha256,
    validate_label_sidecar,
    validate_page_hash_binding,
    validate_review_decision,
    validate_semantic_raw_rows,
)


AUDIT_DIR = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round10_corruption_semantic_audit_amendment01"
)
BUILD_PATH = AUDIT_DIR / "build_summary.json"
RAW_PATH = AUDIT_DIR / "raw_manifest.csv"
SIDECAR_PATH = AUDIT_DIR / "label_sidecar.jsonl"
DECISION_PATH = AUDIT_DIR / "review_decision.json"
REVIEWED_PATH = AUDIT_DIR / "reviewed_manifest.csv"
SUMMARY_PATH = AUDIT_DIR / "audit_summary.json"
TEST_MANIFEST = PROJECT_ROOT / "data" / "processed" / "test.jsonl"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return rows, fieldnames


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> int:
    for path in (REVIEWED_PATH, SUMMARY_PATH):
        require(not path.exists(), f"review output already exists: {path}")
    build = read_json(BUILD_PATH)
    decision = read_json(DECISION_PATH)
    require(
        build["status"]
        == "AWAITING_LABEL_VISIBLE_MODEL_OUTPUT_BLIND_REVIEW",
        "unexpected semantic build status",
    )
    require(
        build["outcomes_read_or_computed"] is False,
        "semantic build was not outcome blind",
    )
    require(
        build["technical_gate"]["passed"] is True,
        "technical semantic gate failed",
    )
    require(
        sha256_file(RAW_PATH) == build["raw_manifest_sha256"],
        "raw manifest hash differs",
    )
    require(
        sha256_file(SIDECAR_PATH) == build["label_sidecar_sha256"],
        "label sidecar hash differs",
    )
    expected_page_map = build["labelled_page_sha256"]
    actual_page_map = {
        path_text: sha256_file(PROJECT_ROOT / path_text)
        for path_text in expected_page_map
    }
    validate_page_hash_binding(
        expected_page_map,
        decision["reviewed_page_sha256"],
        actual_page_map,
    )

    records = read_jsonl(TEST_MANIFEST)
    indices = expected_sample_indices(len(records))
    require(
        indices.tolist() == build["selected_dataset_indices"],
        "recomputed semantic sample differs",
    )
    selected = [records[int(index)] for index in indices]
    raw_rows, fieldnames = read_csv(RAW_PATH)
    valid_keys = validate_semantic_raw_rows(
        raw_rows,
        indices.tolist(),
        selected,
    )
    require(
        semantic_key_sha256(valid_keys) == build["row_key_sha256"],
        "semantic row-key hash differs",
    )
    sidecar = read_jsonl(SIDECAR_PATH)
    validate_label_sidecar(sidecar, indices.tolist(), selected)
    expected_bindings = {
        "raw_manifest_sha256": build["raw_manifest_sha256"],
        "label_sidecar_sha256": build["label_sidecar_sha256"],
        "row_key_sha256": build["row_key_sha256"],
        "selected_indices_array_sha256": (
            build["selected_indices_array_sha256"]
        ),
        "labelled_page_map_sha256": build[
            "labelled_page_map_sha256"
        ],
        "build_summary_sha256": sha256_file(BUILD_PATH),
    }
    overrides = validate_review_decision(
        decision,
        valid_keys,
        expected_bindings,
    )
    defaults = decision["default_decisions"]

    reviewed_rows = []
    by_stratum: dict[
        tuple[str, int],
        list[tuple[bool, bool]],
    ] = defaultdict(list)
    for row, key in zip(raw_rows, valid_keys):
        override = overrides.get(key)
        labels = (
            override[
                "action_and_rationale_labels_still_applicable"
            ]
            if override is not None
            else defaults[
                "action_and_rationale_labels_still_applicable"
            ]
        )
        scene = (
            override["scene_semantics_preserved"]
            if override is not None
            else defaults["scene_semantics_preserved"]
        )
        notes = (
            override["review_notes"] if override is not None else ""
        )
        output_row = dict(row)
        output_row[
            "action_and_rationale_labels_still_applicable"
        ] = "true" if labels else "false"
        output_row["scene_semantics_preserved"] = (
            "true" if scene else "false"
        )
        output_row["review_notes"] = notes
        reviewed_rows.append(output_row)
        by_stratum[(row["family"], int(row["level"]))].append(
            (labels, scene)
        )

    temp_reviewed = REVIEWED_PATH.with_suffix(".csv.tmp")
    with temp_reviewed.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(reviewed_rows)
    os.replace(temp_reviewed, REVIEWED_PATH)
    require(
        sha256_file(RAW_PATH) == build["raw_manifest_sha256"],
        "raw manifest was modified during transition",
    )

    threshold = 0.95
    strata = {}
    for (family, level), values in sorted(by_stratum.items()):
        require(len(values) == 100, "semantic stratum count differs")
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
    require(len(strata) == 12, "semantic summary needs 12 strata")
    manual_pass = all(item["passed"] for item in strata.values())
    complete_pass = bool(
        manual_pass and build["technical_gate"]["passed"]
    )
    status = (
        "PASS_LABEL_VISIBLE_MODEL_OUTPUT_BLIND_SEMANTIC_GATE"
        if complete_pass
        else "STOP_SEMANTIC_OR_TECHNICAL_GATE"
    )
    summary = {
        "schema_version": (
            "ARSC_ROUND10_SEMANTIC_AUDIT_AMENDMENT01_SUMMARY_V1"
        ),
        "status": status,
        "outcomes_read_or_computed": False,
        "reviewer": decision["reviewer"],
        "review_completed_at_utc": decision[
            "review_completed_at_utc"
        ],
        "reviewed_unique_images": 100,
        "reviewed_pairs": 1200,
        "reviewed_decisions": 2400,
        "labels_displayed_for_every_pair": True,
        "all_1200_pairs_attested_reviewed": decision[
            "reviewed_all_1200_pairs_with_displayed_labels"
        ],
        "strata": strata,
        "manual_gate_passed": manual_pass,
        "technical_gate": build["technical_gate"],
        "immutable_transition": {
            "raw_manifest": str(
                RAW_PATH.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
            "raw_manifest_sha256_before": (
                build["raw_manifest_sha256"]
            ),
            "raw_manifest_sha256_after": sha256_file(RAW_PATH),
            "raw_manifest_unchanged": True,
            "reviewed_manifest": str(
                REVIEWED_PATH.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
            "reviewed_manifest_sha256": sha256_file(REVIEWED_PATH),
            "row_key_sha256": build["row_key_sha256"],
            "label_sidecar": str(
                SIDECAR_PATH.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
            "label_sidecar_sha256": build[
                "label_sidecar_sha256"
            ],
        },
        "review_decision": str(
            DECISION_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "review_decision_sha256": sha256_file(DECISION_PATH),
        "build_summary_sha256": sha256_file(BUILD_PATH),
        "page_hash_bindings_verified": len(expected_page_map),
        "complete_grid_passed": complete_pass,
        "failure_rule": (
            "Any failed stratum stops the complete Round 10 grid; "
            "no family or level replacement is permitted."
        ),
    }
    temp_summary = SUMMARY_PATH.with_suffix(".json.tmp")
    temp_summary.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp_summary, SUMMARY_PATH)
    print(json.dumps(summary, indent=2))
    return 0 if complete_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
