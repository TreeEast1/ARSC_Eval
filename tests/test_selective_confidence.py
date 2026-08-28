"""Deterministic tests for the S-axis confidence construct audit."""

from __future__ import annotations

import unittest

import numpy as np

from arsc_eval.internal_validity import selective_metrics
from arsc_eval.selective_confidence import (
    CONFIDENCE_IDS,
    audit_selective_metrics,
    confidence_s0,
    confidence_s1,
    confidence_s2,
    confidence_scores,
    exact_set_error_vector,
    expected_calibration_error,
    selective_metrics_from_confidence,
)


class ConfidenceConstructionTests(unittest.TestCase):
    def test_s0_is_the_row_maximum(self) -> None:
        probabilities = np.array([[0.9, 0.2, 0.4, 0.1], [0.3, 0.3, 0.45, 0.2]])
        np.testing.assert_allclose(
            confidence_s0(probabilities), [0.9, 0.45]
        )

    def test_s1_multiplies_the_predicted_state_probabilities(self) -> None:
        # Row 0 predicts (1, 0, 0, 0) at threshold 0.5.
        probabilities = np.array([[0.9, 0.2, 0.4, 0.1]])
        expected = 0.9 * 0.8 * 0.6 * 0.9
        np.testing.assert_allclose(confidence_s1(probabilities), [expected])

    def test_s1_matches_a_direct_product_in_log_space(self) -> None:
        rng = np.random.default_rng(11)
        probabilities = rng.uniform(0.01, 0.99, size=(64, 4))
        predicted = probabilities >= 0.5
        matched = np.where(predicted, probabilities, 1.0 - probabilities)
        np.testing.assert_allclose(
            confidence_s1(probabilities), matched.prod(axis=1), rtol=1e-12
        )

    def test_s1_is_numerically_safe_for_extreme_probabilities(self) -> None:
        probabilities = np.array([[1.0, 0.0, 1.0, 0.0], [0.5, 0.5, 0.5, 0.5]])
        confidence = confidence_s1(probabilities)
        self.assertTrue(np.all(np.isfinite(confidence)))
        # A fully certain, self-consistent prediction has confidence one.
        np.testing.assert_allclose(confidence[0], 1.0)
        np.testing.assert_allclose(confidence[1], 0.0625)

    def test_s2_is_the_weakest_bit_certainty(self) -> None:
        probabilities = np.array([[0.9, 0.2, 0.4, 0.1], [0.99, 0.98, 0.55, 0.01]])
        np.testing.assert_allclose(confidence_s2(probabilities), [0.6, 0.55])

    def test_s2_is_bounded_below_by_one_half(self) -> None:
        rng = np.random.default_rng(3)
        probabilities = rng.uniform(0.0, 1.0, size=(256, 4))
        self.assertTrue(np.all(confidence_s2(probabilities) >= 0.5))

    def test_s1_never_exceeds_s2(self) -> None:
        # The product over four matched-state probabilities cannot exceed the
        # smallest of them, which is exactly the weakest-bit certainty.
        rng = np.random.default_rng(5)
        probabilities = rng.uniform(0.0, 1.0, size=(256, 4))
        self.assertTrue(
            np.all(confidence_s1(probabilities) <= confidence_s2(probabilities) + 1e-12)
        )

    def test_dispatch_rejects_unregistered_constructions(self) -> None:
        probabilities = np.array([[0.6, 0.4, 0.4, 0.4]])
        for construction in CONFIDENCE_IDS:
            self.assertEqual(
                confidence_scores(construction, probabilities).shape, (1,)
            )
        with self.assertRaises(ValueError):
            confidence_scores("S3", probabilities)


class ExactSetErrorTests(unittest.TestCase):
    def test_any_wrong_bit_is_an_error(self) -> None:
        targets = np.array([[1, 0, 0, 0], [1, 1, 0, 0], [0, 0, 0, 0]])
        probabilities = np.array(
            [[0.9, 0.1, 0.1, 0.1], [0.9, 0.1, 0.1, 0.1], [0.1, 0.1, 0.1, 0.1]]
        )
        np.testing.assert_allclose(
            exact_set_error_vector(targets, probabilities), [0.0, 1.0, 0.0]
        )

    def test_error_vector_is_invariant_to_positive_temperature(self) -> None:
        # Temperature scaling cannot move a probability across 0.5, so the
        # audited error set is shared by all three constructions.
        rng = np.random.default_rng(7)
        logits = rng.normal(scale=3.0, size=(512, 4))
        targets = (rng.uniform(size=(512, 4)) > 0.5).astype(np.float64)
        for temperature in (0.5, 1.0, 2.58642840385437, 10.0):
            scaled = 1.0 / (1.0 + np.exp(-logits / temperature))
            np.testing.assert_array_equal(
                exact_set_error_vector(targets, scaled),
                exact_set_error_vector(targets, 1.0 / (1.0 + np.exp(-logits))),
            )


class SelectiveMetricAgreementTests(unittest.TestCase):
    """The audit harness must reproduce the frozen S0 implementation."""

    def test_s0_matches_frozen_selective_metrics(self) -> None:
        rng = np.random.default_rng(20260731)
        probabilities = rng.uniform(size=(1024, 4))
        targets = (rng.uniform(size=(1024, 4)) > 0.5).astype(np.float64)

        frozen = selective_metrics(targets, probabilities, 0.5)
        errors = exact_set_error_vector(targets, probabilities, 0.5)
        audited = selective_metrics_from_confidence(
            errors, confidence_s0(probabilities), 15
        )
        for metric in ("aurc", "unsafe_acceptance_rate_90", "ece"):
            self.assertAlmostEqual(frozen[metric], audited[metric], places=12)

    def test_aurc_is_zero_when_no_sample_is_wrong(self) -> None:
        errors = np.zeros(32)
        confidence = np.linspace(0.1, 0.9, 32)
        metrics = selective_metrics_from_confidence(errors, confidence)
        self.assertAlmostEqual(metrics["aurc"], 0.0)
        self.assertAlmostEqual(metrics["unsafe_acceptance_rate_90"], 0.0)

    def test_perfect_ranking_beats_inverted_ranking(self) -> None:
        errors = np.array([0.0] * 50 + [1.0] * 50)
        good = np.linspace(1.0, 0.0, 100)  # confident where correct
        bad = np.linspace(0.0, 1.0, 100)  # confident where wrong
        self.assertLess(
            selective_metrics_from_confidence(errors, good)["aurc"],
            selective_metrics_from_confidence(errors, bad)["aurc"],
        )

    def test_ece_is_zero_for_a_perfectly_calibrated_split(self) -> None:
        # Two bins, each with confidence equal to its empirical accuracy.
        confidence = np.array([0.9] * 100 + [0.3] * 100)
        errors = np.array([0.0] * 90 + [1.0] * 10 + [0.0] * 30 + [1.0] * 70)
        self.assertAlmostEqual(
            expected_calibration_error(confidence, errors), 0.0, places=12
        )

    def test_rejects_misaligned_inputs(self) -> None:
        with self.assertRaises(ValueError):
            selective_metrics_from_confidence(np.zeros(4), np.zeros(5))
        with self.assertRaises(ValueError):
            selective_metrics_from_confidence(np.zeros(0), np.zeros(0))


class AuditWrapperTests(unittest.TestCase):
    def test_audit_reports_every_registered_construction(self) -> None:
        rng = np.random.default_rng(2)
        probabilities = rng.uniform(size=(128, 4))
        targets = (rng.uniform(size=(128, 4)) > 0.5).astype(np.float64)
        result = audit_selective_metrics(targets, probabilities)
        self.assertEqual(result["sample_count"], 128)
        for construction in CONFIDENCE_IDS:
            self.assertIn("aurc", result[construction])
            self.assertIn("ece", result[construction])
        self.assertEqual(result["S0"]["role"], "frozen_primary")
        self.assertEqual(result["S1"]["role"], "construct_audit_alternative")
        self.assertEqual(result["S2"]["role"], "construct_audit_alternative")

    def test_all_constructions_share_one_error_rate(self) -> None:
        rng = np.random.default_rng(4)
        probabilities = rng.uniform(size=(64, 4))
        targets = (rng.uniform(size=(64, 4)) > 0.5).astype(np.float64)
        result = audit_selective_metrics(targets, probabilities)
        expected = float(
            exact_set_error_vector(targets, probabilities).mean()
        )
        self.assertAlmostEqual(result["exact_set_error_rate"], expected)


if __name__ == "__main__":
    unittest.main()
