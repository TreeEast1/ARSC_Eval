import unittest
import pickle

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from arsc_eval.data import deterministic_noise, make_benign_perturbation


class DataPerturbationTests(unittest.TestCase):
    def setUp(self):
        pixels = np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3)
        self.image = Image.fromarray(pixels)

    def test_noise_is_deterministic_by_file_name(self):
        transform = make_benign_perturbation(
            "noise", 1.1, 1.0, 5.0, 20260731
        )
        first = np.asarray(transform(self.image, "same.jpg"))
        second = np.asarray(transform(self.image, "same.jpg"))
        other = np.asarray(transform(self.image, "other.jpg"))
        np.testing.assert_array_equal(first, second)
        self.assertFalse(np.array_equal(first, other))

    def test_identity_parameters_preserve_pixels_in_memory(self):
        brightness = make_benign_perturbation(
            "brightness", 1.0, 0.0, 0.0, 20260731
        )
        blur = make_benign_perturbation(
            "blur", 1.0, 0.0, 0.0, 20260731
        )
        noise = make_benign_perturbation(
            "noise", 1.0, 0.0, 0.0, 20260731
        )
        original = np.asarray(self.image)
        np.testing.assert_array_equal(
            np.asarray(brightness(self.image, "a.jpg")), original
        )
        np.testing.assert_array_equal(
            np.asarray(blur(self.image, "a.jpg")), original
        )
        np.testing.assert_array_equal(
            np.asarray(noise(self.image, "a.jpg")), original
        )

    def test_transform_is_pickle_safe_and_pixel_equivalent(self):
        settings = (1.1, 1.0, 5.0, 20260731)
        for kind in ("brightness", "blur", "noise"):
            transform = make_benign_perturbation(kind, *settings)
            restored = pickle.loads(pickle.dumps(transform))
            self.assertEqual(restored, transform)
            actual = np.asarray(restored(self.image, "sample.jpg"))
            self.assertEqual(
                restored(self.image, "sample.jpg").mode, self.image.mode
            )
            self.assertEqual(
                restored(self.image, "sample.jpg").size, self.image.size
            )
            if kind == "brightness":
                expected_image = ImageEnhance.Brightness(
                    self.image
                ).enhance(settings[0])
            elif kind == "blur":
                expected_image = self.image.filter(
                    ImageFilter.GaussianBlur(radius=settings[1])
                )
            else:
                expected_image = deterministic_noise(
                    self.image,
                    "sample.jpg",
                    settings[2],
                    settings[3],
                )
            np.testing.assert_array_equal(
                actual, np.asarray(expected_image)
            )
            self.assertEqual(actual.dtype, np.uint8)

    def test_configured_transforms_match_reference_on_two_boundary_images(self):
        images = [
            (
                Image.fromarray(
                    np.array(
                        [
                            [[0, 0, 0], [255, 255, 255]],
                            [[1, 254, 127], [250, 5, 128]],
                        ],
                        dtype=np.uint8,
                    )
                ),
                "boundary_a.jpg",
            ),
            (self.image, "gradient_b.jpg"),
        ]
        settings = (1.1, 1.0, 5.0, 20260731)
        for image, file_name in images:
            for kind in ("brightness", "blur", "noise"):
                transform = make_benign_perturbation(kind, *settings)
                actual = transform(image, file_name)
                if kind == "brightness":
                    expected = ImageEnhance.Brightness(image).enhance(
                        settings[0]
                    )
                elif kind == "blur":
                    expected = image.filter(
                        ImageFilter.GaussianBlur(radius=settings[1])
                    )
                else:
                    expected = deterministic_noise(
                        image,
                        file_name,
                        settings[2],
                        settings[3],
                    )
                self.assertEqual(actual.mode, expected.mode)
                self.assertEqual(actual.size, expected.size)
                np.testing.assert_array_equal(
                    np.asarray(actual), np.asarray(expected)
                )


if __name__ == "__main__":
    unittest.main()
