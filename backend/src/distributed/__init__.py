"""Módulo de Arquitetura Distribuída (P2P) e Otimizações Paralelas (CUDA / OpenMP)."""

_EXPORTS = {
    "ciede2000_one_to_many": (".native", "ciede2000_one_to_many"),
    "omp_available": (".native", "omp_available"),
    "omp_info": (".native", "omp_info"),
    "rgb_to_lab_fast": (".native", "rgb_to_lab_fast"),
    "WorkerNode": (".node", "WorkerNode"),
    "DistributedExecutor": (".orchestrator", "DistributedExecutor"),
    "LocalParallelExecutor": (".orchestrator", "LocalParallelExecutor"),
    "resolve_executor": (".orchestrator", "resolve_executor"),
    "PeerRegistry": (".registry", "PeerRegistry"),
    "expand_capabilities": (".registry", "expand_capabilities"),
    "parse_peer_specs": (".registry", "parse_peer_specs"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    mod = import_module(target[0], __name__)
    return getattr(mod, target[1])


__all__ = list(_EXPORTS.keys())
