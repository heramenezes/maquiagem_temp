"""Contrato do modelo, máscara anatômica e integridade do peso."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

import numpy as np

from backend.src.segmentation import semantic
from backend.src.segmentation.color import rgb_to_lab
from backend.src.segmentation.skin import InsufficientSkinError, adaptive_clusters


class SemanticTests(unittest.TestCase):
    def test_only_skin_and_nose_are_kept_without_expanding_exclusions(self):
        labels = np.repeat(np.arange(19, dtype=np.uint8)[None], 64, axis=0)
        masks = semantic.masks_from_labels(labels)
        self.assertEqual(int(masks['allowed'].sum()), 128)
        self.assertTrue(masks['allowed'][:, 1].all())
        self.assertTrue(masks['allowed'][:, 10].all())
        self.assertFalse(masks['allowed'][:, [0, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18]].any())

    def test_color_groups_do_not_discard_disconnected_or_darker_skin(self):
        labels = np.zeros((40, 60), np.uint8)
        labels[2:18, 2:18] = 1
        labels[22:38, 42:58] = 10
        rgb = np.zeros((40, 60, 3), np.uint8)
        rgb[labels == 1] = [230, 180, 140]
        rgb[labels == 10] = [45, 30, 20]
        lab = rgb_to_lab(rgb)
        masks = semantic.masks_from_labels(labels)
        before = masks['allowed'].copy()
        adaptive_clusters(lab, masks)
        result = semantic.measure_skin(lab, masks['allowed'])
        np.testing.assert_array_equal(result['mask'], before)
        np.testing.assert_allclose(result['mean_lab'], lab[before].mean(axis=0))

    def test_input_rgb_normalization_and_mask_alignment_preserve_original_pixels(self):
        rgb = np.full((60, 100, 3), [240, 90, 30], np.uint8)
        original = rgb.copy()
        logits = np.zeros((1, 19, 512, 512), np.float32)
        logits[:, 1, :, :256] = 5
        logits[:, 10, :, 256:] = 5
        session = MagicMock()
        session.get_inputs.return_value = [SimpleNamespace(name='input')]
        session.get_outputs.return_value = [SimpleNamespace(name='output')]
        session.run.return_value = [logits]
        with patch.object(semantic, 'get_session', return_value=session):
            labels = semantic.predict_labels(rgb)
        tensor = session.run.call_args.args[1]['input']
        self.assertEqual(tensor.shape, (1, 3, 512, 512))
        self.assertEqual(tensor.dtype, np.float32)
        np.testing.assert_allclose(tensor[0, :, 0, 0],
            (np.array([240, 90, 30]) / 255 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225], rtol=1e-6)
        self.assertEqual(labels.shape, (60, 100))
        self.assertTrue((labels[:, :50] == 1).all())
        self.assertTrue((labels[:, 50:] == 10).all())
        np.testing.assert_array_equal(rgb, original)

    def test_no_skin_or_tiny_crop_requests_new_photo(self):
        with self.assertRaises(InsufficientSkinError):
            semantic.masks_from_labels(np.zeros((100, 100), np.uint8))
        with self.assertRaises(InsufficientSkinError):
            semantic.predict_labels(np.zeros((8, 8, 3), np.uint8))

    def test_missing_and_corrupted_model_are_explicit_errors(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'model.onnx'
            with patch.object(semantic, 'MODEL_PATH', path), patch.object(semantic, '_session', None):
                with self.assertRaises(semantic.ModelUnavailableError):
                    semantic.get_session()
                path.write_bytes(b'not an onnx model')
                with self.assertRaises(semantic.ModelUnavailableError):
                    semantic.get_session()

    def test_real_model_selects_useful_skin_and_reuses_session(self):
        from backend.src.preprocessing import detectar_e_isolar_rosto
        sample = Path(__file__).resolve().parents[2] / 'samples/imagem_teste.jpeg'
        rgb = detectar_e_isolar_rosto(str(sample))
        labels = semantic.predict_labels(rgb)
        masks = semantic.masks_from_labels(labels)
        self.assertGreater(int(masks['allowed'].sum()), 3000)
        self.assertTrue(np.isin(labels, [4, 5, 11, 12, 13]).any())
        self.assertIs(semantic.get_session(), semantic.get_session())
        self.assertEqual(semantic.get_session().get_providers(), ['CPUExecutionProvider'])


if __name__ == '__main__':
    unittest.main()
