"""U-Net/ResNet34 de RihemXX/Acnes; somente segmentação, sem severidade."""

from .contracts import ModuleResult, Transform, probability_masks
from .runtime import infer, imagenet_tensor, sigmoid
from ..segmentation.model_asset import ASSETS


def detect(rgb, anatomy, *, low=.20, high=.50):
    view, transform = Transform.prepare(rgb, 256)
    logits = infer("acne", imagenet_tensor(view))[0]
    if logits.shape != (1, 1, 256, 256):
        raise ValueError("U-Net: esperado [1, 1, 256, 256].")
    probability = transform.restore(sigmoid(logits[0, 0]))
    accepted, uncertain = probability_masks(probability, low, high)
    return ModuleResult(accepted, uncertain, source="unet_resnet34",
                        version={**ASSETS["acne"].metadata(), "preprocessing": "rgb_imagenet_resize256_v1",
                                 "postprocessing": "sigmoid_resize_linear_dual_threshold_v1"},
                        evidence={"transform": transform.metadata(), "thresholds": [low, high],
                                  "calibrated": False, "kind": "modelo_especifico"})
