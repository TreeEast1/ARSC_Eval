"""Small deterministic tests for the internal-validity estimands."""

from __future__ import annotations

import unittest

import numpy as np

from arsc_eval.internal_validity import (
    MODEL_ACTION,
    MODEL_CALIBRATED,
    MODEL_JOINT,
    causal_gap_samples,
    correct_action_state_probability,
    mask_metric_estimates,
    paired_bootstrap,
    prepare_probabilities,
    selective_metrics,
    summarize_families,
    test_metric_estimates as compute_test_metric_estimates,
)


class InternalValidityTests(unittest.TestCase):
    def test_causal_gap_clean_term_cancels(self) -> None:
        targets = np.array([[1, 0], [0, 1]], dtype=np.float64)
        clean = np.array([[0.9, 0.1], [0.2, 0.8]])
        critical = np.array([[0.5, 0.1], [0.2, 0.5]])
        noncritical = np.array([[0.8, 0.1], [0.2, 0.7]])
        components = causal_gap_samples(
            targets, clean, critical, noncritical
        )
        np.testing.assert_allclose(
            components["causal_evidence_gap"], [0.3, 0.2]
        )
        np.testing.assert_allclose(
            components["causal_evidence_gap"],
            np.array([0.8, 0.7]) - np.array([0.5, 0.5]),
        )

    def test_rationale_bound_negative_action_state(self) -> None:
        targets = np.array([[1, 0], [0, 1]], dtype=np.float64)
        probabilities = np.array([[0.8, 0.2], [0.7, 0.6]])
        action_mask = np.array([[0, 1], [1, 0]], dtype=bool)
        np.testing.assert_allclose(
            correct_action_state_probability(
                targets, probabilities, action_mask
            ),
            [0.8, 0.3],
        )

    def test_selective_metrics_perfect_predictions(self) -> None:
        targets = np.array([[1, 0], [0, 1]], dtype=np.float64)
        probabilities = np.array([[0.9, 0.1], [0.2, 0.8]])
        metrics = selective_metrics(targets, probabilities, threshold=0.5)
        self.assertEqual(metrics["aurc"], 0.0)
        self.assertEqual(metrics["unsafe_acceptance_rate_90"], 0.0)

    def test_paired_identical_models_have_zero_contrast(self) -> None:
        values = np.array([0.0, 1.0, 1.0, 0.0])
        action_key = ("cohort", "condition", "metric", MODEL_ACTION)
        joint_key = ("cohort", "condition", "metric", MODEL_JOINT)

        def compute(indices: np.ndarray | None):
            selected = values if indices is None else values[indices]
            estimate = float(selected.mean())
            return {action_key: estimate, joint_key: estimate}

        estimates, draws = paired_bootstrap(
            compute,
            sample_count=len(values),
            replicates=100,
            rng=np.random.default_rng(7),
        )
        families = summarize_families(
            estimates,
            draws,
            {("cohort", "condition"): len(values)},
            confidence_level=0.95,
        )
        contrast = families[0]["paired_contrasts"][0]
        self.assertEqual(contrast["estimate"], 0.0)
        self.assertEqual(contrast["ci_lower"], 0.0)
        self.assertEqual(contrast["ci_upper"], 0.0)

    def test_cache_schema_reaches_action_only_ceg(self) -> None:
        action_targets = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0], [1, 0, 1, 0]],
            dtype=np.float32,
        )
        rationale_targets = np.array(
            [[1, 0], [0, 1], [1, 1]], dtype=np.float32
        )
        clean_action = np.array(
            [[2.0, -2.0, -2.0, -2.0], [-2.0, 2.0, -2.0, -2.0],
             [2.0, -2.0, 2.0, -2.0]],
            dtype=np.float32,
        )
        clean_joint = clean_action + 0.2
        clean_rationale = np.array(
            [[2.0, -2.0], [-2.0, 2.0], [2.0, 2.0]], dtype=np.float32
        )
        cache = {
            "test_action_targets": action_targets,
            "test_rationale_targets": rationale_targets,
            "test_clean_action_logits": clean_action,
            "test_clean_joint_action_logits": clean_joint,
            "test_clean_joint_rationale_logits": clean_rationale,
            "mask_action_targets": action_targets,
        }
        for perturbation in ("brightness", "blur", "noise"):
            cache[f"test_{perturbation}_action_logits"] = clean_action - 0.1
            cache[f"test_{perturbation}_joint_action_logits"] = (
                clean_joint - 0.1
            )
            cache[f"test_{perturbation}_joint_rationale_logits"] = (
                clean_rationale - 0.1
            )
        for condition, offset in (
            ("clean", 0.0),
            ("critical", -0.8),
            ("noncritical", -0.2),
        ):
            cache[f"mask_{condition}_action_logits"] = clean_action + offset
            cache[f"mask_{condition}_joint_action_logits"] = (
                clean_joint + offset
            )

        prepared = prepare_probabilities(
            cache, temperature=1.5, threshold=0.5
        )
        test_estimates = compute_test_metric_estimates(
            prepared, threshold=0.5
        )
        mask_estimates = mask_metric_estimates(prepared)
        self.assertIn(
            ("clean", "official_test", "action_macro_f1", MODEL_CALIBRATED),
            test_estimates,
        )
        self.assertIn(
            (
                "critical_masks",
                "detector_subset",
                "causal_evidence_gap",
                MODEL_ACTION,
            ),
            mask_estimates,
        )


if __name__ == "__main__":
    unittest.main()
