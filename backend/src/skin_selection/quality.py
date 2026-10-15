"""Portão técnico antes da medição. Limiares iniciais ainda não calibrados."""

from dataclasses import dataclass, asdict

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityConfig:
    min_pixels: int = 512
    min_fraction: float = .15
    min_spatial_extent: float = .20
    max_clipped_fraction: float = .08
    min_sharpness: float = 8.
    max_light_spread: float = 35.
    max_dispersion: float = 22.
    max_uncertainty_shift: float = 3.
    max_uncertain_fraction: float = .35


def evaluate(rgb, lab, selection, config=QualityConfig()):
    valid = selection["valid_mask"]
    anatomy = selection["anatomical_mask"]
    n, total = int(valid.sum()), int(anatomy.sum())
    reasons = []
    metrics = {"native_pixels": n, "anatomical_pixels": total,
               "valid_fraction": n / max(total, 1),
               "excluded_fraction": float(selection["excluded_mask"].sum()) / max(total, 1),
               "uncertain_fraction": float((selection["uncertain_mask"] & ~selection["excluded_mask"]).sum()) / max(total, 1)}
    if any(v["state"] != "executado" for v in selection["module_status"].values()):
        reasons.append("modulo_obrigatorio_indisponivel")
    if any(v.get("reason") == "referencia_local_insuficiente" for v in selection["module_status"].values()):
        reasons.append("referencia_local_insuficiente")
    if n < config.min_pixels:
        reasons.append("poucos_pixels_nativos")
    if metrics["valid_fraction"] < config.min_fraction:
        reasons.append("cobertura_insuficiente")
    if metrics["uncertain_fraction"] > config.max_uncertain_fraction:
        reasons.append("incerteza_excessiva")
    if n:
        pixels = lab[valid]
        median = np.median(pixels, axis=0)
        dispersion = float(np.percentile(np.linalg.norm(pixels - median, axis=1), 90))
        ay, ax = np.nonzero(anatomy)
        vy, vx = np.nonzero(valid)
        extent = min(float(np.ptp(vy)) / max(float(np.ptp(ay)), 1),
                     float(np.ptp(vx)) / max(float(np.ptp(ax)), 1))
        clipping = float(np.mean(np.any((rgb[valid] <= 2) | (rgb[valid] >= 253), axis=1)))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        interior = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        laplacian = cv2.Laplacian(gray, cv2.CV_32F)
        sharpness = float(laplacian[interior].var()) if interior.any() else 0.
        light_spread = float(np.percentile(pixels[:, 0], 95) - np.percentile(pixels[:, 0], 5))
        with_uncertain = anatomy & ~selection["excluded_mask"]
        shift = float(np.linalg.norm(pixels.mean(axis=0) - lab[with_uncertain].mean(axis=0)))
        metrics.update(spatial_extent=extent, clipped_fraction=clipping, sharpness=sharpness,
                       light_spread=light_spread, dispersion_delta_e76_p90=dispersion,
                       uncertainty_shift_delta_e76=shift)
        for condition, reason in ((extent < config.min_spatial_extent, "amostra_concentrada"),
                                  (clipping > config.max_clipped_fraction, "clipping_excessivo"),
                                  (sharpness < config.min_sharpness, "nitidez_insuficiente"),
                                  (light_spread > config.max_light_spread, "iluminacao_desigual"),
                                  (dispersion > config.max_dispersion, "cor_inconsistente"),
                                  (shift > config.max_uncertainty_shift, "cor_sensivel_a_incerteza")):
            if condition:
                reasons.append(reason)
    return {"decision": "aprovada" if not reasons else "inconclusiva", "usable": not reasons,
            "reasons": reasons, "metrics": metrics, "thresholds": asdict(config),
            "calibration": "provisoria_sem_validacao_anotada", "released_for_monk": False}
