"""Fixtures demonstrativas; nenhum valor abaixo é inferido da foto enviada.

Substituir generate_analysis pelo pipeline real mantendo o contrato HTTP.
O catálogo é real; apenas a recomendação é simulada.
"""

from .catalog import load_catalog

MONK = ["#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96",
        "#a07e56", "#825c43", "#604134", "#3a312a", "#292420"]


def generate_analysis(*, example=False):
    # Proximidade RGB ao TOM FIXO da demonstração, não à foto do usuário.
    def distance(product):
        color = product["hex"].lstrip("#")
        channels = [int(color[i:i + 2], 16) for i in (0, 2, 4)]
        return sum((v - t) ** 2 for v, t in zip(channels, (160, 126, 86)))

    catalog = load_catalog()
    recommendations = sorted(catalog, key=lambda p: (distance(p), p["id"]))[:3]
    return {
        "simulado": True, "exemplo": example,
        "precheck": {"executado": not example, "rosto_detectado": None if example else True},
        "tom": {"monk": 6, "hex": MONK[5], "ita": 22.0, "pele_utilizada": 74},
        "escala_monk": MONK, "catalogo_total": len(catalog),
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
