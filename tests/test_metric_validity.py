import unittest

import numpy as np

from arsc_eval.metric_validity import (
    binary_auroc,
    compare_risk_curves,
    confidence_scores,
    predicted_state_probabilities,
    selective_metrics_from_confidence,
)


class MetricValidityTests(unittest.TestCase):
    def test_predicted_state_confidence(self):
        probabilities = np.array([[0.9, 0.2], [0.4, 0.6]])
        expected = np.array([[0.9, 0.8], [0.6, 0.6]])
        np.testing.assert_allclose(
            predicted_state_probabilities(probabilities, 0.5),
            expected,
        )
        np.testing.assert_allclose(
            confidence_scores(
                probabilities,
                0.5,
                "minimum_predicted_state_probability",
            ),
            [0.8, 0.6],
        )

    def test_binary_auroc_handles_ties(self):
        self.assertEqual(
            binary_auroc(np.array([0, 1]), np.array([0.0, 1.0])),
            1.0,
        )
        self.assertEqual(
            binary_auroc(np.array([0, 1]), np.array([1.0, 0.0])),
            0.0,
        )
        self.assertEqual(
            binary_auroc(np.array([0, 1]), np.array([0.5, 0.5])),
            0.5,
        )

    def test_selective_metrics_perfect_ordering(self):
        targets = np.array([[1, 0], [1, 0], [0, 1], [0, 1]])
        probabilities = np.array(
            [[0.9, 0.1], [0.8, 0.2], [0.8, 0.2], [0.1, 0.9]]
        )
        confidence = np.array([0.9, 0.8, 0.1, 0.9])
        metrics = selective_metrics_from_confidence(
            targets, probabilities, confidence, 0.5
        )
        self.assertEqual(metrics["correctness_auroc"], 1.0)
        self.assertLess(
            metrics["highest_confidence_decile_error_rate"],
            metrics["lowest_confidence_decile_error_rate"],
        )

    def test_curve_crossing_and_dominance(self):
        dominance = compare_risk_curves(
            np.array([0.0, 0.1, 0.2]),
            np.array([0.1, 0.2, 0.3]),
        )
        self.assertTrue(dominance["strict_first_dominance"])
        crossing = compare_risk_curves(
            np.array([0.0, 0.3, 0.1]),
            np.array([0.1, 0.2, 0.2]),
        )
        self.assertEqual(crossing["direction_crossings"], 2)


if __name__ == "__main__":
    unittest.main()
