"""Testes do contrato HTTP, incluindo o detector real com as amostras locais."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
import json
import base64

import numpy as np
from PIL import Image, ImageCms

from backend.app import MAX_FILE_BYTES, create_app, decode_photo
from backend.src.catalog import load_catalog
from backend.tests.images import face_photo
from backend.src.preprocessing import detectar_e_isolar_rosto
from backend.src.segmentation.semantic import ModelUnavailableError

ROOT = Path(__file__).resolve().parents[2]


def image_file(color="black"):
    data = BytesIO()
    Image.new("RGB", (300, 300), color).save(data, format="PNG")
    data.seek(0)
    return data


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True})
        self.client = self.app.test_client()

    def test_home_and_assets(self):
        for path in ("/", "/css/styles.css", "/js/app.js", "/assets/tonzinha.svg"):
            with self.subTest(path=path):
                with self.client.get(path) as response:
                    self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/backend/data/bases.csv").status_code, 404)

    def test_example_is_explicitly_simulated_and_does_not_run_detector(self):
        with patch("backend.app.detectar_e_isolar_rosto") as detector:
            response = self.client.get("/api/exemplo")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["simulado"])
        self.assertTrue(response.json["exemplo"])
        self.assertEqual(response.json["precheck"], {"executado": False, "rosto_detectado": None})
        detector.assert_not_called()
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_catalog_and_recommendations_keep_real_product_data(self):
        catalog = load_catalog()
        self.assertEqual(len(catalog), 281)
        self.assertEqual(len({p["id"] for p in catalog}), 281)
        self.assertEqual(catalog[0]["preco"], 114.9)
        data = self.client.get("/api/exemplo").json
        self.assertEqual(len(data["recomendacoes"]), 3)
        for product in data["recomendacoes"]:
            self.assertIn(product, catalog)

    def test_missing_photo(self):
        response = self.client.post("/api/analises")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["codigo"], "FOTO_OBRIGATORIA")

    def test_bad_file_is_not_sent_to_detector(self):
        with patch("backend.app.detectar_e_isolar_rosto") as detector:
            response = self.client.post("/api/analises", data={"foto": (BytesIO(b"not an image"), "fake.jpg")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["codigo"], "FOTO_INVALIDA")
        detector.assert_not_called()

    def test_file_size_limit(self):
        response = self.client.post("/api/analises", data={"foto": (BytesIO(b"x" * (MAX_FILE_BYTES + 1)), "big.jpg")})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json["codigo"], "FOTO_MUITO_GRANDE")
        response.request.input_stream.close()

    def test_http_size_limit_is_json(self):
        response = self.client.post("/api/analises", data=b"x" * (MAX_FILE_BYTES + 2 * 1024 * 1024), content_type="application/octet-stream")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json["codigo"], "FOTO_MUITO_GRANDE")

    def test_no_face_blocks_mock_generation(self):
        with patch("backend.app.generate_analysis") as generate:
            response = self.client.post("/api/analises", data={"foto": (image_file(), "no-face.png")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json["codigo"], "ROSTO_NAO_ENCONTRADO")
        generate.assert_not_called()

    def test_real_face_in_sample_passes(self):
        with (ROOT / "samples" / "imagem_teste.jpeg").open("rb") as sample:
            response = self.client.post("/api/analises", data={"foto": (sample, "sample.jpg")})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["precheck"], {"executado": True, "rosto_detectado": True})
        self.assertFalse(response.json["exemplo"])
        self.assertTrue(response.json["simulado"])

    def test_multiple_real_faces_stop_before_color_conversion_in_json_and_stream(self):
        for count, scale in [(2, 1), (3, 1), (2, 0.6)]:
            for stream in [False, True]:
                with self.subTest(count=count, secondary_scale=scale, stream=stream):
                    with patch('backend.src.preprocessing.face_detector.detectar_rosto_mediapipe', return_value=None):
                        with patch('backend.src.segmentation.pipeline.rgb_to_lab') as convert:
                            with patch('backend.app.generate_analysis') as generate:
                                response = self.client.post('/api/analises',
                                    data={'foto': (face_photo(count, scale), 'faces.png')},
                                    headers={'Accept': 'application/x-ndjson' if stream else 'application/json'})
                                if stream:
                                    events = [json.loads(line) for line in response.data.splitlines()]
                                    self.assertEqual(len(events), 2)
                                    self.assertEqual(events[0]['concluidas'], 0)
                                    self.assertEqual(events[-1]['tipo'], 'erro')
                                    self.assertEqual(events[-1]['status'], 422)
                                    self.assertEqual(events[-1]['codigo'], 'MULTIPLOS_ROSTOS')
                                else:
                                    self.assertEqual(response.status_code, 422)
                                    self.assertEqual(response.json['codigo'], 'MULTIPLOS_ROSTOS')
                                convert.assert_not_called()
                                generate.assert_not_called()

    def test_repeated_attempts_do_not_reuse_approved_photo(self):
        face = detectar_e_isolar_rosto(str(ROOT / 'samples/imagem_teste.jpeg'))
        with patch("backend.app.detectar_e_isolar_rosto", side_effect=[face, None]):
            first = self.client.post("/api/analises", data={"foto": (image_file(), "one.png")})
            second = self.client.post("/api/analises", data={"foto": (image_file(), "two.png")})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 422)

    def test_internal_failure_does_not_become_no_face_or_fake_success(self):
        with patch("backend.app.detectar_e_isolar_rosto", side_effect=RuntimeError("test detector failure")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/api/analises", data={"foto": (image_file(), "sample.png")})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json["codigo"], "ERRO_INTERNO")

    def test_orientation_and_resize(self):
        source = Image.new("RGB", (2000, 1000), "white")
        exif = Image.Exif()
        exif[274] = 6  # Celular fotografado em retrato.
        data = BytesIO()
        source.save(data, format="JPEG", exif=exif)
        decoded = decode_photo(data.getvalue())
        self.assertEqual(decoded.shape, (1600, 800, 3))

    def test_embedded_srgb_profile(self):
        source = Image.new("RGB", (20, 20), (190, 120, 85))
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        data = BytesIO()
        source.save(data, format="PNG", icc_profile=profile)
        decoded = decode_photo(data.getvalue())
        # A função de upload entrega BGR ao detector, apesar da conversão ICC RGB.
        np.testing.assert_array_equal(decoded[0, 0], [85, 120, 190])

    def test_invalid_profile_is_rejected_before_detection(self):
        source = Image.new("RGB", (20, 20), (190, 120, 85))
        data = BytesIO()
        source.save(data, format="PNG", icc_profile=b"invalid profile")
        data.seek(0)
        with patch("backend.app.detectar_e_isolar_rosto") as detector:
            response = self.client.post("/api/analises", data={"foto": (data, "profile.png")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["codigo"], "FOTO_INVALIDA")
        detector.assert_not_called()

    def test_pixel_limit(self):
        data = BytesIO()
        Image.new("RGB", (6000, 4100)).save(data, format="PNG")
        data.seek(0)
        with patch("backend.app.detectar_e_isolar_rosto") as detector:
            response = self.client.post("/api/analises", data={"foto": (data, "large.png")})
        self.assertEqual(response.status_code, 400)
        detector.assert_not_called()

    def test_upload_stays_in_memory(self):
        # Exercita o limiar de 500 KB em que Werkzeug costuma usar disco.
        from backend.app import MemoryUploadRequest
        stream = MemoryUploadRequest.from_values()._get_file_stream(900_000, "image/jpeg", "photo.jpg")
        self.assertIsInstance(stream, BytesIO)

    def test_segmentation_statistics_match_actual_mask(self):
        with (ROOT / "samples/imagem_teste.jpeg").open("rb") as source:
            response = self.client.post("/api/analises", data={"foto": (source, "sample.jpg")})
        self.assertEqual(response.status_code, 200)
        data = response.json["preprocessamento"]
        self.assertFalse(data["simulado"])
        self.assertEqual(data["branco_referencia"], "D65")
        mask = np.array(Image.open(BytesIO(base64.b64decode(data["previas"]["mascara"].split(",")[1]))))
        self.assertEqual(int((mask > 0).sum()), data["pixels_pele"])
        self.assertAlmostEqual(data["percentual_pele"], 100 * data["pixels_pele"] / data["pixels_contorno"], places=2)
        rgba = np.array(Image.open(BytesIO(base64.b64decode(data["previas"]["pele"].split(",")[1]))))
        np.testing.assert_array_equal(rgba[..., 3], mask)
        self.assertEqual(len(response.json["etapas"]), 10)

    def test_stream_announces_stage_before_work_and_finishes_in_order(self):
        face = detectar_e_isolar_rosto(str(ROOT / 'samples/imagem_teste.jpeg'))
        with patch("backend.app.detectar_e_isolar_rosto", return_value=face) as detector:
            response = self.client.post("/api/analises", data={"foto": (image_file(), "face.png")},
                                        headers={"Accept": "application/x-ndjson"}, buffered=False)
            events = iter(response.response)
            first = json.loads(next(events))
            detector.assert_not_called()
            self.assertEqual(first["etapas"][0]["estado"], "processando")
            self.assertTrue(all(s["estado"] == "aguardando" for s in first["etapas"][1:]))
            remaining = [json.loads(chunk) for chunk in events]
            self.assertEqual(remaining[-1]["tipo"], "resultado")
            stages = [first] + [e for e in remaining if e["tipo"] == "etapa"]
            self.assertEqual([e["concluidas"] for e in stages], [n for i in range(10) for n in (i, i + 1)])
            self.assertTrue(all(s["estado"] == "concluida" for s in remaining[-1]["dados"]["etapas"]))
            response.close()

    def test_stream_no_face_stops_before_color_conversion(self):
        with patch("backend.src.segmentation.pipeline.rgb_to_lab") as convert:
            response = self.client.post("/api/analises", data={"foto": (image_file(), "blank.png")},
                                        headers={"Accept": "application/x-ndjson"})
            events = [json.loads(line) for line in response.data.splitlines()]
        self.assertEqual(events[-1]["tipo"], "erro")
        self.assertEqual(events[-1]["codigo"], "ROSTO_NAO_ENCONTRADO")
        self.assertEqual(events[-1]["status"], 422)
        self.assertEqual(len(events), 2)
        convert.assert_not_called()

    def test_stream_disconnect_stops_remaining_steps(self):
        with patch("backend.app.detectar_e_isolar_rosto") as detector:
            response = self.client.post("/api/analises", data={"foto": (image_file(), "face.png")},
                                        headers={"Accept": "application/x-ndjson"}, buffered=False)
            next(iter(response.response))
            response.close()
            detector.assert_not_called()

    def test_insufficient_skin_blocks_recommendations(self):
        with patch("backend.app.detectar_e_isolar_rosto", return_value=np.full((8, 8, 3), 150, np.uint8)):
            with patch("backend.app.generate_analysis") as mock:
                response = self.client.post("/api/analises", data={"foto": (image_file(), "tiny.png")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json["codigo"], "PELE_INSUFICIENTE")
        mock.assert_not_called()

    def test_stream_failure_never_returns_fake_success(self):
        with patch("backend.app.detectar_e_isolar_rosto", side_effect=RuntimeError("failure")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/api/analises", data={"foto": (image_file(), "face.png")},
                                            headers={"Accept": "application/x-ndjson"})
                events = [json.loads(line) for line in response.data.splitlines()]
        self.assertEqual(events[-1]["codigo"], "ERRO_INTERNO")
        self.assertFalse(any(e["tipo"] == "resultado" for e in events))

    def test_missing_model_never_falls_back_to_geometric_segmentation(self):
        for stream in (False, True):
            with self.subTest(stream=stream):
                with patch('backend.src.segmentation.semantic.get_session', side_effect=ModelUnavailableError('Modelo ausente.')):
                    with patch('backend.app.generate_analysis') as generate:
                        with (ROOT / 'samples/imagem_teste.jpeg').open('rb') as photo:
                            response = self.client.post('/api/analises', data={'foto': (photo, 'face.jpg')},
                                headers={'Accept': 'application/x-ndjson' if stream else 'application/json'})
                        body = [json.loads(line) for line in response.data.splitlines()][-1] if stream else response.json
                        self.assertEqual(body['codigo'], 'MODELO_INDISPONIVEL')
                        self.assertEqual(body['status'] if stream else response.status_code, 503)
                        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
