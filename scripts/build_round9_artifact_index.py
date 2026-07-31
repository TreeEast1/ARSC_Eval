"""Bind the complete Round 9 evidence chain in one SHA-256 index."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_artifact_index.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_results.json"
)
AUDIT_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_multimap_independent_audit.json"
)
REVIEW_PATH = (
    PROJECT_ROOT
    / "outputs"
    / "validity"
    / "round9_postresult_reviewer_decision.json"
)

ARTIFACTS = (
    ("round8_frozen_input", "outputs/validity/round8_graded_response_primitives.npz"),
    ("round9_preregistration", "outputs/validity/round9_multimap_protocol.json"),
    ("preimplementation_review", "outputs/research_review_memo_round9_preimplementation.md"),
    ("outcome_blind_maps", "outputs/validity/round9_multimap_maps.npz"),
    ("map_manifest", "outputs/validity/round9_multimap_map_manifest.json"),
    ("independent_salt_replay_audit", "outputs/validity/round9_multimap_salt_replay_audit.json"),
    ("association_components", "outputs/validity/round9_multimap_components.npz"),
    ("component_manifest", "outputs/validity/round9_multimap_component_manifest.json"),
    ("preoutcome_independent_audit", "outputs/validity/round9_multimap_preoutcome_independent_audit.json"),
    ("preoutcome_run_manifest", "outputs/validity/round9_multimap_preoutcome_run_manifest.json"),
    ("preoutcome_tests_log", "outputs/validity/round9_multimap_preoutcome_tests.log"),
    ("preserved_stop_preflight", "outputs/validity/round9_multimap_formal_preflight_stop01.json"),
    ("preserved_stop_implementation_manifest", "outputs/validity/round9_multimap_formal_implementation_manifest_stop01.json"),
    ("preserved_stop_review", "outputs/research_review_memo_round9_preregister_stop01.md"),
    ("repaired_formal_preflight", "outputs/validity/round9_multimap_formal_preflight.json"),
    ("repaired_implementation_manifest", "outputs/validity/round9_multimap_formal_implementation_manifest.json"),
    ("formal_go_review", "outputs/research_review_memo_round9_preregister.md"),
    ("formal_go_machine_decision", "outputs/validity/round9_independent_reviewer_decision.json"),
    ("formal_analysis", "scripts/analyze_round9_multimap.py"),
    ("formal_statistics", "src/arsc_eval/multimap_statistics.py"),
    ("formal_response_logic", "src/arsc_eval/multimap_response.py"),
    ("formal_statistics_tests", "tests/test_multimap_statistics.py"),
    ("formal_response_tests", "tests/test_multimap_response.py"),
    ("formal_tmux_launcher", "scripts/launch_round9_multimap_tmux.sh"),
    ("formal_results", "outputs/validity/round9_multimap_results.json"),
    ("formal_primitives", "outputs/validity/round9_multimap_primitives.npz"),
    ("formal_bootstrap_draws", "outputs/validity/round9_multimap_bootstrap_draws.npz"),
    ("formal_point_diagnostics", "outputs/validity/round9_multimap_point_diagnostics.csv"),
    ("formal_bootstrap_summary", "outputs/validity/round9_multimap_bootstrap_summary.csv"),
    ("formal_log", "outputs/validity/round9_multimap_formal.log"),
    ("independent_verifier", "scripts/verify_round9_multimap_outputs.py"),
    ("independent_tmux_launcher", "scripts/launch_round9_independent_audit_tmux.sh"),
    ("independent_audit", "outputs/validity/round9_multimap_independent_audit.json"),
    ("independent_bootstrap_draws", "outputs/validity/round9_multimap_independent_bootstrap_draws.npz"),
    ("independent_log", "outputs/validity/round9_multimap_independent_audit.log"),
    ("descriptive_plot_implementation", "scripts/plot_round9_multimap.py"),
    ("descriptive_plot_png", "outputs/validity/round9_multimap_curves.png"),
    ("descriptive_plot_svg", "outputs/validity/round9_multimap_curves.svg"),
    ("postresult_scientific_review", "outputs/research_review_memo_round9_postresult.md"),
    ("postresult_machine_decision", "outputs/validity/round9_postresult_reviewer_decision.json"),
    ("artifact_index_builder", "scripts/build_round9_artifact_index.py"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing artifact index",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    args = parse_args()
    if OUTPUT_PATH.exists() and not args.force:
        raise RuntimeError(
            f"artifact index already exists; pass --force: {OUTPUT_PATH}"
        )
    missing = [
        relative_path
        for _, relative_path in ARTIFACTS
        if not (PROJECT_ROOT / relative_path).is_file()
    ]
    if missing:
        raise RuntimeError(f"required artifacts are missing: {missing}")

    result = load_json(RESULT_PATH)
    audit = load_json(AUDIT_PATH)
    review = load_json(REVIEW_PATH)
    artifacts = [
        {
            "role": role,
            "path": relative_path,
            "sha256": sha256_file(PROJECT_ROOT / relative_path),
            "bytes": (PROJECT_ROOT / relative_path).stat().st_size,
        }
        for role, relative_path in ARTIFACTS
    ]
    payload = {
        "study": "BDD-OIA Round 9 20-map graded-response robustness",
        "round": 9,
        "formal_execution": "COMPLETED_ONE_SHOT_ATTEMPT01",
        "formal_result_sha256": sha256_file(RESULT_PATH),
        "formal_status": result["status"],
        "formal_axis_gates": result["decisions"]["axis_gates"],
        "independent_reproduction": {
            "status": audit["status"],
            "checks": audit["summary"],
            "maximum_point_abs_difference": audit[
                "point_reproduction"
            ]["maximum_abs_difference"],
            "maximum_bootstrap_abs_difference": audit[
                "bootstrap_reproduction"
            ]["maximum_numeric_abs_difference"],
            "formal_and_independent_draw_file_sha256_equal": (
                sha256_file(
                    PROJECT_ROOT
                    / "outputs/validity/round9_multimap_bootstrap_draws.npz"
                )
                == sha256_file(
                    PROJECT_ROOT
                    / "outputs/validity/round9_multimap_independent_bootstrap_draws.npz"
                )
            ),
        },
        "axis_bottlenecks": {
            axis: {
                "grand_mean": summary["grand_mean"],
                "hierarchical_pointwise_95_percent_interval": summary[
                    "bootstrap_interval"
                ],
                "positive_map_count": summary["positive_map_count"],
            }
            for axis, summary in result["axis_summaries"].items()
        },
        "postresult_independent_review": review,
        "artifacts": artifacts,
        "bounded_limitations": result["claim_boundary"][
            "does_not_support"
        ],
        "stopping_rule": (
            "Round 9 terminates the BDD-OIA map/salt realization line; "
            "no additional salt or map iteration is permitted."
        ),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "path": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)).replace(
                    "\\", "/"
                ),
                "sha256": sha256_file(OUTPUT_PATH),
                "artifact_count": len(artifacts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
