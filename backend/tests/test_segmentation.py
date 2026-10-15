"""Precisão numérica, exclusões e propriedades da segmentação inicial."""

import unittest

import cv2
import numpy as np

from backend.src.segmentation import rgb_to_lab, adaptive_clusters, grow_skin
from backend.src.segmentation.skin import ellipse, InsufficientSkinError, facial_masks


class ColorTests(unittest.TestCase):
    def test_reference_colors_d65(self):
        colors = np.array([[0, 0, 0], [255, 255, 255], [255, 0, 0],
                           [0, 255, 0], [0, 0, 255]], np.uint8)
        expected = [[0, 0, 0], [100, 0, 0], [53.2408, 80.0925, 67.2032],
                    [87.7347, -86.1827, 83.1793], [32.2970, 79.1875, -107.8602]]
        np.testing.assert_allclose(rgb_to_lab(colors), expected, atol=0.001)

    def test_float_and_uint8_agree(self):
        rgb = np.array([[[12, 90, 150], [220, 180, 140]]], np.uint8)
        np.testing.assert_allclose(rgb_to_lab(rgb), rgb_to_lab(rgb.astype(float) / 255), atol=1e-5)

    def test_independent_opencv_float_conversion(self):
        rgb = np.random.default_rng(8).integers(0, 256, (40, 40, 3), dtype=np.uint8)
        # OpenCV float usa L* físico; sua tabela de aproximação tem erro pequeno.
        reference = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
        np.testing.assert_allclose(rgb_to_lab(rgb), reference, atol=0.35)

    def test_neutral_grays_and_gamma_boundary(self):
        values = np.array([0, 0.02, 0.04045, 0.04046, 0.5, 1.0])
        lab = rgb_to_lab(np.repeat(values[:, None], 3, axis=1))
        self.assertTrue(np.all(np.diff(lab[:, 0]) > 0))
        np.testing.assert_allclose(lab[:, 1:], 0, atol=0.0001)
        self.assertLess(abs(lab[2, 0] - lab[3, 0]), 0.002)

    def test_invalid_input(self):
        for invalid in [np.empty((0, 3)), np.zeros((3, 4)), np.array([1, 2, 3]),
                        np.array([1.01, 0., 0.]), np.array([np.nan, 0., 0.]), np.array([-0.1, 0., 0.])]:
            with self.subTest(value=str(invalid)):
                with self.assertRaises(ValueError):
                    rgb_to_lab(invalid)


def synthetic_face(color):
    shape = (200, 200)
    rgb = np.full((*shape, 3), (30, 90, 170), np.uint8)
    face = ellipse(shape, (0.5, 0.5), (0.35, 0.39))
    rgb[face] = color
    # Estruturas escuras e cabelo/barba fora das exclusões de olhos/lábios.
    for center in [(0.34, 0.41), (0.66, 0.41)]:
        rgb[ellipse(shape, center, (0.08, 0.03))] = (5, 5, 5)
    rgb[ellipse(shape, (0.5, 0.72), (0.12, 0.04))] = (150, 30, 50)
    beard = ellipse(shape, (0.5, 0.84), (0.20, 0.04)) & face
    hair = ellipse(shape, (0.35, 0.19), (0.08, 0.04)) & face
    rgb[beard | hair] = (3, 3, 3)
    return rgb, beard, hair


class SkinTests(unittest.TestCase):
    def test_light_and_dark_skin_do_not_use_fixed_brightness_cutoff(self):
        for color in [(220, 175, 145), (90, 58, 42)]:
            with self.subTest(color=color):
                rgb, beard, hair = synthetic_face(color)
                lab = rgb_to_lab(rgb)
                masks = facial_masks(rgb, use_landmarks=False)
                clusters = adaptive_clusters(lab, masks)
                result = grow_skin(lab, masks, clusters)
                skin = result["mask"]
                self.assertGreater(skin.sum(), 2000)
                self.assertFalse(np.any(skin & ~masks["face"]))
                self.assertFalse(np.any(skin & masks["excluded"]))
                self.assertLess((skin & beard).sum(), beard.sum() * 0.05)
                self.assertLess((skin & hair).sum(), hair.sum() * 0.05)
                np.testing.assert_allclose(result["mean_lab"], rgb_to_lab(np.array(color, np.uint8)), atol=0.02)

    def test_uniform_dark_skin_is_retained(self):
        rgb = np.full((100, 100, 3), (35, 23, 18), np.uint8)
        masks = facial_masks(rgb, use_landmarks=False)
        lab = rgb_to_lab(rgb)
        clusters = adaptive_clusters(lab, masks)
        self.assertEqual(clusters["k"], 1)
        self.assertGreater(grow_skin(lab, masks, clusters)["mask"].sum(), 1000)

    def test_cluster_count_adapts_to_color_content(self):
        rgb = np.full((100, 100, 3), (200, 150, 100), np.uint8)
        masks = facial_masks(rgb, use_landmarks=False)
        self.assertEqual(adaptive_clusters(rgb_to_lab(rgb), masks)["k"], 1)
        rgb[:, :40] = (120, 150, 210)
        result = adaptive_clusters(rgb_to_lab(rgb), masks)
        self.assertGreater(result["k"], 1)
        self.assertLessEqual(result["k"], 6)

    def test_region_growing_recovers_connected_nearby_color_only(self):
        # Um cluster de pele adjacente é recuperado; uma ilha igual e isolada não.
        lab = np.full((40, 60, 3), [60, 15, 20], np.float32)
        allowed = np.zeros((40, 60), bool)
        allowed[3:35, 3:35] = True
        allowed[3:20, 45:56] = True
        seeds = np.zeros_like(allowed)
        seeds[10:15, 10:15] = True
        labels = np.ones_like(allowed, dtype=int)
        labels[:, :20] = 0
        lab[:, 20:35, 1] += 2
        masks = {"allowed": allowed, "face": allowed, "seeds": seeds}
        result = grow_skin(lab, masks, {"core": seeds, "labels": labels, "skin_cluster": 0})
        self.assertGreater(result["recovered_pixels"], 100)
        self.assertTrue(result["mask"][15, 30])
        self.assertFalse(result["mask"][10, 50])

    def test_small_face_rejected(self):
        with self.assertRaises(InsufficientSkinError):
            facial_masks(np.full((8, 8, 3), 150, np.uint8), use_landmarks=False)

    def test_deterministic_without_global_random_state(self):
        rgb, _, _ = synthetic_face((190, 120, 90))
        masks = facial_masks(rgb, use_landmarks=False)
        first = adaptive_clusters(rgb_to_lab(rgb), masks)
        second = adaptive_clusters(rgb_to_lab(rgb), masks)
        np.testing.assert_array_equal(first["labels"], second["labels"])


if __name__ == "__main__":
    unittest.main()
