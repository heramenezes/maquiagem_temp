"""Fixtures demonstrativas; nenhum valor abaixo é inferido da foto enviada.

Usadas somente por /api/exemplo. Uploads usam tone_matching.analysis.
O catálogo é real; a recomendação deste exemplo é simulada.
"""

from .catalog import load_catalog
from .tone_matching.color import hex_to_lab
from .tone_matching.matching import rank_foundations


def generate_analysis(*, example=False):
    # Cor fixa ilustrativa; não é inferida de uma foto enviada pelo usuário.
    color = "#B4785A"
    lab = hex_to_lab(color)
    catalog = load_catalog()
    recommendations = rank_foundations(lab, catalog)
    return {
        "schema_version": 3,
        "simulado": True, "exemplo": example,
        "precheck": {"executado": not example, "rosto_detectado": None if example else True},
        "tom": {"cor_pele_hex": color, "lab": lab.tolist(), "pele_utilizada": 74},
        "catalogo_total": len(catalog),
        "recomendacoes": recommendations,
        "condicoes": [
            {"id": "acne", "nome": "Acne", "detectada": True,
             "descricao": "Pequenas inflamações que mudam a cor da pele em pontos isolados.",
             "intensidade": "Leve", "local": "Testa e bochechas"},
            {"id": "vitiligo", "nome": "Vitiligo", "detectada": True,
             "descricao": "Áreas com perda de pigmentação, mais claras que o restante da pele.",
             "intensidade": "1 área pequena", "local": "Queixo"},
            {"id": "barba", "nome": "Barba e bigode", "detectada": False,
             "descricao": "Exemplo ilustrativo de exclusão de pelos faciais.",
             "intensidade": None, "local": None},
        ],
        "marcacoes": [
            {"nome": "Acne", "x": 50, "y": 20, "largura": 14, "altura": 9},
            {"nome": "Acne", "x": 27, "y": 50, "largura": 12, "altura": 10},
            {"nome": "Acne", "x": 61, "y": 52, "largura": 12, "altura": 10},
            {"nome": "Vitiligo", "x": 42, "y": 74, "largura": 16, "altura": 9},
        ],
    }
