"""Orquestração paralela dos especialistas; nenhuma imagem é pintada.

Os três detectores (acne, vitiligo, barba) são despachados simultaneamente
via ThreadPoolExecutor. Quando o CUDAExecutionProvider estiver disponível
(onnxruntime-gpu instalado) cada sessão ONNX pode utilizar a GPU; as threads
permitem que o despacho e a cópia de dados da próxima inferência ocorram
enquanto a GPU processa a anterior.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from . import acne, vitiligo, beard
from .compose import compose
from .contracts import ModuleResult
from .quality import evaluate
from ..segmentation.model_asset import ASSETS
from ..segmentation.semantic import ModelUnavailableError

DETECTORS = {"acne": acne.detect, "vitiligo": vitiligo.detect, "barba": beard.detect}
logger = logging.getLogger(__name__)


def run_module(key, rgb, anatomy):
    start = perf_counter()
    try:
        result = DETECTORS[key](rgb, anatomy)
        result.validate(rgb.shape[:2])
    except ModelUnavailableError as exc:
        result = ModuleResult.empty(rgb.shape[:2], status="indisponivel", reason=str(exc),
                                    source=key, version=ASSETS[key].metadata())
    except Exception:
        logger.exception("Falha no especialista %s", key)
        result = ModuleResult.empty(rgb.shape[:2], status="falha", reason="falha_inferencia",
                                    source=key, version=ASSETS[key].metadata())
    result.elapsed_ms = (perf_counter() - start) * 1000
    return result


def finish(rgb, lab, anatomy, modules):
    result = compose(anatomy["allowed"], modules)
    result["model_versions"]["anatomia"] = (
        {"method": anatomy["method"], "model": None}
        if anatomy["method"] == "regiao_central_rosto" else ASSETS["bisenet"].metadata())
    result["quality"] = evaluate(rgb, lab, result)
    # Preserva as exclusões e a seleção estrita para auditoria. A máscara de
    # medição só é ampliada quando a seleção estrita não contém nenhum pixel.
    candidates = (
        ("pele_valida", result["valid_mask"]),
        ("pele_com_incertezas", result["anatomical_mask"] & ~result["excluded_mask"]),
        ("pele_antes_exclusoes", result["anatomical_mask"]),
    )
    source, mask = next((source, mask) for source, mask in candidates if mask.any())
    result["measurement_mask"] = mask.copy()
    result["measurement_source"] = source
    quality = result["quality"]
    quality["reasons"].extend(anatomy.get("quality_reasons", []))
    if source != "pele_valida":
        quality["reasons"].append(source)
    quality["reasons"] = list(dict.fromkeys(quality["reasons"]))
    quality.update(usable=not quality["reasons"],
                   decision="com_ressalvas" if quality["reasons"] else "aprovada")
    return result


def select_skin(rgb, lab, anatomy):
    """Executa os especialistas em paralelo e compõe a máscara final.

    Cada detector roda em uma thread separada. Se o onnxruntime-gpu estiver
    instalado, o CUDAExecutionProvider é escolhido automaticamente por
    runtime._build_providers() e a GPU é compartilhada entre as threads.
    """
    modules = {}
    with ThreadPoolExecutor(max_workers=len(DETECTORS)) as pool:
        futures = {pool.submit(run_module, key, rgb, anatomy): key for key in DETECTORS}
        for future in as_completed(futures):
            key = futures[future]
            modules[key] = future.result()  # exceções já absorvidas em run_module
    return finish(rgb, lab, anatomy, modules)
