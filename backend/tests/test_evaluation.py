"""Verificações offline opcionais; requer requirements-evaluation.txt."""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from backend.evaluate_selection import selection_metrics, report
from backend.src.skin_selection.contracts import CATEGORIES, ModuleResult
from backend.src.segmentation.color import rgb_to_lab


@unittest.skipUnless(importlib.util.find_spec('skimage') and importlib.util.find_spec('psutil'),
                     'Dependências offline de avaliação não instaladas.')
class EvaluationIntegrationTests(unittest.TestCase):
    def test_color_comparison_is_null_for_empty_and_zero_for_identical_selection(self):
        lab = rgb_to_lab(np.full((20, 30, 3), [130, 85, 60], np.uint8))
        mask = np.ones((20, 30), bool)
        result = selection_metrics(mask, mask, lab)
        self.assertEqual(result['color_comparison_research_only']['delta_e00'], 0)
        self.assertEqual(result['remaining_contamination_fraction'], 0)
        self.assertIsNone(selection_metrics(~mask, mask, lab)['color_comparison_research_only'])

    def test_full_report_runs_ablations_and_keeps_failures(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shape = (80, 100)
            rgb = np.full((*shape, 3), [130, 85, 60], np.uint8)
            Image.fromarray(rgb).save(root / 'crop.png')
            Image.fromarray(np.full(shape, 255, np.uint8)).save(root / 'valid.png')
            Image.fromarray(np.zeros(shape, np.uint8)).save(root / 'empty.png')
            row = {'id': 'synthetic', 'person_id': 'synthetic', 'split': 'test',
                   'image': 'crop.png', 'valid_mask': 'valid.png', 'tone_group': 'synthetic',
                   'lighting': 'synthetic', 'exclusions': {k: 'empty.png' for k in CATEGORIES}}
            failed = {**row, 'id': 'missing', 'image': 'missing.png'}
            mask = np.ones(shape, bool)
            with patch('backend.evaluate_selection.facial_masks', return_value={'allowed': mask, 'face': mask}), \
                 patch('backend.evaluate_selection.run_module', side_effect=lambda *a: ModuleResult.empty(shape, status='executado')):
                result = report([row, failed], root, 'test')
            self.assertEqual(result['failed_photos'], 1)
            self.assertFalse(result['quality_validated'])
            self.assertEqual(set(result['results'][0]['variants']),
                             {'bisenet', 'manual', 'acne', 'vitiligo', 'barba', 'completa'})
            self.assertEqual(result['results'][0]['variants']['manual']['dice'], 1)
            self.assertIn('error', result['results'][1])


if __name__ == '__main__':
    unittest.main()
