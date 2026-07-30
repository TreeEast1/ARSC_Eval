import unittest

import numpy as np

from arsc_eval.association_components import (
    build_association_components,
    expand_component_draw,
    pack_members,
    shared_component_bootstrap_draw,
    validate_association_components,
)


class AssociationComponentTests(unittest.TestCase):
    def setUp(self):
        self.clip_ids = np.array([0, 0, 1, 2, 3, 3])
        self.q0 = np.arange(6)
        self.q1 = np.array([2, 3, 0, 1, 5, 4])

    def test_components_are_deterministic_dyadic_closure(self):
        by_clip, by_image = build_association_components(
            self.clip_ids, self.q1
        )
        np.testing.assert_array_equal(by_clip, [0, 0, 0, 1])
        np.testing.assert_array_equal(by_image, [0, 0, 0, 0, 1, 1])
        audit = validate_association_components(
            self.clip_ids,
            {"q0": self.q0, "q1": self.q1},
            by_clip,
            by_image,
        )
        self.assertTrue(audit["all_maps_passed"])
        self.assertEqual(audit["component_count"], 2)
        self.assertEqual(audit["clip_count_histogram"], {"1": 1, "3": 1})
        self.assertEqual(audit["image_count_histogram"], {"2": 1, "4": 1})

    def test_pack_and_repeated_draw_keep_complete_membership(self):
        _, by_image = build_association_components(
            self.clip_ids, self.q1
        )
        offsets, images = pack_members(by_image)
        expanded = expand_component_draw(
            np.array([1, 0, 1]), offsets, images
        )
        np.testing.assert_array_equal(expanded, [4, 5, 0, 1, 2, 3, 4, 5])

    def test_bootstrap_uses_one_shared_component_draw(self):
        _, by_image = build_association_components(
            self.clip_ids, self.q1
        )
        offsets, images = pack_members(by_image)
        selected_seeds, selected_components, shared_images = (
            shared_component_bootstrap_draw(
                np.random.default_rng(123), 5, offsets, images
            )
        )
        self.assertEqual(len(selected_seeds), 5)
        self.assertEqual(len(selected_components), 2)
        np.testing.assert_array_equal(
            shared_images,
            expand_component_draw(selected_components, offsets, images),
        )

    def test_invalid_nonbijection_is_rejected(self):
        with self.assertRaises(ValueError):
            build_association_components(
                self.clip_ids, np.array([0, 0, 1, 2, 3, 4])
            )


if __name__ == "__main__":
    unittest.main()
