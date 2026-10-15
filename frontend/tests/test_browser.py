"""Testes em navegador isolado. Execute da raiz, como descrito no README."""

from io import BytesIO
from pathlib import Path
import os
import logging
import threading
import unittest

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from backend.app import create_app

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".test-artifacts"


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        logging.getLogger("FaceDetector").setLevel(logging.ERROR)
        cls.server = make_server("127.0.0.1", 0, create_app(), threaded=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        options = {"headless": True}
        if os.environ.get("BROWSER_CHANNEL"):
            options["channel"] = os.environ["BROWSER_CHANNEL"]
        cls.browser = cls.playwright.chromium.launch(**options)
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)
        self.page.evaluate("document.fonts.ready")

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [])

    def select_sample(self):
        self.page.get_by_role("button", name="Começar", exact=True).click()
        self.page.screenshot(path=str(ARTIFACTS / "capture-desktop.png"), full_page=True)
        self.page.locator("#gallery-input").set_input_files(str(ROOT / "samples/imagem_teste.jpeg"))
        expect(self.page.get_by_role("heading", name="Vamos analisar esta foto?")).to_be_visible()

    def test_real_upload_and_result(self):
        self.assertTrue(self.page.evaluate("document.fonts.check('800 16px Archivo')"))
        self.page.screenshot(path=str(ARTIFACTS / "home-desktop.png"), full_page=True)
        self.select_sample()
        self.page.screenshot(path=str(ARTIFACTS / "review-desktop.png"), full_page=True)
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible()
        self.assertEqual(self.page.locator(".product-card").count(), 3)
        self.page.screenshot(path=str(ARTIFACTS / "result-desktop.png"), full_page=True)
        self.page.get_by_role("button", name="Fazer nova análise").click()
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()
        self.assertEqual(self.page.locator(".product-card").count(), 0)

    def test_no_face_error_and_retry(self):
        self.page.get_by_role("button", name="Começar", exact=True).click()
        data = BytesIO()
        Image.new("RGB", (300, 300), "black").save(data, format="PNG")
        self.page.locator("#gallery-input").set_input_files({"name": "no-face.png", "mimeType": "image/png", "buffer": data.getvalue()})
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_role("alert")).to_contain_text("Não encontramos um rosto visível")
        self.assertEqual(self.page.locator(".product-card").count(), 0)
        self.page.screenshot(path=str(ARTIFACTS / "no-face-error.png"), full_page=True)
        self.page.locator("#gallery-input").set_input_files(str(ROOT / "samples/imagem_teste.jpeg"))
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible()

    def test_example_and_marks(self):
        self.page.get_by_role("button", name="Ver um exemplo", exact=True).click()
        expect(self.page.get_by_text("Exemplo de resultado", exact=True)).to_be_visible()
        expect(self.page.locator(".notice").first).to_contain_text("não enviou uma foto")
        # Bootstrap também define .mark; as marcações não podem cobrir a foto.
        self.assertEqual(self.page.locator(".mark").first.evaluate("el => getComputedStyle(el).backgroundColor"), "rgba(0, 0, 0, 0)")
        self.page.get_by_role("button", name="Ocultar marcações").click()
        expect(self.page.locator("#marks")).to_be_hidden()
        self.page.get_by_role("button", name="Mostrar marcações").click()
        expect(self.page.locator("#marks")).to_be_visible()

    def test_connection_failure_keeps_photo_for_retry(self):
        self.select_sample()
        self.page.route("**/api/analises", lambda route: route.abort())
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_role("alert")).to_contain_text("Não foi possível conectar")
        expect(self.page.get_by_alt_text("Prévia da foto selecionada")).to_be_visible()
        self.page.unroute("**/api/analises")
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible()

    def test_invalid_file(self):
        self.page.get_by_role("button", name="Começar", exact=True).click()
        self.page.locator("#gallery-input").set_input_files({"name": "fake.jpg", "mimeType": "image/jpeg", "buffer": b"bad image"})
        expect(self.page.get_by_role("alert")).to_contain_text("Não foi possível abrir esta imagem")
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()

    def test_reset_cancels_pending_request(self):
        requests = []
        self.page.route("**/api/exemplo", lambda route: requests.append(route))
        self.page.get_by_role("button", name="Ver um exemplo", exact=True).click()
        expect(self.page.get_by_role("heading", name="Preparando o exemplo…")).to_be_visible()
        self.page.screenshot(path=str(ARTIFACTS / "processing-desktop.png"), full_page=True)
        self.page.get_by_role("button", name="Cancelar e voltar ao início").click()
        expect(self.page.get_by_role("heading", name="Encontre a base certa para o seu tom de pele.")).to_be_visible()
        self.assertEqual(len(requests), 1)
        requests[0].abort()
        self.assertEqual(self.page.locator(".product-card").count(), 0)

    def test_mobile_layout_and_camera_input(self):
        for width in (390, 320):
            self.page.set_viewport_size({"width": width, "height": 844})
            self.page.goto(self.url)
            expect(self.page.get_by_role("heading", level=1)).to_be_visible()
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
            self.page.screenshot(path=str(ARTIFACTS / f"home-mobile-{width}.png"), full_page=True)
            self.page.get_by_role("button", name="Começar", exact=True).click()
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
            self.page.screenshot(path=str(ARTIFACTS / f"capture-mobile-{width}.png"), full_page=True)
            self.assertEqual(self.page.locator("#camera-input").get_attribute("capture"), "user")
            with self.page.expect_file_chooser() as chooser:
                self.page.get_by_role("button", name="Tirar foto", exact=True).click()
            chooser.value.set_files(str(ROOT / "samples/imagem_teste.jpeg"))
            self.page.get_by_role("button", name="Enviar para análise").click()
            expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible()
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
            self.page.screenshot(path=str(ARTIFACTS / f"result-mobile-{width}.png"), full_page=True)


if __name__ == "__main__":
    unittest.main()
