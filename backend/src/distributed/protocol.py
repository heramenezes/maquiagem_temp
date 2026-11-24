"""Protocolo binário P2P persistente sobre TCP, seguro contra endianness e sem pickle.

Formato do quadro (network byte-order, 30 bytes fixos de cabeçalho):
    [4B Magic b"MTOM"][1B Version=1][1B MsgType][16B ReqUUID][4B HeaderLen][4B PayloadLen]
    seguido de Header JSON UTF-8 e Payload binário opcional (até MAX_FRAME_BYTES).

Todos os sockets usam TCP_NODELAY=1 para evitar atraso de Nagle (~40 ms) no envio
de máscaras compactas (~2 KB) e confirmações de etapa (~100 B).
"""

import hashlib
import hmac
import json
import logging
import os
import socket
import struct
import threading
import uuid

logger = logging.getLogger(__name__)

MAGIC = b"MTOM"
PROTOCOL_VERSION = 1
HEADER_STRUCT = struct.Struct("!4sBB16sII")
MAX_HEADER_BYTES = 2 * 1024 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024

# Tipos de mensagem P2P
MSG_HELLO = 1          # Handshake / capacidades / autenticação / assinatura de peer
MSG_HELLO_ACK = 2      # Confirmação de handshake e metadados do nó
MSG_PING = 3           # Heartbeat
MSG_PONG = 4           # Resposta de heartbeat com carga ativa
MSG_SUBMIT_BATCH = 10  # Envio único de recorte RGB para 1..N estágios de visão
MSG_STAGE_EVENT = 11   # Evento leve de conclusão/estado de etapa para o Gateway
MSG_STAGE_DATA = 12    # Transferência direta P2P de máscara/anatomia para o próximo nó
MSG_COLOR_INIT = 13    # Inicialização de contexto de cor (RGB -> Lab + medição + match)
MSG_COLOR_RESULT = 14  # Resultado final v3 calculado pelo nó de cor/match
MSG_CANCEL = 15        # Cancelamento imediato e limpeza de buffers em RAM
MSG_ERROR = 99         # Erro explícito de protocolo/execução


class ProtocolError(RuntimeError):
    pass


def configure_socket(sock: socket.socket) -> None:
    """Desativa algoritmo de Nagle e ativa keep-alive em conexões P2P."""
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass


def compute_auth_tag(secret: str, nonce: str, node_id: str) -> str:
    msg = f"{nonce}:{node_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _recv_exact(sock: socket.socket, length: int) -> bytes:
    if length == 0:
        return b""
    buf = bytearray(length)
    view = memoryview(buf)
    pos = 0
    while pos < length:
        chunk_len = sock.recv_into(view[pos:], length - pos)
        if chunk_len == 0:
            raise EOFError("Conexão P2P encerrada pelo par remoto.")
        pos += chunk_len
    return bytes(buf)


def send_frame(
    sock: socket.socket,
    msg_type: int,
    header: dict,
    payload: bytes = b"",
    *,
    req_id: uuid.UUID | bytes | str | None = None,
    write_lock: threading.Lock | None = None,
) -> None:
    if req_id is None:
        req_bytes = b"\x00" * 16
    elif isinstance(req_id, uuid.UUID):
        req_bytes = req_id.bytes
    elif isinstance(req_id, str):
        req_bytes = uuid.UUID(req_id).bytes
    elif isinstance(req_id, (bytes, bytearray)) and len(req_id) == 16:
        req_bytes = bytes(req_id)
    else:
        raise ValueError("req_id deve ser UUID, hex string, 16 bytes ou None.")

    header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(header_bytes) > MAX_HEADER_BYTES:
        raise ProtocolError("Cabeçalho JSON excede limite seguro do protocolo.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError("Payload binário excede limite seguro do protocolo.")

    prefix = HEADER_STRUCT.pack(
        MAGIC,
        PROTOCOL_VERSION,
        int(msg_type),
        req_bytes,
        len(header_bytes),
        len(payload),
    )
    if write_lock is not None:
        with write_lock:
            sock.sendall(prefix + header_bytes)
            if payload:
                sock.sendall(payload)
    else:
        sock.sendall(prefix + header_bytes)
        if payload:
            sock.sendall(payload)


def recv_frame(sock: socket.socket) -> tuple[int, str | None, dict, bytes]:
    prefix = _recv_exact(sock, HEADER_STRUCT.size)
    magic, version, msg_type, req_bytes, header_len, payload_len = HEADER_STRUCT.unpack(prefix)
    if magic != MAGIC:
        raise ProtocolError("Magic inválido no quadro P2P.")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Versão de protocolo P2P incompatível: {version}.")
    if header_len > MAX_HEADER_BYTES or payload_len > MAX_PAYLOAD_BYTES:
        raise ProtocolError("Quadro P2P excede limites máximos de memória.")

    header_raw = _recv_exact(sock, header_len)
    payload = _recv_exact(sock, payload_len)
    try:
        header = json.loads(header_raw.decode("utf-8")) if header_len else {}
    except (UnicodeDecodeError, ValueError) as exc:
        raise ProtocolError("Cabeçalho JSON inválido no quadro P2P.") from exc

    req_id = None if req_bytes == b"\x00" * 16 else str(uuid.UUID(bytes=req_bytes))
    return msg_type, req_id, header, payload


class PeerConnection:
    """Conexão TCP bidirecional multiplexada com escrita thread-safe e despacho de quadros."""

    def __init__(
        self,
        sock: socket.socket,
        peer_addr: str,
        on_frame,
        on_close=None,
    ):
        configure_socket(sock)
        self.sock = sock
        self.peer_addr = peer_addr
        self._on_frame = on_frame
        self._on_close = on_close
        self._write_lock = threading.Lock()
        self._closed = threading.Event()
        self.remote_node_id: str | None = None
        self.remote_capabilities: tuple[str, ...] = ()
        self._reader = threading.Thread(
            target=self._read_loop,
            name=f"p2p-reader-{peer_addr}",
            daemon=True,
        )

    def start(self) -> None:
        self._reader.start()

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    def send(self, msg_type: int, header: dict, payload: bytes = b"", *, req_id=None) -> None:
        if self._closed.is_set():
            raise ConnectionError(f"Conexão P2P já encerrada ({self.peer_addr}).")
        try:
            send_frame(self.sock, msg_type, header, payload, req_id=req_id, write_lock=self._write_lock)
        except OSError as exc:
            self.close()
            raise ConnectionError(f"Falha de envio P2P para {self.peer_addr}: {exc}") from exc

    def _read_loop(self) -> None:
        try:
            while not self._closed.is_set():
                msg_type, req_id, header, payload = recv_frame(self.sock)
                self._on_frame(self, msg_type, req_id, header, payload)
        except EOFError:
            pass
        except OSError:
            if not self._closed.is_set():
                logger.debug("Socket P2P encerrado (%s).", self.peer_addr)
        except Exception:
            logger.exception("Erro inesperado lendo quadro P2P de %s", self.peer_addr)
        finally:
            self.close()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        if self._on_close is not None:
            try:
                self._on_close(self)
            except Exception:
                pass


def parse_host_port(address: str) -> tuple[str, int]:
    text = address.strip()
    if text.startswith("["):
        # IPv6 [::1]:7100
        end = text.find("]")
        if end == -1 or end + 2 > len(text) or text[end + 1] != ":":
            raise ValueError(f"Endereço IPv6 inválido: {address!r}")
        return text[1:end], int(text[end + 2:])
    host, sep, port_str = text.rpartition(":")
    if not sep or not host:
        raise ValueError(f"Esperado formato host:porta, recebido: {address!r}")
    port = int(port_str)
    if not (0 <= port <= 65535):
        raise ValueError(f"Porta fora do intervalo: {port}")
    return host, port


def cluster_secret() -> str:
    return os.environ.get("MAQUIAGEM_CLUSTER_TOKEN", "")
