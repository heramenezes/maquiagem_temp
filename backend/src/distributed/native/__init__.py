"""Kernels nativos C/OpenMP opcionais com fallback automático para NumPy."""


def __getattr__(name):
    if name in {"ciede2000_one_to_many", "omp_available", "omp_info", "rgb_to_lab_fast"}:
        from . import omp_bridge
        return getattr(omp_bridge, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ciede2000_one_to_many",
    "omp_available",
    "omp_info",
    "rgb_to_lab_fast",
]
