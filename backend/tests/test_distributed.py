"""Testes automatizados da arquitetura P2P distribuída, multi-processo e kernel OpenMP."""

from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from backend.app import create_app
from backend.src.distributed import (
    DistributedExecutor,
    WorkerNode,
    ciede2000_one_to_many,
    omp_info,
    rgb_to_lab_fast,
)
from backend.src.distributed.cluster import build_local_specs, compute_thread_budgets
from backend.src.distributed.codec import (
    decode_anatomy,
    decode_bool_mask,
    decode_module_result,
    decode_rgb,
    encode_anatomy,
    encode_bool_mask,
    encode_module_result,
    encode_rgb,
)
from backend.src.distributed.registry import PeerRegistry, expand_capabilities
from backend.src.skin_selection.contracts import ModuleResult
from backend.src.tone_matching import compare_tone_algorithms, three_random_points_tone
from backend.src.catalog import load_catalog
from backend.tests.images import face_photo

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_BYTES = (ROOT / "samples" / "imagem_teste.jpeg").read_bytes()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port(addr: str, timeout: float = 15.0) -> None:
    host, _, port = addr.rpartition(":")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=0.3):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Porta não respondeu a tempo: {addr}")


class OpenMPAndCodecTests(unittest.TestCase):
    def test_openmp_rgb_to_lab_and_ciede2000_match_numpy_reference(self):
        rng = np.random.default_rng(19)
        for shape in ((17, 29, 3), (240, 320, 3)):
            u8 = rng.integers(0, 256, shape, dtype=np.uint8)
            np.testing.assert_allclose(
                rgb_to_lab_fast(u8, prefer_native=True),
                rgb_to_lab_fast(u8, prefer_native=False),
                atol=1e-5,
            )
            f64 = u8.astype(np.float64) / 255.0
            np.testing.assert_allclose(
                rgb_to_lab_fast(f64, prefer_native=True),
                rgb_to_lab_fast(f64, prefer_native=False),
                atol=1e-5,
            )

        targets = rgb_to_lab_fast(rng.integers(0, 256, (5000, 3), dtype=np.uint8), prefer_native=False).astype(np.float64)
        for ref in ([50.0, 0.0, 0.0], [65.2, 18.4, 24.9], [22.1, 8.0, -5.0], [95.0, -2.0, 4.0]):
            ref_arr = np.array(ref, dtype=np.float64)
            np.testing.assert_allclose(
                ciede2000_one_to_many(ref_arr, targets, prefer_native=True),
                ciede2000_one_to_many(ref_arr, targets, prefer_native=False),
                atol=1e-11,
            )
        self.assertEqual(ciede2000_one_to_many([50.0, 0.0, 0.0], np.empty((0, 3))).shape, (0,))

    def test_compact_codec_preserves_shapes_empty_masks_and_metadata(self):
        rng = np.random.default_rng(11)
        rgb = rng.integers(0, 256, (73, 119, 3), dtype=np.uint8)
        meta, blob = encode_rgb(rgb)
        np.testing.assert_array_equal(decode_rgb(meta, blob), rgb)

        empty_bytes = encode_bool_mask(np.zeros((73, 119), dtype=bool))
        full_bytes = encode_bool_mask(np.ones((73, 119), dtype=bool))
        self.assertEqual(len(empty_bytes), 1)
        self.assertEqual(len(full_bytes), 1)
        np.testing.assert_array_equal(decode_bool_mask(empty_bytes, (73, 119)), np.zeros((73, 119), dtype=bool))
        np.testing.assert_array_equal(decode_bool_mask(full_bytes, (73, 119)), np.ones((73, 119), dtype=bool))

        sparse = rgb[:, :, 0] > 220
        np.testing.assert_array_equal(decode_bool_mask(encode_bool_mask(sparse), (73, 119)), sparse)

        anat = {
            "face": np.ones((73, 119), dtype=bool),
            "allowed": rgb[:, :, 1] > 60,
            "seeds": rgb[:, :, 1] > 60,
            "labels": (rgb[:, :, 2] % 19).astype(np.uint8),
            "method": "bisenet_resnet18_onnx",
            "model": "yakhyo",
            "warnings": ["w"],
        }
        dec_anat = decode_anatomy(*encode_anatomy(anat))
        np.testing.assert_array_equal(dec_anat["allowed"], anat["allowed"])
        np.testing.assert_array_equal(dec_anat["labels"], anat["labels"])

        mod = ModuleResult(
            accepted=sparse,
            uncertain=(rgb[:, :, 0] > 180) & ~sparse,
            status="executado",
            source="beard_test",
            evidence={"nominal_beard_class": True},
            debug_masks={"yolo_beard": sparse.copy()},
            elapsed_ms=33.25,
        )
        key, dec_mod = decode_module_result(*encode_module_result("barba", mod))
        self.assertEqual(key, "barba")
        self.assertEqual(dec_mod.elapsed_ms, 33.25)
        np.testing.assert_array_equal(dec_mod.accepted, mod.accepted)
        np.testing.assert_array_equal(dec_mod.debug_masks["yolo_beard"], mod.debug_masks["yolo_beard"])

    def test_capability_expansion_and_thread_budget_partitioning(self):
        self.assertEqual(expand_capabilities("segmentation"), ("bisenet", "acne", "vitiligo", "barba"))
        self.assertEqual(expand_capabilities("specialists,color_match"), ("acne", "vitiligo", "barba", "color_match"))
        specs = build_local_specs("sharded", has_remote_gpu=False)
        budgets = compute_thread_budgets(8, specs)
        self.assertEqual(len(budgets), len(specs))
        self.assertTrue(all(int(b["OMP_NUM_THREADS"]) >= 1 for b in budgets))
        gpu_specs = build_local_specs("auto", has_remote_gpu=True)
        self.assertEqual(gpu_specs, [("local-color", "color_match")])


class DistributedP2PClusterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Resultado de referência obtido no pipeline local padrão.
        local_app = create_app({"TESTING": True})
        with local_app.test_client() as client:
            resp = client.post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
            assert resp.status_code == 200, resp.data
            cls.baseline = resp.json

    def test_three_node_p2p_pipeline_matches_local_output_and_ndjson_contract(self):
        seg = WorkerNode("127.0.0.1", 0, capabilities="segmentation", node_id="seg-1").start()
        color = WorkerNode(
            "127.0.0.1", 0,
            capabilities="color_match",
            node_id="color-1",
            subscribe_peers=[seg.address],
        ).start()
        executor = DistributedExecutor([seg.address, color.address], fallback_policy="degrade")
        try:
            time.sleep(0.2)
            app = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": executor})
            client = app.test_client()

            status = client.get("/api/cluster").json
            self.assertEqual(status["mode"], "distributed")
            self.assertEqual(len(status["peers"]), 2)
            self.assertTrue(all(p["healthy"] for p in status["peers"]))

            json_resp = client.post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
            self.assertEqual(json_resp.status_code, 200)
            dist_data = json_resp.json

            stream_resp = client.post(
                "/api/analises",
                data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")},
                headers={"Accept": "application/x-ndjson"},
            )
            self.assertEqual(stream_resp.status_code, 200)
            events = [json.loads(line) for line in stream_resp.data.splitlines()]
            stage_events = [e for e in events if e["tipo"] == "etapa"]
            self.assertEqual([e["concluidas"] for e in stage_events], [n for i in range(10) for n in (i, i + 1)])
            self.assertEqual(events[-1]["tipo"], "resultado")

            # Verifica equivalência numérica e de máscaras com o pipeline local v3.
            self.assertEqual(dist_data["schema_version"], 3)
            self.assertEqual(dist_data["tom"], self.baseline["tom"])
            self.assertEqual(dist_data["recomendacoes"], self.baseline["recomendacoes"])
            self.assertEqual(dist_data["condicoes"], self.baseline["condicoes"])
            self.assertEqual(dist_data["match"], self.baseline["match"])
            self.assertEqual(
                dist_data["preprocessamento"]["previas"],
                self.baseline["preprocessamento"]["previas"],
            )
            self.assertEqual(
                dist_data["preprocessamento"]["selecao"]["masks"],
                self.baseline["preprocessamento"]["selecao"]["masks"],
            )
            self.assertEqual(events[-1]["dados"]["tom"], self.baseline["tom"])
        finally:
            executor.close()
            color.stop()
            seg.stop()

    def test_remote_segmentation_without_dedicated_color_node_works_seamlessly(self):
        # Simula cenário onde apenas o nó GPU remoto está configurado e a cor roda no Gateway.
        seg_gpu_sim = WorkerNode("127.0.0.1", 0, capabilities="segmentation", node_id="gpu-remote-sim").start()
        executor = DistributedExecutor([seg_gpu_sim.address], fallback_policy="degrade")
        try:
            app = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": executor})
            resp = app.test_client().post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json["tom"], self.baseline["tom"])
            self.assertEqual(resp.json["recomendacoes"], self.baseline["recomendacoes"])
        finally:
            executor.close()
            seg_gpu_sim.stop()

    def test_real_os_subprocesses_sharded_across_specialists(self):
        """Valida execução PoC real entre processos SO independentes via CLI node.py."""
        procs: list[subprocess.Popen] = []
        addrs: list[str] = []
        seg_addrs: list[str] = []
        roles = [
            ("proc-fast", "bisenet,acne,vitiligo"),
            ("proc-beard", "barba"),
            ("proc-color", "color_match"),
        ]
        try:
            for name, caps in roles:
                port = _free_port()
                addr = f"127.0.0.1:{port}"
                addrs.append(addr)
                cmd = [
                    sys.executable, "-m", "backend.src.distributed.node",
                    "--bind", addr,
                    "--node-id", name,
                    "--capabilities", caps,
                    "--omp-threads", "2",
                    "--ort-threads", "2",
                    "--no-warmup",
                ]
                if caps == "color_match":
                    cmd.extend(["--subscribe-peers", ",".join(seg_addrs)])
                else:
                    seg_addrs.append(addr)
                procs.append(subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

            for addr in addrs:
                _wait_port(addr)

            executor = DistributedExecutor(addrs, fallback_policy="degrade")
            deadline = time.monotonic() + 10.0
            while len(executor.registry.connect_all(force=True)) < len(addrs) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(len(executor.registry.connect_all()), len(addrs))
            try:
                app = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": executor})
                resp = app.test_client().post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json["tom"], self.baseline["tom"])
                self.assertEqual(resp.json["recomendacoes"], self.baseline["recomendacoes"])
            finally:
                executor.close()
        finally:
            for p in procs:
                p.terminate()
            for p in procs:
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()

    def test_precheck_rejection_dispatches_zero_network_traffic_and_dead_peer_degrades_gracefully(self):
        # Porta fechada (par morto):
        dead_port = _free_port()
        dead_addr = f"127.0.0.1:{dead_port}"

        # 1. Sem rosto / múltiplos rostos nunca tentam despachar estágios P2P.
        executor = DistributedExecutor([dead_addr], fallback_policy="degrade", connect_timeout=0.2)
        try:
            app = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": executor})
            client = app.test_client()

            blank = BytesIO()
            Image.new("RGB", (200, 200), "black").save(blank, format="PNG")
            blank.seek(0)
            r_no_face = client.post("/api/analises", data={"foto": (blank, "blank.png")})
            self.assertEqual(r_no_face.status_code, 422)
            self.assertEqual(r_no_face.json["codigo"], "ROSTO_NAO_ENCONTRADO")

            with patch("backend.src.preprocessing.face_detector.detectar_rosto_mediapipe", return_value=None):
                r_multi = client.post("/api/analises", data={"foto": (face_photo(2, 1.0), "two.png")})
            self.assertEqual(r_multi.status_code, 422)
            self.assertEqual(r_multi.json["codigo"], "MULTIPLOS_ROSTOS")

            # 2. Com par remoto morto e política `degrade`, recomenda bases com ressalvas explícitas!
            r_degraded = client.post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
            self.assertEqual(r_degraded.status_code, 200)
            self.assertEqual(len(r_degraded.json["recomendacoes"]), 3)
            self.assertTrue(r_degraded.json["match"]["confianca_reduzida"])
            self.assertIn("modulo_obrigatorio_indisponivel", r_degraded.json["match"]["motivos"])
            self.assertIn("segmentacao_indisponivel", r_degraded.json["match"]["motivos"])
        finally:
            executor.close()

        # 3. Com política `local`, par morto cai automaticamente para inferência local completa!
        exec_local_fb = DistributedExecutor([dead_addr], fallback_policy="local", connect_timeout=0.2)
        try:
            app_fb = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": exec_local_fb})
            r_fb = app_fb.test_client().post("/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")})
            self.assertEqual(r_fb.status_code, 200)
            self.assertEqual(r_fb.json["tom"], self.baseline["tom"])
            self.assertEqual(r_fb.json["recomendacoes"], self.baseline["recomendacoes"])
        finally:
            exec_local_fb.close()

    def test_hmac_cluster_token_blocks_unauthorized_peers(self):
        with patch.dict(os.environ, {"MAQUIAGEM_CLUSTER_TOKEN": "segredo-forte"}):
            node = WorkerNode("127.0.0.1", 0, capabilities="color_match").start()
            try:
                reg_ok = PeerRegistry([node.address], connect_timeout=1.0)
                self.assertEqual(len(reg_ok.connect_all(force=True)), 1)
                reg_ok.close()

                with patch.dict(os.environ, {"MAQUIAGEM_CLUSTER_TOKEN": "token-errado"}):
                    reg_bad = PeerRegistry([node.address], connect_timeout=1.0)
                    self.assertEqual(len(reg_bad.connect_all(force=True)), 0)
                    reg_bad.close()
            finally:
                node.stop()

    def test_three_random_points_algorithm_and_comparative_metrics(self):
        catalog = load_catalog()
        # 1. Pele perfeitamente uniforme: 3 pontos aleatórios igualam exatamente o pipeline completo (ΔE00 = 0).
        uniform_rgb = np.full((60, 80, 3), [180, 120, 90], dtype=np.uint8)
        uniform_lab = rgb_to_lab_fast(uniform_rgb)
        mask = np.ones((60, 80), dtype=bool)
        sample_uni = three_random_points_tone(uniform_lab, mask, rgb_image=uniform_rgb, seed=7)
        self.assertEqual(len(sample_uni["pontos"]), 3)
        np.testing.assert_allclose(sample_uni["lab"], uniform_lab[0, 0], atol=1e-3)

        # Máscara minúscula (< 3 pixels) funciona com reposição sem erro.
        tiny_mask = np.zeros((60, 80), dtype=bool)
        tiny_mask[5, 5] = True
        tiny_res = three_random_points_tone(uniform_lab, tiny_mask, seed=1)
        self.assertEqual(len(tiny_res["pontos"]), 3)
        self.assertTrue(all(pt["x"] == 5 and pt["y"] == 5 for pt in tiny_res["pontos"]))

        # 2. Pele heterogênea com região excluída (ex.: barba escura na metade inferior da máscara inicial):
        het_rgb = np.full((80, 80, 3), [195, 140, 110], dtype=np.uint8)
        het_rgb[40:, :] = [35, 25, 20]  # barba sobre metade da anatomia inicial
        het_lab = rgb_to_lab_fast(het_rgb)
        anatomical = np.ones((80, 80), dtype=bool)
        valid = np.zeros((80, 80), dtype=bool)
        valid[:40, :] = True
        full_lab = het_lab[0, 0].astype(np.float64)
        from backend.src.tone_matching import rank_foundations
        full_recs = rank_foundations(full_lab, catalog)

        comp = compare_tone_algorithms(
            full_lab=full_lab,
            full_recommendations=full_recs,
            full_estimator="lab_regional_ponderado",
            full_pixel_count=int(valid.sum()),
            catalog=catalog,
            skin={"mask": valid, "median_lab": full_lab},
            selection={"anatomical_mask": anatomical, "valid_mask": valid},
            lab_image=het_lab,
            rgb_image=het_rgb,
            seed=42,
        )
        self.assertGreater(comp["metricas"]["delta_e00_entre_algoritmos"], 5.0)
        self.assertGreaterEqual(comp["metricas"]["pontos_fora_pele_estrita"], 1)
        self.assertGreater(comp["metricas"]["estabilidade_monte_carlo"]["dispersao_interna_p90_delta_e00"], 5.0)
        self.assertLess(comp["metricas"]["estabilidade_monte_carlo"]["concordancia_top1_pct"], 80.0)
        json.dumps(comp, allow_nan=False)

    def test_api_returns_both_algorithm_comparison_and_performance_metrics_in_local_and_p2p_modes(self):
        # Valida no baseline local
        self.assertIn("comparacao_algoritmos", self.baseline)
        self.assertIn("desempenho", self.baseline)
        comp_local = self.baseline["comparacao_algoritmos"]
        perf_local = self.baseline["desempenho"]
        self.assertEqual(len(comp_local["tres_pontos_aleatorios"]["pontos"]), 3)
        self.assertEqual(len(comp_local["tres_pontos_aleatorios"]["recomendacoes"]), 3)
        self.assertEqual(perf_local["modo_execucao"], "paralelo_local")
        self.assertGreaterEqual(perf_local["speedup_total"], 1.0)
        self.assertEqual(set(perf_local["etapas_ms"].keys()), {
            "rosto", "cielab", "mascara", "acne", "vitiligo",
            "barba", "selecao", "clusters", "medidas", "resultado",
        })

        # Valida no modo distribuído P2P
        seg = WorkerNode("127.0.0.1", 0, capabilities="segmentation", node_id="seg-perf").start()
        col = WorkerNode("127.0.0.1", 0, capabilities="color_match", node_id="col-perf", subscribe_peers=[seg.address]).start()
        executor = DistributedExecutor([seg.address, col.address], fallback_policy="degrade")
        try:
            time.sleep(0.15)
            resp = create_app({"TESTING": True, "DISTRIBUTED_EXECUTOR": executor}).test_client().post(
                "/api/analises", data={"foto": (BytesIO(SAMPLE_BYTES), "sample.jpg")}
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json
            self.assertEqual(data["desempenho"]["modo_execucao"], "distribuido_p2p")
            self.assertGreaterEqual(len(data["desempenho"]["nos_ativos"]), 3)
            self.assertTrue(data["desempenho"]["rede_p2p"]["transferencia_ativa"])
            self.assertGreater(data["desempenho"]["rede_p2p"]["bytes_rgb_comprimido"], 0)
            self.assertEqual(
                data["comparacao_algoritmos"]["tres_pontos_aleatorios"]["pontos"],
                comp_local["tres_pontos_aleatorios"]["pontos"],
            )
            self.assertEqual(
                data["comparacao_algoritmos"]["metricas"],
                comp_local["metricas"],
            )
        finally:
            executor.close()
            col.stop()
            seg.stop()

    def test_missing_cudnn_at_conv_execution_falls_back_to_cpu_without_failing_analysis(self):
        """Reproduz falha real de dlopen(libcudnn.so) durante session.run(Conv) e garante auto-recuperação em CPU."""
        from types import SimpleNamespace
        from backend.src.skin_selection import runtime as rt
        from backend.src.segmentation import semantic as sem

        broken_cuda_session = SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="input")],
            get_outputs=lambda: [SimpleNamespace(name="output")],
            get_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
            run=lambda *_a, **_kw: (_ for _ in ()).throw(
                RuntimeError("NOT_IMPLEMENTED : cuDNN is unavailable: dlopen failed for libcudnn.so")
            ),
        )
        working_cpu_session = SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="input")],
            get_outputs=lambda: [SimpleNamespace(name="output")],
            get_providers=lambda: ["CPUExecutionProvider"],
            run=lambda *_a, **_kw: [np.zeros((1, 1, 256, 256), dtype=np.float32)],
        )

        old_disabled = rt._cuda_disabled
        old_sessions = dict(rt._sessions)
        old_sem_session = sem._session
        try:
            rt._cuda_disabled = False
            rt._sessions["acne"] = broken_cuda_session
            with patch.object(rt, "_create_session", return_value=working_cpu_session) as recreate:
                out = rt.infer("acne", np.zeros((1, 3, 256, 256), dtype=np.float32))
            self.assertEqual(out[0].shape, (1, 1, 256, 256))
            self.assertTrue(rt._cuda_disabled)
            recreate.assert_called_once_with("acne", force_cpu=True)

            # BiSeNet também se auto-recupera caso CUDAExecutionProvider falhe no primeiro Conv.
            cpu_bisenet = SimpleNamespace(
                get_inputs=lambda: [SimpleNamespace(name="input")],
                get_outputs=lambda: [SimpleNamespace(name="output")],
                get_providers=lambda: ["CPUExecutionProvider"],
                run=lambda *_a, **_kw: [np.ones((1, 19, 512, 512), dtype=np.float32)],
            )
            sem._session = broken_cuda_session
            with patch("onnxruntime.InferenceSession", return_value=cpu_bisenet):
                labels = sem.predict_labels(np.full((64, 64, 3), 150, dtype=np.uint8))
            self.assertEqual(labels.shape, (64, 64))
        finally:
            rt._cuda_disabled = old_disabled
            rt._sessions.clear()
            rt._sessions.update(old_sessions)
            sem._session = old_sem_session


if __name__ == "__main__":
    unittest.main()
