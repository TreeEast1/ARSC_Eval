"""BDD-OIA manifest parsing and PyTorch datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageFilter
from torch.utils.data import Dataset
from torchvision import transforms


IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


def image_transform(image_size: int) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
        ]
    )


def read_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class BDDOIADataset(Dataset):
    def __init__(
        self,
        manifest_path: str | Path,
        image_root: str | Path,
        image_size: int,
        limit: int | None = None,
        path_key: str = "file_name",
        pil_transform: Callable[[Image.Image, str], Image.Image] | None = None,
    ) -> None:
        records = read_jsonl(manifest_path)
        self.records = records[:limit] if limit is not None else records
        self.image_root = Path(image_root)
        self.transform = image_transform(image_size)
        self.path_key = path_key
        self.pil_transform = pil_transform

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, object]:
        record = self.records[index]
        image_path = Path(record[self.path_key])
        if not image_path.is_absolute():
            image_path = self.image_root / image_path
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        if self.pil_transform is not None:
            image = self.pil_transform(image, record["file_name"])
        return {
            "image": self.transform(image),
            "actions": torch.tensor(record["actions"], dtype=torch.float32),
            "rationales": torch.tensor(
                record["rationales"], dtype=torch.float32
            ),
            "file_name": record["file_name"],
        }


def deterministic_noise(
    image: Image.Image, file_name: str, std_255: float, seed: int
) -> Image.Image:
    import hashlib

    name_seed = int.from_bytes(
        hashlib.sha256(file_name.encode("utf-8")).digest()[:8], "little"
    )
    generator = np.random.default_rng(seed ^ name_seed)
    pixels = np.asarray(image, dtype=np.float32)
    noise = generator.normal(0.0, std_255, size=pixels.shape)
    return Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8))


@dataclass(frozen=True)
class BenignPerturbation:
    """Pickle-safe in-memory perturbation for Windows DataLoader workers."""

    kind: str
    brightness_factor: float
    blur_radius: float
    noise_std_255: float
    noise_seed: int

    def __post_init__(self) -> None:
        if self.kind not in {"brightness", "blur", "noise"}:
            raise ValueError(f"unknown perturbation: {self.kind}")

    def __call__(self, image: Image.Image, file_name: str) -> Image.Image:
        if self.kind == "brightness":
            return ImageEnhance.Brightness(image).enhance(
                self.brightness_factor
            )
        if self.kind == "blur":
            return image.filter(
                ImageFilter.GaussianBlur(radius=self.blur_radius)
            )
        return deterministic_noise(
            image,
            file_name,
            self.noise_std_255,
            self.noise_seed,
        )


def make_benign_perturbation(
    kind: str,
    brightness_factor: float,
    blur_radius: float,
    noise_std_255: float,
    noise_seed: int,
) -> Callable[[Image.Image, str], Image.Image]:
    """Create a frozen, pickle-safe transform with no JPEG re-encoding."""

    return BenignPerturbation(
        kind=kind,
        brightness_factor=brightness_factor,
        blur_radius=blur_radius,
        noise_std_255=noise_std_255,
        noise_seed=noise_seed,
    )
