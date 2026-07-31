import unittest

import numpy as np

from arsc_eval.association_components import expand_component_draw
from arsc_eval.graded_response import (
    graded_axis_curves,
    tie_averaged_aurc,
)
from arsc_eval.multimap_statistics import (
    confidence_group_ids,
    curves_from_component_counts,
    grouped_tie_averaged_aurc,
    harmonic_numbers,
    prepare_component_statistics,
)


class MultiMapStatisticsTests(unittest.TestCase):
    def test_weighted_grouped_tie_aurc_matches_explicit_repetition(self):
        errors = np.array([0, 1, 1, 0, 1], dtype=np.uint8)
        confidence = np.array([0.9, 0.9, 0.4, 0.2, 0.2])
        weights = np.array([2, 2, 0, 3, 3], dtype=np.int64)
        groups, count = confidence_group_ids(confidence)
        observed = grouped_tie_averaged_aurc(
            errors,
            groups,
            count,
            weights,
            harmonic_numbers(int(weights.sum())),
        )
        repeated = np.repeat(np.arange(len(errors)), weights)
        expected = tie_averaged_aurc(
            errors[repeated], confidence[repeated]
        )
        self.assertAlmostEqual(observed, expected, places=14)

    def test_component_statistics_match_explicit_complete_draw(self):
        rng = np.random.default_rng(19)
        sample_count = 8
        identity = np.arange(sample_count)
        maps = np.stack(
            [
                identity,
                np.array([1, 0, 2, 3, 4, 5, 6, 7]),
                np.array([1, 0, 3, 2, 4, 5, 6, 7]),
                np.array([1, 0, 3, 2, 5, 4, 6, 7]),
                np.array([1, 0, 3, 2, 5, 4, 7, 6]),
            ]
        )
        component_ids = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        offsets = np.array([0, 4, 8])
        flat = np.arange(sample_count)
        action_targets = rng.integers(0, 2, size=(sample_count, 4))
        rationale_targets = rng.integers(
            0, 2, size=(sample_count, 21)
        )
        primitive = {
            "action_targets": action_targets,
            "rationale_targets": rationale_targets,
            "action_predictions": {},
            "exact_set_errors": {},
            "confidence": {},
            "action_perturbed_predictions": {
                name: {} for name in ("brightness", "blur", "noise")
            },
            "rationale_predictions": rng.integers(
                0, 2, size=(sample_count, 21)
            ),
            "rationale_perturbed_predictions": {},
        }
        for model in ("action_only", "joint"):
            prediction = rng.integers(0, 2, size=(sample_count, 4))
            primitive["action_predictions"][model] = prediction
            primitive["exact_set_errors"][model] = np.any(
                prediction != action_targets, axis=1
            ).astype(np.uint8)
            primitive["confidence"][model] = np.array(
                [0.9, 0.9, 0.7, 0.6, 0.5, 0.5, 0.2, 0.1]
            )
            for perturbation in ("brightness", "blur", "noise"):
                primitive["action_perturbed_predictions"][perturbation][
                    model
                ] = rng.integers(0, 2, size=(sample_count, 4))
        for perturbation in ("brightness", "blur", "noise"):
            primitive["rationale_perturbed_predictions"][perturbation] = (
                rng.integers(0, 2, size=(sample_count, 21))
            )

        prepared = prepare_component_statistics(
            primitive, maps, offsets, flat, component_ids
        )
        selected = np.array([0, 0, 1], dtype=np.int64)
        counts = np.bincount(selected, minlength=2)
        expanded = expand_component_draw(selected, offsets, flat)
        observed = curves_from_component_counts(
            prepared, counts, harmonic_numbers(12)
        )
        expected = graded_axis_curves(primitive, maps, expanded)
        for axis in ("A", "R", "S", "C1"):
            np.testing.assert_allclose(
                observed[axis], expected[axis], atol=1e-14, rtol=0.0
            )


if __name__ == "__main__":
    unittest.main()
