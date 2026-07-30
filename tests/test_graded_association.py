import unittest

import numpy as np

from arsc_eval.graded_association import (
    bottleneck_monotonic_step,
    build_clip_safe_cycles,
    clip_group,
    graded_source_maps,
    shared_clip_bootstrap_draw,
    validate_graded_maps,
)


class GradedAssociationTests(unittest.TestCase):
    def test_clip_group_collapses_only_frozen_suffixes(self):
        self.assertEqual(clip_group("abc-def.jpg"), "abc-def")
        self.assertEqual(clip_group("abc-def_1.jpg"), "abc-def")
        self.assertEqual(clip_group("abc-def_3.jpg"), "abc-def")
        self.assertEqual(clip_group("abc-def_2.jpg"), "abc-def_2")

    def test_cycles_and_nested_maps_are_clip_safe_bijections(self):
        names = [
            "a.jpg",
            "a_1.jpg",
            "b.jpg",
            "c.jpg",
            "d.jpg",
            "e.jpg",
            "f.jpg",
            "g.jpg",
            "h.jpg",
        ]
        cycles, diagnostics = build_clip_safe_cycles(
            names, "synthetic-round8"
        )
        self.assertTrue(diagnostics["all_cycle_members_unique"])
        self.assertTrue(diagnostics["all_cycle_edges_cross_clip"])
        maps = graded_source_maps(
            len(names), cycles, (0.0, 0.25, 0.5, 0.75, 1.0)
        )
        audit = validate_graded_maps(names, maps)
        self.assertTrue(audit["all_passed"])
        self.assertEqual(
            audit["by_severity"]["0.0"]["active_images"], 0
        )
        self.assertEqual(
            audit["by_severity"]["1.0"]["active_images"], len(names)
        )
        self.assertEqual(
            audit["by_severity"]["1.0"]["fixed_points"], 0
        )

    def test_shared_clip_bootstrap_keeps_whole_clip_frames(self):
        groups = [
            np.array([0, 1], dtype=np.int64),
            np.array([2], dtype=np.int64),
            np.array([3, 4, 5], dtype=np.int64),
        ]
        selected_seeds, selected_clips, images = (
            shared_clip_bootstrap_draw(
                np.random.default_rng(7),
                [43, 44, 45, 46, 47],
                groups,
            )
        )
        expected = np.concatenate(
            [groups[index] for index in selected_clips]
        )
        np.testing.assert_array_equal(images, expected)
        self.assertEqual(selected_seeds.shape, (5,))
        self.assertEqual(selected_clips.shape, (3,))

    def test_bottleneck_statistic_requires_every_adjacent_step(self):
        decreasing = [
            [1.0, 0.8, 0.6, 0.4, 0.2],
            [0.9, 0.7, 0.5, 0.3, 0.1],
        ]
        increasing = [
            [0.0, 0.1, 0.3, 0.6, 1.0],
            [0.2, 0.3, 0.4, 0.5, 0.6],
        ]
        self.assertAlmostEqual(
            bottleneck_monotonic_step(decreasing, "decreasing"),
            0.2,
        )
        self.assertAlmostEqual(
            bottleneck_monotonic_step(increasing, "increasing"),
            0.1,
        )
        reversal = [[0.0, 0.2, 0.1, 0.4, 0.5]]
        self.assertLess(
            bottleneck_monotonic_step(reversal, "increasing"), 0.0
        )


if __name__ == "__main__":
    unittest.main()
