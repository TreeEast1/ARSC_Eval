import unittest

import numpy as np

from arsc_eval.multimap_response import (
    average_occurrence_seed_bottlenecks,
    bottleneck_from_curves,
    grand_mean_curve_has_no_reversal,
    hierarchical_multimap_draw,
    round9_axis_gate,
    validate_multimap_stack,
)


class MultiMapResponseTests(unittest.TestCase):
    def test_multimap_stack_requires_nested_bijections_and_unique_q1(self):
        identity = np.arange(8)
        pairs_first = ((0, 1), (2, 3), (4, 5), (6, 7))
        pairs_second = ((0, 2), (1, 3), (4, 6), (5, 7))

        def maps_from_pairs(pairs):
            maps = []
            for active_pairs in range(5):
                source = identity.copy()
                for left, right in pairs[:active_pairs]:
                    source[left], source[right] = right, left
                maps.append(source)
            return np.stack(maps)

        stack = np.stack(
            [
                maps_from_pairs(pairs_first),
                maps_from_pairs(pairs_second),
            ]
        )
        audit = validate_multimap_stack(stack, [0, 2, 4, 6, 8])
        self.assertTrue(audit["all_passed"])
        self.assertTrue(audit["all_q1_unique"])

        duplicate = np.stack([stack[0], stack[0]])
        audit = validate_multimap_stack(
            duplicate, [0, 2, 4, 6, 8]
        )
        self.assertFalse(audit["all_passed"])
        self.assertFalse(audit["all_q1_unique"])

    def test_hierarchy_draws_one_seed_vector_and_per_occurrence_components(self):
        rng = np.random.default_rng(20260809)
        selected_maps, selected_seeds, selected_components = (
            hierarchical_multimap_draw(rng, 4, 3, [2, 3, 4, 5])
        )
        self.assertEqual(selected_maps.shape, (4,))
        self.assertEqual(selected_seeds.shape, (3,))
        self.assertEqual(len(selected_components), 4)
        for map_index, components in zip(
            selected_maps, selected_components
        ):
            self.assertEqual(len(components), [2, 3, 4, 5][map_index])
            self.assertTrue(np.all(components >= 0))
            self.assertTrue(
                np.all(components < [2, 3, 4, 5][map_index])
            )
        for first, second in zip(
            selected_components[:-1], selected_components[1:]
        ):
            self.assertFalse(np.shares_memory(first, second))

    def test_bottleneck_precedes_seed_and_map_averaging(self):
        first = np.array([[1.0, 0.99, 0.79, 0.59, 0.39]])
        second = np.array([[1.0, 0.80, 0.79, 0.59, 0.39]])
        first_value = bottleneck_from_curves(first, ["decreasing"])
        second_value = bottleneck_from_curves(second, ["decreasing"])
        self.assertAlmostEqual(first_value, 0.01)
        self.assertAlmostEqual(second_value, 0.01)
        mean_curve_value = bottleneck_from_curves(
            np.mean([first, second], axis=0), ["decreasing"]
        )
        self.assertGreater(mean_curve_value, 0.01)

        occurrences = [
            {
                0: {axis: first_value for axis in ("A", "R", "S", "C1")},
                1: {axis: second_value for axis in ("A", "R", "S", "C1")},
            },
            {
                0: {axis: 0.03 for axis in ("A", "R", "S", "C1")},
                1: {axis: 0.05 for axis in ("A", "R", "S", "C1")},
            },
        ]
        observed = average_occurrence_seed_bottlenecks(
            occurrences, np.array([0, 1, 1])
        )
        expected = np.mean(
            [
                np.mean([first_value, second_value, second_value]),
                np.mean([0.03, 0.05, 0.05]),
            ]
        )
        for axis in ("A", "R", "S", "C1"):
            self.assertAlmostEqual(observed[axis], expected)

    def test_grand_mean_reversal_and_frozen_18_of_20_gate(self):
        decreasing = np.array([1.0, 0.8, 0.6, 0.4, 0.2])
        curves = np.tile(decreasing, (20, 5, 1, 1))
        self.assertTrue(
            grand_mean_curve_has_no_reversal(
                curves, ["decreasing"]
            )
        )
        curves[:, :, 0, 3] = 0.9
        self.assertFalse(
            grand_mean_curve_has_no_reversal(
                curves, ["decreasing"]
            )
        )

        raw = np.array([0.1] * 18 + [-0.01, -0.02])
        gate = round9_axis_gate(raw, [0.01, 0.20], True)
        self.assertTrue(gate["passed"])
        self.assertEqual(gate["positive_map_count"], 18)
        raw[17] = -0.01
        gate = round9_axis_gate(raw, [0.01, 0.20], True)
        self.assertFalse(gate["passed"])
        self.assertEqual(gate["positive_map_count"], 17)

        gate = round9_axis_gate(
            np.full(20, 0.1), [0.0, 0.20], True
        )
        self.assertFalse(gate["passed"])
        gate = round9_axis_gate(
            np.full(20, 0.1), [0.01, 0.20], False
        )
        self.assertFalse(gate["passed"])


if __name__ == "__main__":
    unittest.main()
