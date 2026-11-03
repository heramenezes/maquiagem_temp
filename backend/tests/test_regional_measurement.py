"""Cenas controladas verificam robustez; não comprovam acurácia cosmética."""

import json
import unittest

import numpy as np
from skimage.color import deltaE_ciede2000

from backend.src.segmentation.color import rgb_to_lab
from backend.src.segmentation.semantic import measure_skin
from backend.src.tone_matching.analysis import build_analysis


class RegionalMeasurementTests(unittest.TestCase):
    def measure(self, rgb, mask=None, face=None):
        mask = np.ones(rgb.shape[:2], bool) if mask is None else mask
        face = np.ones(rgb.shape[:2], bool) if face is None else face
        return measure_skin(rgb_to_lab(rgb), mask, rgb=rgb, face_mask=face)

    def test_uniform_light_and_dark_skin_keep_their_color(self):
        for color in ([220, 175, 145], [35, 23, 18]):
            rgb = np.full((200, 200, 3), color, np.uint8)
            skin = self.measure(rgb)
            regional = skin['regional']
            self.assertEqual(regional['estimador'], 'lab_regional_ponderado')
            np.testing.assert_allclose(regional['lab'], rgb_to_lab(np.array(color, np.uint8)), atol=1e-5)
            self.assertAlmostEqual(sum(r['peso'] for r in regional['regioes']), 1)
            self.assertEqual(regional['motivos'], [])

    def test_shadow_or_highlight_region_is_downweighted_without_changing_masks(self):
        base = [160, 110, 80]
        target = rgb_to_lab(np.array(base, np.uint8))
        for outlier in ([55, 35, 25], [245, 230, 210]):
            rgb = np.full((200, 200, 3), base, np.uint8)
            rgb[24:60, 60:140] = outlier  # testa
            before = rgb.copy()
            mask = np.ones((200, 200), bool)
            skin = self.measure(rgb, mask)
            result = skin['regional']
            self.assertLess(float(deltaE_ciede2000(result['lab'], target)), 1.)
            self.assertLess(result['regioes'][0]['peso'], .05)
            self.assertIn('discordancia_entre_regioes', result['motivos'])
            np.testing.assert_array_equal(rgb, before)
            self.assertTrue(mask.all())
            np.testing.assert_array_equal(skin['mask'], mask)

    def test_two_dark_regions_are_not_overruled_by_a_light_region(self):
        rgb = np.full((200, 200, 3), [60, 40, 30], np.uint8)
        rgb[24:60, 60:140] = [180, 140, 110]
        regional = self.measure(rgb)['regional']
        self.assertLess(regional['regioes'][0]['peso'], .05)
        self.assertLess(regional['lab'][0], 30)

    def test_excluded_pixels_never_affect_regional_estimate(self):
        rgb = np.full((200, 200, 3), [160, 110, 80], np.uint8)
        mask = np.ones((200, 200), bool)
        mask[24:60, 60:100] = False
        clean = self.measure(rgb, mask)['regional']
        rgb[~mask] = [255, 0, 255]
        self.assertEqual(clean, self.measure(rgb, mask)['regional'])

    def test_clipped_regions_and_small_masks_use_global_fallback(self):
        for color in ([0, 0, 0], [255, 255, 255]):
            rgb = np.full((200, 200, 3), color, np.uint8)
            skin = self.measure(rgb)
            self.assertEqual(skin['regional']['estimador'], 'mediana_lab')
            self.assertIn('regioes_insuficientes', skin['regional']['motivos'])
            np.testing.assert_allclose(skin['regional']['lab'], skin['median_lab'])
            json.dumps(skin['regional'], allow_nan=False)
        skin = self.measure(np.full((1, 1, 3), 100, np.uint8))
        self.assertEqual(skin['regional']['estimador'], 'mediana_lab')

    def test_regions_follow_face_bbox_and_do_not_include_background(self):
        rgb = np.full((300, 400, 3), [255, 0, 255], np.uint8)
        face = np.zeros((300, 400), bool)
        face[50:250, 100:300] = True
        rgb[face] = [160, 110, 80]
        regional = self.measure(rgb, face.copy(), face)['regional']
        self.assertEqual(regional['regioes'][0]['bbox'], [160, 74, 80, 36])
        self.assertEqual(regional['estimador'], 'lab_regional_ponderado')
        np.testing.assert_allclose(regional['lab'], rgb_to_lab(np.array([160, 110, 80], np.uint8)), atol=1e-5)

    def test_disagreeing_pair_does_not_arbitrarily_pick_one_side(self):
        rgb = np.full((200, 200, 3), [160, 110, 80], np.uint8)
        mask = np.ones((200, 200), bool)
        mask[24:60, 60:140] = False
        rgb[:, 100:] = [60, 40, 30]
        skin = self.measure(rgb, mask)
        self.assertIn('sem_consenso_regional', skin['regional']['motivos'])
        self.assertEqual(skin['regional']['estimador'], 'mediana_lab')
        np.testing.assert_allclose(skin['regional']['lab'], skin['median_lab'])

    def test_regional_warnings_and_ranking_sensitivity_reach_match(self):
        rgb = np.full((200, 200, 3), [160, 110, 80], np.uint8)
        rgb[24:60, 60:140] = [60, 40, 30]
        skin = self.measure(rgb)
        result = build_analysis(skin, {'quality': {'reasons': []}}, 40000)
        self.assertEqual(result['match']['estimador'], 'lab_regional_ponderado')
        self.assertTrue(result['match']['confianca_reduzida'])
        self.assertIn('discordancia_entre_regioes', result['match']['motivos'])
        self.assertTrue(result['match']['sensibilidade_regional']['ranking_varia'])
        self.assertEqual(len(result['match']['sensibilidade_regional']['top3_por_regiao']), 3)
        json.dumps(result, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
