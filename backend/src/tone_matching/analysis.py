"""Toda medição do rosto gera tom e bases; qualidade reduzida gera ressalvas."""

import hashlib
import json

import numpy as np
from skimage.color import lab2rgb

from ..catalog import load_catalog
from .matching import METHOD_VERSION, rank_foundations


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
    regional = skin.get("regional")
    match = {
        "metodo": METHOD_VERSION,
        "estimador": regional["estimador"] if regional else "mediana_lab",
        "espaco_cor": "CIELAB", "branco_referencia": "D65",
        "catalogo_sha256": fingerprint,
        "criterio_ranking": "delta_e00_pele_base_depois_id",
        "experimental": True, "validado": False,
        "limiar_aceitacao_delta_e00": None,
        "avisos": [
            "Estimativa da cor observada; não corrige iluminação ou balanço de branco.",
            "Comparação com HEX do catálogo, sem validação de bases aplicadas na pele.",
            "Critérios de seleção e recomendação ainda não validados com bases aplicadas na pele.",
            "Regiões faciais e pesos de qualidade são heurísticos, sem validação de acurácia.",
        ],
    }
    result = {
        "schema_version": 3, "simulado": False, "exemplo": False,
        "precheck": {"executado": True, "rosto_detectado": True},
        "tom": None, "catalogo_total": len(catalog),
        "recomendacoes": [], "match": match,
    }
    # A máscara efetivamente medida pode incluir um fallback documentado.
    lab = regional["lab"] if regional else skin["median_lab"]
    recommendations = rank_foundations(lab, catalog)
    regional_rankings = []
    for region in regional["regioes"] if regional else []:
        if region["lab"] is not None:
            candidates = rank_foundations(region["lab"], catalog)
            regional_rankings.append({"regiao": region["nome"],
                                      "ids": [p["id"] for p in candidates]})
    ids = [p["id"] for p in recommendations]
    match["sensibilidade_regional"] = {
        "avaliada": len(regional_rankings) >= 2,
        "top3_por_regiao": regional_rankings,
        "ranking_varia": len(regional_rankings) >= 2 and any(r["ids"] != ids for r in regional_rankings),
    }
    rgb = np.rint(lab2rgb(np.asarray(lab, dtype=np.float64)) * 255).astype(np.uint8)
    tone = dict(
        lab=np.asarray(lab, dtype=float).tolist(),
        cor_pele_hex="#{:02x}{:02x}{:02x}".format(*rgb),
        pele_utilizada=round(100 * int(skin["mask"].sum()) / max(face_pixels, 1), 2),
    )
    result.update(tom=tone, recomendacoes=recommendations)
    reasons = list(dict.fromkeys([*quality["reasons"], *(regional["motivos"] if regional else [])]))
    match.update(status="calculado", motivos=reasons,
                 confianca_reduzida=bool(reasons))
    return result
