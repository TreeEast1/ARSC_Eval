from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_bdd100k_train_v5_gate import (
    clip_group,
    is_keyframe,
    sole_target_state,
    state_boxes,
)


class BDD100KTrainV5GateTests(unittest.TestCase):
    def test_clip_group_collapses_only_frozen_neighbor_suffixes(self) -> None:
        self.assertEqual("abc-def", clip_group("abc-def.jpg"))
        self.assertEqual("abc-def", clip_group("abc-def_1.jpg"))
        self.assertEqual("abc-def", clip_group("abc-def_3.jpg"))
        self.assertEqual("abc-def_2", clip_group("abc-def_2.jpg"))
        self.assertTrue(is_keyframe("abc-def.jpg"))
        self.assertFalse(is_keyframe("abc-def_1.jpg"))

    def test_sole_target_state_requires_exactly_one_state(self) -> None:
        green = [0] * 21
        green[0] = 1
        red = [0] * 21
        red[3] = 1
        both = [0] * 21
        both[0] = both[3] = 1
        self.assertEqual("green", sole_target_state({"rationales": green}))
        self.assertEqual("red", sole_target_state({"rationales": red}))
        self.assertIsNone(sole_target_state({"rationales": both}))
        self.assertIsNone(
            sole_target_state({"rationales": [0] * 21})
        )

    def test_state_boxes_align_category_color_and_box(self) -> None:
        row = {
            "image_id": "frame",
            "ann_categories": [
                "traffic light",
                "traffic light",
                "car",
            ],
            "ann_bboxes": [
                [1, 2, 3, 4],
                [5, 6, 7, 8],
                [9, 10, 11, 12],
            ],
            "ann_traffic_light_colors": ["R", "green", "red"],
        }
        self.assertEqual(
            [[1.0, 2.0, 3.0, 4.0]], state_boxes(row, "red")
        )
        self.assertEqual(
            [[5.0, 6.0, 7.0, 8.0]], state_boxes(row, "green")
        )

    def test_state_boxes_reject_misaligned_arrays(self) -> None:
        row = {
            "image_id": "frame",
            "ann_categories": ["traffic light"],
            "ann_bboxes": [],
            "ann_traffic_light_colors": ["red"],
        }
        with self.assertRaises(ValueError):
            state_boxes(row, "red")


if __name__ == "__main__":
    unittest.main()
