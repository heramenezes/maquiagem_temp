"""Testes do contrato HTTP, incluindo o detector real com as amostras locais."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from backend.app import MAX_FILE_BYTES, create_app, decode_photo
from backend.src.catalog import load_catalog

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

    def test_repeated_attempts_do_not_reuse_approved_photo(self):
        with patch("backend.app.detectar_e_isolar_rosto", side_effect=[np.ones((10, 10, 3), dtype=np.uint8), None]):
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


if __name__ == "__main__":
    unittest.main()
