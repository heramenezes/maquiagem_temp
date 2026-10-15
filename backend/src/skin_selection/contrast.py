"""Contraste Lab multiescala residual, sem limiar absoluto de cor de pele."""

import cv2
import numpy as np

from .contracts import ModuleResult


def detect(lab, anatomy, excluded, uncertain):
    reference = anatomy & ~excluded & ~uncertain
    empty = np.zeros_like(anatomy)
    if reference.sum() < 64:
        return ModuleResult(empty, reference.copy(), source="contraste_lab",
                            reason="referencia_local_insuficiente",
                            evidence={"kind": "heuristica_contraste", "reference_sufficient": False})
    weight = reference.astype(np.float32)
    evidence = np.zeros_like(weight)
    supported = np.zeros_like(reference)
    residuals = []
    # Referência normalizada, com segunda passagem que reduz influência de outliers.
    for fraction in (.025, .07, .16):
        radius = max(2, round(min(lab.shape[:2]) * fraction))
        size = (radius * 2 + 1,) * 2
        count = cv2.boxFilter(weight, -1, size, normalize=False, borderType=cv2.BORDER_CONSTANT)
        mean = cv2.boxFilter(lab * weight[..., None], -1, size, normalize=False,
                             borderType=cv2.BORDER_CONSTANT) / np.maximum(count[..., None], 1e-6)
        delta = np.linalg.norm(lab - mean, axis=2)
        valid_reference = reference & (count >= max(16, size[0] ** 2 * .15))
        if not valid_reference.any():
            continue
        med = np.median(delta[valid_reference])
        mad = np.median(np.abs(delta[valid_reference] - med)) * 1.4826
        # Pesos suaves evitam apagar também o entorno de uma marca escura.
        robust_weight = weight * np.minimum(1., (med + max(4., 3 * mad)) / np.maximum(delta, 1e-6)) ** 2
        count = cv2.boxFilter(robust_weight, -1, size, normalize=False, borderType=cv2.BORDER_CONSTANT)
        mean = cv2.boxFilter(lab * robust_weight[..., None], -1, size, normalize=False,
                             borderType=cv2.BORDER_CONSTANT) / np.maximum(count[..., None], 1e-6)
        delta = np.linalg.norm(lab - mean, axis=2)
        squared = cv2.boxFilter(robust_weight ** 2, -1, size, normalize=False, borderType=cv2.BORDER_CONSTANT)
        effective_count = count ** 2 / np.maximum(squared, 1e-6)
        supported_here = effective_count >= max(16, size[0] ** 2 * .15)
        limit = max(12., float(med + 4 * mad))
        evidence += ((delta > limit) & supported_here).astype(np.float32)
        supported |= supported_here
        residuals.append(np.where(supported_here, delta / limit, 0))
    if not residuals:
        return ModuleResult(empty, reference.copy(), source="contraste_lab",
                            reason="referencia_local_insuficiente",
                            evidence={"kind": "heuristica_contraste", "reference_sufficient": False})
    score = np.max(residuals, axis=0)
    candidates = reference & (score >= .65)
    accepted = empty.copy()
    ambiguous = reference & ~supported
    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidates.astype(np.uint8), 8)
    min_area = max(5, round(anatomy.sum() * .0003))
    max_area = anatomy.sum() * .12
    strong = candidates & (evidence >= 2) & (score >= 1)
    strong_counts = np.bincount(labels[strong], minlength=count)
    areas = stats[:, cv2.CC_STAT_AREA]
    large_enough = areas >= min_area
    large_enough[0] = False  # Não transforma poros em exclusão por padrão.
    keep = large_enough & (areas <= max_area) & (strong_counts >= np.maximum(3, areas * .25))
    accepted = strong & keep[labels]
    ambiguous |= large_enough[labels] & ~accepted
    return ModuleResult(accepted, ambiguous, source="contraste_lab_multiescala_v1",
                        version={"version": "contrast-v1", "calibrated": False},
                        evidence={"kind": "heuristica_contraste", "reference_sufficient": True,
                                  "scales": [.025, .07, .16], "min_component_pixels": min_area})
