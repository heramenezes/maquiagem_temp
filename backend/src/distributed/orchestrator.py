"""Orquestradores local paralelo (DAG) e distribuído P2P para o pipeline de análise.

Garantias de compatibilidade com o pipeline existente:
  1. A pré-verificação `rosto` ocorre sempre antes de qualquer despacho local ou de rede:
     zero/múltiplos rostos abortam com 422 sem executar `rgb_to_lab` nem trafegar dados.
  2. Os 20 eventos incrementais NDJSON (`concluidas` 0..10) são emitidos exatamente na
     mesma ordem monotônica esperada pelo frontend (`processing.js`) e `test_api.py`.
  3. No modo padrão (`LocalParallelExecutor`), `cielab`, `mascara`, `acne`, `vitiligo`
     e `barba` executam simultaneamente em threads, respeitando mocks em `pipeline.py`.
  4. No modo `DistributedExecutor`, o recorte RGB é enviado uma única vez por nó P2P e
     as máscaras fluem diretamente dos nós de segmentação ao nó `color_match` (quando ativo),
     com cancelamento imediato na desconexão do cliente e fallback configurável.
"""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
import logging
import os
import threading
from time import perf_counter
import uuid

import cv2
import numpy as np

from .codec import decode_anatomy, decode_module_result, encode_bool_mask, encode_rgb
from .metrics import build_performance_metrics, measure_numpy_cielab_reference_ms
from .native import omp_info
from .protocol import (
    MSG_CANCEL,
    MSG_COLOR_INIT,
    MSG_COLOR_RESULT,
    MSG_ERROR,
    MSG_STAGE_DATA,
    MSG_STAGE_EVENT,
    MSG_SUBMIT_BATCH,
    PeerConnection,
)
from .registry import PeerRegistry, PeerState, parse_peer_specs
from ..skin_selection.contracts import CATEGORIES, ModuleResult

logger = logging.getLogger(__name__)


def _compute_clusters_local(rgb: np.ndarray, lab: np.ndarray, masks: dict, adaptive_clusters_fn) -> dict:
    factor = min(1, 512 / max(rgb.shape[:2]))
    size = (max(1, round(rgb.shape[1] * factor)), max(1, round(rgb.shape[0] * factor)))
    small_lab = cv2.resize(lab, size, interpolation=cv2.INTER_AREA)
    small_mask = cv2.resize(masks["allowed"].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    return adaptive_clusters_fn(small_lab, {"allowed": small_mask, "seeds": small_mask}) if small_mask.sum() >= 64 else {"k": None}


def _call_build_analysis(build_analysis_fn, skin, selection, face_pixels: int, lab: np.ndarray, rgb: np.ndarray):
    try:
        return build_analysis_fn(skin, selection, face_pixels, lab_image=lab, rgb_image=rgb)
    except TypeError:
        return build_analysis_fn(skin, selection, face_pixels)


def _timed(fn, *args, **kwargs):
    t0 = perf_counter()
    value = fn(*args, **kwargs)
    return value, (perf_counter() - t0) * 1000.0, perf_counter()


class LocalParallelExecutor:
    """Executa estágios independentes simultaneamente no processo local."""

    mode = "local"

    def __init__(self, *, max_workers: int = 5):
        self.max_workers = max_workers

    def status(self) -> dict:
        return {
            "mode": "local",
            "max_workers": self.max_workers,
            "openmp": omp_info(),
            "peers": [],
        }

    def run_after_crop(
        self,
        rgb: np.ndarray,
        steps: list[dict],
        *,
        hooks: dict,
        rosto_ms: float = 0.0,
    ):
        """Gera eventos `etapa` para índices 1..9 e retorna o dicionário final `result`."""
        rgb_to_lab_fn = hooks["rgb_to_lab"]
        facial_masks_fn = hooks["facial_masks"]
        fallback_masks_fn = hooks["fallback_facial_masks"]
        model_unavailable_cls = hooks["ModelUnavailableError"]
        run_module_fn = hooks["run_module"]
        finish_fn = hooks["finish"]
        adaptive_clusters_fn = hooks["adaptive_clusters"]
        measure_skin_fn = hooks["measure_skin"]
        build_analysis_fn = hooks["build_analysis"]
        conditions_fn = hooks["conditions"]
        summarize_fn = hooks["summarize"]

        def _safe_anatomy():
            try:
                m = facial_masks_fn(rgb)
            except model_unavailable_cls:
                m = fallback_masks_fn(rgb, "segmentacao_indisponivel")
            if not m["allowed"].any():
                m = fallback_masks_fn(rgb, "pele_nao_segmentada")
            return m

        dummy_anatomy = {"allowed": np.ones(rgb.shape[:2], dtype=bool)}
        pool = ThreadPoolExecutor(max_workers=self.max_workers + 1, thread_name_prefix="local-dag")
        futures: dict[str, Future] = {}
        stage_ms: dict[str, float] = {"rosto": float(rosto_ms)}
        omp_info()  # Garante que o carregamento único da biblioteca C não contamine o tempo de cielab.
        try:
            fanout_t0 = perf_counter()
            # Despacha imediatamente todas as tarefas que dependem apenas do recorte RGB.
            futures["cielab"] = pool.submit(_timed, rgb_to_lab_fn, rgb)
            futures["cielab_seq_ref"] = pool.submit(measure_numpy_cielab_reference_ms, rgb)
            futures["mascara"] = pool.submit(_timed, _safe_anatomy)
            for key in CATEGORIES:
                futures[key] = pool.submit(_timed, run_module_fn, key, rgb, dummy_anatomy)

            lab = masks = selection = clusters = skin = result = None
            modules: dict[str, ModuleResult] = {}
            fanout_end_timestamps: list[float] = []
            post_wall_ms = 0.0

            for index in range(1, len(steps)):
                step = steps[index]
                sid = step["id"]
                step["estado"] = "processando"
                yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
                       "concluidas": index, "total": len(steps)}

                if sid == "cielab":
                    lab, stage_ms["cielab"], t_done = futures["cielab"].result()
                    fanout_end_timestamps.append(t_done)
                elif sid == "mascara":
                    masks, stage_ms["mascara"], t_done = futures["mascara"].result()
                    fanout_end_timestamps.append(t_done)
                    # Assim que lab e máscara anatômica existem, agenda K-means em paralelo aos especialistas restantes.
                    futures["clusters"] = pool.submit(_timed, _compute_clusters_local, rgb, lab, masks, adaptive_clusters_fn)
                elif sid in CATEGORIES:
                    mod_val, wall_mod_ms, t_done = futures[sid].result()
                    modules[sid] = mod_val
                    stage_ms[sid] = float(mod_val.elapsed_ms) if mod_val.elapsed_ms > 0 else wall_mod_ms
                    fanout_end_timestamps.append(t_done)
                    step["estado_modulo"] = modules[sid].status
                elif sid == "selecao":
                    t0 = perf_counter()
                    selection = finish_fn(rgb, lab, masks, modules)
                    dt = (perf_counter() - t0) * 1000.0
                    stage_ms["selecao"] = dt
                    post_wall_ms += dt
                elif sid == "clusters":
                    t_wait0 = perf_counter()
                    clusters, stage_ms["clusters"], _ = futures["clusters"].result()
                    post_wall_ms += (perf_counter() - t_wait0) * 1000.0
                elif sid == "medidas":
                    t0 = perf_counter()
                    skin = measure_skin_fn(lab, selection["measurement_mask"], rgb=rgb, face_mask=masks["face"])
                    dt = (perf_counter() - t0) * 1000.0
                    stage_ms["medidas"] = dt
                    post_wall_ms += dt
                elif sid == "resultado":
                    t0 = perf_counter()
                    result = _call_build_analysis(build_analysis_fn, skin, selection, int(masks["face"].sum()), lab, rgb)
                    result["condicoes"] = conditions_fn(selection)
                    result["marcacoes"] = []
                    result["preprocessamento"] = summarize_fn(rgb, masks, clusters, skin, selection)
                    result["status_analise"] = "concluida"
                    dt = (perf_counter() - t0) * 1000.0
                    stage_ms["resultado"] = dt
                    post_wall_ms += dt

                    fanout_wall_ms = (max(fanout_end_timestamps) - fanout_t0) * 1000.0 if fanout_end_timestamps else 0.0
                    total_wall_ms = float(rosto_ms) + fanout_wall_ms + post_wall_ms
                    omp = omp_info()
                    result["desempenho"] = build_performance_metrics(
                        mode="paralelo_local",
                        rgb=rgb,
                        selection=selection,
                        rosto_ms=rosto_ms,
                        total_wall_ms=total_wall_ms,
                        fanout_wall_ms=fanout_wall_ms,
                        stage_times_ms=stage_ms,
                        cielab_numpy_seq_ms=futures["cielab_seq_ref"].result(),
                        active_nodes=[{
                            "id": "local-dag",
                            "papel": "Pipeline completo (threads + OpenMP)",
                            "dispositivo": "CPU-OMP" if omp.get("openmp") else "CPU",
                            "threads_omp": omp.get("max_threads", 1),
                        }],
                    )

                step["estado"] = "concluida"
                yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
                       "concluidas": index + 1, "total": len(steps)}

            return result
        finally:
            for fut in futures.values():
                fut.cancel()
            pool.shutdown(wait=False, cancel_futures=True)


@dataclass
class _RemoteRequestTracker:
    req_id: str
    cond: threading.Condition = field(default_factory=threading.Condition)
    stage_events: dict[str, dict] = field(default_factory=dict)
    anatomy: dict | None = None
    modules: dict[str, ModuleResult] = field(default_factory=dict)
    color_result: dict | None = None
    color_meta: dict = field(default_factory=dict)
    color_conn: PeerConnection | None = None
    event_timestamps: dict[str, float] = field(default_factory=dict)
    mask_wire_bytes: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    involved_peers: set[str] = field(default_factory=set)
    closed_peers: set[str] = field(default_factory=set)


class DistributedExecutor:
    """Orquestrador P2P entre processos/máquinas com encaminhamento direto entre estágios."""

    mode = "distributed"

    def __init__(
        self,
        peer_addresses: str | list[str],
        *,
        fallback_policy: str = "local",
        stage_timeout: float = 25.0,
        connect_timeout: float = 2.5,
    ):
        if fallback_policy not in {"local", "degrade"}:
            raise ValueError("fallback_policy deve ser 'local' ou 'degrade'.")
        self.fallback_policy = fallback_policy
        self.stage_timeout = stage_timeout
        self._lock = threading.Lock()
        self._requests: dict[str, _RemoteRequestTracker] = {}
        self.registry = PeerRegistry(
            parse_peer_specs(peer_addresses),
            on_Async_frame=self._on_peer_frame,
            connect_timeout=connect_timeout,
        )

    def status(self, *, probe: bool = False) -> dict:
        return {
            "mode": "distributed",
            "fallback_policy": self.fallback_policy,
            "openmp": omp_info(),
            "peers": self.registry.snapshot(probe=probe),
        }

    def close(self) -> None:
        self.registry.close()

    def _on_peer_frame(
        self,
        peer: PeerState,
        _conn: PeerConnection,
        msg_type: int,
        req_id: str | None,
        header: dict,
        payload: bytes,
    ) -> None:
        if not req_id:
            return
        with self._lock:
            tracker = self._requests.get(req_id)
        if tracker is None:
            return

        if msg_type == MSG_STAGE_EVENT:
            stage = str(header.get("stage", ""))
            with tracker.cond:
                tracker.stage_events[stage] = header
                tracker.event_timestamps[stage] = perf_counter()
                tracker.cond.notify_all()
        elif msg_type == MSG_STAGE_DATA:
            try:
                # Se um nó remoto não pôde enviar diretamente ao nó `color_match` local (ex.: NAT/firewall),
                # o Gateway retransmite o quadro binário imediatamente via loopback para `color_conn`.
                if tracker.color_conn is not None and not tracker.color_conn.is_closed:
                    try:
                        tracker.color_conn.send(MSG_STAGE_DATA, header, payload, req_id=req_id)
                    except ConnectionError:
                        pass
                kind = header.get("kind")
                if kind == "anatomy":
                    anat = decode_anatomy(header, payload)
                    with tracker.cond:
                        tracker.anatomy = anat
                        tracker.mask_wire_bytes += len(payload)
                        tracker.stage_events.setdefault("mascara", {"stage": "mascara"})
                        tracker.event_timestamps.setdefault("mascara", perf_counter())
                        tracker.cond.notify_all()
                elif kind == "module":
                    mkey, mres = decode_module_result(header, payload)
                    with tracker.cond:
                        tracker.modules[mkey] = mres
                        tracker.mask_wire_bytes += len(payload)
                        tracker.stage_events.setdefault(mkey, {"stage": mkey, "module_status": mres.status})
                        tracker.event_timestamps.setdefault(mkey, perf_counter())
                        tracker.cond.notify_all()
            except Exception as exc:
                with tracker.cond:
                    tracker.errors["stage_data"] = str(exc)
                    tracker.cond.notify_all()
        elif msg_type == MSG_COLOR_RESULT:
            with tracker.cond:
                tracker.color_result = header.get("result")
                tracker.color_meta = {
                    "node_id": header.get("node_id"),
                    "device": header.get("device"),
                    "timings_ms": dict(header.get("timings_ms") or {}),
                    "mask_wire_bytes": int(header.get("mask_wire_bytes") or 0),
                }
                tracker.stage_events.setdefault("resultado", {"stage": "resultado"})
                tracker.event_timestamps["resultado"] = perf_counter()
                tracker.cond.notify_all()
        elif msg_type == MSG_ERROR:
            stage = str(header.get("stage", "remote"))
            with tracker.cond:
                tracker.errors[stage] = str(header.get("message", "Erro remoto no par P2P"))
                tracker.cond.notify_all()

    def _wait_condition(self, tracker: _RemoteRequestTracker, predicate) -> bool:
        with tracker.cond:
            return tracker.cond.wait_for(predicate, timeout=self.stage_timeout)

    def _fallback_specialist(self, key: str, rgb: np.ndarray, hooks: dict) -> ModuleResult:
        if self.fallback_policy == "local":
            dummy_anatomy = {"allowed": np.ones(rgb.shape[:2], dtype=bool)}
            return hooks["run_module"](key, rgb, dummy_anatomy)
        from ..segmentation.model_asset import ASSETS
        return ModuleResult.empty(
            rgb.shape[:2],
            status="indisponivel",
            reason="no_remoto_indisponivel",
            source=key,
            version=ASSETS[key].metadata(),
        )

    def _fallback_anatomy(self, rgb: np.ndarray, hooks: dict) -> dict:
        if self.fallback_policy == "local":
            try:
                m = hooks["facial_masks"](rgb)
            except hooks["ModelUnavailableError"]:
                m = hooks["fallback_facial_masks"](rgb, "segmentacao_indisponivel")
            if not m["allowed"].any():
                m = hooks["fallback_facial_masks"](rgb, "pele_nao_segmentada")
            return m
        return hooks["fallback_facial_masks"](rgb, "segmentacao_indisponivel")

    def run_after_crop(
        self,
        rgb: np.ndarray,
        steps: list[dict],
        *,
        hooks: dict,
        rosto_ms: float = 0.0,
    ):
        req_id = str(uuid.uuid4())
        tracker = _RemoteRequestTracker(req_id=req_id)
        with self._lock:
            self._requests[req_id] = tracker

        local_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="dist-fallback")
        local_futures: dict[str, Future] = {}
        peer_increments: dict[str, tuple[PeerState, int]] = {}
        active_nodes: list[dict] = [{"id": "gateway", "papel": "Pré-verificação e streaming HTTP", "dispositivo": "CPU"}]
        stage_ms: dict[str, float] = {"rosto": float(rosto_ms)}
        completed_all = False

        def _add_inflight(peer: PeerState, amount: int) -> None:
            peer.inflight += amount
            prev = peer_increments.get(peer.address, (peer, 0))[1]
            peer_increments[peer.address] = (peer, prev + amount)

        try:
            omp_info()
            dist_t0 = perf_counter()
            rgb_meta, rgb_blob = encode_rgb(rgb)
            local_futures["cielab_seq_ref"] = local_pool.submit(measure_numpy_cielab_reference_ms, rgb)

            # 1. Verifica se há um nó remoto/processo dedicado `color_match` saudável (Estágio 3 P2P).
            color_peer = self.registry.select_peer("color_match")
            seg_assignment, unassigned_seg = self.registry.plan_segmentation_assignment(
                ("bisenet", "acne", "vitiligo", "barba")
            )

            use_remote_color = color_peer is not None and color_peer.conn is not None
            if use_remote_color:
                try:
                    _add_inflight(color_peer, 1)
                    tracker.color_conn = color_peer.conn
                    color_peer.conn.send(
                        MSG_COLOR_INIT,
                        {"rgb": rgb_meta, "expected_modules": list(CATEGORIES)},
                        rgb_blob,
                        req_id=req_id,
                    )
                    active_nodes.append({
                        "id": color_peer.node_id or color_peer.address,
                        "endereco": color_peer.address,
                        "papel": "CIELAB OpenMP + Qualidade + Match ΔE00",
                        "dispositivo": color_peer.device,
                    })
                except ConnectionError:
                    peer_increments.pop(color_peer.address, None)
                    color_peer.inflight = max(0, color_peer.inflight - 1)
                    self.registry.mark_failed(color_peer)
                    use_remote_color = False
                    color_peer = None

            if not use_remote_color:
                # Se não há nó `color_match` dedicado, calcula CIELAB localmente em paralelo.
                local_futures["cielab"] = local_pool.submit(_timed, hooks["rgb_to_lab"], rgb)

            # 2. Despacha cada lote de segmentação uma única vez por nó P2P!
            for seg_peer, peer_stages in seg_assignment:
                if seg_peer.conn is None:
                    unassigned_seg.extend(peer_stages)
                    continue
                try:
                    _add_inflight(seg_peer, len(peer_stages))
                    seg_is_loopback = seg_peer.address.startswith(("127.", "localhost:", "[::1]:"))
                    color_is_loopback = bool(
                        color_peer and color_peer.address.startswith(("127.", "localhost:", "[::1]:"))
                    )
                    # Nunca envia `forward_addr` 127.0.0.1 para outra máquina física na LAN.
                    can_direct_dial = use_remote_color and color_peer and (not color_is_loopback or seg_is_loopback)
                    seg_peer.conn.send(
                        MSG_SUBMIT_BATCH,
                        {
                            "rgb": rgb_meta,
                            "stages": peer_stages,
                            "forward_node_id": color_peer.node_id if use_remote_color and color_peer else None,
                            "forward_addr": color_peer.address if can_direct_dial else None,
                        },
                        rgb_blob,
                        req_id=req_id,
                    )
                    active_nodes.append({
                        "id": seg_peer.node_id or seg_peer.address,
                        "endereco": seg_peer.address,
                        "papel": ", ".join(peer_stages),
                        "dispositivo": seg_peer.device,
                    })
                except ConnectionError:
                    prev_inc = peer_increments.pop(seg_peer.address, (seg_peer, 0))[1]
                    seg_peer.inflight = max(0, seg_peer.inflight - prev_inc)
                    self.registry.mark_failed(seg_peer)
                    unassigned_seg.extend(peer_stages)

            # 3. Qualquer estágio sem par remoto saudável entra em fallback imediato em paralelo.
            if unassigned_seg:
                active_nodes.append({
                    "id": "gateway-fallback",
                    "papel": f"Fallback local ({', '.join(unassigned_seg)}) — sem par remoto com estes modelos",
                    "dispositivo": "CPU",
                })
            for stage in unassigned_seg:
                if stage == "bisenet":
                    local_futures["bisenet"] = local_pool.submit(_timed, self._fallback_anatomy, rgb, hooks)
                elif stage in CATEGORIES:
                    local_futures[stage] = local_pool.submit(_timed, self._fallback_specialist, stage, rgb, hooks)

            # Se `color_peer` está ativo e algum estágio rodou em fallback local, encaminha a máscara P2P a `color_peer`.
            if use_remote_color and color_peer and color_peer.conn is not None and (
                any(k in local_futures for k in ("bisenet", *CATEGORIES))
            ):
                from .codec import encode_anatomy as _enc_anat, encode_module_result as _enc_mod

                def _push_local_fallbacks():
                    for stg in ("bisenet", *CATEGORIES):
                        fut = local_futures.get(stg)
                        if fut is None:
                            continue
                        res, _, _ = fut.result()
                        if color_peer.conn is None or color_peer.conn.is_closed:
                            return
                        if stg == "bisenet":
                            m, b = _enc_anat(res)
                            color_peer.conn.send(MSG_STAGE_DATA, m, b, req_id=req_id)
                        elif stg in CATEGORIES:
                            m, b = _enc_mod(stg, res)
                            color_peer.conn.send(MSG_STAGE_DATA, m, b, req_id=req_id)

                local_pool.submit(_push_local_fallbacks)

            # 4. Percorre os estágios 1..9 emitindo eventos monotônicos conforme os nós concluem.
            lab = masks = selection = clusters = skin = final_result = None
            modules: dict[str, ModuleResult] = {}
            fanout_end_ts: list[float] = []
            local_post_wall_ms = 0.0

            for index in range(1, len(steps)):
                step = steps[index]
                sid = step["id"]
                step["estado"] = "processando"
                yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
                       "concluidas": index, "total": len(steps)}

                if sid == "cielab":
                    if use_remote_color:
                        ok = self._wait_condition(
                            tracker,
                            lambda: "cielab" in tracker.stage_events or tracker.color_result is not None or "color_match" in tracker.errors or "color_init" in tracker.errors,
                        )
                        if not ok or "color_match" in tracker.errors or "color_init" in tracker.errors:
                            use_remote_color = False
                            lab, stage_ms["cielab"], t_done = _timed(hooks["rgb_to_lab"], rgb)
                            fanout_end_ts.append(t_done)
                        else:
                            ev = tracker.stage_events.get("cielab", {})
                            stage_ms["cielab"] = float(ev.get("elapsed_ms", 0.5))
                            fanout_end_ts.append(tracker.event_timestamps.get("cielab", perf_counter()))
                    else:
                        lab, stage_ms["cielab"], t_done = local_futures["cielab"].result()
                        fanout_end_ts.append(t_done)

                elif sid == "mascara":
                    if "bisenet" in local_futures:
                        masks, stage_ms["mascara"], t_done = local_futures["bisenet"].result()
                        fanout_end_ts.append(t_done)
                    else:
                        ok = self._wait_condition(
                            tracker,
                            lambda: "mascara" in tracker.stage_events or tracker.anatomy is not None or "bisenet" in tracker.errors,
                        )
                        if not ok or "bisenet" in tracker.errors:
                            masks, stage_ms["mascara"], t_done = _timed(self._fallback_anatomy, rgb, hooks)
                            fanout_end_ts.append(t_done)
                            if use_remote_color and color_peer and color_peer.conn and not color_peer.conn.is_closed:
                                from .codec import encode_anatomy as _enc_anat
                                try:
                                    m, b = _enc_anat(masks)
                                    color_peer.conn.send(MSG_STAGE_DATA, m, b, req_id=req_id)
                                except ConnectionError:
                                    use_remote_color = False
                            else:
                                use_remote_color = False
                        else:
                            ev = tracker.stage_events.get("mascara", {})
                            stage_ms["mascara"] = float(ev.get("elapsed_ms", 1.0))
                            fanout_end_ts.append(tracker.event_timestamps.get("mascara", perf_counter()))
                            if not use_remote_color:
                                masks = tracker.anatomy if tracker.anatomy is not None else self._fallback_anatomy(rgb, hooks)
                    if not use_remote_color and lab is None:
                        lab, stage_ms["cielab"], _ = _timed(hooks["rgb_to_lab"], rgb)
                    if not use_remote_color and masks is not None:
                        local_futures["clusters"] = local_pool.submit(
                            _timed, _compute_clusters_local, rgb, lab, masks, hooks["adaptive_clusters"]
                        )

                elif sid in CATEGORIES:
                    if sid in local_futures:
                        mod_res, wall_mod_ms, t_done = local_futures[sid].result()
                        modules[sid] = mod_res
                        stage_ms[sid] = float(mod_res.elapsed_ms) if mod_res.elapsed_ms > 0 else wall_mod_ms
                        fanout_end_ts.append(t_done)
                        step["estado_modulo"] = mod_res.status
                    else:
                        ok = self._wait_condition(
                            tracker,
                            lambda k=sid: k in tracker.stage_events or k in tracker.modules or k in tracker.errors,
                        )
                        if not ok or sid in tracker.errors:
                            mod_res, wall_mod_ms, t_done = _timed(self._fallback_specialist, sid, rgb, hooks)
                            modules[sid] = mod_res
                            stage_ms[sid] = float(mod_res.elapsed_ms) if mod_res.elapsed_ms > 0 else wall_mod_ms
                            fanout_end_ts.append(t_done)
                            step["estado_modulo"] = mod_res.status
                            if use_remote_color and color_peer and color_peer.conn and not color_peer.conn.is_closed:
                                from .codec import encode_module_result as _enc_mod
                                try:
                                    m, b = _enc_mod(sid, mod_res)
                                    color_peer.conn.send(MSG_STAGE_DATA, m, b, req_id=req_id)
                                except ConnectionError:
                                    use_remote_color = False
                            else:
                                use_remote_color = False
                        else:
                            ev = tracker.stage_events.get(sid, {})
                            stage_ms[sid] = float(ev.get("elapsed_ms") or (tracker.modules[sid].elapsed_ms if sid in tracker.modules else 0.0))
                            fanout_end_ts.append(tracker.event_timestamps.get(sid, perf_counter()))
                            step["estado_modulo"] = ev.get("module_status") or (
                                tracker.modules[sid].status if sid in tracker.modules else "executado"
                            )
                            if not use_remote_color:
                                modules[sid] = tracker.modules.get(sid) or self._fallback_specialist(sid, rgb, hooks)

                elif sid == "selecao":
                    if use_remote_color:
                        ok = self._wait_condition(
                            tracker,
                            lambda: "selecao" in tracker.stage_events or tracker.color_result is not None or bool(tracker.errors),
                        )
                        if not ok or tracker.errors:
                            use_remote_color = False
                        else:
                            stage_ms["selecao"] = float(tracker.stage_events.get("selecao", {}).get("elapsed_ms", 0.5))
                    if not use_remote_color:
                        if lab is None:
                            lab, stage_ms["cielab"], _ = _timed(hooks["rgb_to_lab"], rgb)
                        if masks is None:
                            masks = tracker.anatomy or self._fallback_anatomy(rgb, hooks)
                        for k in CATEGORIES:
                            if k not in modules:
                                modules[k] = tracker.modules.get(k) or self._fallback_specialist(k, rgb, hooks)
                        t0 = perf_counter()
                        selection = hooks["finish"](rgb, lab, masks, modules)
                        dt = (perf_counter() - t0) * 1000.0
                        stage_ms["selecao"] = dt
                        local_post_wall_ms += dt

                elif sid == "clusters":
                    if use_remote_color:
                        ok = self._wait_condition(
                            tracker,
                            lambda: "clusters" in tracker.stage_events or tracker.color_result is not None or bool(tracker.errors),
                        )
                        if not ok or tracker.errors:
                            use_remote_color = False
                        else:
                            stage_ms["clusters"] = float(tracker.stage_events.get("clusters", {}).get("elapsed_ms", 0.5))
                    if not use_remote_color:
                        t_w0 = perf_counter()
                        if "clusters" in local_futures:
                            clusters, stage_ms["clusters"], _ = local_futures["clusters"].result()
                        else:
                            clusters, stage_ms["clusters"], _ = _timed(
                                _compute_clusters_local, rgb, lab, masks, hooks["adaptive_clusters"]
                            )
                        local_post_wall_ms += (perf_counter() - t_w0) * 1000.0

                elif sid == "medidas":
                    if use_remote_color:
                        ok = self._wait_condition(
                            tracker,
                            lambda: "medidas" in tracker.stage_events or tracker.color_result is not None or bool(tracker.errors),
                        )
                        if not ok or tracker.errors:
                            use_remote_color = False
                        else:
                            stage_ms["medidas"] = float(tracker.stage_events.get("medidas", {}).get("elapsed_ms", 0.5))
                    if not use_remote_color:
                        if selection is None:
                            selection = hooks["finish"](rgb, lab, masks, modules)
                        t0 = perf_counter()
                        skin = hooks["measure_skin"](lab, selection["measurement_mask"], rgb=rgb, face_mask=masks["face"])
                        dt = (perf_counter() - t0) * 1000.0
                        stage_ms["medidas"] = dt
                        local_post_wall_ms += dt

                elif sid == "resultado":
                    if use_remote_color:
                        ok = self._wait_condition(
                            tracker,
                            lambda: tracker.color_result is not None or bool(tracker.errors),
                        )
                        if ok and tracker.color_result is not None:
                            final_result = tracker.color_result
                            remote_timings = tracker.color_meta.get("timings_ms") or {}
                            for k_tm in ("cielab", "selecao", "clusters", "medidas", "resultado"):
                                if k_tm in remote_timings:
                                    stage_ms[k_tm] = float(remote_timings[k_tm])
                        else:
                            use_remote_color = False
                    if not use_remote_color:
                        t0 = perf_counter()
                        if lab is None:
                            lab, stage_ms["cielab"], _ = _timed(hooks["rgb_to_lab"], rgb)
                        if masks is None:
                            masks = tracker.anatomy or self._fallback_anatomy(rgb, hooks)
                        for k in CATEGORIES:
                            if k not in modules:
                                modules[k] = tracker.modules.get(k) or self._fallback_specialist(k, rgb, hooks)
                        if selection is None:
                            selection = hooks["finish"](rgb, lab, masks, modules)
                        if clusters is None:
                            clusters = _compute_clusters_local(rgb, lab, masks, hooks["adaptive_clusters"])
                        if skin is None:
                            skin = hooks["measure_skin"](lab, selection["measurement_mask"], rgb=rgb, face_mask=masks["face"])
                        final_result = _call_build_analysis(
                            hooks["build_analysis"], skin, selection, int(masks["face"].sum()), lab, rgb
                        )
                        final_result["condicoes"] = hooks["conditions"](selection)
                        final_result["marcacoes"] = []
                        final_result["preprocessamento"] = hooks["summarize"](rgb, masks, clusters, skin, selection)
                        final_result["status_analise"] = "concluida"
                        dt = (perf_counter() - t0) * 1000.0
                        stage_ms["resultado"] = dt
                        local_post_wall_ms += dt

                    fanout_wall_ms = (max(fanout_end_ts) - dist_t0) * 1000.0 if fanout_end_ts else 1.0
                    if use_remote_color:
                        end_res_ts = tracker.event_timestamps.get("resultado", perf_counter())
                        total_wall_ms = float(rosto_ms) + max(fanout_wall_ms, (end_res_ts - dist_t0) * 1000.0)
                        seq_np_ms = float(
                            (tracker.color_meta.get("timings_ms") or {}).get("cielab_numpy_seq")
                            or local_futures["cielab_seq_ref"].result()
                        )
                        mask_bytes = int(tracker.color_meta.get("mask_wire_bytes") or 0)
                        selection_for_perf = {
                            "anatomical_mask": np.zeros(rgb.shape[:2], bool),
                            "accepted_masks": {},
                        }
                    else:
                        total_wall_ms = float(rosto_ms) + fanout_wall_ms + local_post_wall_ms
                        seq_np_ms = local_futures["cielab_seq_ref"].result()
                        mask_bytes = tracker.mask_wire_bytes or None
                        selection_for_perf = selection

                    has_remote_peer = len(active_nodes) > 1
                    final_result["desempenho"] = build_performance_metrics(
                        mode="distribuido_p2p" if has_remote_peer else "paralelo_local",
                        rgb=rgb,
                        selection=selection_for_perf,
                        rosto_ms=rosto_ms,
                        total_wall_ms=total_wall_ms,
                        fanout_wall_ms=fanout_wall_ms,
                        stage_times_ms=stage_ms,
                        cielab_numpy_seq_ms=seq_np_ms,
                        active_nodes=active_nodes,
                        rgb_wire_bytes=len(rgb_blob),
                        mask_wire_bytes=mask_bytes if mask_bytes else sum(
                            len(encode_bool_mask(m))
                            for m in (
                                selection_for_perf["anatomical_mask"],
                                *selection_for_perf["accepted_masks"].values(),
                            )
                        ),
                    )

                step["estado"] = "concluida"
                yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
                       "concluidas": index + 1, "total": len(steps)}

            completed_all = True
            return final_result
        finally:
            with self._lock:
                self._requests.pop(req_id, None)
            for peer, inc in peer_increments.values():
                peer.inflight = max(0, peer.inflight - inc)
                if not completed_all and peer.conn is not None and not peer.conn.is_closed:
                    try:
                        peer.conn.send(MSG_CANCEL, {}, req_id=req_id)
                    except ConnectionError:
                        pass
            for fut in local_futures.values():
                fut.cancel()
            local_pool.shutdown(wait=False, cancel_futures=True)


_default_local_executor = LocalParallelExecutor()
_env_executor_lock = threading.Lock()
_env_executor_cache: tuple[str, str, DistributedExecutor] | None = None


def resolve_executor(explicit_executor=None):
    """Retorna o executor configurado ou o LocalParallelExecutor padrão."""
    if explicit_executor is not None:
        return explicit_executor
    peers_env = os.environ.get("MAQUIAGEM_PEERS", "").strip()
    if not peers_env:
        return _default_local_executor
    policy = os.environ.get("MAQUIAGEM_FALLBACK_POLICY", "local").strip() or "local"
    global _env_executor_cache
    with _env_executor_lock:
        if _env_executor_cache is None or _env_executor_cache[:2] != (peers_env, policy):
            if _env_executor_cache is not None:
                _env_executor_cache[2].close()
            _env_executor_cache = (peers_env, policy, DistributedExecutor(peers_env, fallback_policy=policy))
        return _env_executor_cache[2]
