"""Data loading and inference shared by training and evaluation scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader

from arsc_eval.data import BDDOIADataset


def make_loader(
    manifest_path: str | Path,
    image_root: str | Path,
    image_size: int,
    batch_size: int,
    num_workers: int,
    shuffle: bool = False,
    limit: int | None = None,
    path_key: str = "file_name",
    seed: int | None = None,
    pil_transform: Callable[[Image.Image, str], Image.Image] | None = None,
) -> DataLoader:
    dataset = BDDOIADataset(
        manifest_path=manifest_path,
        image_root=image_root,
        image_size=image_size,
        limit=limit,
        path_key=path_key,
        pil_transform=pil_transform,
    )
    generator = None
    if seed is not None:
        generator = torch.Generator()
        generator.manual_seed(seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        persistent_workers=num_workers > 0,
        drop_last=False,
        generator=generator,
    )


@torch.inference_mode()
def predict(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    amp: bool = True,
) -> dict[str, Any]:
    model.eval()
    action_logits = []
    rationale_logits = []
    action_targets = []
    rationale_targets = []
    file_names = []
    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        with torch.autocast(
            device_type=device.type,
            dtype=torch.float16,
            enabled=amp and device.type == "cuda",
        ):
            output = model(images)
        action_logits.append(output["action_logits"].float().cpu())
        if "rationale_logits" in output:
            rationale_logits.append(output["rationale_logits"].float().cpu())
        action_targets.append(batch["actions"].float())
        rationale_targets.append(batch["rationales"].float())
        file_names.extend(batch["file_name"])
    result: dict[str, Any] = {
        "file_names": file_names,
        "action_logits": torch.cat(action_logits).numpy(),
        "action_targets": torch.cat(action_targets).numpy(),
        "rationale_targets": torch.cat(rationale_targets).numpy(),
    }
    if rationale_logits:
        result["rationale_logits"] = torch.cat(rationale_logits).numpy()
    return result


def sigmoid_numpy(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = np.clip(logits / temperature, -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-scaled))
