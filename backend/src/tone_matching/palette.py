"""Referências digitais Monk 1–10, em sRGB e CIELAB/D65 (observador 2°)."""

import re

import numpy as np

from ..segmentation.color import rgb_to_lab

MONK_HEX = (
    "#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96",
    "#a07e56", "#825c43", "#604134", "#3a312a", "#292420",
)
PALETTE_VERSION = "monk-srgb-10-v1"
PALETTE_SOURCE = "https://skintone.google/"


def hex_to_lab(color):
    """Usa a mesma conversão da foto; rejeita HEX inválido explicitamente."""
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("A cor deve ser HEX sRGB no formato #RRGGBB.")
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8)
    return rgb_to_lab(rgb).astype(np.float64)


MONK_LAB = np.stack([hex_to_lab(color) for color in MONK_HEX])
MONK_LAB.setflags(write=False)
