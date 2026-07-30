"""Freeze and hash the reviewed five-seed RQ1 protocol before test inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.utils import load_config, write_json


SEEDS = [43, 44, 45, 46, 47]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="outputs/validity/rq1_multiseed_frozen_protocol.json",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> int:
    args = parse_args()
    configs = []
    for seed in SEEDS:
        path = PROJECT_ROOT / "configs" / f"rq1_seed{seed}.yaml"
        config = load_config(path)
        if int(config["seed"]) != seed:
            raise RuntimeError(f"seed mismatch in {path}")
        if int(config["training"]["epochs"]) != 5:
            raise RuntimeError(f"epochs must be 5 in {path}")
        if float(config["training"]["threshold"]) != 0.5:
            raise RuntimeError(f"threshold must be 0.5 in {path}")
        if int(config["perturbations"]["noise_seed"]) != 20260731:
            raise RuntimeError(f"noise seed is not frozen in {path}")
        configs.append(fingerprint(path))

    audit_path = (
        PROJECT_ROOT
        / "outputs"
        / "validity"
        / "perturbation_semantic_audit"
        / "audit_summary.json"
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if not audit["gate_passed"]:
        raise RuntimeError("C1 semantic audit gate failed")
    design_checks = []
    for seed in SEEDS:
        path = (
            PROJECT_ROOT
            / "outputs"
            / "validity"
            / f"rq1_seed_{seed}"
            / "paired_design_check.json"
        )
        result = json.loads(path.read_text(encoding="utf-8"))
        if not result["gate_passed"] or int(result["seed"]) != seed:
            raise RuntimeError(f"paired design failed for seed {seed}")
        design_checks.append(fingerprint(path))

    code_paths = [
        PROJECT_ROOT / "src" / "arsc_eval" / "data.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "engine.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "models.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "metrics.py",
        PROJECT_ROOT / "src" / "arsc_eval" / "rq1.py",
        PROJECT_ROOT / "scripts" / "train_model.py",
        PROJECT_ROOT / "scripts" / "calibrate.py",
        PROJECT_ROOT / "scripts" / "evaluate_rq1_seed.py",
        PROJECT_ROOT / "scripts" / "aggregate_rq1_multiseed.py",
    ]
    protocol = {
        "status": "frozen_before_new_seed_training_and_test_inference",
        "independent_review": fingerprint(
            PROJECT_ROOT
            / "outputs"
            / "research_review_memo_round4_vla_feasibility.md"
        ),
        "primary_new_seeds": SEEDS,
        "archival_pilot_seed_excluded": 42,
        "epochs": 5,
        "checkpoint_selection": "best validation action Macro-F1",
        "thresholds": {"action": 0.5, "rationale": 0.5},
        "models": (
            "paired ImageNet ResNet-50 initialization and data order; "
            "Joint adds only the 21-label rationale head/loss"
        ),
        "action_equivalence_margin": [-0.03, 0.03],
        "c1": {
            "transforms": "in-memory, no JPEG re-encoding",
            "semantic_audit": fingerprint(audit_path),
            "semantic_audit_rates": audit["by_perturbation"],
            "minimum_rate": 0.95,
        },
        "rq2_light_perturbation_decision": {
            "mean_flip_advantage_action_minus_joint_minimum": 0.01,
            "minimum_positive_seeds": 4,
            "no_single_perturbation_mean_advantage_below": -0.01,
        },
        "ceg": "excluded; v4 measurement gate failed",
        "configs": configs,
        "paired_design_checks": design_checks,
        "frozen_code": [fingerprint(path) for path in code_paths],
        "test_nonadaptation": (
            "No test result may change epochs, checkpoints, thresholds, "
            "loss weights, seeds, perturbation parameters, or analysis code."
        ),
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != protocol:
            raise RuntimeError(
                "existing frozen protocol differs; refusing overwrite"
            )
    else:
        write_json(output, protocol)
    print(json.dumps(protocol, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
