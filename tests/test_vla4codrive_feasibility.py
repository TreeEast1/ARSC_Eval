from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_vla4codrive_feasibility import (
    count_rising_edges,
    lexicon_flags,
    parse_window_identity,
)
from analyze_vla4codrive_repository_index import parse_window_path


class VLA4CoDriveFeasibilityTests(unittest.TestCase):
    def test_window_identity_uses_town_and_scene(self) -> None:
        modality_root = Path("Action")
        path = (
            modality_root
            / "clearNoon"
            / "Vehicle_2"
            / "Town10HD_WeatherclearNoon_scene007_win03.json"
        )
        identity = parse_window_identity(path, modality_root)
        self.assertEqual("town10hd::scene007", identity["canonical_scene_key"])
        self.assertEqual(
            "clearNoon::Vehicle_2::Town10HD::scene007::win03",
            identity["window_key"],
        )

    def test_rising_edges_count_events_not_positive_frames(self) -> None:
        self.assertEqual(
            3,
            count_rising_edges(
                [False, True, True, False, True, False, False, True]
            ),
        )

    def test_exploratory_lexicon_is_reason_not_action_only(self) -> None:
        flags = lexicon_flags(
            "The vehicle stops because a pedestrian is crossing at an "
            "intersection in heavy rain."
        )
        self.assertTrue(flags["pedestrian_or_cyclist"])
        self.assertTrue(flags["junction_or_route_constraint"])
        self.assertTrue(flags["visibility_or_weather_hazard"])

    def test_repository_window_path_parser(self) -> None:
        record = parse_window_path(
            "Action/clearNoon/Vehicle_3/"
            "Town10HD_WeatherclearNoon_scene009_win10.json"
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual("town10hd::scene009", record["canonical_scene_key"])
        self.assertEqual(10, record["window"])
        self.assertTrue(record["weather_matches_filename"])
        self.assertIsNone(
            parse_window_path(
                "Language/clearNoon/Vehicle_3/V3_windows_cdr.json"
            )
        )
        mismatch = parse_window_path(
            "Action/hardFogNoon/Vehicle_1/"
            "Town10HD_WeathercustomWeather_scene001_win01.json"
        )
        self.assertIsNotNone(mismatch)
        assert mismatch is not None
        self.assertFalse(mismatch["weather_matches_filename"])


if __name__ == "__main__":
    unittest.main()
