"""Inicializador multiplataforma (Linux / Windows) do cluster PoC multi-processo.

Exemplos de uso:
  1. PoC Híbrido (Processos locais + Nó NVIDIA GPU em outra máquina na rede):
       Na máquina GPU (Windows/Linux .venv-cuda):
         python -m backend.src.distributed.node --bind 0.0.0.0:7102 --capabilities segmentation
       Na máquina principal:
         python -m backend.src.distributed.cluster --gpu-peer 192.168.1.50:7102

  2. PoC 100% Local em Múltiplos Processos (Estágios P2P em processos separados):
       python -m backend.src.distributed.cluster --topology stages

  3. PoC Fragmentado por Especialista (Gateway + 4 processos de modelo + 1 processo Color/OpenMP):
       python -m backend.src.distributed.cluster --topology sharded
"""

import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]


def _pick_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _wait_tcp_ready(address: str, timeout: float = 20.0) -> bool:
    host, _, port_s = address.rpartition(":")
    port = int(port_s)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def compute_thread_budgets(total_cores: int, local_worker_specs: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Particiona threads CPU (OpenMP / ONNX Runtime) proporcionalmente ao peso computacional."""
    cores = max(2, int(total_cores))

    def _weight(caps: str) -> int:
        if "segmentation" in caps or "all_models" in caps:
            return 6
        w = 0
        if "barba" in caps:
            w += 4  # YOLOv8l-seg 640x640 é o especialista de maior custo
        if "bisenet" in caps:
            w += 2
        if "acne" in caps:
            w += 1
        if "vitiligo" in caps:
            w += 1
        if "color_match" in caps and w == 0:
            w += 1
        return max(1, w)

    weights = [_weight(caps) for _name, caps in local_worker_specs]
    total_w = max(1, sum(weights))
    budgets = []
    for (_name, caps), w in zip(local_worker_specs, weights):
        share = max(1, round(cores * w / total_w))
        if "color_match" in caps and w == 1 and "acne" not in caps and "vitiligo" not in caps:
            # Nó dedicado de cor usa OpenMP em rajadas curtas sem competir durante toda a inferência.
            omp_threads = max(2, min(cores, max(share, cores // 2)))
            ort_threads = 1
        elif "segmentation" in caps or "all_models" in caps:
            # Deixa runtime.py balancear barba vs modelos leves internamente até metade dos núcleos.
            omp_threads = max(2, share)
            ort_threads = max(2, min(8, cores // 2))
        else:
            omp_threads = max(1, share)
            ort_threads = max(1, share)
        budgets.append({
            "OMP_NUM_THREADS": str(omp_threads),
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "MAQUIAGEM_ORT_THREADS": str(ort_threads),
        })
    return budgets


def build_local_specs(topology: str, *, has_remote_gpu: bool) -> list[tuple[str, str]]:
    """Retorna lista (node_id, capabilities_csv) de processos trabalhadores locais."""
    if has_remote_gpu and topology == "auto":
        # Com GPU remota cuidando das 4 redes neurais, a máquina local roda o Gateway
        # e um processo separado dedicado a Cor/OpenMP + Match (e opcionalmente fallback local).
        return [("local-color", "color_match")]
    if topology in {"auto", "stages"}:
        # Pipeline P2P canônico de 3 estágios da Seção 3.5 do artigo:
        # Processo 1: Gateway/Rosto | Processo 2: Segmentação | Processo 3: Cor/OpenMP & Match
        return [
            ("local-seg", "segmentation"),
            ("local-color", "color_match"),
        ]
    if topology == "sharded":
        # Isola o modelo pesado de barba (YOLOv8l-seg) em seu próprio processo SO.
        return [
            ("local-fast-seg", "bisenet,acne,vitiligo"),
            ("local-beard", "barba"),
            ("local-color", "color_match"),
        ]
    if topology == "full-sharded":
        return [
            ("local-bisenet", "bisenet"),
            ("local-acne", "acne"),
            ("local-vitiligo", "vitiligo"),
            ("local-barba", "barba"),
            ("local-color", "color_match"),
        ]
    raise ValueError(f"Topologia desconhecida: {topology!r}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Inicializador PoC multi-processo do Meu Tom.")
    parser.add_argument("--host", default="127.0.0.1", help="Host HTTP do Gateway Flask (padrão: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Porta HTTP do Gateway Flask (padrão: 5000)")
    parser.add_argument(
        "--topology",
        choices=("auto", "stages", "sharded", "full-sharded"),
        default="auto",
        help="Layout dos processos locais na máquina principal (padrão: auto)",
    )
    parser.add_argument(
        "--gpu-peer",
        default="",
        help="Endereço host:porta do nó NVIDIA GPU em outra máquina (ex.: 192.168.1.50:7102)",
    )
    parser.add_argument(
        "--fallback",
        choices=("local", "degrade"),
        default="local",
        help="Política caso um nó remoto caia: 'local' (executa localmente) ou 'degrade' (aviso com_ressalvas)",
    )
    parser.add_argument("--no-warmup", action="store_true", help="Não pré-aquecer sessões ONNX na partida")
    args = parser.parse_args(argv)

    remote_peers = [p.strip() for p in args.gpu_peer.split(",") if p.strip()]
    specs = build_local_specs(args.topology, has_remote_gpu=bool(remote_peers))
    budgets = compute_thread_budgets(os.cpu_count() or 4, specs)

    processes: list[subprocess.Popen] = []
    peer_addrs: list[str] = list(remote_peers)

    # Descobre portas locais antes de iniciar para permitir assinatura P2P entre os nós.
    assigned: list[tuple[str, str, str, dict[str, str]]] = []
    seg_addrs_for_color_sub: list[str] = list(remote_peers)
    for (node_id, caps), env_budget in zip(specs, budgets):
        p_port = _pick_free_port("127.0.0.1")
        addr = f"127.0.0.1:{p_port}"
        assigned.append((node_id, caps, addr, env_budget))
        peer_addrs.append(addr)
        if any(k in caps for k in ("segmentation", "bisenet", "acne", "vitiligo", "barba")):
            seg_addrs_for_color_sub.append(addr)

    try:
        for node_id, caps, addr, env_budget in assigned:
            cmd = [
                sys.executable, "-m", "backend.src.distributed.node",
                "--bind", addr,
                "--node-id", node_id,
                "--capabilities", caps,
                "--omp-threads", env_budget["OMP_NUM_THREADS"],
                "--ort-threads", env_budget["MAQUIAGEM_ORT_THREADS"],
            ]
            if "color_match" in caps and seg_addrs_for_color_sub:
                # Abre canal P2P de saída do nó Color para os nós de segmentação (incluindo GPU remota!).
                cmd.extend(["--subscribe-peers", ",".join(seg_addrs_for_color_sub)])
            if args.no_warmup:
                cmd.append("--no-warmup")

            child_env = {**os.environ, **env_budget}
            proc = subprocess.Popen(cmd, cwd=str(ROOT), env=child_env)
            processes.append(proc)

        for node_id, _caps, addr, _ in assigned:
            if not _wait_tcp_ready(addr, timeout=30.0):
                raise RuntimeError(f"Nó local {node_id} ({addr}) não ficou pronto a tempo.")

        # Verifica explicitamente conectividade e handshake P2P com todos os pares (especialmente GPU remota).
        from .registry import PeerRegistry
        probe_reg = PeerRegistry(peer_addrs, connect_timeout=3.0)
        probe_reg.connect_all(force=True)
        peer_statuses = probe_reg.snapshot()
        probe_reg.close()

        gateway_env = {
            **os.environ,
            "MAQUIAGEM_PEERS": ",".join(peer_addrs),
            "MAQUIAGEM_FALLBACK_POLICY": args.fallback,
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "1",
        }
        print("=" * 72)
        print(" Cluster PoC Meu Tom ativo!")
        print(f"   Gateway HTTP : http://{args.host}:{args.port}")
        print(f"   Status P2P   : http://{args.host}:{args.port}/api/cluster")
        for st in peer_statuses:
            if st["healthy"]:
                print(f"   [OK] Par P2P : {st['address']} -> id={st['node_id']} device={st['device']} caps={st['capabilities']} ({st['rtt_ms']} ms)")
            else:
                print(
                    f"   [FALHA CONEXÃO] Par P2P inacessível: {st['address']} "
                    "(verifique IP da rede, se node.py já iniciou e liberação da porta TCP no firewall!)"
                )
        print("=" * 72, flush=True)

        gateway_cmd = [
            sys.executable, "-m", "flask",
            "--app", "backend.app:create_app",
            "run", "--host", args.host, "--port", str(args.port), "--no-reload",
        ]
        gw_proc = subprocess.Popen(gateway_cmd, cwd=str(ROOT), env=gateway_env)
        processes.append(gw_proc)

        while gw_proc.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
        deadline = time.monotonic() + 5.0
        for proc in reversed(processes):
            remaining = max(0.1, deadline - time.monotonic())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
