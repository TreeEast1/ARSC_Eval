from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from arsc_eval.corruption_dose_response import (
    FAMILIES,
    PARAMETERS,
    PixelCorruption,
    validate_grid,
)


def test_frozen_grid_and_historical_level_two() -> None:
    validate_grid()
    assert tuple(PARAMETERS) == FAMILIES
    assert PARAMETERS["brightness"][2] == 1.10
    assert PARAMETERS["blur"][2] == 1.0
    assert PARAMETERS["noise"][2] == 5.0


def test_level_zero_is_exact_rgb_identity() -> None:
    pixels = np.arange(8 * 9 * 3, dtype=np.uint8).reshape(8, 9, 3)
    image = Image.fromarray(pixels, mode="RGB")
    for family in FAMILIES:
        observed = np.asarray(PixelCorruption(family, 0)(image, "x.jpg"))
        assert np.array_equal(observed, pixels)


def test_noise_is_filename_deterministic_and_nested_before_clipping() -> None:
    pixels = np.full((32, 32, 3), 128, dtype=np.uint8)
    image = Image.fromarray(pixels, mode="RGB")
    level_one = np.asarray(
        PixelCorruption("noise", 1)(image, "same.jpg"),
        dtype=np.int16,
    )
    level_two = np.asarray(
        PixelCorruption("noise", 2)(image, "same.jpg"),
        dtype=np.int16,
    )
    repeated = np.asarray(
        PixelCorruption("noise", 2)(image, "same.jpg"),
        dtype=np.int16,
    )
    assert np.array_equal(level_two, repeated)
    # Integer quantization permits a one-value discrepancy from exact 2x.
    delta_one = level_one - 128
    delta_two = level_two - 128
    assert np.max(np.abs(delta_two - 2 * delta_one)) <= 1


def test_invalid_family_or_level_is_rejected() -> None:
    with pytest.raises(ValueError):
        PixelCorruption("jpeg", 1)
    with pytest.raises(ValueError):
        PixelCorruption("blur", 5)
