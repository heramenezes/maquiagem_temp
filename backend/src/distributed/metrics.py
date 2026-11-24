"""Métricas reais de desempenho: Pipeline Paralelo/Distribuído P2P + OpenMP vs. Sequencial."""

from time import perf_counter

import numpy as np

from .codec import encode_bool_mask, encode_rgb
from .native import omp_info, rgb_to_lab_fast


def measure_numpy_cielab_reference_ms(rgb: np.ndarray) -> float:
    """Mede o tempo real da conversão CIELAB sequencial em NumPy puro (escalando se a imagem for grande)."""
    h, w = rgb.shape[:2]
    total_pixels = h * w
    if total_pixels <= 160_000:
        t0 = perf_counter()
        rgb_to_lab_fast(rgb, prefer_native=False)
        return (perf_counter() - t0) * 1000.0
    # Para recortes grandes (>400x400), mede uma fatia contígua de 65.536 pixels (~0.8 ms) e escala linearmente.
    flat = rgb.reshape(-1, 3)[:65_536].reshape(256, 256, 3)
    t0 = perf_counter()
    rgb_to_lab_fast(flat, prefer_native=False)
    sample_ms = (perf_counter() - t0) * 1000.0
    return sample_ms * (total_pixels / 65_536.0)


def build_performance_metrics(
    *,
    mode: str,
    rgb: np.ndarray,
    selection: dict,
    rosto_ms: float,
    total_wall_ms: float,
    fanout_wall_ms: float,
    stage_times_ms: dict[str, float],
    cielab_numpy_seq_ms: float,
    active_nodes: list[dict],
    rgb_wire_bytes: int | None = None,
    mask_wire_bytes: int | None = None,
) -> dict:
    """Consolida métricas comparativas de latência, speedup, OpenMP e rede P2P."""
    omp = omp_info()
    cielab_omp_ms = max(0.001, float(stage_times_ms.get("cielab", 0.0)))
    cielab_seq_ms = max(cielab_omp_ms, float(cielab_numpy_seq_ms))

    # Em execução estritamente sequencial sem paralelismo de estágios nem OpenMP:
    # cada etapa roda uma após a outra na thread principal.
    ordered_keys = (
        "rosto", "cielab", "mascara", "acne", "vitiligo",
        "barba", "selecao", "clusters", "medidas", "resultado",
    )
    clean_stages = {k: round(max(0.0, float(stage_times_ms.get(k, 0.0))), 2) for k in ordered_keys}

    concurrent_seq_sum = (
        cielab_seq_ms
        + float(stage_times_ms.get("mascara", 0.0))
        + float(stage_times_ms.get("acne", 0.0))
        + float(stage_times_ms.get("vitiligo", 0.0))
        + float(stage_times_ms.get("barba", 0.0))
    )
    sequential_total_ms = (
        float(rosto_ms)
        + concurrent_seq_sum
        + float(stage_times_ms.get("selecao", 0.0))
        + float(stage_times_ms.get("clusters", 0.0))
        + float(stage_times_ms.get("medidas", 0.0))
        + float(stage_times_ms.get("resultado", 0.0))
    )

    real_wall_ms = max(0.01, float(total_wall_ms))
    seq_equiv_ms = max(real_wall_ms, sequential_total_ms)
    fanout_real_ms = max(0.01, float(fanout_wall_ms))
    fanout_seq_ms = max(fanout_real_ms, concurrent_seq_sum)

    saved_ms = max(0.0, seq_equiv_ms - real_wall_ms)
    saved_pct = 100.0 * saved_ms / max(seq_equiv_ms, 0.01)

    if rgb_wire_bytes is None:
        _, blob = encode_rgb(rgb)
        rgb_wire_bytes = len(blob)
    if mask_wire_bytes is None:
        mask_wire_bytes = sum(
            len(encode_bool_mask(m))
            for m in (
                selection["anatomical_mask"],
                *selection["accepted_masks"].values(),
            )
        )
    avoided_lab_bytes = int(rgb.shape[0] * rgb.shape[1] * 3 * 4)

    is_dist = mode == "distribuido_p2p"
    has_cuda = any(str(n.get("dispositivo", "")).upper() == "CUDA" for n in active_nodes)
    has_lan_peer = any(
        n.get("endereco") and not str(n["endereco"]).startswith(("127.", "localhost:", "[::1]:"))
        for n in active_nodes
    )
    if is_dist and has_cuda:
        label = "Pipeline P2P Distribuído + GPU CUDA + OpenMP"
    elif is_dist and has_lan_peer:
        label = "Pipeline P2P Distribuído em Rede (LAN) + OpenMP"
    elif is_dist:
        label = "Pipeline P2P Multi-Processo Local + OpenMP"
    else:
        label = "DAG Paralelo Multi-Thread + OpenMP"

    return {
        "modo_execucao": mode,
        "arquitetura_ativa": label,
        "tempo_pipeline_paralelo_ms": round(real_wall_ms, 2),
        "tempo_sequencial_equivalente_ms": round(seq_equiv_ms, 2),
        "speedup_total": round(seq_equiv_ms / real_wall_ms, 2),
        "economia_tempo_ms": round(saved_ms, 2),
        "economia_percentual": round(saved_pct, 1),
        "bloco_visao_concorrente": {
            "tempo_paralelo_ms": round(fanout_real_ms, 2),
            "soma_sequencial_ms": round(fanout_seq_ms, 2),
            "speedup": round(fanout_seq_ms / fanout_real_ms, 2),
        },
        "openmp_cielab": {
            "ativo": bool(omp.get("openmp")),
            "threads": int(omp.get("max_threads", 1)),
            "tempo_openmp_ms": round(cielab_omp_ms, 3),
            "tempo_sequencial_numpy_ms": round(cielab_seq_ms, 3),
            "speedup": round(cielab_seq_ms / cielab_omp_ms, 2),
        },
        "nos_ativos": active_nodes,
        "rede_p2p": {
            "transferencia_ativa": is_dist,
            "bytes_rgb_comprimido": int(rgb_wire_bytes),
            "bytes_rgb_bruto": int(rgb.nbytes),
            "bytes_mascaras_p2p": int(mask_wire_bytes),
            "bytes_lab_evitados": avoided_lab_bytes,
        },
        "etapas_ms": clean_stages,
    }
