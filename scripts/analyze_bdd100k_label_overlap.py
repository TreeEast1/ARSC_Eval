"""Measure BDD-OIA coverage by mirrored official BDD100K validation labels."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import RATIONALE_NAMES
from arsc_eval.data import read_jsonl
from arsc_eval.utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labels",
        default="data/external/bdd100k/validation_samples.json",
    )
    parser.add_argument(
        "--bdd-oia-manifest", default="data/processed/test.jsonl"
    )
    parser.add_argument(
        "--exclude-sample-manifest",
        action="append",
        default=[],
    )
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def light_colors(sample: dict) -> Counter[str]:
    colors: Counter[str] = Counter()
    for detection in sample.get("detections", {}).get("detections", []):
        if detection.get("label") == "traffic light":
            colors[str(detection.get("trafficLightColor", "NA"))] += 1
    return colors


def main() -> int:
    args = parse_args()
    label_path = rooted(args.labels)
    labels = json.loads(label_path.read_text(encoding="utf-8"))
    samples = labels["samples"]
    official = {
        Path(sample["filepath"]).name: sample for sample in samples
    }
    if len(official) != len(samples):
        raise ValueError("duplicate BDD100K validation filenames")

    records = read_jsonl(rooted(args.bdd_oia_manifest))
    excluded_names: set[str] = set()
    exclusion_counts = {}
    for exclusion in args.exclude_sample_manifest:
        exclusion_path = rooted(exclusion)
        names = {
            record["file_name"] for record in read_jsonl(exclusion_path)
        }
        excluded_names.update(names)
        exclusion_counts[str(exclusion_path.relative_to(PROJECT_ROOT))] = len(
            names
        )

    rationale_index = {
        name: index for index, name in enumerate(RATIONALE_NAMES)
    }
    overlap = 0
    single_state = 0
    state_match = Counter()
    state_match_unseen = Counter()
    official_light_images = 0
    official_color_counts: Counter[str] = Counter()
    for record in records:
        sample = official.get(record["file_name"])
        if sample is None:
            continue
        overlap += 1
        colors = light_colors(sample)
        if colors:
            official_light_images += 1
            official_color_counts.update(colors)
        active = [
            rationale
            for rationale in ("red_light", "green_light")
            if record["rationales"][rationale_index[rationale]] == 1
        ]
        if len(active) != 1:
            continue
        single_state += 1
        rationale = active[0]
        target = "R" if rationale == "red_light" else "G"
        if colors[target] > 0:
            state_match[rationale] += 1
            if record["file_name"] not in excluded_names:
                state_match_unseen[rationale] += 1

    summary = {
        "label_source": str(label_path.relative_to(PROJECT_ROOT)),
        "official_validation_samples": len(samples),
        "bdd_oia_manifest": args.bdd_oia_manifest,
        "bdd_oia_records": len(records),
        "filename_overlap": overlap,
        "filename_overlap_rate": overlap / max(len(records), 1),
        "overlap_with_official_traffic_lights": official_light_images,
        "official_traffic_light_color_counts": dict(official_color_counts),
        "overlap_single_red_or_green_rationale": single_state,
        "rationale_with_matching_official_state_box": dict(state_match),
        "rationale_with_matching_official_state_box_unseen_by_any_audit": dict(
            state_match_unseen
        ),
        "excluded_unique_prior_audit_filenames": len(excluded_names),
        "exclusion_manifests": exclusion_counts,
        "candidate_gate": {
            "minimum_total_unseen_state_matched": 100,
            "minimum_each_state_unseen_state_matched": 30,
        },
    }
    unseen_total = sum(state_match_unseen.values())
    summary["candidate_gate"]["observed_total"] = unseen_total
    summary["candidate_gate"]["observed_red"] = state_match_unseen["red_light"]
    summary["candidate_gate"]["observed_green"] = state_match_unseen[
        "green_light"
    ]
    summary["candidate_gate"]["passed"] = (
        unseen_total >= 100
        and state_match_unseen["red_light"] >= 30
        and state_match_unseen["green_light"] >= 30
    )
    output_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "bdd100k_validation_label_overlap.json"
    )
    write_json(output_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
