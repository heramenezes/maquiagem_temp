"""Daemon de nó trabalhador P2P multiplataforma (Linux / Windows).

Cada instância de `WorkerNode` é um processo independente escutando TCP e executando
apenas os estágios declarados em `--capabilities`:
  - `bisenet`, `acne`, `vitiligo`, `barba` (atalhos: `segmentation`, `specialists`)
  - `color_match` (conversão OpenMP CIELAB, K-means, composição, qualidade e ranking ΔE00)

Transferência P2P direta:
  Os nós de segmentação encaminham as máscaras compactadas (`MSG_STAGE_DATA`, ~2–5 KB)
  diretamente ao nó `color_match` (seja por conexão de saída assinada pelo `color_match`
  — exigindo apenas 1 porta aberta na máquina GPU — ou discagem direta `forward_addr`),
  enquanto enviam apenas confirmações leves (`MSG_STAGE_EVENT`) ao Gateway HTTP.
"""

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
import hmac
import logging
import os
import signal
import socket
import threading
import time
import uuid

import cv2
import numpy as np

from .codec import (
    decode_anatomy,
    decode_module_result,
    decode_rgb,
    encode_anatomy,
    encode_module_result,
    encode_rgb,
)
from .native import omp_info
from .protocol import (
    MSG_CANCEL,
    MSG_COLOR_INIT,
    MSG_COLOR_RESULT,
    MSG_ERROR,
    MSG_HELLO,
    MSG_HELLO_ACK,
    MSG_PING,
    MSG_PONG,
    MSG_STAGE_DATA,
    MSG_STAGE_EVENT,
    MSG_SUBMIT_BATCH,
    PeerConnection,
    cluster_secret,
    compute_auth_tag,
    configure_socket,
    parse_host_port,
    recv_frame,
    send_frame,
)
from .registry import expand_capabilities, parse_peer_specs

logger = logging.getLogger(__name__)


def _detect_compute_device(capabilities: tuple[str, ...]) -> str:
    if not any(c in {"bisenet", "acne", "vitiligo", "barba"} for c in capabilities):
        return "CPU-OMP" if omp_info().get("openmp") else "CPU"
    try:
        import onnxruntime as ort
        from ..skin_selection.runtime import _cuda_runtime_usable
        if "CUDAExecutionProvider" in ort.get_available_providers() and _cuda_runtime_usable():
            return "CUDA"
    except Exception:
        pass
    return "CPU"


@dataclass
class _ColorJoinContext:
    req_id: str
    created_at: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancelled: bool = False
    completed: bool = False
    gateway_conn: PeerConnection | None = None
    expected_modules: tuple[str, ...] = ("acne", "vitiligo", "barba")
    rgb: np.ndarray | None = None
    lab_future: Future | None = None
    clusters_future: Future | None = None
    anatomy: dict | None = None
    modules: dict = field(default_factory=dict)
    cielab_ms: float = 0.0
    cielab_seq_ref_future: Future | None = None
    mask_wire_bytes: int = 0


class WorkerNode:
    """Servidor TCP P2P para execução distribuída de estágios do pipeline."""

    def __init__(
        self,
        bind_host: str = "127.0.0.1",
        bind_port: int = 0,
        *,
        capabilities: str | list[str] | tuple[str, ...] = ("segmentation",),
        node_id: str | None = None,
        subscribe_peers: list[str] | None = None,
        workers: int | None = None,
        advertise_addr: str | None = None,
        ttl_seconds: float = 45.0,
        secret: str | None = None,
    ):
        self.capabilities = expand_capabilities(capabilities)
        if not self.capabilities:
            raise ValueError("WorkerNode exige pelo menos uma capacidade.")
        if "bisenet" in self.capabilities:
            # Permite que nós dedicados/GPU acelerem também o BiSeNet via CUDA quando disponível.
            os.environ.setdefault("MAQUIAGEM_BISENET_CUDA", "1")

        self.bind_host = bind_host
        self.bind_port = int(bind_port)
        self.node_id = node_id or f"node-{'-'.join(self.capabilities[:2])}-{uuid.uuid4().hex[:6]}"
        self._advertise_override = advertise_addr
        self.subscribe_peers = parse_peer_specs(subscribe_peers)
        self.ttl_seconds = ttl_seconds
        self.secret = cluster_secret() if secret is None else secret
        self.device = _detect_compute_device(self.capabilities)

        pool_size = workers or max(4, min(8, (os.cpu_count() or 4)))
        self._pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix=f"worker-{self.node_id}")
        self._server_sock: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._reaper_thread: threading.Thread | None = None
        self._sub_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._conns_lock = threading.Lock()
        self._dial_lock = threading.Lock()
        self._connections: set[PeerConnection] = set()
        self._subscribers: dict[str, PeerConnection] = {}  # remote_node_id -> PeerConnection
        self._outbound_peers: dict[str, PeerConnection] = {}  # addr -> PeerConnection

        self._tasks_lock = threading.Lock()
        self._cancelled_reqs: dict[str, float] = {}
        self._color_contexts: dict[str, _ColorJoinContext] = {}
        self._inflight = 0
        self._inflight_lock = threading.Lock()

    @property
    def bound_port(self) -> int:
        if self._server_sock is None:
            return self.bind_port
        return int(self._server_sock.getsockname()[1])

    @property
    def active_device(self) -> str:
        if self.device == "CUDA":
            from ..skin_selection import runtime as _rt
            if _rt._cuda_disabled:
                self.device = "CPU"
        return self.device

    @property
    def address(self) -> str:
        if self._advertise_override:
            return self._advertise_override
        host = "127.0.0.1" if self.bind_host in {"0.0.0.0", "::"} else self.bind_host
        return f"{host}:{self.bound_port}"

    def _inc_inflight(self, delta: int) -> int:
        with self._inflight_lock:
            self._inflight = max(0, self._inflight + delta)
            return self._inflight

    def warmup(self) -> None:
        """Pré-carrega e valida na memória/VRAM apenas os modelos atribuídos a este nó."""
        available_caps: list[str] = []
        if "bisenet" in self.capabilities:
            from ..segmentation import semantic
            try:
                semantic.get_session()
                available_caps.append("bisenet")
                logger.info("[OK] Modelo pronto em %s: bisenet", self.node_id)
            except semantic.ModelUnavailableError as exc:
                logger.warning("[INDISPONÍVEL] BiSeNet ausente/inválido em %s: %s", self.node_id, exc)
        for key in ("acne", "vitiligo", "barba"):
            if key in self.capabilities:
                from ..skin_selection.runtime import get_session as get_specialist_session
                from ..segmentation.semantic import ModelUnavailableError
                try:
                    get_specialist_session(key)
                    available_caps.append(key)
                    logger.info("[OK] Modelo pronto em %s: %s", self.node_id, key)
                except ModelUnavailableError as exc:
                    logger.warning("[INDISPONÍVEL] Especialista %s ausente/inválido em %s: %s", key, self.node_id, exc)
        if "color_match" in self.capabilities:
            from ..catalog import load_catalog
            try:
                load_catalog()
            except Exception as exc:
                logger.warning("Warmup catálogo falhou em %s: %s", self.node_id, exc)
            omp_info()
            available_caps.append("color_match")
        if available_caps:
            self.capabilities = tuple(available_caps)

    def start(self, *, warmup: bool = False) -> "WorkerNode":
        family = socket.AF_INET6 if ":" in self.bind_host else socket.AF_INET
        srv = socket.socket(family, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.bind_host, self.bind_port))
        srv.listen(64)
        self._server_sock = srv

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name=f"accept-{self.node_id}",
            daemon=True,
        )
        self._accept_thread.start()

        self._reaper_thread = threading.Thread(
            target=self._reap_loop,
            name=f"reaper-{self.node_id}",
            daemon=True,
        )
        self._reaper_thread.start()

        if self.subscribe_peers:
            self._sub_thread = threading.Thread(
                target=self._subscription_loop,
                name=f"sub-{self.node_id}",
                daemon=True,
            )
            self._sub_thread.start()

        if warmup:
            logger.info("Carregando modelos atribuídos para %s (%s)...", self.node_id, self.capabilities)
            self.warmup()

        logger.info(
            "Nó P2P pronto: id=%s bind=%s:%d caps=%s device=%s",
            self.node_id, self.bind_host, self.bound_port, self.capabilities, self.active_device,
        )
        return self

    def stop(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
        with self._conns_lock:
            conns = list(self._connections) + list(self._outbound_peers.values())
            self._connections.clear()
            self._subscribers.clear()
            self._outbound_peers.clear()
        for conn in conns:
            conn.close()
        with self._tasks_lock:
            self._color_contexts.clear()
            self._cancelled_reqs.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── Gerenciamento de conexões TCP e assinatura P2P de saída ───────────────

    def _accept_loop(self) -> None:
        assert self._server_sock is not None
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._server_sock.accept()
            except OSError:
                break
            peer_label = f"{addr[0]}:{addr[1]}"
            threading.Thread(
                target=self._handshake_inbound,
                args=(client_sock, peer_label),
                daemon=True,
            ).start()

    def _handshake_inbound(self, sock: socket.socket, peer_label: str) -> None:
        try:
            configure_socket(sock)
            sock.settimeout(5.0)
            msg_type, _, header, _ = recv_frame(sock)
            if msg_type != MSG_HELLO:
                sock.close()
                return

            secret = self.secret
            if secret:
                nonce = str(header.get("nonce", ""))
                remote_id = str(header.get("node_id", ""))
                expected = compute_auth_tag(secret, nonce, remote_id)
                provided = str(header.get("auth", ""))
                if not nonce or not hmac.compare_digest(expected, provided):
                    send_frame(sock, MSG_ERROR, {"code": "AUTH_FAILED", "message": "Token P2P inválido."})
                    sock.close()
                    return

            ack = {
                "node_id": self.node_id,
                "address": self.address,
                "capabilities": list(self.capabilities),
                "device": self.active_device,
                "omp_threads": omp_info().get("max_threads", 1),
                "inflight": self._inflight,
            }
            send_frame(sock, MSG_HELLO_ACK, ack)
            sock.settimeout(None)

            conn = PeerConnection(
                sock,
                peer_label,
                on_frame=self._on_frame,
                on_close=self._on_conn_close,
            )
            conn.remote_node_id = str(header.get("node_id") or peer_label)
            conn.remote_capabilities = tuple(header.get("capabilities") or ())
            with self._conns_lock:
                self._connections.add(conn)
                if header.get("subscriber") and conn.remote_node_id:
                    self._subscribers[conn.remote_node_id] = conn
                    logger.info("Par assinante P2P registrado: %s (%s)", conn.remote_node_id, peer_label)
            conn.start()
        except Exception:
            try:
                sock.close()
            except OSError:
                pass

    def _on_conn_close(self, conn: PeerConnection) -> None:
        with self._conns_lock:
            self._connections.discard(conn)
            if conn.remote_node_id and self._subscribers.get(conn.remote_node_id) is conn:
                self._subscribers.pop(conn.remote_node_id, None)
            for addr, existing in list(self._outbound_peers.items()):
                if existing is conn:
                    self._outbound_peers.pop(addr, None)

    def _dial_outbound(self, target_addr: str, *, subscriber: bool = False) -> PeerConnection | None:
        with self._conns_lock:
            existing = self._outbound_peers.get(target_addr)
            if existing is not None and not existing.is_closed:
                return existing

        with self._dial_lock:
            with self._conns_lock:
                existing = self._outbound_peers.get(target_addr)
                if existing is not None and not existing.is_closed:
                    return existing

            host, port = parse_host_port(target_addr)
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=2.5)
                configure_socket(sock)
                nonce = uuid.uuid4().hex
                secret = self.secret
                hello = {
                    "node_id": self.node_id,
                    "capabilities": list(self.capabilities),
                    "subscriber": subscriber,
                    "nonce": nonce,
                }
                if secret:
                    hello["auth"] = compute_auth_tag(secret, nonce, self.node_id)
                send_frame(sock, MSG_HELLO, hello)
                msg_type, _, ack, _ = recv_frame(sock)
                if msg_type != MSG_HELLO_ACK:
                    sock.close()
                    return None
                sock.settimeout(None)
                conn = PeerConnection(sock, target_addr, on_frame=self._on_frame, on_close=self._on_conn_close)
                conn.remote_node_id = str(ack.get("node_id") or target_addr)
                conn.remote_capabilities = tuple(ack.get("capabilities") or ())
                with self._conns_lock:
                    self._connections.add(conn)
                    self._outbound_peers[target_addr] = conn
                conn.start()
                return conn
            except OSError:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                return None

    def _subscription_loop(self) -> None:
        """Mantém canal P2P de saída aberto com nós produtores (ex.: nó GPU na LAN)."""
        backoff = 0.05
        while not self._stop_event.is_set():
            all_ok = True
            for peer_addr in self.subscribe_peers:
                if self._stop_event.is_set():
                    return
                if self._dial_outbound(peer_addr, subscriber=True) is None:
                    all_ok = False
            backoff = 2.0 if all_ok else min(2.0, backoff * 2.0)
            self._stop_event.wait(backoff)

    def _reap_loop(self) -> None:
        """Limpa imediatamente contextos órfãos vencidos (garantia estrita somente-RAM)."""
        while not self._stop_event.is_set():
            self._stop_event.wait(5.0)
            now = time.monotonic()
            with self._tasks_lock:
                expired_ctx = [rid for rid, ctx in self._color_contexts.items() if now - ctx.created_at > self.ttl_seconds]
                for rid in expired_ctx:
                    self._color_contexts.pop(rid, None)
                expired_cancel = [rid for rid, ts in self._cancelled_reqs.items() if now - ts > self.ttl_seconds]
                for rid in expired_cancel:
                    self._cancelled_reqs.pop(rid, None)

    def _is_cancelled(self, req_id: str | None) -> bool:
        if not req_id:
            return False
        with self._tasks_lock:
            return req_id in self._cancelled_reqs

    # ── Despacho de mensagens P2P ─────────────────────────────────────────────

    def _on_frame(self, conn: PeerConnection, msg_type: int, req_id: str | None, header: dict, payload: bytes) -> None:
        if msg_type == MSG_PING:
            try:
                conn.send(MSG_PONG, {"sent_ns": header.get("sent_ns"), "inflight": self._inflight}, req_id=req_id)
            except ConnectionError:
                pass
            return

        if msg_type == MSG_CANCEL and req_id:
            with self._tasks_lock:
                self._cancelled_reqs[req_id] = time.monotonic()
                ctx = self._color_contexts.pop(req_id, None)
            if ctx is not None:
                with ctx.lock:
                    ctx.cancelled = True
                    if ctx.lab_future:
                        ctx.lab_future.cancel()
                    if ctx.clusters_future:
                        ctx.clusters_future.cancel()
            return

        if msg_type == MSG_SUBMIT_BATCH and req_id:
            self._handle_submit_batch(conn, req_id, header, payload)
            return

        if msg_type == MSG_COLOR_INIT and req_id:
            self._handle_color_init(conn, req_id, header, payload)
            return

        if msg_type == MSG_STAGE_DATA and req_id:
            self._handle_stage_data(conn, req_id, header, payload)
            return

    # ── Execução de Segmentação (BiSeNet + Especialistas) e Encaminhamento P2P ─

    def _forward_stage_data(
        self,
        caller_conn: PeerConnection,
        req_id: str,
        forward_node_id: str | None,
        forward_addr: str | None,
        data_meta: dict,
        data_blob: bytes,
    ) -> bool:
        """Envia máscara P2P diretamente ao nó seguinte; faz fallback ao chamador se inacessível."""
        target_conn: PeerConnection | None = None
        if forward_node_id:
            with self._conns_lock:
                sub = self._subscribers.get(forward_node_id)
                if sub is not None and not sub.is_closed:
                    target_conn = sub

        if target_conn is not None:
            try:
                target_conn.send(MSG_STAGE_DATA, data_meta, data_blob, req_id=req_id)
                return True
            except ConnectionError:
                target_conn = None

        if forward_addr:
            dialed = self._dial_outbound(forward_addr, subscriber=False)
            if dialed is not None:
                try:
                    dialed.send(MSG_STAGE_DATA, data_meta, data_blob, req_id=req_id)
                    return True
                except ConnectionError:
                    pass

        # Se não há próximo nó externo (ou falhou conexão direta), entrega ao próprio Gateway.
        caller_conn.send(MSG_STAGE_DATA, data_meta, data_blob, req_id=req_id)
        return False

    def _handle_submit_batch(self, caller_conn: PeerConnection, req_id: str, header: dict, payload: bytes) -> None:
        if self._is_cancelled(req_id):
            return
        stages = [str(s) for s in header.get("stages", [])]
        forward_node_id = header.get("forward_node_id")
        forward_addr = header.get("forward_addr")
        try:
            rgb = decode_rgb(header["rgb"], payload)
        except Exception as exc:
            try:
                caller_conn.send(MSG_ERROR, {"stage": "decode_rgb", "message": str(exc)}, req_id=req_id)
            except ConnectionError:
                pass
            return

        for stage in stages:
            self._inc_inflight(1)
            self._pool.submit(
                self._run_vision_stage,
                caller_conn,
                req_id,
                stage,
                rgb,
                forward_node_id,
                forward_addr,
            )

    def _run_vision_stage(
        self,
        caller_conn: PeerConnection,
        req_id: str,
        stage: str,
        rgb: np.ndarray,
        forward_node_id: str | None,
        forward_addr: str | None,
    ) -> None:
        t0 = time.perf_counter()
        try:
            if self._is_cancelled(req_id) or caller_conn.is_closed:
                return

            if stage == "bisenet":
                from ..segmentation.semantic import (
                    ModelUnavailableError,
                    facial_masks,
                    fallback_facial_masks,
                )
                try:
                    anatomy = facial_masks(rgb)
                except ModelUnavailableError:
                    anatomy = fallback_facial_masks(rgb, "segmentacao_indisponivel")
                if not anatomy["allowed"].any():
                    anatomy = fallback_facial_masks(rgb, "pele_nao_segmentada")
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                meta, blob = encode_anatomy(anatomy)
                forwarded = self._forward_stage_data(caller_conn, req_id, forward_node_id, forward_addr, meta, blob)
                caller_conn.send(
                    MSG_STAGE_EVENT,
                    {
                        "stage": "mascara",
                        "capability": "bisenet",
                        "node_id": self.node_id,
                        "device": self.device,
                        "elapsed_ms": round(elapsed_ms, 2),
                        "forwarded_p2p": forwarded,
                    },
                    req_id=req_id,
                )
            elif stage in {"acne", "vitiligo", "barba"}:
                from ..skin_selection.pipeline import run_module
                # Os detectores neurais dependem exclusivamente de rgb; a interseção anatômica ocorre em compose().
                dummy_anatomy = {"allowed": np.ones(rgb.shape[:2], dtype=bool)}
                mod_result = run_module(stage, rgb, dummy_anatomy)
                meta, blob = encode_module_result(stage, mod_result)
                forwarded = self._forward_stage_data(caller_conn, req_id, forward_node_id, forward_addr, meta, blob)
                caller_conn.send(
                    MSG_STAGE_EVENT,
                    {
                        "stage": stage,
                        "capability": stage,
                        "module_status": mod_result.status,
                        "node_id": self.node_id,
                        "device": self.device,
                        "elapsed_ms": round(mod_result.elapsed_ms, 2),
                        "forwarded_p2p": forwarded,
                    },
                    req_id=req_id,
                )
            else:
                caller_conn.send(MSG_ERROR, {"stage": stage, "message": f"Capacidade não suportada: {stage}"}, req_id=req_id)
        except ConnectionError:
            pass
        except Exception as exc:
            logger.exception("Falha executando estágio %s em %s", stage, self.node_id)
            try:
                caller_conn.send(MSG_ERROR, {"stage": stage, "message": str(exc)}, req_id=req_id)
            except ConnectionError:
                pass
        finally:
            self._inc_inflight(-1)

    # ── Execução do Nó de Cor, Qualidade e Match (Estágio 3 P2P) ──────────────

    def _get_or_create_color_ctx(self, req_id: str) -> _ColorJoinContext | None:
        with self._tasks_lock:
            if req_id in self._cancelled_reqs:
                return None
            ctx = self._color_contexts.get(req_id)
            if ctx is None:
                ctx = _ColorJoinContext(req_id=req_id)
                self._color_contexts[req_id] = ctx
            return ctx

    def _handle_color_init(self, caller_conn: PeerConnection, req_id: str, header: dict, payload: bytes) -> None:
        if "color_match" not in self.capabilities:
            try:
                caller_conn.send(MSG_ERROR, {"stage": "color_match", "message": "Nó não possui capacidade color_match."}, req_id=req_id)
            except ConnectionError:
                pass
            return

        ctx = self._get_or_create_color_ctx(req_id)
        if ctx is None:
            return

        try:
            rgb = decode_rgb(header["rgb"], payload)
        except Exception as exc:
            with self._tasks_lock:
                self._color_contexts.pop(req_id, None)
            try:
                caller_conn.send(MSG_ERROR, {"stage": "color_init", "message": str(exc)}, req_id=req_id)
            except ConnectionError:
                pass
            return

        from .metrics import measure_numpy_cielab_reference_ms

        with ctx.lock:
            ctx.gateway_conn = caller_conn
            ctx.expected_modules = tuple(header.get("expected_modules") or ("acne", "vitiligo", "barba"))
            ctx.rgb = rgb
            # Dispara conversão CIELAB (OpenMP C) imediatamente enquanto as redes neurais rodam em paralelo!
            ctx.lab_future = self._pool.submit(self._compute_lab_and_notify, ctx)
            ctx.cielab_seq_ref_future = self._pool.submit(measure_numpy_cielab_reference_ms, rgb)
            self._maybe_schedule_downstream_locked(ctx)

    def _compute_lab_and_notify(self, ctx: _ColorJoinContext) -> np.ndarray:
        from ..segmentation.color import rgb_to_lab
        t0 = time.perf_counter()
        assert ctx.rgb is not None
        lab = rgb_to_lab(ctx.rgb)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        ctx.cielab_ms = elapsed_ms
        if ctx.gateway_conn is not None and not ctx.cancelled:
            try:
                ctx.gateway_conn.send(
                    MSG_STAGE_EVENT,
                    {"stage": "cielab", "node_id": self.node_id, "elapsed_ms": round(elapsed_ms, 2)},
                    req_id=ctx.req_id,
                )
            except ConnectionError:
                pass
        return lab

    def _handle_stage_data(self, _sender_conn: PeerConnection, req_id: str, header: dict, payload: bytes) -> None:
        if "color_match" not in self.capabilities:
            return
        ctx = self._get_or_create_color_ctx(req_id)
        if ctx is None:
            return

        try:
            kind = header.get("kind")
            if kind == "anatomy":
                decoded_anatomy = decode_anatomy(header, payload)
                with ctx.lock:
                    ctx.anatomy = decoded_anatomy
                    ctx.mask_wire_bytes += len(payload)
                    self._maybe_schedule_downstream_locked(ctx)
            elif kind == "module":
                mod_key, mod_res = decode_module_result(header, payload)
                with ctx.lock:
                    ctx.modules[mod_key] = mod_res
                    ctx.mask_wire_bytes += len(payload)
                    self._maybe_schedule_downstream_locked(ctx)
        except Exception as exc:
            logger.exception("Erro decodificando MSG_STAGE_DATA em %s", self.node_id)
            with self._tasks_lock:
                self._color_contexts.pop(req_id, None)
            if ctx.gateway_conn is not None:
                try:
                    ctx.gateway_conn.send(MSG_ERROR, {"stage": "stage_data", "message": str(exc)}, req_id=req_id)
                except ConnectionError:
                    pass

    @staticmethod
    def _compute_clusters(rgb: np.ndarray, lab: np.ndarray, anatomy: dict) -> tuple[dict, float]:
        from ..segmentation.skin import adaptive_clusters
        t0 = time.perf_counter()
        factor = min(1, 512 / max(rgb.shape[:2]))
        size = (max(1, round(rgb.shape[1] * factor)), max(1, round(rgb.shape[0] * factor)))
        small_lab = cv2.resize(lab, size, interpolation=cv2.INTER_AREA)
        small_mask = cv2.resize(anatomy["allowed"].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
        clusters = adaptive_clusters(small_lab, {"allowed": small_mask, "seeds": small_mask}) if small_mask.sum() >= 64 else {"k": None}
        return clusters, (time.perf_counter() - t0) * 1000.0

    def _maybe_schedule_downstream_locked(self, ctx: _ColorJoinContext) -> None:
        if ctx.cancelled or ctx.completed or ctx.rgb is None or ctx.lab_future is None:
            return
        if ctx.anatomy is not None and ctx.clusters_future is None:
            # K-means descritivo depende apenas de lab + anatomia inicial; roda em paralelo aos especialistas restantes.
            rgb_ref = ctx.rgb
            anat_ref = ctx.anatomy
            lab_fut = ctx.lab_future
            ctx.clusters_future = self._pool.submit(lambda: self._compute_clusters(rgb_ref, lab_fut.result(), anat_ref))

        if ctx.anatomy is not None and all(k in ctx.modules for k in ctx.expected_modules):
            ctx.completed = True
            self._inc_inflight(1)
            self._pool.submit(self._finalize_color_and_match, ctx)

    def _finalize_color_and_match(self, ctx: _ColorJoinContext) -> None:
        from ..segmentation.pipeline import summarize
        from ..segmentation.semantic import measure_skin
        from ..skin_selection.pipeline import finish
        from ..skin_selection.serialization import conditions
        from ..tone_matching.analysis import build_analysis

        try:
            with self._tasks_lock:
                self._color_contexts.pop(ctx.req_id, None)
            if ctx.cancelled or self._is_cancelled(ctx.req_id) or ctx.gateway_conn is None or ctx.gateway_conn.is_closed:
                return

            assert ctx.rgb is not None and ctx.lab_future is not None and ctx.anatomy is not None
            rgb = ctx.rgb
            lab = ctx.lab_future.result()
            anatomy = ctx.anatomy
            modules = ctx.modules

            t_sel = time.perf_counter()
            selection = finish(rgb, lab, anatomy, modules)
            selecao_ms = (time.perf_counter() - t_sel) * 1000.0
            ctx.gateway_conn.send(MSG_STAGE_EVENT, {"stage": "selecao", "node_id": self.node_id, "elapsed_ms": round(selecao_ms, 2)}, req_id=ctx.req_id)

            if ctx.clusters_future is not None:
                clusters, clusters_ms = ctx.clusters_future.result()
            else:
                clusters, clusters_ms = self._compute_clusters(rgb, lab, anatomy)
            ctx.gateway_conn.send(MSG_STAGE_EVENT, {"stage": "clusters", "node_id": self.node_id, "elapsed_ms": round(clusters_ms, 2)}, req_id=ctx.req_id)

            t_med = time.perf_counter()
            skin = measure_skin(lab, selection["measurement_mask"], rgb=rgb, face_mask=anatomy["face"])
            medidas_ms = (time.perf_counter() - t_med) * 1000.0
            ctx.gateway_conn.send(MSG_STAGE_EVENT, {"stage": "medidas", "node_id": self.node_id, "elapsed_ms": round(medidas_ms, 2)}, req_id=ctx.req_id)

            t_res = time.perf_counter()
            result = build_analysis(skin, selection, int(anatomy["face"].sum()), lab_image=lab, rgb_image=rgb)
            result["condicoes"] = conditions(selection)
            result["marcacoes"] = []
            result["preprocessamento"] = summarize(rgb, anatomy, clusters, skin, selection)
            result["status_analise"] = "concluida"
            resultado_ms = (time.perf_counter() - t_res) * 1000.0
            seq_np_ms = ctx.cielab_seq_ref_future.result() if ctx.cielab_seq_ref_future is not None else ctx.cielab_ms

            ctx.gateway_conn.send(
                MSG_COLOR_RESULT,
                {
                    "result": result,
                    "node_id": self.node_id,
                    "device": self.device,
                    "timings_ms": {
                        "cielab": round(ctx.cielab_ms, 3),
                        "cielab_numpy_seq": round(seq_np_ms, 3),
                        "selecao": round(selecao_ms, 2),
                        "clusters": round(clusters_ms, 2),
                        "medidas": round(medidas_ms, 2),
                        "resultado": round(resultado_ms, 2),
                    },
                    "mask_wire_bytes": int(ctx.mask_wire_bytes),
                },
                req_id=ctx.req_id,
            )
        except ConnectionError:
            pass
        except Exception as exc:
            logger.exception("Falha na etapa de cor/match em %s", self.node_id)
            if ctx.gateway_conn is not None:
                try:
                    ctx.gateway_conn.send(MSG_ERROR, {"stage": "color_match", "message": str(exc)}, req_id=ctx.req_id)
                except ConnectionError:
                    pass
        finally:
            # Limpa explicitamente referências aos buffers de imagem da requisição.
            ctx.rgb = None
            ctx.anatomy = None
            ctx.modules.clear()
            self._inc_inflight(-1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Nó trabalhador P2P para execução distribuída do Meu Tom.")
    parser.add_argument("--bind", default="0.0.0.0:7102", help="Endereço host:porta de escuta TCP (padrão: 0.0.0.0:7102)")
    parser.add_argument(
        "--capabilities",
        default="segmentation",
        help="Capacidades separadas por vírgula: bisenet,acne,vitiligo,barba,color_match ou segmentation (padrão)",
    )
    parser.add_argument("--node-id", default=None, help="Identificador único opcional deste nó")
    parser.add_argument("--advertise", default=None, help="Endereço host:porta anunciado a outros nós")
    parser.add_argument(
        "--subscribe-peers",
        default="",
        help="Lista host:porta de nós produtores (ex.: nó GPU) para abrir canal P2P de saída",
    )
    parser.add_argument("--ort-threads", type=int, default=None, help="Threads intra-op do ONNX Runtime neste processo")
    parser.add_argument("--omp-threads", type=int, default=None, help="Limite OMP_NUM_THREADS neste processo")
    parser.add_argument("--no-warmup", action="store_true", help="Não carregar pesos ONNX na inicialização")
    args = parser.parse_args(argv)

    if args.omp_threads is not None:
        os.environ["OMP_NUM_THREADS"] = str(max(1, args.omp_threads))
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
    if args.ort_threads is not None:
        os.environ["MAQUIAGEM_ORT_THREADS"] = str(max(1, args.ort_threads))
    cv2.setNumThreads(1)

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(name)s — %(message)s")
    host, port = parse_host_port(args.bind)
    node = WorkerNode(
        host,
        port,
        capabilities=args.capabilities,
        node_id=args.node_id,
        subscribe_peers=parse_peer_specs(args.subscribe_peers),
        advertise_addr=args.advertise,
    )
    node.start(warmup=not args.no_warmup)

    stop = threading.Event()

    def _handle_sig(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGINT, _handle_sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_sig)

    try:
        while not stop.is_set():
            stop.wait(1.0)
    finally:
        node.stop()


if __name__ == "__main__":
    main()
