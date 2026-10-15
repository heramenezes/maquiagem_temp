"""Contratos da máscara específica de barba/bigode, sem validar acurácia."""

import unittest
from unittest.mock import patch

import numpy as np

from backend.src.skin_selection import beard
from backend.src.skin_selection.compose import compose
from backend.src.skin_selection.contracts import Transform


def outputs():
    detections = np.zeros((1, 38, 8400), np.float32)
    prototypes = np.zeros((1, 32, 160, 160), np.float32)
    prototypes[:, 0] = 1
    return detections, prototypes


def instance(detections, index, box, beard_score=.9, hair_score=.01):
    detections[0, :6, index] = [*box, beard_score, hair_score]
    detections[0, 6, index] = 10


class BeardTests(unittest.TestCase):
    def test_hair_is_ignored_even_with_high_beard_score(self):
        d, p = outputs()
        instance(d, 0, [320, 320, 400, 300], beard_score=.8, hair_score=.9)
        transform = Transform.prepare(np.zeros((80, 120, 3), np.uint8), 640, letterbox=True)[1]
        accepted, uncertain = beard.decode([d, p], transform)
        self.assertFalse((accepted | uncertain).any())

    def test_letterbox_multiple_regions_uncertainty_and_nms(self):
        d, p = outputs()
        transform = Transform.prepare(np.zeros((80, 160, 3), np.uint8), 640, letterbox=True)[1]
        instance(d, 0, [200, 320, 100, 100])
        instance(d, 1, [200, 320, 100, 100], beard_score=.4)  # duplicata suprimida
        instance(d, 2, [400, 320, 100, 100], beard_score=.4)
        accepted, uncertain = beard.decode([d, p], transform)
        self.assertTrue(accepted[40, 50])
        self.assertFalse(uncertain[40, 50])
        self.assertTrue(uncertain[40, 100])
        self.assertFalse(accepted[40, 100])
        self.assertFalse((accepted | uncertain)[:10].any())
        self.assertFalse((accepted & uncertain).any())

    def test_mask_holes_and_raw_regions_outside_anatomy_are_preserved(self):
        d, p = outputs()
        instance(d, 0, [320, 320, 400, 400])
        p[0, 0, 70:90, 70:90] = -1
        rgb = np.full((100, 100, 3), 150, np.uint8)
        allowed = np.ones((100, 100), bool)
        allowed[:, :50] = False
        with patch.object(beard, 'infer', return_value=[d, p]):
            result = beard.detect(rgb, {'allowed': allowed})  # não precisa de nariz/textura
        self.assertTrue(result.accepted[30, 30])
        self.assertFalse(result.accepted[50, 50])
        selected = compose(allowed, {'barba': result})
        self.assertFalse(selected['accepted_masks']['barba'][:, :50].any())
        self.assertTrue(selected['debug_masks']['barba']['raw_accepted'][30, 30])
        self.assertTrue(selected['valid_mask'][50, 50])

    def test_invalid_outputs_fail_explicitly(self):
        transform = Transform.prepare(np.zeros((80, 120, 3), np.uint8), 640, letterbox=True)[1]
        for kind in ('classes', 'prototypes', 'nan', 'confidence'):
            d, p = outputs()
            if kind == 'classes':
                d = d[:, :37]
            elif kind == 'prototypes':
                p = p[:, :31]
            elif kind == 'nan':
                p[0, 0, 0, 0] = np.nan
            else:
                d[0, 5, 0] = 1.1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                beard.decode([d, p], transform)


if __name__ == '__main__':
    unittest.main()
