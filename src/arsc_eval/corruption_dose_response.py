"""Frozen pixel-space corruption operators for Round 10.

This module contains no model or metric code. Operators depend only on the
input RGB image, canonical filename, frozen family/level, and frozen noise
seed. They are applied in memory before resize/normalization and never use
JPEG re-encoding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from PIL import Image, ImageEnhance, ImageFilter

from .data import deterministic_noise


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


@dataclass(frozen=True)
class PixelCorruption:
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
        return deterministic_noise(
            rgb, file_name, self.parameter, self.noise_seed
        )


def make_pixel_corruption(family: str, level: int) -> PixelCorruption:
    return PixelCorruption(family=family, level=level)
