"""Testes em navegador isolado. Execute da raiz, como descrito no README."""

from io import BytesIO
from pathlib import Path
import os
import logging
import json
import threading
import unittest
import base64

import numpy as np

from PIL import Image
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from backend.app import create_app
from backend.tests.images import face_photo
from backend.src.mock_analysis import generate_analysis
from backend.src.segmentation.color import rgb_to_lab
from backend.src.segmentation.semantic import measure_skin
from backend.src.segmentation.pipeline import STAGES, summarize
from backend.src.skin_selection.contracts import CATEGORIES, ModuleResult
from backend.src.skin_selection.compose import compose
from backend.src.skin_selection.quality import evaluate
from backend.src.skin_selection.serialization import conditions

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".test-artifacts"


def selection_fixture(module_states=None, empty=()):
    """Recorte não quadrado com sobreposição, furos e incerteza externa."""
    shape = (60, 100)
    noise = np.random.default_rng(8).integers(-4, 5, (*shape, 1))
    rgb = (np.full((*shape, 3), [180, 120, 90]) + noise).astype(np.uint8)
    anatomy = np.zeros(shape, bool)
    anatomy[5:55, 10:90] = True
    modules = {key: ModuleResult.empty(shape, status='executado', source='fixture') for key in CATEGORIES}
    modules['acne'].accepted[10:20, 20:30] = True
    modules['acne'].accepted[13:17, 23:27] = False
    modules['vitiligo'].accepted[15:25, 25:40] = True
    modules['barba'].accepted[40:45, 20:70] = True
    modules['acne'].uncertain[25:30, 20:25] = True
    modules['acne'].uncertain[:5, :5] = True
    for key in empty:
        modules[key] = ModuleResult.empty(shape, status='executado', source='fixture')
    for key, status in (module_states or {}).items():
        modules[key] = ModuleResult.empty(shape, status=status, source='fixture')
    selected = compose(anatomy, modules)
    lab = rgb_to_lab(rgb)
    selected['quality'] = evaluate(rgb, lab, selected)
    skin = measure_skin(lab, selected['valid_mask']) if selected['quality']['usable'] else None
    result = generate_analysis()
    result['preprocessamento'] = summarize(rgb, {'face': anatomy, 'method': 'fixture', 'model': 'fixture', 'warnings': []}, {'k': 1}, skin, selected)
    result['condicoes'] = conditions(selected)
    result['marcacoes'] = []
    result['status_analise'] = 'concluida' if skin else 'inconclusiva'
    return result, rgb, selected


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

    def show_fixture(self, data):
        self.page.route('**/api/analises', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(data)))
        self.select_sample()
        self.page.get_by_role('button', name='Enviar para análise').click()
        expect(self.page.locator('.final-selection')).to_be_visible()
        expect(self.page.locator('.mask-render[data-render-state="loading"]')).to_have_count(0)

    def image_pixels(self, selector):
        url = self.page.locator(selector).get_attribute('src')
        return np.array(Image.open(BytesIO(base64.b64decode(url.split(',', 1)[1]))).convert('RGBA'))

    def test_masks_keep_alignment_holes_uncertainty_and_final_union(self):
        data, rgb, selected = selection_fixture()
        self.assertTrue(selected['quality']['usable'])
        self.show_fixture(data)
        expect(self.page.locator('.selection-quality')).to_have_attribute('data-quality', 'approved')
        expect(self.page.locator('.final-metrics')).to_contain_text('L*')
        expect(self.page.locator('.mask-render[data-render-state="error"]')).to_have_count(0)
        anatomy = self.image_pixels('[data-mask-preview="anatomy"]')
        np.testing.assert_array_equal(anatomy[:, :, 3] > 0, selected['anatomical_mask'])
        np.testing.assert_array_equal(anatomy[:, :, :3][selected['anatomical_mask']], rgb[selected['anatomical_mask']])
        final = self.image_pixels('#segmentation-overlay')
        np.testing.assert_array_equal(final[:, :, 3] > 0, selected['valid_mask'])
        np.testing.assert_array_equal(final[:, :, :3][selected['valid_mask']], rgb[selected['valid_mask']])
        # Cada motivo mantém suas sobreposições; a prévia final usa a união sem duplicar pixels.
        for key, color in {'acne': [219, 76, 90], 'vitiligo': [142, 91, 205],
                           'barba': [43, 120, 194]}.items():
            expected = rgb.copy()
            uncertain = selected['debug_masks'][key]['raw_uncertain'] & selected['anatomical_mask']
            accepted = selected['accepted_masks'][key]
            expected[uncertain] = np.floor(rgb[uncertain] * .3 + np.array([244, 181, 57]) * .7 + .5)
            expected[accepted] = np.floor(rgb[accepted] * .3 + np.array(color) * .7 + .5)
            np.testing.assert_array_equal(self.image_pixels(f'[data-mask-preview="{key}"]')[:, :, :3], expected)
        acne = self.page.locator('[data-category="acne"]')
        expect(acne.locator('dd').nth(0)).to_have_text('84')
        expect(acne.locator('dd').nth(1)).to_have_text('2,1%')
        expect(acne.locator('dd').nth(2)).to_have_text('25')
        # Nem o recorte não quadrado nem a imagem quadrada podem extrapolar o quadro.
        for selector in ('[data-mask-preview="acne"]', '[data-mask-preview="anatomy"]'):
            self.assertTrue(self.page.locator(selector).evaluate('''img => {
              const box = img.getBoundingClientRect(), frame = img.parentElement.getBoundingClientRect();
              return box.height <= frame.height + 1 && box.width <= frame.width + 1
                && getComputedStyle(img).objectFit === 'contain';
            }'''))

    def test_unavailable_is_distinct_from_empty_and_color_not_measured(self):
        data, _, _ = selection_fixture({'vitiligo': 'indisponivel', 'barba': 'falha'}, empty=('acne',))
        self.show_fixture(data)
        expect(self.page.locator('[data-category="acne"]')).to_contain_text('Nenhuma área selecionada')
        expect(self.page.locator('[data-mask-preview="acne"]')).to_be_visible()
        for key, label in [('vitiligo', 'Modelo indisponível'), ('barba', 'Falha na análise')]:
            card = self.page.locator(f'[data-category="{key}"]')
            expect(card).to_contain_text(label)
            expect(card.locator('img')).to_have_count(0)
            self.assertEqual(card.locator('dd').all_text_contents()[:4], ['—'] * 4)
        expect(self.page.locator('.selection-quality')).to_have_attribute('data-quality', 'inconclusive')
        expect(self.page.locator('.selection-quality')).to_contain_text('Uma das análises necessárias não ficou disponível.')
        self.assertEqual(self.page.locator('.final-metrics dd').all_text_contents()[-2:], ['Não calculada'] * 2)

    def test_processing_reports_unavailable_failed_and_skipped_modules(self):
        stages = [{'id': key, 'nome': name, 'descricao': description, 'estado': 'concluida'}
                  for key, name, description, _ in STAGES]
        states = {'acne': 'indisponivel', 'vitiligo': 'falha', 'medidas': 'nao_executado'}
        for stage in stages:
            if stage['id'] in states:
                stage['estado_modulo'] = states[stage['id']]
            if stage['id'] == 'medidas':
                stage['motivo'] = 'qualidade_inconclusiva'
        self.page.evaluate('''async progress => {
          const { processing, updateProcessing } = await import('/js/screens/processing.js');
          document.querySelector('main').innerHTML = processing({ example: false });
          updateProcessing(progress);
        }''', {'etapas': stages, 'concluidas': 10, 'total': 10})
        expect(self.page.locator('.processing-step')).to_have_count(10)
        expect(self.page.locator('.processing-step.partial')).to_have_count(3)
        expect(self.page.locator('[data-step="acne"]')).to_contain_text('Indisponível')
        expect(self.page.locator('[data-step="vitiligo"]')).to_contain_text('Falha na análise')
        expect(self.page.locator('[data-step="medidas"]')).to_contain_text('a cor não foi medida')
        expect(self.page.locator('#processing-progress')).to_have_attribute('aria-valuenow', '100')

    def test_misaligned_preview_reports_error_without_hiding_other_results(self):
        data, _, _ = selection_fixture()
        buffer = BytesIO()
        Image.new('L', (3, 3)).save(buffer, format='PNG')
        data['preprocessamento']['selecao']['masks']['accepted_masks']['acne'] = (
            'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode())
        self.show_fixture(data)
        card = self.page.locator('[data-category="acne"]')
        expect(card.locator('.mask-render')).to_have_attribute('data-render-state', 'error')
        expect(card).to_contain_text('Não foi possível montar esta prévia')
        expect(self.page.locator('[data-mask-preview="vitiligo"]')).to_be_visible()
        expect(self.page.locator('#segmentation-overlay')).to_be_visible()

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
        self.page.wait_for_function('document.querySelector(\'[data-step="cielab"][data-state="processando"]\')', timeout=10000)
        self.page.screenshot(path=str(ARTIFACTS / "pipeline-progress-desktop.png"), full_page=True)
        expect(self.page.get_by_text("✓ Rosto detectado · verificação real", exact=True)).to_be_visible(timeout=40000)
        states = self.page.evaluate("window.pipelineStates")
        for stage in ("rosto", "cielab", "mascara", "acne", "vitiligo", "barba", "selecao", "clusters", "medidas", "resultado"):
            self.assertIn(stage, states)
        expect(self.page.get_by_role("heading", name="Segmentação básica do rosto")).to_be_visible()
        overlay = self.page.locator('#segmentation-overlay')
        expect(overlay).to_be_visible()
        self.assertTrue(overlay.evaluate('img => img.complete && img.naturalWidth > 0'))
        self.assertEqual(self.page.locator('#marks, .segmentation-source').count(), 0)
        self.assertEqual(self.page.locator('.exclusion-card').count(), 3)
        expect(self.page.locator('[data-mask-preview="anatomy"]')).to_be_visible()
        expect(self.page.locator('.mask-render[data-render-state="loading"]')).to_have_count(0)
        self.assertEqual(self.page.locator('.mask-render[data-render-state="error"]').count(), 0)
        self.assertTrue(self.page.locator('[data-mask-preview="barba"]').evaluate(
            'img => img.getBoundingClientRect().height <= img.parentElement.getBoundingClientRect().height + 1'))
        expect(self.page.locator('.selection-quality')).to_contain_text('Seleção inconclusiva')
        expect(self.page.locator('.final-metrics')).to_contain_text('Não calculada')
        self.assertEqual(self.page.locator('.preprocessing-previews img').count(), 3)
        self.assertTrue(self.page.locator('.preprocessing-previews img').evaluate_all("images => images.every(i => i.complete && i.naturalWidth > 0)"))
        self.assertEqual(self.page.locator(".product-card").count(), 3)
        self.page.screenshot(path=str(ARTIFACTS / "result-desktop.png"), full_page=True)
        self.page.locator('.preprocessing-previews').screenshot(path=str(ARTIFACTS / 'segmentation-basic-desktop.png'))
        self.page.locator('.exclusion-grid').screenshot(path=str(ARTIFACTS / 'exclusions-desktop.png'), style='.site-header { visibility: hidden; }')
        self.page.locator('.final-selection').screenshot(path=str(ARTIFACTS / 'useful-skin-desktop.png'))
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

    def test_old_backend_without_selection_keeps_photo_for_retry(self):
        self.select_sample()
        legacy, _, _ = selection_fixture()
        del legacy['preprocessamento']['selecao']
        self.page.route('**/api/analises', lambda route: route.fulfill(
            status=200, content_type='application/json', body=json.dumps(legacy)))
        self.page.get_by_role('button', name='Enviar para análise').click()
        expect(self.page.get_by_role('alert')).to_contain_text('O servidor não enviou as máscaras da seleção de pele')
        expect(self.page.get_by_alt_text('Prévia da foto selecionada')).to_be_visible()
        expect(self.page.locator('.final-selection')).to_have_count(0)

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
            expect(self.page.locator('.mask-render[data-render-state="loading"]')).to_have_count(0)
            expect(self.page.locator('.mask-render[data-render-state="error"]')).to_have_count(0)
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), width)
            self.page.screenshot(path=str(ARTIFACTS / f"result-mobile-{width}.png"), full_page=True)
            self.page.locator('[data-category="barba"]').screenshot(path=str(ARTIFACTS / f'beard-mobile-{width}.png'), style='.site-header { visibility: hidden; }')
            self.page.locator('.final-selection').screenshot(path=str(ARTIFACTS / f'useful-skin-mobile-{width}.png'), style='.site-header { visibility: hidden; }')

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
        self.page.wait_for_function('document.querySelector(".processing-step.active")', timeout=10000)
        self.page.get_by_role("button", name="Cancelar e voltar ao início").click()
        expect(self.page.get_by_role("heading", name="Encontre a base certa para o seu tom de pele.")).to_be_visible()
        # A próxima interação garante que eventos antigos não alteram a captura.
        self.page.get_by_role("button", name="Começar", exact=True).click()
        expect(self.page.get_by_role("heading", name="Vamos começar pela sua foto.")).to_be_visible()
        self.assertEqual(self.page.locator('.real-preprocessing').count(), 0)


if __name__ == "__main__":
    unittest.main()
