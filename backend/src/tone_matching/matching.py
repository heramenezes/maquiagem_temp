"""Ranking direto pele/base por CIEDE2000, sem classes intermediárias."""

import re

import numpy as np

from ..distributed.native import ciede2000_one_to_many
from ..segmentation.color import rgb_to_lab

METHOD_VERSION = "regional-ciede2000-lab-v3"
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


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
    if not catalog:
        return []

    seen = set()
    rgb_rows = np.empty((len(catalog), 3), dtype=np.uint8)
    for idx, product in enumerate(catalog):
        pid = product["id"]
        if pid in seen:
            raise ValueError("IDs de produtos devem ser únicos.")
        seen.add(pid)
        color = product.get("hex")
        if not isinstance(color, str) or not _HEX_RE.fullmatch(color):
            raise ValueError("A cor deve ser HEX sRGB no formato #RRGGBB.")
        rgb_rows[idx, 0] = int(color[1:3], 16)
        rgb_rows[idx, 1] = int(color[3:5], 16)
        rgb_rows[idx, 2] = int(color[5:7], 16)

    product_labs = rgb_to_lab(rgb_rows).astype(np.float64)
    distances = ciede2000_one_to_many(lab, product_labs)

    ranked = [
        (float(distances[idx]), product["id"], {
            **product,
            "lab": product_labs[idx].tolist(),
            "delta_e00": float(distances[idx]),
        })
        for idx, product in enumerate(catalog)
    ]
    ranked.sort(key=lambda item: item[:2])
    return [item[2] for item in ranked[:limit]]
