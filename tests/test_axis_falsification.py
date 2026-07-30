import unittest

import numpy as np

from arsc_eval.axis_falsification import (
    action_pairing_estimates,
    confidence_control_scores,
    crossed_bootstrap_draw,
    cyclic_source_indices,
    f1_control_estimates,
    fixed_random_scores,
    intervene_targets,
    rationale_pairing_estimates,
    safety_control_estimates,
    shifted_column_sources,
)


class AxisFalsificationTests(unittest.TestCase):
    def test_crossed_bootstrap_returns_one_shared_image_draw(self):
        selected_seeds, shared_images = crossed_bootstrap_draw(
            np.random.default_rng(99), [43, 44, 45, 46, 47], 12
        )
        self.assertEqual(selected_seeds.shape, (5,))
        self.assertEqual(shared_images.shape, (12,))
        self.assertTrue(np.all((shared_images >= 0) & (shared_images < 12)))
        # The API exposes one image multiset, not one independent draw per seed.
        self.assertEqual(shared_images.ndim, 1)

    def test_frozen_maps_are_derangements_and_compose(self):
        targets = np.arange(24).reshape(6, 4)
        rows = cyclic_source_indices(6, 1)
        columns = shifted_column_sources(4, 1)
        self.assertTrue(np.all(rows != np.arange(6)))
        self.assertTrue(np.all(columns != np.arange(4)))
        expected = targets[rows][:, columns]
        np.testing.assert_array_equal(
            intervene_targets(targets, rows, columns), expected
        )

    def test_f1_perfect_control_is_exact_and_destruction_responds(self):
        targets = np.array(
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 1, 0, 0],
                [0, 0, 1, 1],
            ],
            dtype=np.float64,
        )
        probabilities = np.where(targets > 0.5, 0.9, 0.1)
        result = f1_control_estimates(
            targets,
            probabilities,
            ["a", "b", "c", "d"],
            cyclic_source_indices(len(targets), 3),
            shifted_column_sources(targets.shape[1], 1),
            0.5,
        )
        self.assertEqual(result["perfect"]["macro_f1"], 1.0)
        self.assertEqual(result["perfect"]["micro_f1"], 1.0)
        self.assertEqual(result["original"]["macro_f1"], 1.0)
        self.assertLess(
            result["row_and_class_destroyed"]["macro_f1"],
            result["original"]["macro_f1"],
        )

    def test_confidence_controls_preserve_errors_and_are_extremal(self):
        targets = np.array(
            [
                [1, 0],
                [1, 0],
                [0, 1],
                [0, 1],
                [1, 1],
                [0, 0],
            ],
            dtype=np.float64,
        )
        probabilities = np.array(
            [
                [0.9, 0.1],
                [0.4, 0.2],
                [0.2, 0.8],
                [0.7, 0.8],
                [0.8, 0.7],
                [0.6, 0.2],
            ],
            dtype=np.float64,
        )
        random_scores = fixed_random_scores(len(targets), 123)
        errors, scores = confidence_control_scores(
            targets, probabilities, random_scores, 0.5
        )
        self.assertEqual(int(errors.sum()), 3)
        self.assertTrue(
            np.all(scores["oracle"][errors == 0] > 0.5)
        )
        self.assertTrue(
            np.all(scores["oracle"][errors == 1] < 0.5)
        )
        self.assertTrue(
            np.all(scores["adversarial"][errors == 1] > 0.5)
        )
        result = safety_control_estimates(
            targets, probabilities, random_scores, 0.5
        )
        hashes = {
            values["prediction_sha256"] for values in result.values()
        }
        error_hashes = {
            values["exact_set_error_sha256"]
            for values in result.values()
        }
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(error_hashes), 1)
        aurcs = {name: values["aurc"] for name, values in result.items()}
        self.assertLessEqual(
            aurcs["oracle"], min(aurcs["original"], aurcs["random"])
        )
        self.assertGreaterEqual(
            aurcs["adversarial"],
            max(aurcs["original"], aurcs["random"]),
        )
        self.assertGreater(aurcs["adversarial"], aurcs["oracle"])

    def test_pairing_identity_and_wrong_pairing_controls(self):
        clean = np.array(
            [
                [0.9, 0.1],
                [0.1, 0.9],
                [0.9, 0.9],
                [0.1, 0.1],
            ]
        )
        perturbed = {
            "brightness": clean.copy(),
            "blur": clean.copy(),
            "noise": clean.copy(),
        }
        wrong = cyclic_source_indices(len(clean), 1)
        action = action_pairing_estimates(
            clean, perturbed, wrong, 0.5
        )
        rationale = rationale_pairing_estimates(
            clean, perturbed, wrong, 0.5
        )
        self.assertEqual(action["identity"]["self"], 0.0)
        self.assertEqual(rationale["identity"]["self"], 1.0)
        self.assertEqual(action["correct"]["mean_three"], 0.0)
        self.assertEqual(rationale["correct"]["mean_three"], 1.0)
        self.assertGreater(action["primary_contrast"], 0.0)
        self.assertGreater(rationale["primary_contrast"], 0.0)


if __name__ == "__main__":
    unittest.main()
