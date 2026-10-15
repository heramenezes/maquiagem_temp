"""sRGB -> RGB linear -> XYZ -> CIELAB, branco D65 (observador 2°).

Fórmulas: https://geratools.com/rgb-to-lab e IEC sRGB / W3C.
Não é Lab uint8 do OpenCV (L* escalado e a*/b* deslocados em 128).
"""

import numpy as np


def rgb_to_lab(rgb):
    """Converte (..., 3) RGB: uint8 [0,255] ou float normalizado [0,1].

    Retorna float32: L* [0,100], a*/b* com sinal. Valores de entrada são
    presumidos sRGB; não há correção de iluminação/balanço de branco aqui.
    """
    values = np.asarray(rgb)
    if values.ndim < 1 or values.shape[-1] != 3 or values.size == 0:
        raise ValueError("RGB deve ter formato (..., 3) e não pode ser vazio.")
    if values.dtype == np.uint8:
        values = values.astype(np.float64) / 255.0
    elif np.issubdtype(values.dtype, np.floating):
        values = values.astype(np.float64)
        if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
            raise ValueError("RGB float deve ser finito e normalizado em [0, 1].")
    else:
        raise ValueError("Use RGB uint8 [0,255] ou float [0,1].")

    linear = np.where(values <= 0.04045, values / 12.92,
                      ((values + 0.055) / 1.055) ** 2.4)
    # Coeficientes sRGB de maior precisão; XYZ e branco na mesma escala 0–1.
    matrix = np.array([[0.4124564, 0.3575761, 0.1804375],
                       [0.2126729, 0.7151522, 0.0721750],
                       [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ matrix.T
    relative = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(relative > delta ** 3, np.cbrt(relative),
                 relative / (3 * delta ** 2) + 4 / 29)
    lab = np.stack((116 * f[..., 1] - 16,
                    500 * (f[..., 0] - f[..., 1]),
                    200 * (f[..., 1] - f[..., 2])), axis=-1)
    return np.ascontiguousarray(lab, dtype=np.float32)
