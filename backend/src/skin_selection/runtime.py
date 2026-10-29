"""Sessões ONNX locais verificadas, carregadas uma vez por processo.

CUDA é usado automaticamente quando o CUDAExecutionProvider estiver
disponível no onnxruntime instalado. Caso contrário, a execução cai
sem ruído para CPUExecutionProvider.
"""

import logging
import threading

import numpy as np

from ..segmentation.model_asset import ASSETS, verify_asset
from ..segmentation.semantic import ModelUnavailableError

logger = logging.getLogger(__name__)

_sessions = {}
_lock = threading.Lock()


def _build_providers():
    """Retorna a lista de providers preferida: CUDA quando disponível, CPU como fallback."""
    import onnxruntime as ort
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        logger.info("ONNX Runtime: CUDAExecutionProvider disponível — usando GPU.")
        return [
            ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"}),
            "CPUExecutionProvider",
        ]
    logger.info("ONNX Runtime: CUDAExecutionProvider indisponível — usando CPU.")
    return ["CPUExecutionProvider"]


def get_session(key):
    with _lock:
        if key not in _sessions:
            asset = ASSETS[key]
            try:
                verify_asset(asset)
                import onnxruntime as ort
                options = ort.SessionOptions()
                options.intra_op_num_threads = 2
                options.inter_op_num_threads = 1
                _sessions[key] = ort.InferenceSession(
                    str(asset.path),
                    sess_options=options,
                    providers=_build_providers(),
                )
            except Exception as exc:
                raise ModelUnavailableError(
                    f"{key}: modelo ausente, inválido ou runtime indisponível. "
                    "Consulte backend/models/README.md.") from exc
        return _sessions[key]


def infer(key, tensor):
    session = get_session(key)
    outputs = session.run(None, {session.get_inputs()[0].name: np.ascontiguousarray(tensor, dtype=np.float32)})
    if not outputs or any(not np.isfinite(value).all() for value in outputs):
        raise ValueError(f"Saída não finita de {key}.")
    return outputs


def imagenet_tensor(view):
    values = (view.astype(np.float32) / 255 - np.array([.485, .456, .406], np.float32))
    values /= np.array([.229, .224, .225], np.float32)
    return values.transpose(2, 0, 1)[None]


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -80, 80)))
