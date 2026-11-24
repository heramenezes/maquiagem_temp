"""Codificação binária compacta e sem perdas para matrizes RGB e máscaras bool.

Não utiliza pickle: todos os metadados são JSON UTF-8 e os buffers binários usam
bytes uint8 contíguos ou np.packbits comprimidos com zlib nível 1, garantindo
compatibilidade entre Linux/Windows e versões diferentes de Python (ex.: 3.12 e 3.14).
"""

import struct
import zlib

import numpy as np

from ..skin_selection.contracts import ModuleResult

_MASK_ALL_FALSE = 0
_MASK_ALL_TRUE = 1
_MASK_PACKBITS_ZLIB = 2


def encode_rgb(rgb: np.ndarray) -> tuple[dict, bytes]:
    """Serializa imagem RGB uint8 (H, W, 3) sem perdas."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.size == 0:
        raise ValueError("encode_rgb requer array RGB uint8 (H, W, 3) não vazio.")
    contiguous = np.ascontiguousarray(rgb, dtype=np.uint8)
    compressed = zlib.compress(memoryview(contiguous).cast("B"), level=1)
    return {"shape": list(contiguous.shape), "codec": "rgb_u8_zlib1"}, compressed


def decode_rgb(meta: dict, payload: bytes) -> np.ndarray:
    """Reconstrói array RGB uint8 (H, W, 3) preservando valores exatos."""
    shape = tuple(int(v) for v in meta["shape"])
    if len(shape) != 3 or shape[2] != 3 or min(shape) <= 0:
        raise ValueError("Shape RGB inválido no payload.")
    expected_bytes = shape[0] * shape[1] * 3
    raw = zlib.decompress(payload, bufsize=expected_bytes)
    if len(raw) != expected_bytes:
        raise ValueError("Tamanho de buffer RGB inconsistente após descompressão.")
    return np.frombuffer(raw, dtype=np.uint8).reshape(shape).copy()


def encode_bool_mask(mask: np.ndarray) -> bytes:
    """Compacta máscara bool (H, W) em 1 byte (vazia/cheia) ou packbits+zlib."""
    if mask.dtype != bool or mask.ndim != 2:
        raise ValueError("encode_bool_mask requer máscara bool 2D.")
    if not mask.any():
        return bytes((_MASK_ALL_FALSE,))
    if mask.all():
        return bytes((_MASK_ALL_TRUE,))
    packed = np.packbits(np.ascontiguousarray(mask).reshape(-1))
    return bytes((_MASK_PACKBITS_ZLIB,)) + zlib.compress(packed.tobytes(), level=1)


def decode_bool_mask(data: bytes, shape: tuple[int, int]) -> np.ndarray:
    """Reconstrói máscara bool (H, W) a partir de bytes compactados."""
    h, w = int(shape[0]), int(shape[1])
    if not data or h <= 0 or w <= 0:
        raise ValueError("Dados ou shape inválidos para máscara bool.")
    tag = data[0]
    if tag == _MASK_ALL_FALSE:
        return np.zeros((h, w), dtype=bool)
    if tag == _MASK_ALL_TRUE:
        return np.ones((h, w), dtype=bool)
    if tag != _MASK_PACKBITS_ZLIB:
        raise ValueError(f"Tag de máscara desconhecida: {tag}")
    total_bits = h * w
    packed_len = (total_bits + 7) // 8
    raw = zlib.decompress(data[1:], bufsize=packed_len)
    if len(raw) != packed_len:
        raise ValueError("Tamanho de packbits inválido após descompressão.")
    packed = np.frombuffer(raw, dtype=np.uint8)
    return np.unpackbits(packed, count=total_bits).reshape((h, w)).astype(bool)


def encode_uint8_2d(values: np.ndarray) -> bytes:
    if values.dtype != np.uint8 or values.ndim != 2:
        raise ValueError("Esperado array uint8 2D.")
    return zlib.compress(memoryview(np.ascontiguousarray(values)).cast("B"), level=1)


def decode_uint8_2d(data: bytes, shape: tuple[int, int]) -> np.ndarray:
    h, w = int(shape[0]), int(shape[1])
    expected = h * w
    raw = zlib.decompress(data, bufsize=expected)
    if len(raw) != expected:
        raise ValueError("Tamanho de mapa uint8 inválido.")
    return np.frombuffer(raw, dtype=np.uint8).reshape((h, w)).copy()


def _pack_chunks(chunks: list[bytes]) -> bytes:
    parts = [struct.pack("!I", len(chunks))]
    for chunk in chunks:
        parts.append(struct.pack("!I", len(chunk)))
        parts.append(chunk)
    return b"".join(parts)


def _unpack_chunks(blob: bytes) -> list[bytes]:
    if len(blob) < 4:
        raise ValueError("Blob multiplexado truncado.")
    (count,) = struct.unpack_from("!I", blob, 0)
    offset = 4
    chunks = []
    for _ in range(count):
        if offset + 4 > len(blob):
            raise ValueError("Cabeçalho de chunk truncado.")
        (size,) = struct.unpack_from("!I", blob, offset)
        offset += 4
        if offset + size > len(blob):
            raise ValueError("Conteúdo de chunk truncado.")
        chunks.append(blob[offset:offset + size])
        offset += size
    if offset != len(blob):
        raise ValueError("Bytes excedentes no blob multiplexado.")
    return chunks


def encode_anatomy(anatomy: dict) -> tuple[dict, bytes]:
    """Serializa saída de facial_masks / fallback_facial_masks."""
    allowed = anatomy["allowed"]
    face = anatomy["face"]
    seeds = anatomy.get("seeds", allowed)
    shape = list(allowed.shape)
    chunks = [
        encode_bool_mask(face),
        encode_bool_mask(allowed),
        encode_bool_mask(seeds),
    ]
    has_labels = "labels" in anatomy and anatomy["labels"] is not None
    if has_labels:
        chunks.append(encode_uint8_2d(anatomy["labels"]))
    meta = {
        "kind": "anatomy",
        "shape": shape,
        "has_labels": has_labels,
        "method": anatomy.get("method"),
        "model": anatomy.get("model"),
        "warnings": list(anatomy.get("warnings", [])),
        "quality_reasons": list(anatomy.get("quality_reasons", [])),
    }
    return meta, _pack_chunks(chunks)


def decode_anatomy(meta: dict, blob: bytes) -> dict:
    shape = (int(meta["shape"][0]), int(meta["shape"][1]))
    chunks = _unpack_chunks(blob)
    expected = 4 if meta.get("has_labels") else 3
    if len(chunks) != expected:
        raise ValueError("Contagem de chunks inválida para anatomia.")
    result = {
        "face": decode_bool_mask(chunks[0], shape),
        "allowed": decode_bool_mask(chunks[1], shape),
        "seeds": decode_bool_mask(chunks[2], shape),
        "method": meta.get("method"),
        "model": meta.get("model"),
        "warnings": list(meta.get("warnings", [])),
    }
    if meta.get("quality_reasons"):
        result["quality_reasons"] = list(meta["quality_reasons"])
    if meta.get("has_labels"):
        result["labels"] = decode_uint8_2d(chunks[3], shape)
    return result


def encode_module_result(key: str, result: ModuleResult) -> tuple[dict, bytes]:
    """Serializa ModuleResult (accepted, uncertain, debug_masks e metadados)."""
    shape = list(result.accepted.shape)
    debug_keys = sorted(result.debug_masks.keys())
    chunks = [
        encode_bool_mask(result.accepted),
        encode_bool_mask(result.uncertain),
        *(encode_bool_mask(result.debug_masks[k]) for k in debug_keys),
    ]
    meta = {
        "kind": "module",
        "key": key,
        "shape": shape,
        "status": result.status,
        "source": result.source,
        "reason": result.reason,
        "version": result.version,
        "evidence": result.evidence,
        "debug_keys": debug_keys,
        "elapsed_ms": float(result.elapsed_ms),
    }
    return meta, _pack_chunks(chunks)


def decode_module_result(meta: dict, blob: bytes) -> tuple[str, ModuleResult]:
    shape = (int(meta["shape"][0]), int(meta["shape"][1]))
    debug_keys = list(meta.get("debug_keys", []))
    chunks = _unpack_chunks(blob)
    if len(chunks) != 2 + len(debug_keys):
        raise ValueError("Contagem de chunks inválida para ModuleResult.")
    accepted = decode_bool_mask(chunks[0], shape)
    uncertain = decode_bool_mask(chunks[1], shape)
    debug_masks = {k: decode_bool_mask(chunks[2 + idx], shape) for idx, k in enumerate(debug_keys)}
    mod = ModuleResult(
        accepted=accepted,
        uncertain=uncertain,
        status=meta["status"],
        source=meta.get("source", ""),
        reason=meta.get("reason"),
        version=dict(meta.get("version") or {}),
        evidence=dict(meta.get("evidence") or {}),
        debug_masks=debug_masks,
        elapsed_ms=float(meta.get("elapsed_ms", 0.0)),
    )
    mod.validate(shape)
    return str(meta["key"]), mod
