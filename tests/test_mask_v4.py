from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_masks_v2 import intersection_area
from generate_masks_v4 import (
    expanded_box,
    matched_clean_control,
    strict_light_evidence,
)


class MaskV4Tests(unittest.TestCase):
    def test_strict_red_and_green_rules(self) -> None:
        red = np.zeros((50, 20, 3), dtype=np.uint8)
        red[5:15, 5:15] = (255, 0, 0)
        red_ok, _ = strict_light_evidence(
            Image.fromarray(red), (0, 0, 20, 50), "red"
        )
        self.assertTrue(red_ok)

        green = np.zeros((60, 20, 3), dtype=np.uint8)
        green[42:52, 5:15] = (0, 255, 0)
        green_ok, _ = strict_light_evidence(
            Image.fromarray(green), (0, 0, 20, 60), "green"
        )
        self.assertTrue(green_ok)

    def test_squat_high_area_red_is_rejected(self) -> None:
        image = np.zeros((40, 40, 3), dtype=np.uint8)
        image[5:25, 5:30] = (255, 0, 0)
        passed, diagnostics = strict_light_evidence(
            Image.fromarray(image), (0, 0, 40, 40), "red"
        )
        self.assertGreater(diagnostics["strict_area_fraction"], 0.30)
        self.assertFalse(passed)

    def test_wrong_lamp_position_and_low_pixel_count_are_rejected(self) -> None:
        red = np.zeros((50, 20, 3), dtype=np.uint8)
        red[35:45, 5:15] = (255, 0, 0)
        red_ok, _ = strict_light_evidence(
            Image.fromarray(red), (0, 0, 20, 50), "red"
        )
        self.assertFalse(red_ok)

        green = np.zeros((60, 20, 3), dtype=np.uint8)
        green[48:50, 8:12] = (0, 255, 0)
        green_ok, _ = strict_light_evidence(
            Image.fromarray(green), (0, 0, 20, 60), "green"
        )
        self.assertFalse(green_ok)

    def test_control_avoids_signal_color(self) -> None:
        image = np.zeros((100, 160, 3), dtype=np.uint8)
        critical = (60, 20, 80, 60)
        image[20:60, 30:50] = (255, 0, 0)
        result = matched_clean_control(
            image,
            critical,
            [critical],
            width=160,
            height=100,
            max_offset=0.50,
        )
        self.assertIsNotNone(result)
        selected, _ = result
        self.assertEqual(0, image[selected[1] : selected[3], selected[0] : selected[2], 0].max())
        self.assertEqual(
            (critical[2] - critical[0], critical[3] - critical[1]),
            (selected[2] - selected[0], selected[3] - selected[1]),
        )
        self.assertEqual(0, intersection_area(critical, selected))

    def test_control_returns_none_when_expanded_detection_covers_image(self) -> None:
        image = np.zeros((100, 160, 3), dtype=np.uint8)
        result = matched_clean_control(
            image,
            (60, 20, 80, 60),
            [(0, 0, 160, 100)],
            width=160,
            height=100,
            max_offset=0.50,
        )
        self.assertIsNone(result)

    def test_expanded_box_clips_to_image(self) -> None:
        self.assertEqual(
            (0, 0, 26, 37), expanded_box((2, 3, 20, 30), 100, 80)
        )


if __name__ == "__main__":
    unittest.main()
