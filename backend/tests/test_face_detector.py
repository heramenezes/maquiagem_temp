"""Contagem de rostos, propagação de rejeições e limites do recorte."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from backend.src.preprocessing import face_detector as detector


def detection(x, score=0.9):
    return SimpleNamespace(score=[score], location_data=SimpleNamespace(
        relative_bounding_box=SimpleNamespace(xmin=x, ymin=0.2, width=0.2, height=0.4)))


class FaceDetectorTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((240, 480, 3), np.uint8)

    def mediapipe(self, detections):
        fake = MagicMock()
        fake.solutions.face_detection.FaceDetection.return_value.__enter__.return_value.process.return_value.detections = detections
        return patch.dict('sys.modules', {'mediapipe': fake})

    def test_mediapipe_multiple_is_not_swallowed_or_sent_to_fallback(self):
        with self.mediapipe([detection(0.1), detection(0.65)]):
            with patch.object(detector, 'detectar_rosto_haar') as haar:
                with self.assertRaises(detector.MultipleFacesError):
                    detector.detectar_e_isolar_rosto(self.image)
                haar.assert_not_called()

    def test_mediapipe_single_and_low_confidence_candidate(self):
        with self.mediapipe([detection(0.1), detection(0.65, 0.3)]):
            self.assertIsNotNone(detector.detectar_rosto_mediapipe(self.image))

    def test_mediapipe_missing_uses_haar(self):
        with patch.dict('sys.modules', {'mediapipe': None}):
            with patch.object(detector, 'detectar_rosto_haar', return_value=(10, 20, 80, 90)):
                face = detector.detectar_e_isolar_rosto(self.image)
        self.assertEqual(face.shape, (90, 80, 3))
        self.assertTrue(face.flags['C_CONTIGUOUS'])

    def test_single_mediapipe_face_passes_without_second_detector(self):
        with patch.object(detector, 'detectar_rosto_mediapipe', return_value=(0, 0, 100, 100)):
            with patch.object(detector, 'detectar_rosto_haar', side_effect=detector.MultipleFacesError(2)) as haar:
                face = detector.detectar_e_isolar_rosto(self.image)
                self.assertEqual(face.shape, (100, 100, 3))
                haar.assert_not_called()

    def test_haar_counts_all_faces_instead_of_choosing_largest(self):
        classifier = MagicMock()
        classifier.empty.return_value = False
        classifier.detectMultiScale.return_value = np.array([(10, 20, 150, 150), (300, 70, 45, 45)])
        with patch.object(detector.cv2, 'CascadeClassifier', return_value=classifier):
            with self.assertRaises(detector.MultipleFacesError) as error:
                detector.detectar_rosto_haar(self.image)
        self.assertEqual(error.exception.count, 2)

    def test_missing_classifier_is_an_error_not_no_face(self):
        classifier = MagicMock()
        classifier.empty.return_value = True
        with patch.object(detector.cv2, 'CascadeClassifier', return_value=classifier):
            with self.assertRaises(RuntimeError):
                detector.detectar_rosto_haar(self.image)

    def test_multiple_detections_abort_even_when_boxes_overlap(self):
        with self.assertRaises(detector.MultipleFacesError):
            detector.selecionar_rosto_unico(
                [(20, 30, 100, 100), (22, 32, 98, 98)], 480, 240)

    def test_nearby_distinct_faces_are_not_merged(self):
        with self.assertRaises(detector.MultipleFacesError):
            detector.selecionar_rosto_unico([(20, 30, 100, 100), (90, 30, 100, 100)], 480, 240)

    def test_invalid_or_outside_boxes_do_not_become_faces(self):
        self.assertIsNone(detector.selecionar_rosto_unico(
            [(500, 0, 40, 40), (0, 0, -1, 20), (-100, -100, 10, 10), (np.nan, 0, 10, 10)], 480, 240))

    def test_margin_is_clipped_without_shifting_opposite_edge(self):
        self.assertEqual(detector.aplicar_margem_bounding_box(0, 0, 100, 100, 200, 200), (0, 0, 115, 115))
        self.assertEqual(detector.aplicar_margem_bounding_box(100, 100, 100, 100, 200, 200), (85, 85, 115, 115))

    def test_empty_or_wrong_dtype_image_rejected(self):
        for image in [np.zeros((0, 100, 3), np.uint8), np.zeros((100, 100, 3), np.float32)]:
            with self.subTest(shape=image.shape, dtype=image.dtype):
                with self.assertRaises(ValueError):
                    detector.carregar_imagem(image)


if __name__ == '__main__':
    unittest.main()
