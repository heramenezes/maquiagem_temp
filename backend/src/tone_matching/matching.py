"""Ranking direto pele/base por CIEDE2000, sem classes intermediárias."""

import numpy as np
from skimage.color import deltaE_ciede2000

from .color import hex_to_lab

METHOD_VERSION = "regional-ciede2000-lab-v3"


def validate_lab(lab):
    values = np.asarray(lab, dtype=np.float64)
    if values.shape != (3,) or not np.isfinite(values).all() or not -1e-4 <= values[0] <= 100 + 1e-4:
        raise ValueError("Informe um vetor Lab/D65 finito, com L* entre 0 e 100.")
    values = values.copy()
    values[0] = np.clip(values[0], 0, 100)  # Tolerância à conversão float32 do branco sRGB.
    return values


def rank_foundations(lab, catalog, *, limit=3):
    """Retorna uma lista ordenada pela menor ΔE00 pele/base em todo o catálogo.

    Distâncias sem arredondamento decidem a ordem; ID desempata cores idênticas.
    Nenhum limiar de adequação cosmética é presumido.
    """
    lab = validate_lab(lab)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit deve ser um inteiro positivo.")
    ranked = []
    seen = set()
    for product in catalog:
        if product["id"] in seen:
            raise ValueError("IDs de produtos devem ser únicos.")
        seen.add(product["id"])
        product_lab = hex_to_lab(product["hex"])
        distance = float(deltaE_ciede2000(lab, product_lab))
        ranked.append((distance, product["id"], {
            **product,
            "lab": product_lab.tolist(),
            "delta_e00": distance,
        }))
    ranked.sort(key=lambda item: item[:2])
    return [item[2] for item in ranked[:limit]]
