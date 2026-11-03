"""Estimador regional heurístico, sem clarear a pele ou corrigir iluminante.

Regiões geométricas relativas ao contorno facial, adequadas a rostos frontais.
Todos os pixels consultados pertencem à máscara explícita de medição.
"""

import numpy as np
from skimage.color import deltaE_ciede2000

MIN_PIXELS = 32
# Coordenadas relativas ao bbox do rosto: x0, y0, x1, y1.
REGIONS = {
    "testa": (.30, .12, .70, .30),
    "bochecha_esquerda_imagem": (.12, .45, .40, .68),
    "bochecha_direita_imagem": (.60, .45, .88, .68),
}


def estimate_regions(lab, rgb, measurement_mask, face_mask):
    if (rgb.shape != lab.shape or rgb.dtype != np.uint8
            or face_mask.shape != measurement_mask.shape or face_mask.dtype != bool):
        raise ValueError("RGB e contorno facial devem estar alinhados à medição.")
    result = {"estimador": "mediana_lab", "lab": np.median(lab[measurement_mask], axis=0).tolist(),
              "geometria": "bbox_facial_frontal_aproximado", "regioes": [],
              "dispersao_regional_delta_e00": None, "motivos": []}
    if not face_mask.any():
        result["motivos"].append("regioes_insuficientes")
        return result
    yy, xx = np.nonzero(face_mask)
    left, top = int(xx.min()), int(yy.min())
    width, height = int(np.ptp(xx)) + 1, int(np.ptp(yy)) + 1
    usable = []
    for name, (x0, y0, x1, y1) in REGIONS.items():
        xa, xb = left + round(x0 * width), left + round(x1 * width)
        ya, yb = top + round(y0 * height), top + round(y1 * height)
        mask = measurement_mask[ya:yb, xa:xb] & face_mask[ya:yb, xa:xb]
        pixels = lab[ya:yb, xa:xb][mask]
        colors = rgb[ya:yb, xa:xb][mask]
        n = len(pixels)
        # Clipping é perda de informação, não um corte absoluto de L*.
        unclipped = ~np.any((colors <= 2) | (colors >= 253), axis=1)
        clipped = float(1 - unclipped.mean()) if n else None
        pixels = pixels[unclipped]
        if len(pixels):
            low, high = np.percentile(pixels[:, 0], [10, 90])
            pixels = pixels[(pixels[:, 0] >= low) & (pixels[:, 0] <= high)]
        region = {"nome": name, "bbox": [xa, ya, xb - xa, yb - ya],
                  "pixels_selecionados": n, "pixels_utilizados": len(pixels),
                  "fracao_clipping": clipped, "lab": None, "peso": 0.,
                  "dispersao_delta_e00_p90": None}
        result["regioes"].append(region)
        if len(pixels) < MIN_PIXELS:
            continue
        median = np.median(pixels, axis=0).astype(float)
        spread = float(np.percentile(deltaE_ciede2000(pixels, median[None, :]), 90))
        # Cobertura satura: uma região maior não domina as outras duas.
        coverage = len(pixels) / max((yb - ya) * (xb - xa), 1)
        quality = min(1., coverage / .5) * (1 - clipped) / (1 + (spread / 8.) ** 2)
        region.update(lab=median.tolist(), dispersao_delta_e00_p90=spread)
        usable.append((region, median, quality))
    if len(usable) < 2:
        result["motivos"].append("regioes_insuficientes")
        return result
    centers = np.array([item[1] for item in usable])
    distances = deltaE_ciede2000(centers[:, None, :], centers[None, :, :])
    spread = float(distances.max())
    result["dispersao_regional_delta_e00"] = spread
    if spread > 6.:
        result["motivos"].append("discordancia_entre_regioes")
    pairs = distances[np.triu_indices(len(usable), k=1)]
    if float(pairs.min()) > 6.:
        result["motivos"].append("sem_consenso_regional")
        return result
    # Medoide sem preferência por L* alto: duas regiões concordantes têm apoio.
    anchor = int(np.argmin(distances.sum(axis=1)))
    weights = np.array([item[2] for item in usable]) / (1 + (distances[anchor] / 5.) ** 4)
    weights /= weights.sum()
    for (region, _, _), weight in zip(usable, weights):
        region["peso"] = float(weight)
    result.update(estimador="lab_regional_ponderado", lab=np.average(centers, axis=0, weights=weights).tolist(),
                  dispersao_regional_delta_e00=spread)
    return result
