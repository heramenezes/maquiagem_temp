"""Benchmark: execucao sequencial x paralela dos especialistas de pele.

Executa cada detector N vezes com uma imagem sintetica e compara os tempos.
Nao requer os modelos reais: usa mocks de tempo configuravel por argumento.

Uso:
    python -m backend.tests.bench_pipeline          # mocks, 5 rodadas
    python -m backend.tests.bench_pipeline 10       # mocks, 10 rodadas
    python -m backend.tests.bench_pipeline --real   # modelos reais (requer download)
"""

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter
from typing import Callable

import numpy as np

# Garante que o terminal do Windows aceite a saida sem UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de imagem e anatomia sintética (mesmo estilo de test_skin_selection.py)
# ──────────────────────────────────────────────────────────────────────────────

def _fake_rgb(shape=(256, 256)):
    rng = np.random.default_rng(42)
    noise = rng.integers(-5, 6, (*shape, 1), dtype=np.int16)
    return np.clip(np.full((*shape, 3), [160, 110, 85], dtype=np.int16) + noise,
                   0, 255).astype(np.uint8)


def _fake_anatomy(shape=(256, 256)):
    mask = np.ones(shape, bool)
    return {"allowed": mask, "face": mask, "seeds": mask,
            "method": "bench", "model": "bench", "warnings": []}


# ──────────────────────────────────────────────────────────────────────────────
# Mock de detecção: dorme um tempo fixo simulando inferência
# ──────────────────────────────────────────────────────────────────────────────

MOCK_LATENCIES = {"acne": 0.045, "vitiligo": 0.040, "barba": 0.085}  # segundos


def _make_mock_detector(key: str, latency: float):
    """Retorna uma função que simula um detector com latência fixa."""
    from backend.src.skin_selection.contracts import ModuleResult

    def _detect(rgb, anatomy):
        time.sleep(latency)
        shape = rgb.shape[:2]
        return ModuleResult(
            accepted=np.zeros(shape, bool),
            uncertain=np.zeros(shape, bool),
            status="executado",
            source=f"mock_{key}",
        )
    return _detect


# ──────────────────────────────────────────────────────────────────────────────
# Estratégias de execução (espelham pipeline.py para comparação justa)
# ──────────────────────────────────────────────────────────────────────────────

def _run_sequential(detectors: dict[str, Callable], rgb, anatomy) -> dict[str, float]:
    """Roda os detectores um por um; retorna {key: elapsed_ms}."""
    times = {}
    for key, fn in detectors.items():
        t0 = perf_counter()
        fn(rgb, anatomy)
        times[key] = (perf_counter() - t0) * 1000
    return times


def _run_parallel(detectors: dict[str, Callable], rgb, anatomy) -> dict[str, float]:
    """Roda os detectores em paralelo; retorna {key: elapsed_ms} medido por thread."""
    results = {}

    def _timed(key, fn):
        t0 = perf_counter()
        fn(rgb, anatomy)
        return key, (perf_counter() - t0) * 1000

    with ThreadPoolExecutor(max_workers=len(detectors)) as pool:
        futures = {pool.submit(_timed, k, fn): k for k, fn in detectors.items()}
        for future in as_completed(futures):
            key, elapsed = future.result()
            results[key] = elapsed
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Coleta de métricas: múltiplas rodadas
# ──────────────────────────────────────────────────────────────────────────────

def _collect(fn, detectors, rgb, anatomy, rounds: int):
    """Executa fn(detectors, rgb, anatomy) N vezes; devolve listas de wall-time e por módulo."""
    per_module = {k: [] for k in detectors}
    wall_times = []
    for _ in range(rounds):
        t0 = perf_counter()
        times = fn(detectors, rgb, anatomy)
        wall_times.append((perf_counter() - t0) * 1000)
        for k, ms in times.items():
            per_module[k].append(ms)
    return wall_times, per_module


# ──────────────────────────────────────────────────────────────────────────────
# Impressão do relatório
# ──────────────────────────────────────────────────────────────────────────────

def _bar(fraction: float, width: int = 20) -> str:
    filled = round(fraction * width)
    return "#" * filled + "." * (width - filled)


def _print_report(wall_seq, wall_par, per_seq, per_par, rounds: int, provider: str):
    W = 69

    def hline(char="-"):
        return "+" + char * (W - 2) + "+"

    def row(*cols, widths=(12, 10, 10, 14, 14)):
        cells = []
        for i, (c, w) in enumerate(zip(cols, widths)):
            if i == 0:
                cells.append(f" {str(c):<{w-2}} ")
            else:
                cells.append(f" {str(c):^{w-2}} ")
        return "|" + "|".join(cells) + "|"

    keys = list(per_seq)

    print()
    print(hline("="))
    title = f" benchmark: sequencial x paralelo  ({rounds} rodadas) "
    print(f"|{title:^{W-2}}|")
    print(hline("-"))
    print(row("detector", "min ms", "med ms", "max ms (s)", "max ms (p)"))
    print(hline("-"))

    for k in keys:
        s = per_seq[k]
        p = per_par[k]
        print(row(
            k,
            f"{min(s):.1f}",
            f"{statistics.median(s):.1f}",
            f"{max(s):.1f}",
            f"{max(p):.1f}",
        ))

    print(hline("-"))

    med_seq = statistics.median(wall_seq)
    med_par = statistics.median(wall_par)
    speedup = med_seq / med_par if med_par > 0 else float("inf")
    saved_ms = med_seq - med_par
    saved_pct = (saved_ms / med_seq * 100) if med_seq > 0 else 0

    print(f"|  {'SEQUENCIAL  wall-time':<28}  med {med_seq:7.1f} ms   min {min(wall_seq):7.1f} ms  |")
    print(f"|  {'PARALELO    wall-time':<28}  med {med_par:7.1f} ms   min {min(wall_par):7.1f} ms  |")
    print(f"|  speedup: {speedup:.2f}x   economia: {saved_ms:.1f} ms ({saved_pct:.0f}%)   provider: {provider:<14}|")

    # barra de speedup visual
    bar_fraction = min((speedup - 1) / max(len(keys) - 1, 1), 1.0)
    bar = _bar(bar_fraction, 30)
    print(f"|  [{bar}]  {speedup:.2f}x  (max teorico: {len(keys):.0f}x)  |")
    print(hline("="))
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Modo real: usa os detectores reais via pipeline.py
# ──────────────────────────────────────────────────────────────────────────────

def _real_provider() -> str:
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        return "CUDA" if "CUDAExecutionProvider" in available else "CPU"
    except Exception:
        return "desconhecido"


def _run_real(rounds: int):
    from backend.src.skin_selection import acne, vitiligo, beard
    from backend.src.skin_selection.runtime import _build_providers

    detectors = {"acne": acne.detect, "vitiligo": vitiligo.detect, "barba": beard.detect}
    rgb = _fake_rgb()
    anatomy = _fake_anatomy()

    try:
        providers = _build_providers()
        provider = "CUDA" if any(
            (p[0] if isinstance(p, tuple) else p) == "CUDAExecutionProvider"
            for p in providers
        ) else "CPU"
    except Exception:
        provider = _real_provider()

    print(f"\nAquecendo sessões ONNX (provider: {provider})…")
    # rodada de aquecimento — carrega os modelos na memória/GPU
    try:
        _run_sequential(detectors, rgb, anatomy)
    except Exception as exc:
        print(f"  ⚠  Falha no aquecimento: {exc}")
        print("  Certifique-se de que os modelos estão baixados (backend/models/README.md).")
        sys.exit(1)

    print(f"Coletando {rounds} rodadas…")
    wall_seq, per_seq = _collect(_run_sequential, detectors, rgb, anatomy, rounds)
    wall_par, per_par = _collect(_run_parallel, detectors, rgb, anatomy, rounds)
    _print_report(wall_seq, wall_par, per_seq, per_par, rounds, provider)


# ──────────────────────────────────────────────────────────────────────────────
# Modo mock: não requer modelos baixados
# ──────────────────────────────────────────────────────────────────────────────

def _run_mock(rounds: int):
    detectors = {k: _make_mock_detector(k, lat) for k, lat in MOCK_LATENCIES.items()}
    rgb = _fake_rgb()
    anatomy = _fake_anatomy()

    print(f"\nModo mock — latências simuladas: "
          + ", ".join(f"{k}={int(lat*1000)}ms" for k, lat in MOCK_LATENCIES.items()))
    print(f"Coletando {rounds} rodadas…")

    wall_seq, per_seq = _collect(_run_sequential, detectors, rgb, anatomy, rounds)
    wall_par, per_par = _collect(_run_parallel, detectors, rgb, anatomy, rounds)
    _print_report(wall_seq, wall_par, per_seq, per_par, rounds, "mock")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Benchmark sequencial × paralelo dos especialistas de pele."
    )
    parser.add_argument(
        "rounds", nargs="?", type=int, default=5,
        help="Número de rodadas (padrão: 5)",
    )
    parser.add_argument(
        "--real", action="store_true",
        help="Usa os detectores reais (requer modelos baixados). "
             "Sem esta flag, usa mocks de latência fixa.",
    )
    args = parser.parse_args()

    if args.real:
        _run_real(args.rounds)
    else:
        _run_mock(args.rounds)


if __name__ == "__main__":
    main()
