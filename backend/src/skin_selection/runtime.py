"""Sessões ONNX locais verificadas, carregadas uma vez por processo.

CUDA é usado automaticamente quando o CUDAExecutionProvider e suas bibliotecas
dinâmicas (cuBLAS + cuDNN) estiverem disponíveis e funcionais. Caso contrário —
inclusive se o kernel CUDA/cuDNN falhar na primeira inferência — a sessão cai
automaticamente para CPUExecutionProvider sem interromper a análise.
"""

import ctypes
import logging
import os
import platform
import threading

import numpy as np

from ..segmentation.model_asset import ASSETS, verify_asset
from ..segmentation.semantic import ModelUnavailableError

logger = logging.getLogger(__name__)

_sessions = {}
_lock = threading.Lock()
_cuda_disabled = False
_preload_attempted = False


def disable_cuda_globally(reason: str = "") -> None:
    """Desativa tentativas futuras de CUDA neste processo após falha de runtime/cuDNN."""
    global _cuda_disabled
    if not _cuda_disabled:
        _cuda_disabled = True
        logger.warning(
            "ONNX Runtime CUDA desativado neste processo (%s) — alternando para CPUExecutionProvider.",
            reason or "indisponível",
        )


def _try_preload_ort_dlls() -> None:
    global _preload_attempted
    if _preload_attempted:
        return
    _preload_attempted = True
    try:
        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
    except Exception:
        pass


def _cuda_runtime_usable() -> bool:
    """Confirma se CUDA e cuDNN estão acessíveis antes de selecionar CUDAExecutionProvider."""
    if _cuda_disabled:
        return False
    if os.environ.get("MAQUIAGEM_FORCE_CPU", "").strip() in {"1", "true", "yes"}:
        return False
    _try_preload_ort_dlls()
    if platform.system().lower() != "linux":
        return True

    # Em Linux, o CUDAExecutionProvider exige tanto cuBLASLt quanto libcudnn.so (usado em nós Conv).
    cublas_ok = False
    for soname in ("libcublasLt.so.13", "libcublasLt.so.12", "libcublasLt.so"):
        try:
            ctypes.CDLL(soname)
            cublas_ok = True
            break
        except OSError:
            continue
    if not cublas_ok:
        return False

    try:
        ctypes.CDLL("libcudnn.so")
        return True
    except OSError:
        return False


def _session_options_for(key: str):
    import onnxruntime as ort
    options = ort.SessionOptions()
    env_threads = os.environ.get("MAQUIAGEM_ORT_THREADS")
    if env_threads is not None:
        intra_threads = max(1, int(env_threads))
    elif key == "barba":
        # YOLOv8l-seg (640x640) domina o caminho crítico em CPU (~75% dos FLOPs).
        intra_threads = max(2, min(8, (os.cpu_count() or 4) // 2))
    else:
        intra_threads = 2
    options.intra_op_num_threads = intra_threads
    options.inter_op_num_threads = 1
    return options


def _build_providers(*, force_cpu: bool = False):
    """Retorna a lista de providers preferida: CUDA quando disponível, CPU como fallback."""
    if force_cpu:
        return ["CPUExecutionProvider"]
    import onnxruntime as ort
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available and _cuda_runtime_usable():
        logger.info("ONNX Runtime: CUDAExecutionProvider disponível — usando GPU.")
        return [
            ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "DEFAULT"}),
            "CPUExecutionProvider",
        ]
    logger.info("ONNX Runtime: CUDAExecutionProvider indisponível — usando CPU.")
    return ["CPUExecutionProvider"]


def _create_session(key: str, *, force_cpu: bool = False):
    asset = ASSETS[key]
    verify_asset(asset)
    import onnxruntime as ort
    return ort.InferenceSession(
        str(asset.path),
        sess_options=_session_options_for(key),
        providers=_build_providers(force_cpu=force_cpu),
    )


def get_session(key, *, force_cpu: bool = False):
    with _lock:
        existing = _sessions.get(key)
        if existing is not None:
            existing_providers = existing.get_providers() if hasattr(existing, "get_providers") else []
            if not force_cpu or "CUDAExecutionProvider" not in existing_providers:
                return existing
        try:
            _sessions[key] = _create_session(key, force_cpu=force_cpu)
        except Exception as exc:
            raise ModelUnavailableError(
                f"{key}: modelo ausente, inválido ou runtime indisponível. "
                "Consulte backend/models/README.md.") from exc
        return _sessions[key]


def infer(key, tensor):
    contiguous = np.ascontiguousarray(tensor, dtype=np.float32)
    session = get_session(key)
    input_name = session.get_inputs()[0].name
    try:
        outputs = session.run(None, {input_name: contiguous})
    except Exception as exc:
        providers = session.get_providers() if hasattr(session, "get_providers") else []
        if "CUDAExecutionProvider" not in providers:
            raise
        disable_cuda_globally(f"{key}: {exc}")
        session = get_session(key, force_cpu=True)
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: contiguous})

    if not outputs or any(not np.isfinite(value).all() for value in outputs):
        raise ValueError(f"Saída não finita de {key}.")
    return outputs


def imagenet_tensor(view):
    values = (view.astype(np.float32) / 255 - np.array([.485, .456, .406], np.float32))
    values /= np.array([.229, .224, .225], np.float32)
    return values.transpose(2, 0, 1)[None]


def sigmoid(values):
    return 1 / (1 + np.exp(-np.clip(values, -80, 80)))
