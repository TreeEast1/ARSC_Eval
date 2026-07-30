from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from generate_masks_v3 import road_relevance, traffic_light_state


class MaskV3Tests(unittest.TestCase):
    def test_red_and_green_state_rules(self) -> None:
        red = np.zeros((30, 10, 3), dtype=np.uint8)
        red[2:10, 2:8] = [255, 0, 0]
        state, _ = traffic_light_state(
            Image.fromarray(red), (0, 0, 10, 30)
        )
        self.assertEqual(state, "red")

        green = np.zeros((30, 10, 3), dtype=np.uint8)
        green[20:28, 2:8] = [0, 255, 0]
        state, _ = traffic_light_state(
            Image.fromarray(green), (0, 0, 10, 30)
        )
        self.assertEqual(state, "green")

    def test_ambiguous_light_is_rejected(self) -> None:
        dark = Image.fromarray(np.zeros((30, 10, 3), dtype=np.uint8))
        state, _ = traffic_light_state(dark, (0, 0, 10, 30))
        self.assertIsNone(state)

    def test_road_corridor_rejects_side_object(self) -> None:
        central = {
            "box": (500, 350, 700, 700),
            "confidence": 0.8,
        }
        side = {
            "box": (0, 350, 100, 700),
            "confidence": 0.8,
        }
        self.assertIsNotNone(road_relevance(central, 1280, 720))
        self.assertIsNone(road_relevance(side, 1280, 720))


if __name__ == "__main__":
    unittest.main()
