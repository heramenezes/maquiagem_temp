"""EasyPortrait: candidatos a pelos por discordância + posição + textura.

Não existe classe barba neste peso. Discordância isolada permanece incerta.
"""

import cv2
import numpy as np

from .contracts import ModuleResult, Transform
from .runtime import infer
from ..segmentation.model_asset import ASSETS


def from_probabilities(rgb, anatomy, background, skin, transform=None):
    allowed = anatomy["allowed"]
    face = anatomy["face"]
    accepted = np.zeros_like(allowed)
    # Exclui bordas do parser e usa estruturas reais do BiSeNet como âncora.
    interior = cv2.erode(allowed.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    labels = anatomy.get("labels")
    lower = np.zeros_like(allowed)
    if labels is not None:
        nose_y = np.nonzero(labels == 10)[0]
        face_y, face_x = np.nonzero(face)
        if nose_y.size and face_y.size:
            yy, xx = np.ogrid[:allowed.shape[0], :allowed.shape[1]]
            # Inclui bigode desde a base do nariz; não usa mandíbula inteira.
            lower = ((yy >= np.percentile(nose_y, 65)) &
                     (xx >= np.percentile(face_x, 5)) & (xx <= np.percentile(face_x, 95)))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    smooth = cv2.GaussianBlur(gray, (0, 0), max(.8, min(gray.shape) / 200))
    texture = cv2.GaussianBlur(np.abs(gray - smooth), (0, 0), 1)
    reference = texture[allowed & (skin >= .8)]
    threshold = max(3., float(np.percentile(reference, 85)) + 1.) if reference.size else float("inf")
    disagreement = allowed & (skin < .6)
    candidate = interior & lower & (background >= .8) & (texture > threshold)
    count, components, stats, _ = cv2.connectedComponentsWithStats(candidate.astype(np.uint8), 8)
    min_area = max(4, round(allowed.sum() * .0005))
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    accepted = keep[components]
    uncertain = disagreement & ~accepted
    return ModuleResult(accepted, uncertain, source="easyportrait_segformer_b0",
                        version={**ASSETS["barba"].metadata(), "preprocessing": "bgr_easyportrait_resize512_v1",
                                 "postprocessing": "softmax_disagreement_texture_location_v1"},
                        evidence={"kind": "discordancia_parsers_com_textura_e_localizacao",
                                  "nominal_beard_class": False, "calibrated": False,
                                  "texture_threshold": None if not np.isfinite(threshold) else threshold,
                                  "transform": transform.metadata() if transform else None},
                        debug_masks={"easy_background": background >= .8,
                                     "easy_skin": skin >= .6, "parser_disagreement": disagreement})


def detect(rgb, anatomy):
    view, transform = Transform.prepare(rgb, 512)
    bgr = view[..., ::-1].astype(np.float32)
    bgr -= np.array([143.55267075, 132.96705975, 126.94924335], np.float32)
    bgr /= np.array([60.2625333, 60.32740275, 59.30988645], np.float32)
    logits = infer("barba", bgr.transpose(2, 0, 1)[None])[0]
    if logits.shape != (1, 8, 512, 512):
        raise ValueError("EasyPortrait fp: esperadas oito classes em 512x512.")
    probabilities = np.exp(logits[0] - logits[0].max(axis=0, keepdims=True))
    probabilities /= probabilities.sum(axis=0, keepdims=True)
    return from_probabilities(rgb, anatomy, transform.restore(probabilities[0]),
                              transform.restore(probabilities[1]), transform)
