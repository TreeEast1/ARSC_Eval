"""Verify common initialization and deterministic paired data order."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.engine import make_loader
from arsc_eval.models import build_model
from arsc_eval.utils import load_config, resolve_paths, set_seed, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/validity_seed42.yaml")
    parser.add_argument(
        "--output", default="outputs/validity/paired_design_check.json"
    )
    return parser.parse_args()


def loader_prefix(config: dict, paths: dict, batches: int = 3) -> list[str]:
    loader = make_loader(
        paths["processed_root"] / "train.jsonl",
        paths["dataset_root"] / "data",
        int(config["image_size"]),
        32,
        0,
        shuffle=True,
        seed=int(config["seed"]),
    )
    names = []
    for index, batch in enumerate(loader):
        names.extend(str(name) for name in batch["file_name"])
        if index + 1 == batches:
            break
    return names


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    seed = int(config["seed"])

    set_seed(seed)
    action_model = build_model("action_only", pretrained=True)
    set_seed(seed)
    joint_model = build_model("joint", pretrained=True)
    action_state = action_model.state_dict()
    joint_state = joint_model.state_dict()
    common_keys = sorted(set(action_state).intersection(joint_state))
    mismatches = [
        key
        for key in common_keys
        if not torch.equal(action_state[key], joint_state[key])
    ]
    action_only_keys = sorted(set(action_state).difference(joint_state))
    joint_only_keys = sorted(set(joint_state).difference(action_state))

    first_order = loader_prefix(config, paths)
    # Deliberately consume global RNG before creating the second iterator.
    torch.rand(4096)
    second_order = loader_prefix(config, paths)
    result = {
        "seed": seed,
        "common_parameter_tensors": len(common_keys),
        "common_initialization_exact_match": not mismatches,
        "mismatched_common_keys": mismatches,
        "unexpected_action_only_keys": action_only_keys,
        "joint_only_keys": joint_only_keys,
        "expected_joint_only_keys": [
            "rationale_head.bias",
            "rationale_head.weight",
        ],
        "checked_training_order_samples": len(first_order),
        "training_order_exact_match_after_global_rng_consumption": (
            first_order == second_order
        ),
        "first_training_file_names": first_order[:10],
        "gate_passed": (
            not mismatches
            and not action_only_keys
            and joint_only_keys
            == ["rationale_head.bias", "rationale_head.weight"]
            and first_order == second_order
        ),
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    write_json(output, result)
    print(json.dumps(result, indent=2))
    return 0 if result["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
