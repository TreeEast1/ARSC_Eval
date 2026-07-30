import unittest
from itertools import permutations

import numpy as np

from arsc_eval.graded_response import (
    axis_bottlenecks,
    bottleneck_statistic,
    confidence_diagnostics,
    graded_axis_curves,
    mean_curve_checks,
    mean_curves_have_no_reversal,
    mean_selected_seed_bottlenecks,
    stable_aurc,
    tie_averaged_aurc,
)


class GradedResponseTests(unittest.TestCase):
    def test_tie_averaged_aurc_matches_brute_force(self):
        errors = np.array([0.0, 1.0, 1.0])
        confidence = np.array([0.9, 0.9, 0.2])
        brute_force = []
        for tied_order in permutations((0, 1)):
            order = np.array([*tied_order, 2])
            risk = np.cumsum(errors[order]) / np.arange(1, 4)
            brute_force.append(float(risk.mean()))
        self.assertAlmostEqual(
            tie_averaged_aurc(errors, confidence),
            float(np.mean(brute_force)),
        )

    def test_tie_average_matches_stable_without_ties(self):
        errors = np.array([0.0, 1.0, 0.0, 1.0])
        confidence = np.array([0.9, 0.8, 0.7, 0.6])
        self.assertEqual(
            tie_averaged_aurc(errors, confidence),
            stable_aurc(errors, confidence),
        )

    def test_confidence_diagnostics_split_tie_conventions(self):
        errors = np.array([1.0, 0.0, 0.0])
        confidence = np.array([0.9, 0.9, 0.2])
        diagnostics = confidence_diagnostics(errors, confidence)
        self.assertEqual(
            diagnostics["canonical_stable_aurc"],
            stable_aurc(errors, confidence),
        )
        self.assertEqual(
            diagnostics["tie_averaged_aurc"],
            tie_averaged_aurc(errors, confidence),
        )
        self.assertNotEqual(
            diagnostics["canonical_stable_aurc"],
            diagnostics["tie_averaged_aurc"],
        )

    def test_bottleneck_combines_mixed_directions(self):
        curves = [
            [1.0, 0.8, 0.6, 0.4, 0.2],
            [0.0, 0.1, 0.3, 0.6, 1.0],
        ]
        self.assertAlmostEqual(
            bottleneck_statistic(
                curves, ["decreasing", "increasing"]
            ),
            0.1,
        )
        curves[1][2] = 0.05
        self.assertLess(
            bottleneck_statistic(
                curves, ["decreasing", "increasing"]
            ),
            0.0,
        )

    def test_mean_curve_reversal_check(self):
        curves = [
            [[1.0, 0.8, 0.6, 0.4, 0.2]],
            [[0.9, 0.7, 0.5, 0.3, 0.1]],
        ]
        self.assertTrue(
            mean_curves_have_no_reversal(curves, ["decreasing"])
        )
        curves[1][0][3] = 0.8
        self.assertFalse(
            mean_curves_have_no_reversal(curves, ["decreasing"])
        )

    def test_per_seed_bottleneck_is_taken_before_seed_mean(self):
        first = {
            "A": np.array([[1.0, 0.9, 0.8, 0.7, 0.6]] * 2),
            "R": np.array([[1.0, 0.9, 0.8, 0.7, 0.6]]),
            "S": np.array([[0.0, 0.1, 0.2, 0.3, 0.4]] * 2),
            "C1": np.array(
                [
                    [0.0, 0.1, 0.2, 0.3, 0.4],
                    [0.0, 0.1, 0.2, 0.3, 0.4],
                    [1.0, 0.9, 0.8, 0.7, 0.6],
                ]
            ),
        }
        second = {axis: values.copy() for axis, values in first.items()}
        first["R"][0] = [1.0, 0.99, 0.79, 0.59, 0.39]
        second["R"][0] = [1.0, 0.8, 0.79, 0.59, 0.39]
        result = mean_selected_seed_bottlenecks(
            [first, second], np.array([0, 1])
        )
        self.assertAlmostEqual(result["R"], 0.01)
        mean_curve_bottleneck = bottleneck_statistic(
            np.mean([first["R"], second["R"]], axis=0),
            ["decreasing"],
        )
        self.assertGreater(mean_curve_bottleneck, result["R"])

    def test_graded_axis_curve_shapes_and_identity_q0(self):
        targets_a = np.array(
            [[1, 0], [0, 1], [1, 1], [0, 0]], dtype=bool
        )
        targets_r = np.array(
            [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]],
            dtype=bool,
        )
        action_only = targets_a.copy()
        joint = targets_a.copy()
        rationale = targets_r.copy()
        source_maps = np.array(
            [
                [0, 1, 2, 3],
                [1, 0, 3, 2],
                [1, 0, 3, 2],
                [1, 0, 3, 2],
                [1, 0, 3, 2],
            ]
        )
        prepared = {
            "action_targets": targets_a,
            "rationale_targets": targets_r,
            "action_predictions": {
                "action_only": action_only,
                "joint": joint,
            },
            "rationale_predictions": rationale,
            "exact_set_errors": {
                "action_only": np.zeros(4),
                "joint": np.zeros(4),
            },
            "confidence": {
                "action_only": np.array([0.9, 0.8, 0.7, 0.6]),
                "joint": np.array([0.9, 0.8, 0.7, 0.6]),
            },
            "action_perturbed_predictions": {
                perturbation: {
                    "action_only": action_only,
                    "joint": joint,
                }
                for perturbation in ("brightness", "blur", "noise")
            },
            "rationale_perturbed_predictions": {
                perturbation: rationale
                for perturbation in ("brightness", "blur", "noise")
            },
        }
        curves = graded_axis_curves(prepared, source_maps)
        self.assertEqual(curves["A"].shape, (2, 5))
        self.assertEqual(curves["R"].shape, (1, 5))
        self.assertEqual(curves["S"].shape, (2, 5))
        self.assertEqual(curves["C1"].shape, (3, 5))
        np.testing.assert_array_equal(curves["A"][:, 0], [1.0, 1.0])
        np.testing.assert_array_equal(curves["R"][:, 0], [1.0])
        np.testing.assert_array_equal(curves["C1"][:, 0], [0.0, 0.0, 1.0])
        self.assertEqual(set(axis_bottlenecks(curves)), {"A", "R", "S", "C1"})
        self.assertEqual(set(mean_curve_checks([curves])), {"A", "R", "S", "C1"})

    def test_c1_mean_three_uses_round7_scalar_reduction_exactly(self):
        patterns = np.array(
            [
                [0, 0, 1, 1],
                [0, 0, 0, 1],
                [1, 0, 1, 0],
            ],
            dtype=bool,
        )
        expected = float(
            np.mean([float(row.mean()) for row in patterns])
        )
        old_reduction = float(np.mean(patterns, axis=0).mean())
        self.assertNotEqual(expected, old_reduction)

        clean_action = np.zeros((4, 1), dtype=bool)
        clean_rationale = np.ones((4, 1), dtype=bool)
        source_maps = np.tile(np.arange(4), (5, 1))
        prepared = {
            "action_targets": clean_action,
            "rationale_targets": clean_rationale,
            "action_predictions": {
                "action_only": clean_action,
                "joint": clean_action,
            },
            "rationale_predictions": clean_rationale,
            "exact_set_errors": {
                "action_only": np.zeros(4),
                "joint": np.zeros(4),
            },
            "confidence": {
                "action_only": np.array([0.9, 0.8, 0.7, 0.6]),
                "joint": np.array([0.9, 0.8, 0.7, 0.6]),
            },
            "action_perturbed_predictions": {
                perturbation: {
                    "action_only": patterns[index, :, None],
                    "joint": patterns[index, :, None],
                }
                for index, perturbation in enumerate(
                    ("brightness", "blur", "noise")
                )
            },
            "rationale_perturbed_predictions": {
                perturbation: patterns[index, :, None]
                for index, perturbation in enumerate(
                    ("brightness", "blur", "noise")
                )
            },
        }
        curves = graded_axis_curves(prepared, source_maps)
        for model_index in (0, 1):
            self.assertEqual(curves["C1"][model_index, 0], expected)
        self.assertEqual(curves["C1"][2, 0], expected)


if __name__ == "__main__":
    unittest.main()
