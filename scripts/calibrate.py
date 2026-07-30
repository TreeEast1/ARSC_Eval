"""Fit one scalar temperature on Joint validation action logits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.engine import make_loader, predict
from arsc_eval.models import load_checkpoint_model
from arsc_eval.utils import (
    device_from_arg,
    load_config,
    resolve_paths,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument(
        "--checkpoint", default="checkpoints/joint_best_action.pt"
    )
    parser.add_argument(
        "--model",
        choices=("action_only", "joint"),
        default="joint",
    )
    parser.add_argument(
        "--output",
        help=(
            "Optional result path. Defaults to output_dir/calibration.json "
            "for Joint and calibration_action_only.json for Action-Only."
        ),
    )
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    device = device_from_arg(args.device)
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.is_absolute():
        checkpoint_path = PROJECT_ROOT / checkpoint_path
    model = load_checkpoint_model(
        str(checkpoint_path), args.model, device=device
    )
    loader = make_loader(
        paths["processed_root"] / "val.jsonl",
        paths["dataset_root"] / "data",
        int(config["image_size"]),
        int(config["training"]["batch_size"]),
        int(config["training"]["num_workers"]),
    )
    predictions = predict(
        model, loader, device, amp=bool(config["training"]["amp"])
    )
    logits = torch.tensor(predictions["action_logits"], device=device)
    targets = torch.tensor(predictions["action_targets"], device=device)
    loss_fn = nn.BCEWithLogitsLoss()
    before = float(loss_fn(logits, targets).detach())

    log_temperature = nn.Parameter(torch.zeros((), device=device))
    optimizer = torch.optim.LBFGS(
        [log_temperature],
        lr=0.1,
        max_iter=int(config["calibration"]["max_iterations"]),
        line_search_fn="strong_wolfe",
    )

    def closure() -> torch.Tensor:
        optimizer.zero_grad()
        temperature = log_temperature.exp().clamp(0.05, 20.0)
        loss = loss_fn(logits / temperature, targets)
        loss.backward()
        return loss

    optimizer.step(closure)
    temperature = float(
        log_temperature.exp().clamp(0.05, 20.0).detach().cpu()
    )
    after = float(loss_fn(logits / temperature, targets).detach())
    result = {
        "method": "scalar temperature scaling",
        "model_type": args.model,
        "checkpoint": str(checkpoint_path.relative_to(PROJECT_ROOT)),
        "split": "official validation (valid four-action samples)",
        "validation_samples": len(predictions["file_names"]),
        "temperature": temperature,
        "bce_before": before,
        "bce_after": after,
        "optimized_outputs": "four action logits only",
    }
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
    else:
        output_name = (
            "calibration.json"
            if args.model == "joint"
            else "calibration_action_only.json"
        )
        output_path = paths["output_dir"] / output_name
    write_json(output_path, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
