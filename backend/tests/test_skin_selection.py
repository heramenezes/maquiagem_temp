"""Invariantes de seleção, transformações e abstenção; não validam acurácia clínica."""

from contextlib import nullcontext
from io import BytesIO
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from backend.app import create_app
from backend.src.segmentation.color import rgb_to_lab
from backend.src.segmentation.semantic import measure_skin, ModelUnavailableError
from backend.src.segmentation.pipeline import analysis_events
from backend.src.mock_analysis import generate_analysis
from backend.src.skin_selection import acne, beard, contrast, vitiligo
from backend.src.skin_selection.contracts import Transform, ModuleResult, CATEGORIES, probability_masks
from backend.src.skin_selection.compose import compose
from backend.src.skin_selection.pipeline import run_module
from backend.src.skin_selection.quality import evaluate


def empty_modules(shape):
    return {key: ModuleResult.empty(shape, status='executado', source='test') for key in CATEGORIES}


def textured_skin(shape=(100, 160)):
    noise = np.random.default_rng(1).integers(-3, 4, (*shape, 1))
    return (np.full((*shape, 3), [160, 110, 85]) + noise).astype(np.uint8)


def anatomy(shape):
    mask = np.ones(shape, bool)
    return {'allowed': mask, 'face': mask, 'seeds': mask, 'method': 'test', 'model': 'test', 'warnings': []}


class TransformTests(unittest.TestCase):
    def test_letterbox_landscape_portrait_and_odd_padding(self):
        for shape in ((31, 101), (101, 31), (37, 53)):
            rgb = np.full((*shape, 3), 200, np.uint8)
            view, transform = Transform.prepare(rgb, 64, letterbox=True)
            mask = np.zeros((64, 64), np.float32)
            rh, rw = transform.resized_shape
            mask[transform.top:transform.top + rh, transform.left:transform.left + rw] = 1
            np.testing.assert_array_equal(transform.restore(mask), np.ones(shape))
            self.assertEqual(view.shape, (64, 64, 3))
            self.assertEqual(transform.metadata()['original_shape'], shape)

    def test_probabilities_are_resampled_before_threshold_and_labels_use_nearest(self):
        transform = Transform((1, 5), (1, 2), (1, 2))
        values = np.array([[0, 1]], np.float32)
        soft = transform.restore(values)
        hard = transform.restore(values, labels=True)
        self.assertTrue(np.any((soft > 0) & (soft < 1)))
        self.assertTrue(np.isin(hard, [0, 1]).all())
        accepted, uncertain = probability_masks(soft, .2, .8)
        self.assertTrue(uncertain.any())
        self.assertFalse((accepted & uncertain).any())


class CompositionTests(unittest.TestCase):
    def test_overlaps_count_once_and_never_expand_anatomy(self):
        mask = np.zeros((20, 20), bool)
        mask[3:17, 3:17] = True
        modules = empty_modules(mask.shape)
        modules['acne'].accepted[:10, :10] = True
        modules['vitiligo'].accepted[5:12, 5:12] = True
        modules['barba'].uncertain[10:15, 10:15] = True
        selected = compose(mask, modules)
        expected = mask & (modules['acne'].accepted | modules['vitiligo'].accepted)
        np.testing.assert_array_equal(selected['excluded_mask'], expected)
        np.testing.assert_array_equal(selected['valid_mask'], mask & ~expected & ~modules['barba'].uncertain)
        self.assertTrue(selected['debug_masks']['acne']['raw_accepted'][0, 0])
        self.assertFalse(selected['accepted_masks']['acne'][0, 0])
        self.assertLess(expected.sum(), sum(m.sum() for m in selected['accepted_masks'].values()))

    def test_empty_executed_missing_and_failed_are_distinct(self):
        modules = empty_modules((20, 20))
        modules['vitiligo'].status = 'indisponivel'
        modules['barba'].status = 'falha'
        del modules['outras_regioes']
        status = compose(np.ones((20, 20), bool), modules)['module_status']
        self.assertIs(status['acne']['detected'], False)
        for key in ('vitiligo', 'barba', 'outras_regioes'):
            self.assertIsNone(status[key]['detected'])
        self.assertEqual(status['outras_regioes']['state'], 'nao_executado')

    def test_invalid_alignment_fails_instead_of_broadcasting(self):
        with self.assertRaises(ValueError):
            compose(np.ones((20, 20), bool), {'acne': ModuleResult.empty((1, 20))})


class AdapterTests(unittest.TestCase):
    def test_acne_rgb_and_original_colors(self):
        rgb = np.full((31, 61, 3), [210, 100, 40], np.uint8)
        before = rgb.copy()
        output = np.full((1, 1, 256, 256), -8, np.float32)
        output[:, :, :, :128] = 8
        with patch.object(acne, 'infer', return_value=[output]) as infer:
            result = acne.detect(rgb, anatomy(rgb.shape[:2]))
        tensor = infer.call_args.args[1]
        np.testing.assert_allclose(tensor[0, :, 0, 0],
                                   (np.array([210, 100, 40]) / 255 - [.485, .456, .406]) / [.229, .224, .225], rtol=1e-5)
        np.testing.assert_array_equal(rgb, before)
        self.assertEqual(result.accepted.shape, (31, 61))
        self.assertTrue(result.accepted[:, :29].all())
        self.assertFalse(result.accepted[:, 32:].any())

    def test_easy_bgr_and_eight_class_contract(self):
        rgb = np.full((32, 48, 3), [200, 100, 25], np.uint8)
        logits = np.zeros((1, 8, 512, 512), np.float32)
        logits[:, 1] = 10
        with patch.object(beard, 'infer', return_value=[logits]) as infer:
            result = beard.detect(rgb, anatomy(rgb.shape[:2]))
        values = infer.call_args.args[1][0, :, 0, 0]
        np.testing.assert_allclose(values,
            (np.array([25, 100, 200]) - [143.55267075, 132.96705975, 126.94924335]) /
            [60.2625333, 60.32740275, 59.30988645], rtol=1e-5)
        self.assertFalse(result.accepted.any())
        self.assertFalse(result.uncertain.any())
        with patch.object(beard, 'infer', return_value=[np.zeros((1, 19, 512, 512), np.float32)]):
            with self.assertRaises(ValueError):
                beard.detect(rgb, anatomy(rgb.shape[:2]))

    def test_parser_disagreement_alone_is_not_beard(self):
        rgb = np.full((80, 100, 3), 100, np.uint8)
        masks = anatomy(rgb.shape[:2])
        masks['labels'] = np.ones(rgb.shape[:2], np.uint8)
        masks['labels'][30:40, 40:60] = 10
        result = beard.from_probabilities(rgb, masks, np.ones(rgb.shape[:2]), np.zeros(rgb.shape[:2]))
        self.assertFalse(result.accepted.any())
        self.assertTrue(result.uncertain.all())
        self.assertFalse(result.evidence['nominal_beard_class'])

    def test_beard_needs_lower_face_texture_and_parser_support(self):
        rgb = np.full((100, 100, 3), 130, np.uint8)
        rgb[60:90:2, 25:75] = 30
        masks = anatomy(rgb.shape[:2])
        masks['labels'] = np.ones(rgb.shape[:2], np.uint8)
        masks['labels'][30:40, 40:60] = 10
        background = np.zeros((100, 100), np.float32)
        background[60:90, 25:75] = 1
        result = beard.from_probabilities(rgb, masks, background, 1 - background)
        self.assertGreater(result.accepted.sum(), 100)
        self.assertFalse(result.accepted[:40].any())
        self.assertFalse(result.accepted[:, :20].any())

    def test_vitiligo_empty_and_letterbox_instance_union(self):
        rgb = np.zeros((60, 120, 3), np.uint8)
        _, transform = Transform.prepare(rgb, 416, letterbox=True)
        detections = np.zeros((1, 37, 3549), np.float32)
        prototypes = np.ones((1, 32, 104, 104), np.float32)
        accepted, uncertain = vitiligo.decode([detections, prototypes], transform)
        self.assertFalse((accepted | uncertain).any())
        detections[0, :5, 0] = [208, 208, 208, 104, .9]
        detections[0, 5, 0] = 10
        detections[0, :5, 1] = [300, 208, 100, 104, .4]
        detections[0, 5, 1] = 10
        accepted, uncertain = vitiligo.decode([detections, prototypes], transform)
        self.assertTrue(accepted[30, 60])
        self.assertFalse(accepted[2, 60])
        self.assertTrue(uncertain[30, 95])
        self.assertFalse((accepted & uncertain).any())

    def test_model_failure_is_explicit_and_blocks_quality(self):
        rgb = textured_skin()
        masks = anatomy(rgb.shape[:2])
        for error, state in ((ModelUnavailableError('missing'), 'indisponivel'), (ValueError('bad shape'), 'falha')):
            with patch.dict('backend.src.skin_selection.pipeline.DETECTORS', {'acne': lambda *args: (_ for _ in ()).throw(error)}):
                with self.assertLogs('backend.src.skin_selection.pipeline', level='ERROR') if state == 'falha' else nullcontext():
                    result = run_module('acne', rgb, masks)
            self.assertEqual(result.status, state)
            modules = empty_modules(rgb.shape[:2])
            modules['acne'] = result
            selection = compose(masks['allowed'], modules)
            quality = evaluate(rgb, rgb_to_lab(rgb), selection)
            self.assertFalse(quality['usable'])
            self.assertIn('modulo_obrigatorio_indisponivel', quality['reasons'])


class ContrastQualityTests(unittest.TestCase):
    def test_uniform_light_dark_and_smooth_shadow_are_not_exclusions(self):
        for color in ([220, 170, 140], [35, 23, 18]):
            rgb = np.full((120, 160, 3), color, np.uint8)
            for shadow in (False, True):
                values = rgb if not shadow else (rgb * np.linspace(.7, 1., 160)[None, :, None]).astype(np.uint8)
                mask = np.ones(values.shape[:2], bool)
                result = contrast.detect(rgb_to_lab(values), mask, ~mask, ~mask)
                self.assertFalse(result.accepted.any())

    def test_dark_ring_preserves_hole_and_exclusions_are_not_references(self):
        rgb = np.full((160, 160, 3), [190, 140, 110], np.uint8)
        ring = np.zeros((160, 160), np.uint8)
        cv2.circle(ring, (80, 80), 10, 1, 3)
        rgb[ring > 0] = 5
        mask = np.ones(ring.shape, bool)
        result = contrast.detect(rgb_to_lab(rgb), mask, ~mask, ~mask)
        self.assertGreater((result.accepted & (ring > 0)).sum(), 0)
        self.assertFalse(result.accepted[80, 80])
        excluded = ring.astype(bool)
        result = contrast.detect(rgb_to_lab(rgb), mask, excluded, ~mask)
        self.assertFalse((result.accepted & excluded).any())

    def test_quality_rejects_empty_tiny_clipped_and_uncertainty_sensitive_samples(self):
        rgb = textured_skin()
        mask = np.ones(rgb.shape[:2], bool)
        selection = compose(mask, empty_modules(mask.shape))
        self.assertTrue(evaluate(rgb, rgb_to_lab(rgb), selection)['usable'])
        selection['valid_mask'][:] = False
        self.assertIn('poucos_pixels_nativos', evaluate(rgb, rgb_to_lab(rgb), selection)['reasons'])
        selection = compose(mask, empty_modules(mask.shape))
        clipped = np.full_like(rgb, 255)
        self.assertIn('clipping_excessivo', evaluate(clipped, rgb_to_lab(clipped), selection)['reasons'])
        rgb[:, :40] = [230, 220, 210]
        modules = empty_modules(mask.shape)
        modules['vitiligo'].uncertain[:, :40] = True
        selection = compose(mask, modules)
        self.assertIn('cor_sensivel_a_incerteza', evaluate(rgb, rgb_to_lab(rgb), selection)['reasons'])

    def test_measurement_uses_only_selected_original_values(self):
        rgb = textured_skin()
        rgb[:, :40] = [255, 255, 255]
        lab = rgb_to_lab(rgb)
        mask = np.ones(rgb.shape[:2], bool)
        mask[:, :40] = False
        measured = measure_skin(lab, mask)
        np.testing.assert_allclose(measured['mean_lab'], lab[mask].mean(axis=0))
        np.testing.assert_allclose(measured['median_lab'], np.median(lab[mask], axis=0))


class PipelineIntegrationTests(unittest.TestCase):
    def test_native_resolution_and_quality_gate_prevent_measurement(self):
        rgb = textured_skin((600, 900))
        before = rgb.copy()
        masks = anatomy(rgb.shape[:2])
        unavailable = ModuleResult.empty(rgb.shape[:2], status='indisponivel')
        with patch('backend.src.segmentation.pipeline.facial_masks', return_value=masks), \
             patch('backend.src.segmentation.pipeline.run_module', return_value=unavailable), \
             patch('backend.src.segmentation.pipeline.measure_skin') as measure:
            events = list(analysis_events(rgb, lambda image: image, generate_analysis))
        result = events[-1]['dados']
        measure.assert_not_called()
        self.assertEqual(result['preprocessamento']['dimensoes'], {'largura': 900, 'altura': 600})
        self.assertIsNone(result['preprocessamento']['media_lab'])
        self.assertEqual(result['status_analise'], 'inconclusiva')
        self.assertEqual(result['marcacoes'], [])
        self.assertEqual({c['id'] for c in result['condicoes']}, set(CATEGORIES))
        self.assertTrue(all(c['detectada'] is None for c in result['condicoes'][:3]))
        json.dumps(result, allow_nan=False)
        np.testing.assert_array_equal(rgb, before)

    def test_approved_pipeline_measures_only_valid_mask(self):
        rgb = textured_skin()
        masks = anatomy(rgb.shape[:2])
        modules = empty_modules(rgb.shape[:2])
        modules['acne'].accepted[:, :30] = True
        selected = compose(masks['allowed'], modules)
        selected['quality'] = evaluate(rgb, rgb_to_lab(rgb), selected)
        self.assertTrue(selected['quality']['usable'])
        with patch('backend.src.segmentation.pipeline.facial_masks', return_value=masks), \
             patch('backend.src.segmentation.pipeline.run_module', return_value=modules['barba']), \
             patch('backend.src.segmentation.pipeline.finish', return_value=selected), \
             patch('backend.src.segmentation.pipeline.measure_skin', wraps=measure_skin) as measure:
            events = list(analysis_events(rgb, lambda image: image, generate_analysis))
        np.testing.assert_array_equal(measure.call_args.args[1], selected['valid_mask'])
        np.testing.assert_allclose(events[-1]['dados']['preprocessamento']['media_lab'],
                                   rgb_to_lab(rgb)[selected['valid_mask']].mean(axis=0), atol=.0001)

    def test_json_ndjson_partial_analysis_has_one_terminal_and_matching_contract(self):
        rgb = textured_skin()
        image = BytesIO()
        Image.fromarray(rgb).save(image, format='PNG')
        client = create_app({'TESTING': True}).test_client()
        def fail(*args):
            return ModuleResult.empty(rgb.shape[:2], status='falha', reason='falha_inferencia')
        with patch('backend.app.detectar_e_isolar_rosto', return_value=rgb), \
             patch('backend.src.segmentation.pipeline.facial_masks', return_value=anatomy(rgb.shape[:2])), \
             patch('backend.src.segmentation.pipeline.run_module', side_effect=fail):
            plain = client.post('/api/analises', data={'foto': (BytesIO(image.getvalue()), 'test.png')}).json
            response = client.post('/api/analises', data={'foto': (BytesIO(image.getvalue()), 'test.png')},
                                   headers={'Accept': 'application/x-ndjson'})
            events = [json.loads(line) for line in response.data.splitlines()]
        self.assertEqual(sum(e['tipo'] in ('resultado', 'erro') for e in events), 1)
        streamed = events[-1]['dados']
        self.assertEqual(plain['condicoes'], streamed['condicoes'])
        self.assertEqual(plain['preprocessamento']['selecao']['quality'], streamed['preprocessamento']['selecao']['quality'])
        self.assertIsNone(streamed['preprocessamento']['media_lab'])


if __name__ == '__main__':
    unittest.main()
