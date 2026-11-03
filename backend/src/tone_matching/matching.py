"""Classificação Monk e ranking determinístico por CIEDE2000, sem treinamento."""

import numpy as np
from skimage.color import deltaE_ciede2000

from .palette import MONK_HEX, MONK_LAB, hex_to_lab

METHOD_VERSION = "monk-ciede2000-lab-v1"


def validate_lab(lab):
    values = np.asarray(lab, dtype=np.float64)
    if values.shape != (3,) or not np.isfinite(values).all() or not -1e-4 <= values[0] <= 100 + 1e-4:
        raise ValueError("Informe um vetor Lab/D65 finito, com L* entre 0 e 100.")
    values = values.copy()
    values[0] = np.clip(values[0], 0, 100)  # Tolerância à conversão float32 do branco sRGB.
    return values


def classify_monk(lab):
    """Retorna todas as distâncias; empate exato favorece o menor índice Monk."""
    # Mesma dimensionalidade evita interpretação ambígua do eixo de canais.
    distances = deltaE_ciede2000(validate_lab(lab)[None, :], MONK_LAB)
    index = int(np.argmin(distances))
    order = np.argsort(distances, kind="stable")
    return {
        "monk": index + 1,
        "hex": MONK_HEX[index],
        "delta_e00": float(distances[index]),
        "distancias_monk": distances.tolist(),
        "margem_delta_e00": float(distances[order[1]] - distances[order[0]]),
    }


def rank_foundations(lab, catalog, *, limit=3):
    """Mesmo Monk primeiro; dentro de cada grupo, menor ΔE00 pele/base.

    Grupos de complemento são visitados pela distância entre seus swatches e
    o swatch Monk da pele, não pela diferença numérica de índices. Distâncias
    sem arredondamento decidem a ordem; ID desempata produtos de cor idêntica.
    Nenhum limiar de adequação cosmética é presumido.
    """
    lab = validate_lab(lab)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit deve ser um inteiro positivo.")
    tone = classify_monk(lab)
    group_distances = deltaE_ciede2000(MONK_LAB[tone["monk"] - 1][None, :], MONK_LAB)
    group_order = np.argsort(group_distances, kind="stable")
    group_priority = {int(index) + 1: priority for priority, index in enumerate(group_order)}
    ranked = []
    seen = set()
    for product in catalog:
        if product["id"] in seen:
            raise ValueError("IDs de produtos devem ser únicos.")
        seen.add(product["id"])
        product_lab = hex_to_lab(product["hex"])
        product_tone = classify_monk(product_lab)
        distance = float(deltaE_ciede2000(lab, product_lab))
        monk = product_tone["monk"]
        ranked.append((group_priority[monk], distance, product["id"], {
            **product,
            "monk": monk,
            "lab": product_lab.tolist(),
            "delta_e00": distance,
            "mesmo_monk": monk == tone["monk"],
            "delta_e00_monk": float(group_distances[monk - 1]),
        }))
    ranked.sort(key=lambda item: item[:3])
    return tone, [item[3] for item in ranked[:limit]]
