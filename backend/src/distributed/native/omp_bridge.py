"""Ponte ctypes para o kernel C/OpenMP com fallback transparente para NumPy/scikit-image."""

import ctypes
import logging
import os
import threading

import numpy as np
from skimage.color import deltaE_ciede2000

from .build_omp import build_library, library_path

logger = logging.getLogger(__name__)

_lib = None
_lib_checked = False
_lock = threading.Lock()


def _load_lib():
    global _lib, _lib_checked
    if os.environ.get("MAQUIAGEM_DISABLE_OMP", "").strip() in {"1", "true", "yes"}:
        return None
    if _lib_checked:
        return _lib
    with _lock:
        if _lib_checked:
            return _lib
        path = library_path()
        if not path.is_file():
            path = build_library(force=False)
        if path is not None and path.is_file():
            try:
                loaded = ctypes.CDLL(str(path))
                loaded.mtom_omp_max_threads.argtypes = []
                loaded.mtom_omp_max_threads.restype = ctypes.c_int
                loaded.mtom_has_openmp.argtypes = []
                loaded.mtom_has_openmp.restype = ctypes.c_int

                loaded.mtom_rgb_u8_to_lab_f32.argtypes = [
                    ctypes.POINTER(ctypes.c_uint8),
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_ssize_t,
                ]
                loaded.mtom_rgb_u8_to_lab_f32.restype = None

                loaded.mtom_rgb_f64_to_lab_f32.argtypes = [
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_ssize_t,
                ]
                loaded.mtom_rgb_f64_to_lab_f32.restype = None

                loaded.mtom_ciede2000_one_to_many_f64.argtypes = [
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.c_ssize_t,
                ]
                loaded.mtom_ciede2000_one_to_many_f64.restype = None

                _lib = loaded
                logger.info(
                    "Kernel nativo C carregado (%s, OpenMP=%s, max_threads=%d).",
                    path.name,
                    bool(loaded.mtom_has_openmp()),
                    loaded.mtom_omp_max_threads(),
                )
            except OSError as exc:
                logger.info("Kernel C indisponível (%s); usando fallback NumPy.", exc)
                _lib = None
        _lib_checked = True
        return _lib


def omp_available() -> bool:
    lib = _load_lib()
    return lib is not None and bool(lib.mtom_has_openmp())


def omp_info() -> dict:
    lib = _load_lib()
    if lib is None:
        return {"native_loaded": False, "openmp": False, "max_threads": 1}
    return {
        "native_loaded": True,
        "openmp": bool(lib.mtom_has_openmp()),
        "max_threads": int(lib.mtom_omp_max_threads()),
    }


def _numpy_rgb_to_lab(values: np.ndarray) -> np.ndarray:
    if values.dtype == np.uint8:
        norm = values.astype(np.float64) / 255.0
    else:
        norm = values.astype(np.float64)
    linear = np.where(norm <= 0.04045, norm / 12.92, ((norm + 0.055) / 1.055) ** 2.4)
    matrix = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = linear @ matrix.T
    relative = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(relative > delta ** 3, np.cbrt(relative), relative / (3 * delta ** 2) + 4 / 29)
    lab = np.stack((
        116 * f[..., 1] - 16,
        500 * (f[..., 0] - f[..., 1]),
        200 * (f[..., 1] - f[..., 2]),
    ), axis=-1)
    return np.ascontiguousarray(lab, dtype=np.float32)


def rgb_to_lab_fast(values: np.ndarray, *, prefer_native: bool = True) -> np.ndarray:
    """Converte array validado (..., 3) uint8 ou float normalizado [0,1] para float32 Lab."""
    lib = _load_lib() if prefer_native else None
    if lib is None:
        return _numpy_rgb_to_lab(values)

    shape = values.shape
    num_pixels = values.size // 3
    out = np.empty(shape, dtype=np.float32)
    if values.dtype == np.uint8:
        contiguous = np.ascontiguousarray(values, dtype=np.uint8)
        lib.mtom_rgb_u8_to_lab_f32(
            contiguous.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            num_pixels,
        )
        return out

    contiguous = np.ascontiguousarray(values, dtype=np.float64)
    lib.mtom_rgb_f64_to_lab_f32(
        contiguous.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        num_pixels,
    )
    return out


def ciede2000_one_to_many(lab_ref, lab_targets, *, prefer_native: bool = True) -> np.ndarray:
    """Calcula ΔE00 entre lab_ref (3,) e lab_targets (N, 3) em float64."""
    ref = np.ascontiguousarray(lab_ref, dtype=np.float64)
    targets = np.ascontiguousarray(lab_targets, dtype=np.float64)
    if ref.shape != (3,) or targets.ndim != 2 or targets.shape[1] != 3:
        raise ValueError("Esperado lab_ref (3,) e lab_targets (N, 3).")
    count = targets.shape[0]
    if count == 0:
        return np.empty((0,), dtype=np.float64)

    lib = _load_lib() if prefer_native else None
    if lib is None:
        return np.asarray(deltaE_ciede2000(targets, ref[None, :]), dtype=np.float64)

    out = np.empty((count,), dtype=np.float64)
    lib.mtom_ciede2000_one_to_many_f64(
        ref.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        targets.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        count,
    )
    return out
