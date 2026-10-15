"""YOLO11n-seg auditado: uma classe vitiligo, 32 protótipos, entrada 416."""

import cv2
import numpy as np

from .contracts import ModuleResult, Transform, probability_masks
from .runtime import infer, sigmoid
from ..segmentation.model_asset import ASSETS


def decode(outputs, transform, *, low=.25, high=.60, mask_low=.35, mask_high=.65):
    if len(outputs) != 2:
        raise ValueError("YOLO: esperadas detecções e protótipos.")
    detections, prototypes = outputs
    if detections.shape != (1, 37, 3549) or prototypes.shape != (1, 32, 104, 104):
        raise ValueError("YOLO: contrato de classes/protótipos incompatível.")
    rows = detections[0].T
    if np.any((rows[:, 4] < 0) | (rows[:, 4] > 1)):
        raise ValueError("YOLO: confiança inválida.")
    rows = rows[(rows[:, 4] >= low) & (rows[:, 2] > 0) & (rows[:, 3] > 0)]
    accepted = np.zeros(transform.original_shape, bool)
    uncertain = accepted.copy()
    # NMS somente nesta classe; limite explícito de instâncias limita RAM/CPU.
    boxes = np.column_stack((rows[:, :2] - rows[:, 2:4] / 2, rows[:, 2:4]))
    keep = cv2.dnn.NMSBoxes(boxes.tolist(), rows[:, 4].tolist(), low, .7, top_k=100)
    for index in np.asarray(keep).reshape(-1):
        row = rows[index]
        probability = sigmoid((row[5:] @ prototypes[0].reshape(32, -1)).reshape(104, 104))
        # Recorta pela caixa na resolução de entrada; não preenche a caixa.
        probability = cv2.resize(probability, (416, 416), interpolation=cv2.INTER_LINEAR)
        x, y, w, h = boxes[index]
        yy, xx = np.ogrid[:416, :416]
        probability *= (xx >= x) & (xx < x + w) & (yy >= y) & (yy < y + h)
        probability = transform.restore(probability)
        strong, weak = probability_masks(probability, mask_low, mask_high)
        if row[4] >= high:
            accepted |= strong
            uncertain |= weak
        else:
            uncertain |= strong | weak
    return accepted, uncertain & ~accepted


def detect(rgb, anatomy):
    view, transform = Transform.prepare(rgb, 416, letterbox=True)
    tensor = (view.astype(np.float32) / 255).transpose(2, 0, 1)[None]
    accepted, uncertain = decode(infer("vitiligo", tensor), transform)
    return ModuleResult(accepted, uncertain, source="yolo11n_seg",
                        version={**ASSETS["vitiligo"].metadata(), "preprocessing": "rgb_255_letterbox416_v1",
                                 "postprocessing": "nms07_prototypes_probability_resize_v1"},
                        evidence={"kind": "modelo_especifico", "transform": transform.metadata(),
                                  "classes": {"0": "vitiligo"}, "confidence_thresholds": [.25, .60],
                                  "mask_thresholds": [.35, .65], "calibrated": False})
