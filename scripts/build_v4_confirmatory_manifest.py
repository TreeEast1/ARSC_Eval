"""Freeze the v4 confirmatory population by removing development-audit images."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.data import read_jsonl
from arsc_eval.utils import write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="data/processed/masks_v4/manifest.jsonl",
    )
    parser.add_argument(
        "--output",
        default="data/processed/masks_v4/manifest_confirmatory.jsonl",
    )
    parser.add_argument(
        "--exclude-sample-manifest",
        action="append",
        required=True,
        help="Development audit sample JSONL. Repeat for multiple rounds.",
    )
    return parser.parse_args()


def rooted(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def main() -> int:
    args = parse_args()
    manifest_path = rooted(args.manifest)
    output_path = rooted(args.output)
    records = read_jsonl(manifest_path)
    excluded_names: set[str] = set()
    exclusion_counts = {}
    for exclusion in args.exclude_sample_manifest:
        exclusion_path = rooted(exclusion)
        names = {
            record["file_name"] for record in read_jsonl(exclusion_path)
        }
        exclusion_counts[str(exclusion_path.relative_to(PROJECT_ROOT))] = len(
            names
        )
        excluded_names.update(names)

    retained = [
        record for record in records if record["file_name"] not in excluded_names
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in retained:
            handle.write(
                json.dumps(record, separators=(",", ":")) + "\n"
            )

    removed = len(records) - len(retained)
    summary = {
        "source_manifest": str(manifest_path.relative_to(PROJECT_ROOT)),
        "confirmatory_manifest": str(output_path.relative_to(PROJECT_ROOT)),
        "source_pairs": len(records),
        "excluded_unique_development_audit_file_names": len(excluded_names),
        "removed_source_pairs": removed,
        "confirmatory_pairs": len(retained),
        "exclusion_manifests": exclusion_counts,
        "state_counts": dict(
            Counter(record["light_state"] for record in retained)
        ),
        "freeze_policy": (
            "all filenames shown during v2/v3 measurement-development audits "
            "are excluded before the v4 confirmatory audit and CEG analysis"
        ),
    }
    summary_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "masks_v4_confirmatory_population.json"
    )
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
