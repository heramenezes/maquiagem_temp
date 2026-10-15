"""Testes em navegador isolado. Execute da raiz, como descrito no README."""

from io import BytesIO
from pathlib import Path
import os
import logging
import json
import threading
import unittest

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from backend.app import create_app
from backend.tests.images import face_photo

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
        self.page.evaluate("""() => {
          window.pipelineStates = [];
          new MutationObserver(() => {
            const active = document.querySelector('.processing-step.active');
            if (active) window.pipelineStates.push(active.dataset.step);
          }).observe(document.querySelector('main'), {childList: true, subtree: true});
        }""")
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.locator('[data-step="cielab"][data-state="processando"]')).to_be_visible(timeout=10000)
        self.page.screenshot(path=str(ARTIFACTS / "pipeline-progress-desktop.png"), full_page=True)
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible(timeout=40000)
        states = self.page.evaluate("window.pipelineStates")
        for stage in ("rosto", "cielab", "mascara", "clusters", "medidas", "resultado"):
            self.assertIn(stage, states)
        expect(self.page.get_by_role("heading", name="Pele separada para a próxima etapa")).to_be_visible()
        overlay = self.page.locator('#segmentation-overlay')
        expect(overlay).to_be_visible()
        self.assertTrue(overlay.evaluate('img => img.complete && img.naturalWidth > 0'))
        source = self.page.locator('.segmentation-source')
        self.assertEqual(source.bounding_box(), overlay.bounding_box())
        expect(self.page.locator('#marks')).to_be_visible()
        self.page.get_by_role('button', name='Ocultar segmentação', exact=True).click()
        expect(overlay).to_be_hidden()
        expect(self.page.locator('#marks')).to_be_visible()
        self.assertEqual(source.evaluate('img => getComputedStyle(img).filter'), 'none')
        self.page.get_by_role('button', name='Mostrar segmentação', exact=True).click()
        expect(overlay).to_be_visible()
        self.page.get_by_role('button', name='Ocultar marcações', exact=True).click()
        expect(self.page.locator('#marks')).to_be_hidden()
        expect(overlay).to_be_visible()
        self.page.get_by_role('button', name='Mostrar marcações', exact=True).click()
        self.assertEqual(self.page.locator('.preprocessing-previews img').count(), 3)
        self.assertTrue(self.page.locator('.preprocessing-previews img').evaluate_all("images => images.every(i => i.complete && i.naturalWidth > 0)"))
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
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible(timeout=40000)

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

    def test_multiple_faces_requests_new_photo_before_analysis(self):
        self.page.get_by_role('button', name='Começar', exact=True).click()
        self.page.locator('#gallery-input').set_input_files({
            'name': 'two-faces.png', 'mimeType': 'image/png', 'buffer': face_photo().getvalue()})
        self.page.get_by_role('button', name='Enviar para análise').click()
        expect(self.page.get_by_role('alert')).to_contain_text('Encontramos mais de um rosto', timeout=10000)
        expect(self.page.get_by_role('heading', name='Vamos começar pela sua foto.')).to_be_visible()
        self.assertEqual(self.page.locator('.product-card').count(), 0)
        self.assertEqual(self.page.locator('#gallery-input').input_value(), '')
        self.page.locator('#gallery-input').set_input_files(str(ROOT / 'samples/imagem_teste.jpeg'))
        self.page.get_by_role('button', name='Enviar para análise').click()
        expect(self.page.locator('#segmentation-overlay')).to_be_visible(timeout=40000)

    def test_connection_failure_keeps_photo_for_retry(self):
        self.select_sample()
        self.page.route("**/api/analises", lambda route: route.abort())
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_role("alert")).to_contain_text("Não foi possível conectar")
        expect(self.page.get_by_alt_text("Prévia da foto selecionada")).to_be_visible()
        self.page.unroute("**/api/analises")
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible(timeout=40000)

    def test_invalid_file(self):
        self.page.get_by_role("button", name="Começar", exact=True).click()
        self.page.locator("#gallery-input").set_input_files({"name": "fake.jpg", "mimeType": "image/jpeg", "buffer": b"bad image"})
        expect(self.page.get_by_role("alert")).to_contain_text("Não foi possível abrir esta imagem")
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()

    def test_old_backend_without_segmentation_keeps_photo_for_retry(self):
        self.select_sample()
        legacy = self.page.request.get(self.url + '/api/exemplo').json()
        legacy['exemplo'] = False
        legacy['precheck'] = {'executado': True, 'rosto_detectado': True}
        self.page.route('**/api/analises', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(legacy)))
        self.page.get_by_role('button', name='Enviar para análise').click()
        expect(self.page.get_by_role('alert')).to_contain_text('O servidor não enviou a segmentação')
        expect(self.page.get_by_alt_text('Prévia da foto selecionada')).to_be_visible()
        self.assertEqual(self.page.locator('.product-card').count(), 0)

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
            expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible(timeout=40000)
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
            self.page.screenshot(path=str(ARTIFACTS / f"result-mobile-{width}.png"), full_page=True)

    def test_truncated_stream_retains_preview_and_reports_failure(self):
        self.select_sample()
        self.page.route("**/api/analises", lambda route: route.fulfill(
            status=200, content_type="application/x-ndjson", body='\n'))
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_role("alert")).to_contain_text("O processamento foi interrompido")
        expect(self.page.get_by_alt_text("Prévia da foto selecionada")).to_be_visible()

    def test_late_skin_error_requests_new_photo(self):
        self.select_sample()
        body = json.dumps({"tipo": "erro", "codigo": "PELE_INSUFICIENTE",
                           "mensagem": "Não conseguimos separar pele suficiente.", "status": 422}) + '\n'
        self.page.route("**/api/analises", lambda route: route.fulfill(
            status=200, content_type="application/x-ndjson", body=body))
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.get_by_role("alert")).to_contain_text("Não conseguimos separar pele suficiente")
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()

    def test_cancel_real_processing_does_not_show_stale_result(self):
        self.select_sample()
        self.page.get_by_role("button", name="Enviar para análise").click()
        expect(self.page.locator('[data-step="cielab"][data-state="processando"]')).to_be_visible(timeout=10000)
        self.page.get_by_role("button", name="Cancelar e voltar ao início").click()
        expect(self.page.get_by_role("heading", name="Encontre a base certa para o seu tom de pele.")).to_be_visible()
        # A próxima interação garante que eventos antigos não alteram a captura.
        self.page.get_by_role("button", name="Começar", exact=True).click()
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()
        self.assertEqual(self.page.locator('.real-preprocessing').count(), 0)


if __name__ == "__main__":
    unittest.main()
