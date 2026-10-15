"""Referencial único, transformações reversíveis e resultados dos especialistas."""

from dataclasses import dataclass, field, asdict

import cv2
import numpy as np

CATEGORIES = ("acne", "vitiligo", "barba")
STATES = {"executado", "indisponivel", "nao_executado", "falha"}


@dataclass(frozen=True)
class Transform:
    original_shape: tuple
    input_shape: tuple
    resized_shape: tuple
    top: int = 0
    left: int = 0

    @classmethod
    def prepare(cls, rgb, size, *, letterbox=False):
        h, w = rgb.shape[:2]
        if letterbox:
            scale = min(size / h, size / w)
            rh, rw = max(1, round(h * scale)), max(1, round(w * scale))
        else:
            rh = rw = size
        top, left = (size - rh) // 2, (size - rw) // 2
        view = np.full((size, size, 3), 114, dtype=np.uint8)
        view[top:top + rh, left:left + rw] = cv2.resize(rgb, (rw, rh), interpolation=cv2.INTER_LINEAR)
        return view, cls((h, w), (size, size), (rh, rw), top, left)

    def restore(self, values, *, labels=False):
        if values.ndim != 2 or values.size == 0 or not np.isfinite(values).all():
            raise ValueError("Mapa de saída inválido.")
        interpolation = cv2.INTER_NEAREST if labels else cv2.INTER_LINEAR
        ih, iw = self.input_shape
        full = cv2.resize(values.astype(np.float32), (iw, ih), interpolation=interpolation)
        rh, rw = self.resized_shape
        crop = full[self.top:self.top + rh, self.left:self.left + rw]
        h, w = self.original_shape
        return cv2.resize(crop, (w, h), interpolation=interpolation)

    def metadata(self):
        result = asdict(self)
        result["scale_yx"] = [self.resized_shape[i] / self.original_shape[i] for i in (0, 1)]
        return result


@dataclass
class ModuleResult:
    accepted: np.ndarray
    uncertain: np.ndarray
    status: str = "executado"
    source: str = ""
    reason: str | None = None
    version: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    debug_masks: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0

    @classmethod
    def empty(cls, shape, *, status="nao_executado", reason=None, source="", version=None):
        return cls(np.zeros(shape, bool), np.zeros(shape, bool), status, source,
                   reason, version or {})

    def validate(self, shape):
        if self.status not in STATES:
            raise ValueError("Estado de módulo inválido.")
        for mask in (self.accepted, self.uncertain, *self.debug_masks.values()):
            if mask.shape != shape or mask.dtype != bool:
                raise ValueError("Máscaras devem ser bool no referencial do recorte.")
        if self.status != "executado" and (self.accepted.any() or self.uncertain.any()):
            raise ValueError("Módulo não executado não pode fornecer detecções.")


def probability_masks(probability, low, high):
    if not 0 <= low < high <= 1 or not np.isfinite(probability).all():
        raise ValueError("Probabilidade ou limiares inválidos.")
    if np.any((probability < 0) | (probability > 1)):
        raise ValueError("Probabilidade fora de [0, 1].")
    return probability >= high, (probability >= low) & (probability < high)
