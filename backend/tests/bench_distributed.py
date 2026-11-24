"""Benchmark ponta-a-ponta: Sequencial vs. OpenMP+DAG Local vs. Multi-Processo P2P (+ Nó GPU).

Exemplos:
    python -m backend.tests.bench_distributed                 # Mocks rápidos, 5 rodadas
    python -m backend.tests.bench_distributed --real 5        # Modelos ONNX reais na amostra
    python -m backend.tests.bench_distributed --real 5 --gpu-peer 192.168.1.50:7102
    python -m backend.tests.bench_distributed --real 5 --concurrency 4 --json bench_results.json
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
from time import perf_counter
from unittest.mock import patch

import numpy as np

from backend.src.distributed import DistributedExecutor, LocalParallelExecutor, omp_info
from backend.src.distributed.cluster import compute_thread_budgets
from backend.src.distributed.codec import encode_anatomy, encode_module_result, encode_rgb
from backend.src.preprocessing import detectar_e_isolar_rosto
from backend.src.segmentation.color import rgb_to_lab
from backend.src.segmentation.pipeline import analysis_events, summarize
from backend.src.segmentation.semantic import facial_masks, fallback_facial_masks, measure_skin, ModelUnavailableError
from backend.src.segmentation.skin import adaptive_clusters
from backend.src.skin_selection.contracts import CATEGORIES, ModuleResult
from backend.src.skin_selection.pipeline import finish, run_module
from backend.src.skin_selection.serialization import conditions
from backend.src.tone_matching.analysis import build_analysis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
MOCK_LATENCIES = {"bisenet": 0.055, "acne": 0.045, "vitiligo": 0.040, "barba": 0.095}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port(addr: str, timeout: float = 20.0) -> None:
    host, _, port = addr.rpartition(":")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=0.3):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Nó P2P não respondeu: {addr}")


def _synthetic_crop(shape=(360, 360)) -> np.ndarray:
    rng = np.random.default_rng(42)
    noise = rng.integers(-5, 6, (*shape, 1), dtype=np.int16)
    return np.clip(np.full((*shape, 3), [172, 122, 95], dtype=np.int16) + noise, 0, 255).astype(np.uint8)


def _run_legacy_sequential(rgb: np.ndarray, *, facial_fn, module_fn) -> dict:
    """Executa exatamente na ordem estritamente sequencial anterior à paralelização."""
    lab = rgb_to_lab(rgb)
    try:
        masks = facial_fn(rgb)
    except ModelUnavailableError:
        masks = fallback_facial_masks(rgb, "segmentacao_indisponivel")
    if not masks["allowed"].any():
        masks = fallback_facial_masks(rgb, "pele_nao_segmentada")
    modules = {k: module_fn(k, rgb, masks) for k in CATEGORIES}
    selection = finish(rgb, lab, masks, modules)
    factor = min(1, 512 / max(rgb.shape[:2]))
    size = (max(1, round(rgb.shape[1] * factor)), max(1, round(rgb.shape[0] * factor)))
    import cv2
    small_lab = cv2.resize(lab, size, interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(masks["allowed"].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    clusters = adaptive_clusters(small_lab, {"allowed": small_mask, "seeds": small_mask}) if small_mask.sum() >= 64 else {"k": None}
    skin = measure_skin(lab, selection["measurement_mask"], rgb=rgb, face_mask=masks["face"])
    result = build_analysis(skin, selection, int(masks["face"].sum()))
    result["condicoes"] = conditions(selection)
    result["marcacoes"] = []
    result["preprocessamento"] = summarize(rgb, masks, clusters, skin, selection)
    return result


def _consume_pipeline(rgb: np.ndarray, executor) -> dict:
    out = None
    for ev in analysis_events(rgb, lambda _img: rgb, executor=executor):
        if ev["tipo"] == "resultado":
            out = ev["dados"]
    assert out is not None
    return out


def _measure_mode(fn, rounds: int, concurrency: int) -> dict:
    # Aquecimento
    fn()
    latencies = []
    t_batch_start = perf_counter()
    if concurrency <= 1:
        for _ in range(rounds):
            t0 = perf_counter()
            fn()
            latencies.append((perf_counter() - t0) * 1000.0)
    else:
        total_reqs = rounds * concurrency

        def _one(_i):
            t0 = perf_counter()
            fn()
            return (perf_counter() - t0) * 1000.0

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            latencies = list(pool.map(_one, range(total_reqs)))
    total_s = perf_counter() - t_batch_start
    total_done = len(latencies)
    return {
        "requests": total_done,
        "concurrency": concurrency,
        "min_ms": round(min(latencies), 2),
        "p50_ms": round(statistics.median(latencies), 2),
        "mean_ms": round(statistics.mean(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "throughput_rps": round(total_done / max(total_s, 1e-9), 2),
    }


def _spawn_cluster_procs(roles: list[tuple[str, str]], *, warmup: bool) -> tuple[list[subprocess.Popen], list[str]]:
    import os
    procs: list[subprocess.Popen] = []
    addrs: list[str] = []
    seg_addrs: list[str] = []
    budgets = compute_thread_budgets(os.cpu_count() or 4, roles)
    for (name, caps), budget in zip(roles, budgets):
        addr = f"127.0.0.1:{_free_port()}"
        addrs.append(addr)
        cmd = [
            sys.executable, "-m", "backend.src.distributed.node",
            "--bind", addr,
            "--node-id", name,
            "--capabilities", caps,
            "--omp-threads", budget["OMP_NUM_THREADS"],
            "--ort-threads", budget["MAQUIAGEM_ORT_THREADS"],
        ]
        if "color_match" in caps and seg_addrs:
            cmd.extend(["--subscribe-peers", ",".join(seg_addrs)])
        elif any(c in caps for c in ("segmentation", "bisenet", "acne", "vitiligo", "barba")):
            seg_addrs.append(addr)
        if not warmup:
            cmd.append("--no-warmup")
        procs.append(
            subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env={**os.environ, **budget},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
    for addr in addrs:
        _wait_port(addr, timeout=30.0)
    time.sleep(0.25)
    return procs, addrs


def _stop_procs(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def _wire_overhead_summary(rgb: np.ndarray) -> dict:
    _, rgb_blob = encode_rgb(rgb)
    raw_rgb_bytes = rgb.nbytes
    raw_lab_bytes = rgb.shape[0] * rgb.shape[1] * 3 * 4
    anat = {"allowed": np.ones(rgb.shape[:2], bool), "face": np.ones(rgb.shape[:2], bool), "warnings": []}
    _, anat_blob = encode_anatomy(anat)
    mod = ModuleResult.empty(rgb.shape[:2], status="executado", source="bench")
    mod.accepted[10:30, 10:30] = True
    _, mod_blob = encode_module_result("acne", mod)
    return {
        "crop_shape": list(rgb.shape),
        "raw_rgb_bytes": raw_rgb_bytes,
        "compressed_rgb_bytes": len(rgb_blob),
        "avoided_float32_lab_bytes": raw_lab_bytes,
        "encoded_anatomy_bytes": len(anat_blob),
        "encoded_specialist_mask_bytes": len(mod_blob),
    }


def _print_summary(report_data: dict) -> None:
    w = 84
    print("\n+" + "=" * (w - 2) + "+")
    header = f" Benchmark Pipeline Meu Tom ({report_data['mode']}) — OpenMP={report_data['openmp']['openmp']} ({report_data['openmp']['max_threads']} threads) "
    print(f"|{header:^{w - 2}}|")
    wire = report_data["wire_payload"]
    wire_line = (
        f" Crop {wire['crop_shape'][1]}x{wire['crop_shape'][0]}: RGB rede={wire['compressed_rgb_bytes'] / 1024:.1f} KB "
        f"(bruto {wire['raw_rgb_bytes'] / 1024:.1f} KB; Lab evitado {wire['avoided_float32_lab_bytes'] / 1024:.1f} KB) | "
        f"Máscara P2P={wire['encoded_specialist_mask_bytes']} B "
    )
    print(f"|{wire_line:<{w - 2}}|")
    print("+" + "-" * (w - 2) + "+")
    print(f"| {'Arquitetura':<28} | {'p50 ms':>9} | {'min ms':>9} | {'max ms':>9} | {'req/s':>8} | {'speedup':>8} |")
    print("+" + "-" * (w - 2) + "+")
    base_p50 = report_data["results"]["sequential"]["p50_ms"]
    for name, stats in report_data["results"].items():
        sp = base_p50 / max(stats["p50_ms"], 1e-6)
        print(
            f"| {name:<28} | {stats['p50_ms']:>9.2f} | {stats['min_ms']:>9.2f} | "
            f"{stats['max_ms']:>9.2f} | {stats['throughput_rps']:>8.2f} | {sp:>7.2f}x |"
        )
    print("+" + "=" * (w - 2) + "+\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rounds", nargs="?", type=int, default=5, help="Rodadas por arquitetura (padrão: 5)")
    parser.add_argument("--real", action="store_true", help="Executa modelos ONNX reais na amostra do projeto")
    parser.add_argument("--concurrency", type=int, default=1, help="Requisições simultâneas (padrão: 1)")
    parser.add_argument("--gpu-peer", default="", help="Endereço host:porta opcional do nó NVIDIA GPU remoto")
    parser.add_argument("--json", default="", help="Caminho opcional para salvar relatório JSON")
    args = parser.parse_args()

    results = {}
    if args.real:
        import os
        from backend.src.skin_selection import runtime as _rt
        rgb = detectar_e_isolar_rosto(str(ROOT / "samples" / "imagem_teste.jpeg"))
        assert rgb is not None

        # 1. Baseline sequencial original (2 threads ORT fixas, sem kernel C/OpenMP, estágios 1-a-1)
        with patch.dict(os.environ, {"MAQUIAGEM_ORT_THREADS": "2", "MAQUIAGEM_DISABLE_OMP": "1"}):
            _rt._sessions.clear()
            results["sequential"] = _measure_mode(
                lambda: _run_legacy_sequential(rgb, facial_fn=facial_masks, module_fn=run_module),
                args.rounds,
                args.concurrency,
            )

        # 2. Local paralelo + OpenMP + escalonamento proporcional de threads
        _rt._sessions.clear()
        local_exec = LocalParallelExecutor()
        results["local_parallel_omp"] = _measure_mode(
            lambda: _consume_pipeline(rgb, local_exec),
            args.rounds,
            args.concurrency,
        )

        # Cluster P2P em processos separados (Estágios: Gateway -> Seg Process -> Color/OpenMP Process)
        procs, addrs = _spawn_cluster_procs([("seg-proc", "segmentation"), ("color-proc", "color_match")], warmup=True)
        dist_stages = DistributedExecutor(addrs, fallback_policy="degrade")
        try:
            results["p2p_multiprocess_stages"] = _measure_mode(
                lambda: _consume_pipeline(rgb, dist_stages),
                args.rounds,
                args.concurrency,
            )
        finally:
            dist_stages.close()
            _stop_procs(procs)

        # Cluster P2P fragmentado (Especialista pesado YOLOv8l-seg isolado em processo próprio)
        procs, addrs = _spawn_cluster_procs(
            [("fast-seg", "bisenet,acne,vitiligo"), ("beard-seg", "barba"), ("color-proc", "color_match")],
            warmup=True,
        )
        dist_sharded = DistributedExecutor(addrs, fallback_policy="degrade")
        try:
            results["p2p_multiprocess_sharded"] = _measure_mode(
                lambda: _consume_pipeline(rgb, dist_sharded),
                args.rounds,
                args.concurrency,
            )
        finally:
            dist_sharded.close()
            _stop_procs(procs)

        if args.gpu_peer.strip():
            procs, local_addrs = _spawn_cluster_procs([("color-proc", "color_match")], warmup=True)
            dist_gpu = DistributedExecutor([args.gpu_peer.strip(), *local_addrs], fallback_policy="degrade")
            try:
                results["p2p_hybrid_remote_gpu"] = _measure_mode(
                    lambda: _consume_pipeline(rgb, dist_gpu),
                    args.rounds,
                    args.concurrency,
                )
            finally:
                dist_gpu.close()
                _stop_procs(procs)
    else:
        rgb = _synthetic_crop()

        def _mock_facial(crop):
            time.sleep(MOCK_LATENCIES["bisenet"])
            m = np.ones(crop.shape[:2], bool)
            return {"allowed": m, "face": m, "seeds": m, "method": "mock", "model": "mock", "warnings": []}

        def _mock_mod(key, crop, _anat):
            time.sleep(MOCK_LATENCIES[key])
            return ModuleResult.empty(crop.shape[:2], status="executado", source=f"mock_{key}")

        results["sequential"] = _measure_mode(
            lambda: _run_legacy_sequential(rgb, facial_fn=_mock_facial, module_fn=_mock_mod),
            args.rounds,
            args.concurrency,
        )
        local_exec = LocalParallelExecutor()
        with patch("backend.src.segmentation.pipeline.facial_masks", side_effect=_mock_facial), \
             patch("backend.src.segmentation.pipeline.run_module", side_effect=_mock_mod):
            results["local_parallel_omp"] = _measure_mode(
                lambda: _consume_pipeline(rgb, local_exec),
                args.rounds,
                args.concurrency,
            )

    report_data = {
        "mode": "real_onnx" if args.real else "synthetic_mock",
        "rounds": args.rounds,
        "concurrency": args.concurrency,
        "openmp": omp_info(),
        "wire_payload": _wire_overhead_summary(rgb),
        "results": results,
    }
    _print_summary(report_data)
    if args.json:
        Path(args.json).write_text(json.dumps(report_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
