"""Train Action-Only or Joint Action-Rationale with resume support."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
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
    load_config,
    resolve_paths,
    set_seed,
)


LOG_COLUMNS = [
    "epoch",
    "train_action_loss",
    "train_rationale_loss",
    "train_total_loss",
    "validation_action_macro_f1",
    "validation_rationale_macro_f1",
    "learning_rate",
    "duration_seconds",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/experiment.yaml")
    parser.add_argument(
        "--model", choices=("action_only", "joint"), required=True
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--epochs", type=int)
    return parser.parse_args()


def save_checkpoint(
    path: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    model_type: str,
    best_action_f1: float,
    best_rationale_f1: float | None,
    validation_metrics: dict,
    config: dict,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "epoch": epoch,
            "model_type": model_type,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "best_action_f1": best_action_f1,
            "best_rationale_f1": best_rationale_f1,
            "validation_metrics": validation_metrics,
            "config": {
                "seed": config["seed"],
                "image_size": config["image_size"],
                "model": config["model"],
                "training": config["training"],
            },
        },
        path,
    )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    paths = resolve_paths(config)
    training = config["training"]
    set_seed(int(config["seed"]))
    device = device_from_arg(args.device)
    use_amp = bool(training["amp"]) and device.type == "cuda"
    epochs = args.epochs or int(training["epochs"])
    image_root = paths["dataset_root"] / "data"
    train_loader = make_loader(
        paths["processed_root"] / "train.jsonl",
        image_root,
        int(config["image_size"]),
        int(training["batch_size"]),
        int(training["num_workers"]),
        shuffle=True,
        seed=int(config["seed"]),
    )
    validation_loader = make_loader(
        paths["processed_root"] / "val.jsonl",
        image_root,
        int(config["image_size"]),
        int(training["batch_size"]),
        int(training["num_workers"]),
        shuffle=False,
    )
    model = build_model(
        args.model, pretrained=bool(config["model"]["pretrained"])
    ).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )
    scaler = torch.amp.GradScaler(device.type, enabled=use_amp)
    loss_fn = nn.BCEWithLogitsLoss()
    start_epoch = 1
    best_action = -1.0
    best_rationale = -1.0 if args.model == "joint" else None

    checkpoint_dir = paths["checkpoint_dir"]
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    prefix = "action_only" if args.model == "action_only" else "joint"
    last_checkpoint = checkpoint_dir / f"{prefix}_last.pt"
    if args.resume:
        resume_path = args.resume.resolve()
        checkpoint = torch.load(
            resume_path, map_location=device, weights_only=False
        )
        if checkpoint["model_type"] != args.model:
            raise ValueError("Resume checkpoint model type does not match.")
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_action = float(checkpoint["best_action_f1"])
        if args.model == "joint":
            best_rationale = float(checkpoint["best_rationale_f1"])

    log_name = (
        "training_log_action_only.csv"
        if args.model == "action_only"
        else "training_log_joint.csv"
    )
    log_path = paths["output_dir"] / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_mode = "a" if args.resume and log_path.exists() else "w"
    with log_path.open(log_mode, newline="", encoding="utf-8") as log_handle:
        writer = csv.DictWriter(log_handle, fieldnames=LOG_COLUMNS)
        if log_mode == "w":
            writer.writeheader()

        for epoch in range(start_epoch, epochs + 1):
            started = time.perf_counter()
            model.train()
            action_loss_sum = 0.0
            rationale_loss_sum = 0.0
            total_loss_sum = 0.0
            sample_count = 0
            for batch in train_loader:
                images = batch["image"].to(device, non_blocking=True)
                actions = batch["actions"].to(device, non_blocking=True)
                rationales = batch["rationales"].to(
                    device, non_blocking=True
                )
                optimizer.zero_grad(set_to_none=True)
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.float16,
                    enabled=use_amp,
                ):
                    output = model(images)
                    action_loss = loss_fn(output["action_logits"], actions)
                    rationale_loss = torch.zeros(
                        (), device=device, dtype=action_loss.dtype
                    )
                    if args.model == "joint":
                        rationale_loss = loss_fn(
                            output["rationale_logits"], rationales
                        )
                    total_loss = (
                        float(training["action_loss_weight"]) * action_loss
                        + float(training["rationale_loss_weight"])
                        * rationale_loss
                    )
                scaler.scale(total_loss).backward()
                scaler.step(optimizer)
                scaler.update()
                batch_size = images.shape[0]
                sample_count += batch_size
                action_loss_sum += float(action_loss.detach()) * batch_size
                rationale_loss_sum += (
                    float(rationale_loss.detach()) * batch_size
                )
                total_loss_sum += float(total_loss.detach()) * batch_size

            validation = predict(
                model, validation_loader, device, amp=use_amp
            )
            action_metrics = multilabel_f1(
                validation["action_targets"],
                sigmoid_numpy(validation["action_logits"]),
                ACTION_NAMES,
                threshold=float(training["threshold"]),
            )
            rationale_metrics = None
            if args.model == "joint":
                rationale_metrics = multilabel_f1(
                    validation["rationale_targets"],
                    sigmoid_numpy(validation["rationale_logits"]),
                    RATIONALE_NAMES,
                    threshold=float(training["threshold"]),
                )
            validation_metrics = {
                "action": action_metrics,
                "rationale": rationale_metrics,
            }
            action_improved = action_metrics["macro_f1"] > best_action
            rationale_improved = (
                args.model == "joint"
                and rationale_metrics["macro_f1"] > best_rationale
            )
            if action_improved:
                best_action = action_metrics["macro_f1"]
            if rationale_improved:
                best_rationale = rationale_metrics["macro_f1"]

            duration = time.perf_counter() - started
            row = {
                "epoch": epoch,
                "train_action_loss": action_loss_sum / sample_count,
                "train_rationale_loss": (
                    rationale_loss_sum / sample_count
                    if args.model == "joint"
                    else "N/A"
                ),
                "train_total_loss": total_loss_sum / sample_count,
                "validation_action_macro_f1": action_metrics["macro_f1"],
                "validation_rationale_macro_f1": (
                    rationale_metrics["macro_f1"]
                    if rationale_metrics
                    else "N/A"
                ),
                "learning_rate": optimizer.param_groups[0]["lr"],
                "duration_seconds": duration,
            }
            writer.writerow(row)
            log_handle.flush()

            save_checkpoint(
                last_checkpoint,
                model,
                optimizer,
                epoch,
                args.model,
                best_action,
                best_rationale,
                validation_metrics,
                config,
            )
            if action_improved:
                save_checkpoint(
                    checkpoint_dir / f"{prefix}_best_action.pt",
                    model,
                    optimizer,
                    epoch,
                    args.model,
                    best_action,
                    best_rationale,
                    validation_metrics,
                    config,
                )
            if rationale_improved:
                save_checkpoint(
                    checkpoint_dir / "joint_best_rationale.pt",
                    model,
                    optimizer,
                    epoch,
                    args.model,
                    best_action,
                    best_rationale,
                    validation_metrics,
                    config,
                )
            print(
                json.dumps(
                    {
                        "model": args.model,
                        "epoch": epoch,
                        "train_total_loss": row["train_total_loss"],
                        "validation_action_macro_f1": action_metrics[
                            "macro_f1"
                        ],
                        "validation_rationale_macro_f1": (
                            rationale_metrics["macro_f1"]
                            if rationale_metrics
                            else None
                        ),
                        "duration_seconds": duration,
                    }
                ),
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
