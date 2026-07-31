"""Self-contained frozen pixel corruptions for Round 10 amendment 01.

The noise implementation is intentionally local so its executable semantics
are bound by this module's hash. No model, metric, or outcome code is present.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


FAMILIES = ("brightness", "blur", "noise")
LEVELS = (0, 1, 2, 3, 4)
NOISE_SEED = 20260731
PARAMETERS: Mapping[str, tuple[float, ...]] = {
    "brightness": (1.0, 1.05, 1.10, 1.20, 1.30),
    "blur": (0.0, 0.5, 1.0, 1.5, 2.0),
    "noise": (0.0, 2.5, 5.0, 7.5, 10.0),
}


def validate_grid(
    parameters: Mapping[str, Sequence[float]] = PARAMETERS,
) -> None:
    if tuple(parameters) != FAMILIES:
        raise ValueError("families or family order differ from frozen grid")
    for family in FAMILIES:
        values = tuple(float(value) for value in parameters[family])
        if len(values) != len(LEVELS):
            raise ValueError(f"{family} must contain five levels")
        if any(right <= left for left, right in zip(values, values[1:])):
            raise ValueError(f"{family} parameters must strictly increase")
    if float(parameters["brightness"][0]) != 1.0:
        raise ValueError("brightness level zero must be identity factor 1")
    if float(parameters["blur"][0]) != 0.0:
        raise ValueError("blur level zero must be identity radius 0")
    if float(parameters["noise"][0]) != 0.0:
        raise ValueError("noise level zero must be identity standard deviation 0")
    if (
        float(parameters["brightness"][2]) != 1.10
        or float(parameters["blur"][2]) != 1.0
        or float(parameters["noise"][2]) != 5.0
    ):
        raise ValueError("level two must reproduce the historical light setting")


def deterministic_noise_v2(
    image: Image.Image,
    file_name: str,
    std_255: float,
    seed: int = NOISE_SEED,
) -> Image.Image:
    """Apply the frozen filename-specific Gaussian field pixel-exactly."""

    if std_255 < 0.0:
        raise ValueError("noise standard deviation must be nonnegative")
    name_seed = int.from_bytes(
        hashlib.sha256(file_name.encode("utf-8")).digest()[:8],
        "little",
    )
    generator = np.random.default_rng(int(seed) ^ name_seed)
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    standard_normal = generator.normal(0.0, 1.0, size=pixels.shape)
    noise = standard_normal * float(std_255)
    return Image.fromarray(
        np.clip(pixels + noise, 0, 255).astype(np.uint8),
        mode="RGB",
    )


@dataclass(frozen=True)
class PixelCorruptionV2:
    """Pickle-safe frozen family/level transformation."""

    family: str
    level: int
    noise_seed: int = NOISE_SEED

    def __post_init__(self) -> None:
        validate_grid()
        if self.family not in FAMILIES:
            raise ValueError(f"unknown family: {self.family}")
        if self.level not in LEVELS:
            raise ValueError(f"unknown level: {self.level}")
        if int(self.noise_seed) != NOISE_SEED:
            raise ValueError("noise seed differs from frozen Round 10 value")

    @property
    def parameter(self) -> float:
        return float(PARAMETERS[self.family][self.level])

    def __call__(self, image: Image.Image, file_name: str) -> Image.Image:
        rgb = image.convert("RGB")
        if self.level == 0:
            return rgb.copy()
        if self.family == "brightness":
            return ImageEnhance.Brightness(rgb).enhance(self.parameter)
        if self.family == "blur":
            return rgb.filter(
                ImageFilter.GaussianBlur(radius=self.parameter)
            )
        return deterministic_noise_v2(
            rgb,
            file_name,
            self.parameter,
            self.noise_seed,
        )


def make_pixel_corruption_v2(
    family: str,
    level: int,
) -> PixelCorruptionV2:
    return PixelCorruptionV2(family=family, level=level)
