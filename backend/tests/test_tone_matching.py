"""Referências de cor, ranking e integração HTTP; não valida match físico."""

from io import BytesIO
import json
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from skimage.color import deltaE_ciede2000

from backend.app import create_app
from backend.src.segmentation.color import rgb_to_lab
from backend.src.tone_matching.analysis import build_analysis
from backend.src.tone_matching.matching import classify_monk, rank_foundations
from backend.src.tone_matching.palette import MONK_HEX, hex_to_lab
from backend.src.skin_selection.contracts import ModuleResult


def product(identifier, color):
    return {"id": identifier, "hex": color, "marca": "Teste", "nome": "Base",
            "cor": str(identifier), "preco": 20., "link": "https://example.com/base"}


class ColorMatchingTests(unittest.TestCase):
    def test_ciede2000_reference_pair(self):
        # Sharma et al., supplementary test data, pair 1: ΔE00 = 2.0425.
        distance = deltaE_ciede2000([50, 2.6772, -79.7751], [50, 0, -82.7485])
        self.assertAlmostEqual(float(distance), 2.0425, places=4)

    def test_all_ten_swatches_classify_as_themselves(self):
        for index, color in enumerate(MONK_HEX, 1):
            with self.subTest(monk=index):
                tone = classify_monk(hex_to_lab(color))
                self.assertEqual(tone["monk"], index)
                self.assertAlmostEqual(tone["delta_e00"], 0)
                self.assertEqual(len(tone["distancias_monk"]), 10)
                self.assertGreater(tone["margem_delta_e00"], 0)

    def test_invalid_lab_hex_and_limit_are_rejected(self):
        self.assertEqual(classify_monk(hex_to_lab("#FFFFFF"))["monk"], 1)
        for lab in ([np.nan, 0, 0], [50, np.inf, 0], [101, 0, 0], [-1, 0, 0], [[50, 0, 0]]):
            with self.subTest(lab=lab), self.assertRaises(ValueError):
                classify_monk(lab)
        for color in ("a07e56", "#xyz123", "#123", None):
            with self.subTest(color=color), self.assertRaises(ValueError):
                hex_to_lab(color)
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                rank_foundations(hex_to_lab(MONK_HEX[5]), [], limit=limit)

    def test_refinement_within_monk_and_id_tie_break_do_not_mutate_catalog(self):
        catalog = [product(1, "#a08156"), product(9, MONK_HEX[5]), product(2, MONK_HEX[5])]
        before = json.dumps(catalog, sort_keys=True)
        _, recommendations = rank_foundations(hex_to_lab(MONK_HEX[5]), catalog)
        self.assertEqual([p["id"] for p in recommendations], [2, 9, 1])
        self.assertTrue(all(p["mesmo_monk"] for p in recommendations))
        self.assertEqual(recommendations[0]["delta_e00"], 0)
        self.assertEqual(json.dumps(catalog, sort_keys=True), before)
        _, reversed_result = rank_foundations(hex_to_lab(MONK_HEX[5]), list(reversed(catalog)))
        self.assertEqual(recommendations, reversed_result)

    def test_complementary_groups_follow_swatch_color_distance(self):
        catalog = [product(1, MONK_HEX[4]), product(2, MONK_HEX[6]), product(3, MONK_HEX[5])]
        _, recommendations = rank_foundations(hex_to_lab(MONK_HEX[5]), catalog)
        self.assertEqual([p["monk"] for p in recommendations], [6, 7, 5])
        self.assertEqual([p["mesmo_monk"] for p in recommendations], [True, False, False])

    def test_same_monk_has_priority_even_if_another_group_is_closer(self):
        # Pele perto da fronteira 6/7: candidato Monk 6 é mais próximo em Lab,
        # mas a estratégia escolhida mantém a prioridade do grupo Monk 7.
        tone, recommendations = rank_foundations(hex_to_lab("#916d4f"), [
            product(1, "#946f50"), product(2, MONK_HEX[6]),
        ])
        self.assertEqual(tone["monk"], 7)
        self.assertEqual([p["id"] for p in recommendations], [2, 1])
        self.assertGreater(recommendations[0]["delta_e00"], recommendations[1]["delta_e00"])

    def test_sparse_empty_and_duplicate_catalogs(self):
        lab = hex_to_lab(MONK_HEX[5])
        self.assertEqual(rank_foundations(lab, [product(1, MONK_HEX[5])])[1][0]["id"], 1)
        tone, recommendations = rank_foundations(lab, [])
        self.assertEqual(tone["monk"], 6)
        self.assertEqual(recommendations, [])
        with self.assertRaises(ValueError):
            rank_foundations(lab, [product(1, MONK_HEX[5]), product(1, MONK_HEX[6])])

    def test_color_change_changes_both_tone_and_ranking(self):
        catalog = [product(i, color) for i, color in enumerate(MONK_HEX, 1)]
        for index in (2, 6, 9):
            tone, recommendations = rank_foundations(hex_to_lab(MONK_HEX[index - 1]), catalog)
            self.assertEqual(tone["monk"], index)
            self.assertEqual(recommendations[0]["id"], index)
            self.assertEqual(len(recommendations), 3)

    def test_quality_gate_and_missing_measurement_never_call_ranker(self):
        mask = np.ones((20, 20), bool)
        for usable, skin in ((False, {"median_lab": hex_to_lab(MONK_HEX[5])}), (True, None)):
            selection = {"quality": {"usable": usable, "reasons": [] if usable else ["nitidez_insuficiente"]},
                         "valid_mask": mask}
            with patch("backend.src.tone_matching.analysis.rank_foundations") as ranker:
                result = build_analysis(skin, selection, 400)
            ranker.assert_not_called()
            self.assertIsNone(result["tom"])
            self.assertEqual(result["recomendacoes"], [])
            self.assertEqual(result["match"]["status"], "inconclusivo")
            self.assertTrue(result["match"]["motivos"])
            json.dumps(result, allow_nan=False)

    def test_empty_catalog_preserves_real_tone_and_reports_no_candidates(self):
        selection = {"quality": {"usable": True, "reasons": []}, "valid_mask": np.ones((20, 20), bool)}
        with patch("backend.src.tone_matching.analysis.load_catalog", return_value=[]):
            result = build_analysis({"median_lab": hex_to_lab(MONK_HEX[5])}, selection, 800)
        self.assertEqual(result["tom"]["monk"], 6)
        self.assertEqual(result["tom"]["pele_utilizada"], 50)
        self.assertIsNone(result["tom"]["ita"])
        self.assertEqual(result["match"]["status"], "sem_candidatos")
        self.assertEqual(result["recomendacoes"], [])


class MatchingApiTests(unittest.TestCase):
    def analyze(self, color, *, stream=False, fail=False):
        base = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)])
        noise = np.random.default_rng(1).integers(-3, 4, (100, 160, 1))
        rgb = np.clip(base + noise, 0, 255).astype(np.uint8)
        # A área branca à esquerda representa região excluída pelo especialista.
        rgb[:, :40] = 255
        mask = np.ones(rgb.shape[:2], bool)
        anatomy = {"allowed": mask, "face": mask, "seeds": mask,
                   "method": "test", "model": "test", "warnings": []}

        def module(key, *args):
            result = ModuleResult.empty(mask.shape, status="falha" if fail else "executado")
            if key == "acne" and not fail:
                result.accepted[:, :40] = True
            return result

        photo = BytesIO()
        Image.fromarray(rgb).save(photo, format="PNG")
        photo.seek(0)
        client = create_app({"TESTING": True}).test_client()
        with patch("backend.app.detectar_e_isolar_rosto", return_value=rgb), \
             patch("backend.src.segmentation.pipeline.facial_masks", return_value=anatomy), \
             patch("backend.src.segmentation.pipeline.run_module", side_effect=module), \
             patch("backend.app.generate_analysis") as mock_result:
            response = client.post("/api/analises", data={"foto": (photo, "skin.png")},
                                   headers={"Accept": "application/x-ndjson" if stream else "application/json"})
            self.assertEqual(response.status_code, 200)
            if stream:
                events = [json.loads(line) for line in response.data.splitlines()]
                self.assertEqual(sum(e["tipo"] in ("resultado", "erro") for e in events), 1)
                self.assertEqual(events[-1]["tipo"], "resultado")
                result = events[-1]["dados"]
            else:
                result = response.json
        mock_result.assert_not_called()
        return result, rgb

    def test_json_ndjson_use_only_approved_pixels_and_have_same_match(self):
        plain, rgb = self.analyze(MONK_HEX[5])
        streamed, _ = self.analyze(MONK_HEX[5], stream=True)
        self.assertEqual(plain["tom"], streamed["tom"])
        self.assertEqual(plain["match"], streamed["match"])
        self.assertEqual(plain["recomendacoes"], streamed["recomendacoes"])
        self.assertEqual(plain["tom"]["monk"], 6)
        np.testing.assert_allclose(plain["tom"]["lab"], np.median(rgb_to_lab(rgb[:, 40:]), axis=(0, 1)))
        self.assertEqual(plain["tom"]["pele_utilizada"], 75)
        self.assertEqual(plain["match"]["status"], "calculado")
        self.assertFalse(plain["simulado"])
        self.assertFalse(plain["match"]["validado"])
        self.assertTrue(all(not step["simulado"] for step in plain["etapas"]))
        self.assertEqual(len(plain["recomendacoes"]), 3)
        json.dumps(plain, allow_nan=False)

    def test_different_photos_change_recommendations(self):
        light, _ = self.analyze(MONK_HEX[2])
        dark, _ = self.analyze(MONK_HEX[7])
        self.assertEqual(light["tom"]["monk"], 3)
        self.assertEqual(dark["tom"]["monk"], 8)
        self.assertNotEqual([p["id"] for p in light["recomendacoes"]],
                            [p["id"] for p in dark["recomendacoes"]])

    def test_failed_specialist_abstains_in_json_and_ndjson(self):
        for stream in (False, True):
            with self.subTest(stream=stream):
                result, _ = self.analyze(MONK_HEX[5], stream=stream, fail=True)
                self.assertEqual(result["status_analise"], "inconclusiva")
                self.assertIsNone(result["tom"])
                self.assertEqual(result["recomendacoes"], [])
                self.assertEqual(result["match"]["status"], "inconclusivo")
                self.assertIn("modulo_obrigatorio_indisponivel", result["match"]["motivos"])


if __name__ == "__main__":
    unittest.main()
