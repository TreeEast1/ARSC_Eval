"""Check required artifacts and README reproduction commands."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import load_config, resolve_paths, write_json


REQUIRED_OUTPUTS = [
    "data_summary.json",
    "clean_metrics.json",
    "rationale_metrics.json",
    "critical_mask_metrics.json",
    "safety_metrics.json",
    "consistency_metrics.json",
    "main_results.csv",
    "per_class_results.csv",
    "training_log_action_only.csv",
    "training_log_joint.csv",
    "experiment_summary.md",
]

MAIN_COLUMNS = [
    "Model",
    "Action_Macro_F1",
    "Rationale_Macro_F1",
    "Causal_Evidence_Gap",
    "AURC",
    "Unsafe_Acceptance_Rate_90",
    "ECE",
    "Action_Flip_Rate",
    "Rationale_Jaccard",
]

README_COMMANDS = [
    "scripts/download_data.py",
    "scripts/prepare_data.py",
    "scripts/smoke_test.py",
    "scripts/train_model.py",
    "scripts/calibrate.py",
    "scripts/generate_masks.py",
    "scripts/generate_perturbations.py",
    "scripts/evaluate.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    output_dir = paths["output_dir"]
    missing = [
        name for name in REQUIRED_OUTPUTS if not (output_dir / name).exists()
    ]
    with (output_dir / "main_results.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    missing_readme_commands = [
        command for command in README_COMMANDS if command not in readme
    ]
    checkpoint_names = [
        "action_only_best_action.pt",
        "joint_best_action.pt",
        "joint_best_rationale.pt",
    ]
    missing_checkpoints = [
        name
        for name in checkpoint_names
        if not (paths["checkpoint_dir"] / name).exists()
    ]
    result = {
        "passed": (
            not missing
            and columns == MAIN_COLUMNS
            and len(rows) == 3
            and not missing_readme_commands
            and not missing_checkpoints
        ),
        "required_outputs_missing": missing,
        "main_results_columns": columns,
        "main_results_row_count": len(rows),
        "readme_commands_missing": missing_readme_commands,
        "checkpoints_missing": missing_checkpoints,
    }
    write_json(output_dir / "reproduction_check.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
