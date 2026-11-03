"""Conversão das cores HEX do catálogo para CIELAB/D65 (observador 2°)."""

import re

import numpy as np

from ..segmentation.color import rgb_to_lab


def hex_to_lab(color):
    """Usa a mesma conversão da foto; rejeita HEX inválido explicitamente."""
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("A cor deve ser HEX sRGB no formato #RRGGBB.")
    rgb = np.array([int(color[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.uint8)
    return rgb_to_lab(rgb).astype(np.float64)
