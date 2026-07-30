"""Run the required loader, shape, loss, and evaluation smoke test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from arsc_eval.constants import ACTION_NAMES, RATIONALE_NAMES
from arsc_eval.engine import make_loader, predict, sigmoid_numpy
from arsc_eval.metrics import multilabel_f1
from arsc_eval.models import build_model
from arsc_eval.utils import (
    device_from_arg,
    json_safe,
    load_config,
    resolve_paths,
    set_seed,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument("--device", default="auto")
    return parser.parse_args()


def smoke_model(
    model_type: str,
    train_loader,
    validation_loader,
    device: torch.device,
    repeated_steps: int,
) -> dict:
    model = build_model(model_type, pretrained=True).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    loss_fn = nn.BCEWithLogitsLoss()
    batch = next(iter(train_loader))
    images = batch["image"].to(device)
    actions = batch["actions"].to(device)
    rationales = batch["rationales"].to(device)
    losses = []
    output_shapes = {}
    model.train()
    for _ in range(repeated_steps):
        optimizer.zero_grad(set_to_none=True)
        output = model(images)
        action_loss = loss_fn(output["action_logits"], actions)
        total_loss = action_loss
        if model_type == "joint":
            rationale_loss = loss_fn(output["rationale_logits"], rationales)
            total_loss = total_loss + rationale_loss
        total_loss.backward()
        optimizer.step()
        losses.append(float(total_loss.detach().cpu()))
        output_shapes = {
            key: list(value.shape) for key, value in output.items()
        }

    inference = predict(model, validation_loader, device, amp=True)
    action_metrics = multilabel_f1(
        inference["action_targets"],
        sigmoid_numpy(inference["action_logits"]),
        ACTION_NAMES,
    )
    result = {
        "output_shapes": output_shapes,
        "losses_repeated_same_batch": losses,
        "loss_decreased": losses[-1] < losses[0],
        "action_macro_f1": action_metrics["macro_f1"],
        "evaluation_samples": len(inference["file_names"]),
    }
    if model_type == "joint":
        rationale_metrics = multilabel_f1(
            inference["rationale_targets"],
            sigmoid_numpy(inference["rationale_logits"]),
            RATIONALE_NAMES,
        )
        result["rationale_macro_f1"] = rationale_metrics["macro_f1"]
    if output_shapes["action_logits"][1] != 4:
        raise AssertionError(f"Invalid action shape: {output_shapes}")
    if model_type == "joint" and output_shapes["rationale_logits"][1] != 21:
        raise AssertionError(f"Invalid rationale shape: {output_shapes}")
    if not result["loss_decreased"]:
        raise AssertionError(f"Loss failed to decrease: {losses}")
    return result


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    seed = int(config["seed"])
    set_seed(seed)
    device = device_from_arg(args.device)
    smoke = config["smoke_test"]
    image_root = paths["dataset_root"] / "data"
    train_loader = make_loader(
        paths["processed_root"] / "train.jsonl",
        image_root,
        int(config["image_size"]),
        int(smoke["batch_size"]),
        num_workers=0,
        shuffle=False,
        limit=int(smoke["train_samples"]),
    )
    validation_loader = make_loader(
        paths["processed_root"] / "val.jsonl",
        image_root,
        int(config["image_size"]),
        int(smoke["batch_size"]),
        num_workers=0,
        shuffle=False,
        limit=int(smoke["validation_samples"]),
    )
    results = {
        "passed": True,
        "seed": seed,
        "device": str(device),
        "image_size": int(config["image_size"]),
        "train_samples": len(train_loader.dataset),
        "validation_samples": len(validation_loader.dataset),
        "label_shapes": {"actions": 4, "rationales": 21},
    }
    for model_type in ("action_only", "joint"):
        results[model_type] = smoke_model(
            model_type,
            train_loader,
            validation_loader,
            device,
            int(smoke["repeated_steps"]),
        )
    write_json(paths["output_dir"] / "smoke_test.json", json_safe(results))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

