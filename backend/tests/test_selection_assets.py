"""Integridade dos pesos e integração real dos três especialistas em CPU."""

from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from backend.download_model import download_asset
from backend.src.segmentation import model_asset
from backend.src.skin_selection.pipeline import run_module
from backend.src.skin_selection.runtime import get_session
from backend.src.skin_selection.contracts import CATEGORIES
from backend.evaluate_selection import mask_metrics, validate_manifest


class AssetTests(unittest.TestCase):
    def test_bad_download_does_not_replace_installed_file(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'model.onnx'
            target.write_bytes(b'old model')
            with patch('backend.download_model.urllib.request.urlopen', return_value=BytesIO(b'wrong model')):
                with self.assertRaises(RuntimeError):
                    download_asset('https://example.invalid/model', target, '0' * 64)
            self.assertEqual(target.read_bytes(), b'old model')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_export_manifest_requires_source_parity_and_file_integrity(self):
        with TemporaryDirectory() as directory:
            with patch.object(model_asset, 'MODEL_PATH', Path(directory) / 'resnet18.onnx'):
                asset = model_asset.ASSETS['acne']
                asset.path.write_bytes(b'fake onnx')
                manifest = {'version': asset.version, 'source_sha256': asset.source_sha256,
                            'sha256': model_asset.file_sha256(asset.path), 'parity_passed': True}
                for changed in ({'source_sha256': 'bad'}, {'parity_passed': False}, {'version': 'bad'}, {'sha256': 'bad'}):
                    asset.path.with_suffix('.json').write_text(json.dumps({**manifest, **changed}), encoding='utf8')
                    with self.assertRaises(ValueError):
                        model_asset.verify_asset(asset)
                asset.path.with_suffix('.json').write_text(json.dumps(manifest), encoding='utf8')
                model_asset.verify_asset(asset)
                asset.path.write_bytes(b'corrupted')
                with self.assertRaises(ValueError):
                    model_asset.verify_asset(asset)

    def test_real_models_execute_and_reuse_cpu_sessions(self):
        from backend.src.preprocessing import detectar_e_isolar_rosto
        from backend.src.segmentation.semantic import facial_masks
        sample = Path(__file__).resolve().parents[2] / 'samples/imagem_teste.jpeg'
        rgb = detectar_e_isolar_rosto(str(sample))
        original = rgb.copy()
        masks = facial_masks(rgb)
        for key in ('acne', 'vitiligo', 'barba'):
            with self.subTest(key=key):
                result = run_module(key, rgb, masks)
                self.assertEqual(result.status, 'executado', result.reason)
                result.validate(rgb.shape[:2])
                self.assertEqual(get_session(key).get_providers(), ['CPUExecutionProvider'])
                self.assertIs(get_session(key), get_session(key))
                self.assertTrue(result.version['sha256'])
                if key == 'barba':
                    self.assertEqual(result.source, 'prashants975_yolov8l_seg')
                    self.assertTrue(result.evidence['nominal_beard_class'])
                    self.assertEqual(result.evidence['selected_class'], 0)
        np.testing.assert_array_equal(rgb, original)


class EvaluationTests(unittest.TestCase):
    def row(self, identifier, person, split):
        return {'id': identifier, 'person_id': person, 'split': split, 'image': 'crop.png',
                'valid_mask': 'valid.png', 'exclusions': {key: key + '.png' for key in CATEGORIES},
                'tone_group': 'manual', 'lighting': 'uniforme'}

    def test_same_person_cannot_leak_between_splits(self):
        with self.assertRaises(ValueError):
            validate_manifest([self.row('a', 'person1', 'train'), self.row('b', 'person1', 'test')])
        validate_manifest([self.row('a', 'person1', 'train'), self.row('b', 'person2', 'test')])

    def test_missing_category_is_not_assumed_negative(self):
        row = self.row('a', 'person1', 'validation')
        del row['exclusions']['barba']
        with self.assertRaises(ValueError):
            validate_manifest([row])

    def test_metrics_keep_false_positives_on_negative_images(self):
        empty = np.zeros((10, 10), bool)
        full = ~empty
        result = mask_metrics(full, empty)
        self.assertEqual(result['fp'], 100)
        self.assertEqual(result['precision'], 0)
        self.assertEqual(result['iou'], 0)
        self.assertIsNone(result['recall'])
        self.assertEqual(mask_metrics(empty, empty)['iou'], 1)


if __name__ == '__main__':
    unittest.main()
