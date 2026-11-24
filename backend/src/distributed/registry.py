"""Registro de pares P2P, descoberta de capacidades, balanceamento e circuit-breaker."""

from dataclasses import dataclass, field
import logging
import socket
import threading
import time
import uuid

from .protocol import (
    MSG_HELLO,
    MSG_HELLO_ACK,
    MSG_PING,
    MSG_PONG,
    PeerConnection,
    cluster_secret,
    compute_auth_tag,
    configure_socket,
    parse_host_port,
    recv_frame,
    send_frame,
)

logger = logging.getLogger(__name__)

VALID_CAPABILITIES = frozenset({"bisenet", "acne", "vitiligo", "barba", "color_match"})


def expand_capabilities(raw: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(raw, str):
        tokens = [t.strip().lower() for t in raw.split(",") if t.strip()]
    else:
        tokens = [str(t).strip().lower() for t in raw if str(t).strip()]
    expanded: list[str] = []
    for token in tokens:
        if token in {"segmentation", "all_models"}:
            expanded.extend(("bisenet", "acne", "vitiligo", "barba"))
        elif token == "specialists":
            expanded.extend(("acne", "vitiligo", "barba"))
        elif token == "all":
            expanded.extend(("bisenet", "acne", "vitiligo", "barba", "color_match"))
        elif token in VALID_CAPABILITIES:
            expanded.append(token)
        else:
            raise ValueError(f"Capacidade desconhecida: {token!r}")
    return tuple(dict.fromkeys(expanded))


def parse_peer_specs(spec_str: str | list[str] | None) -> list[str]:
    if not spec_str:
        return []
    if isinstance(spec_str, str):
        items = [part.strip() for part in spec_str.split(",") if part.strip()]
    else:
        items = [str(part).strip() for part in spec_str if str(part).strip()]
    # Valida formato host:porta logo na configuração.
    for item in items:
        parse_host_port(item)
    return list(dict.fromkeys(items))


@dataclass
class PeerState:
    address: str
    node_id: str = ""
    capabilities: tuple[str, ...] = ()
    device: str = "unknown"
    omp_threads: int = 1
    inflight: int = 0
    healthy: bool = False
    last_rtt_ms: float = 0.0
    cooldown_until: float = 0.0
    conn: PeerConnection | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class PeerRegistry:
    """Mantém conexões TCP persistentes multiplexadas com nós pares do cluster."""

    def __init__(
        self,
        peer_addresses: list[str],
        *,
        local_node_id: str | None = None,
        on_Async_frame=None,
        connect_timeout: float = 2.5,
        cooldown_seconds: float = 3.0,
        secret: str | None = None,
    ):
        self.local_node_id = local_node_id or f"gateway-{uuid.uuid4().hex[:8]}"
        self._on_frame_cb = on_Async_frame
        self.connect_timeout = connect_timeout
        self.cooldown_seconds = cooldown_seconds
        self.secret = cluster_secret() if secret is None else secret
        self._peers: dict[str, PeerState] = {
            addr: PeerState(address=addr) for addr in parse_peer_specs(peer_addresses)
        }
        self._closed = threading.Event()

    @property
    def peer_addresses(self) -> list[str]:
        return list(self._peers.keys())

    def _on_peer_frame(self, peer: PeerState, conn: PeerConnection, msg_type: int, req_id: str | None, header: dict, payload: bytes):
        if msg_type == MSG_PONG:
            sent_ns = header.get("sent_ns")
            if isinstance(sent_ns, int):
                peer.last_rtt_ms = (time.perf_counter_ns() - sent_ns) / 1e6
            peer.inflight = int(header.get("inflight", peer.inflight))
            peer.healthy = True
            return
        if self._on_frame_cb is not None:
            self._on_frame_cb(peer, conn, msg_type, req_id, header, payload)

    def _on_peer_close(self, peer: PeerState, conn: PeerConnection):
        if peer.conn is conn:
            peer.conn = None
            peer.healthy = False

    def ensure_connected(self, peer: PeerState, *, force: bool = False) -> PeerConnection | None:
        if self._closed.is_set():
            return None
        now = time.monotonic()
        if peer.conn is not None and not peer.conn.is_closed and peer.healthy:
            return peer.conn
        if not force and now < peer.cooldown_until:
            return None

        with peer.lock:
            if peer.conn is not None and not peer.conn.is_closed and peer.healthy:
                return peer.conn
            now = time.monotonic()
            if not force and now < peer.cooldown_until:
                return None

            host, port = parse_host_port(peer.address)
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=self.connect_timeout)
                configure_socket(sock)
                nonce = uuid.uuid4().hex
                secret = self.secret
                hello = {
                    "node_id": self.local_node_id,
                    "capabilities": [],
                    "subscriber": False,
                    "nonce": nonce,
                }
                if secret:
                    hello["auth"] = compute_auth_tag(secret, nonce, self.local_node_id)

                t0 = time.perf_counter()
                send_frame(sock, MSG_HELLO, hello)
                msg_type, _, ack, _ = recv_frame(sock)
                rtt_ms = (time.perf_counter() - t0) * 1000.0
                if msg_type != MSG_HELLO_ACK:
                    raise ConnectionError(f"Resposta inesperada ao HELLO de {peer.address}: {msg_type}")

                sock.settimeout(None)
                conn = PeerConnection(
                    sock,
                    peer.address,
                    on_frame=lambda c, mt, rid, h, p, ps=peer: self._on_peer_frame(ps, c, mt, rid, h, p),
                    on_close=lambda c, ps=peer: self._on_peer_close(ps, c),
                )
                conn.remote_node_id = str(ack.get("node_id") or peer.address)
                conn.remote_capabilities = tuple(ack.get("capabilities") or ())
                peer.node_id = conn.remote_node_id
                peer.capabilities = conn.remote_capabilities
                peer.device = str(ack.get("device", "CPU"))
                peer.omp_threads = int(ack.get("omp_threads", 1))
                peer.inflight = int(ack.get("inflight", 0))
                peer.last_rtt_ms = rtt_ms
                peer.healthy = True
                peer.cooldown_until = 0.0
                peer.conn = conn
                conn.start()
                logger.info(
                    "Conectado ao nó P2P %s (%s) — caps=%s, device=%s, rtt=%.2fms",
                    peer.node_id, peer.address, peer.capabilities, peer.device, rtt_ms,
                )
                return conn
            except OSError as exc:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                peer.healthy = False
                peer.conn = None
                peer.cooldown_until = time.monotonic() + self.cooldown_seconds
                logger.debug("Par P2P indisponível (%s): %s", peer.address, exc)
                return None

    def mark_failed(self, peer: PeerState) -> None:
        peer.healthy = False
        peer.cooldown_until = time.monotonic() + self.cooldown_seconds
        if peer.conn is not None:
            peer.conn.close()

    def connect_all(self, *, force: bool = False) -> list[PeerState]:
        active = []
        for peer in self._peers.values():
            if self.ensure_connected(peer, force=force) is not None:
                active.append(peer)
        return active

    def select_peer(self, capability: str) -> PeerState | None:
        """Escolhe o par saudável com menor carga em voo (GPU tem prioridade em empate)."""
        candidates: list[PeerState] = []
        for peer in self._peers.values():
            conn = self.ensure_connected(peer)
            if conn is not None and capability in peer.capabilities:
                candidates.append(peer)
        if not candidates:
            return None
        # Prioriza menor inflight; em empate, prefere nó CUDA e menor RTT.
        candidates.sort(key=lambda p: (p.inflight, 0 if p.device == "CUDA" else 1, p.last_rtt_ms))
        return candidates[0]

    def plan_segmentation_assignment(
        self,
        stages: tuple[str, ...] = ("bisenet", "acne", "vitiligo", "barba"),
    ) -> tuple[list[tuple[PeerState, list[str]]], list[str]]:
        """Agrupa estágios por par P2P para enviar o recorte RGB uma única vez por nó."""
        grouped: dict[str, tuple[PeerState, list[str]]] = {}
        unassigned: list[str] = []
        temp_load: dict[str, int] = {}

        for stage in stages:
            candidates: list[PeerState] = []
            for peer in self._peers.values():
                if self.ensure_connected(peer) is not None and stage in peer.capabilities:
                    candidates.append(peer)
            if not candidates:
                unassigned.append(stage)
                continue
            candidates.sort(
                key=lambda p: (
                    p.inflight + temp_load.get(p.address, 0),
                    0 if p.device == "CUDA" else 1,
                    p.last_rtt_ms,
                )
            )
            chosen = candidates[0]
            # Se um nó GPU possui múltiplas capacidades, concentrar no mesmo batch evita múltiplos envios LAN.
            if chosen.device == "CUDA":
                temp_load[chosen.address] = temp_load.get(chosen.address, 0)
            else:
                temp_load[chosen.address] = temp_load.get(chosen.address, 0) + 1

            if chosen.address not in grouped:
                grouped[chosen.address] = (chosen, [])
            grouped[chosen.address][1].append(stage)

        return list(grouped.values()), unassigned

    def snapshot(self, *, probe: bool = False) -> list[dict]:
        rows = []
        for peer in self._peers.values():
            if probe:
                conn = self.ensure_connected(peer)
                if conn is not None:
                    try:
                        conn.send(MSG_PING, {"sent_ns": time.perf_counter_ns()})
                    except ConnectionError:
                        pass
            rows.append({
                "address": peer.address,
                "node_id": peer.node_id or None,
                "healthy": peer.healthy and peer.conn is not None and not peer.conn.is_closed,
                "capabilities": list(peer.capabilities),
                "device": peer.device,
                "omp_threads": peer.omp_threads,
                "inflight": peer.inflight,
                "rtt_ms": round(peer.last_rtt_ms, 2),
            })
        return rows

    def close(self) -> None:
        self._closed.set()
        for peer in self._peers.values():
            if peer.conn is not None:
                peer.conn.close()
                peer.conn = None
