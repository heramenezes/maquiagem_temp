"""sRGB -> RGB linear -> XYZ -> CIELAB, branco D65 (observador 2°).

Fórmulas: https://geratools.com/rgb-to-lab e IEC sRGB / W3C.
Não é Lab uint8 do OpenCV (L* escalado e a*/b* deslocados em 128).
"""

import numpy as np

from ..distributed.native import rgb_to_lab_fast


def rgb_to_lab(rgb):
    """Converte (..., 3) RGB: uint8 [0,255] ou float normalizado [0,1].

    Retorna float32: L* [0,100], a*/b* com sinal. Valores de entrada são
    presumidos sRGB; não há correção de iluminação/balanço de branco aqui.
    Usa kernel nativo C/OpenMP quando disponível, com fallback idêntico em NumPy.
    """
    values = np.asarray(rgb)
    if values.ndim < 1 or values.shape[-1] != 3 or values.size == 0:
        raise ValueError("RGB deve ter formato (..., 3) e não pode ser vazio.")
    if values.dtype == np.uint8:
        return rgb_to_lab_fast(values)
    if np.issubdtype(values.dtype, np.floating):
        values = values.astype(np.float64, copy=False)
        if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
            raise ValueError("RGB float deve ser finito e normalizado em [0, 1].")
        return rgb_to_lab_fast(values)
    raise ValueError("Use RGB uint8 [0,255] ou float [0,1].")
