"""YOLOv8l-seg de prashants975: classe 0 beard, classe 1 hair ignorada."""

import cv2
import numpy as np

from .contracts import ModuleResult, Transform, probability_masks
from .runtime import infer, sigmoid
from ..segmentation.model_asset import ASSETS

INPUT_SIZE = 640
CONFIDENCE_LOW, CONFIDENCE_HIGH = .25, .60
MASK_LOW, MASK_HIGH = .35, .65


def decode(outputs, transform, *, low=CONFIDENCE_LOW, high=CONFIDENCE_HIGH,
           mask_low=MASK_LOW, mask_high=MASK_HIGH):
    if not (0 <= low < high <= 1 and 0 <= mask_low < mask_high <= 1):
        raise ValueError("YOLO barba: limiares inválidos.")
    if len(outputs) != 2:
        raise ValueError("YOLO barba: esperadas detecções e protótipos.")
    detections, prototypes = outputs
    if detections.shape != (1, 38, 8400) or prototypes.shape != (1, 32, 160, 160):
        raise ValueError("YOLO barba: contrato de duas classes/32 protótipos incompatível.")
    if not all(np.isfinite(value).all() for value in outputs):
        raise ValueError("YOLO barba: saída não finita.")
    if transform.input_shape != (INPUT_SIZE, INPUT_SIZE):
        raise ValueError("YOLO barba: transformação incompatível.")
    rows = detections[0].T
    if np.any((rows[:, 4:6] < 0) | (rows[:, 4:6] > 1)):
        raise ValueError("YOLO barba: confiança inválida.")
    # Mesmo critério single-label do Ultralytics: beard deve vencer hair.
    # Filtrar somente score beard permitiria excluir cabelo ambíguo como barba.
    rows = rows[(rows[:, 4] >= low) & (rows[:, 4:6].argmax(axis=1) == 0) &
                (rows[:, 2] > 0) & (rows[:, 3] > 0)]
    accepted = np.zeros(transform.original_shape, bool)
    uncertain = accepted.copy()
    boxes = np.column_stack((rows[:, :2] - rows[:, 2:4] / 2, rows[:, 2:4]))
    keep = cv2.dnn.NMSBoxes(boxes.tolist(), rows[:, 4].tolist(), low, .7, top_k=100)
    yy, xx = np.ogrid[:INPUT_SIZE, :INPUT_SIZE]
    for index in np.asarray(keep).reshape(-1):
        row = rows[index]
        probability = sigmoid((row[6:] @ prototypes[0].reshape(32, -1)).reshape(160, 160))
        probability = cv2.resize(probability, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
        x, y, w, h = boxes[index]
        probability *= (xx >= x) & (xx < x + w) & (yy >= y) & (yy < y + h)
        strong, weak = probability_masks(transform.restore(probability), mask_low, mask_high)
        if row[4] >= high:
            accepted |= strong
            uncertain |= weak
        else:
            uncertain |= strong | weak
    return accepted, uncertain & ~accepted


def detect(rgb, anatomy):
    view, transform = Transform.prepare(rgb, INPUT_SIZE, letterbox=True)
    tensor = (view.astype(np.float32) / 255).transpose(2, 0, 1)[None]
    accepted, uncertain = decode(infer("barba", tensor), transform)
    # Mantém regiões brutas fora de BiSeNet para debug; compose restringe
    # exclusões à anatomia candidata antes de medir a cor.
    return ModuleResult(accepted, uncertain, source="prashants975_yolov8l_seg",
                        version={**ASSETS["barba"].metadata(),
                                 "preprocessing": "rgb_255_letterbox640_v1",
                                 "postprocessing": "beard_class0_nms07_prototypes_probability_resize_v1"},
                        evidence={"kind": "modelo_especifico", "nominal_beard_class": True,
                                  "classes": {"0": "beard", "1": "hair"}, "selected_class": 0,
                                  "confidence_thresholds": [CONFIDENCE_LOW, CONFIDENCE_HIGH],
                                  "mask_thresholds": [MASK_LOW, MASK_HIGH], "calibrated": False,
                                  "transform": transform.metadata()},
                        debug_masks={"yolo_beard": accepted.copy()})
