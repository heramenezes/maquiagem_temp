"""Toda medição do rosto gera tom e bases; qualidade reduzida gera ressalvas."""

import hashlib
import json

import numpy as np
from skimage.color import lab2rgb

from ..catalog import load_catalog
from .matching import METHOD_VERSION, rank_foundations
from .palette import MONK_HEX, PALETTE_SOURCE, PALETTE_VERSION


def build_analysis(skin, selection, face_pixels):
    catalog = load_catalog()
    if not catalog:
        raise ValueError("O catálogo de bases está vazio.")
    fingerprint = hashlib.sha256(json.dumps(
        sorted(catalog, key=lambda product: product["id"]),
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf8")).hexdigest()
    quality = selection["quality"]
    match = {
        "metodo": METHOD_VERSION,
        "estimador": "mediana_lab",
        "espaco_cor": "CIELAB", "branco_referencia": "D65",
        "paleta_versao": PALETTE_VERSION, "paleta_fonte": PALETTE_SOURCE,
        "catalogo_sha256": fingerprint,
        "criterio_ranking": "mesmo_monk_depois_grupos_por_delta_e00_monk_e_refinamento_pele_base",
        "experimental": True, "validado": False,
        "limiar_aceitacao_delta_e00": None,
        "avisos": [
            "Classificação da cor observada; não corrige iluminação ou balanço de branco.",
            "Comparação com HEX do catálogo, sem validação de bases aplicadas na pele.",
            "Critérios de seleção e classificação Monk ainda não validados com anotações humanas.",
        ],
    }
    result = {
        "schema_version": 2, "simulado": False, "exemplo": False,
        "precheck": {"executado": True, "rosto_detectado": True},
        "tom": None, "escala_monk": list(MONK_HEX), "catalogo_total": len(catalog),
        "recomendacoes": [], "match": match,
    }
    # A máscara efetivamente medida pode incluir um fallback documentado.
    lab = skin["median_lab"]
    tone, recommendations = rank_foundations(lab, catalog)
    rgb = np.rint(lab2rgb(np.asarray(lab, dtype=np.float64)) * 255).astype(np.uint8)
    tone.update(
        lab=np.asarray(lab, dtype=float).tolist(),
        cor_pele_hex="#{:02x}{:02x}{:02x}".format(*rgb),
        ita=None,  # ITA não participa desta implementação; nenhum valor demonstrativo.
        pele_utilizada=round(100 * int(skin["mask"].sum()) / max(face_pixels, 1), 2),
    )
    result.update(tom=tone, recomendacoes=recommendations)
    fallback = any(not product["mesmo_monk"] for product in recommendations)
    match.update(status="calculado", motivos=list(quality["reasons"]),
                 confianca_reduzida=bool(quality["reasons"]),
                 grupos_complementares_utilizados=fallback)
    return result
