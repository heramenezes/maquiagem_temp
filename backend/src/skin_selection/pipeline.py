"""Orquestração sequencial dos especialistas; nenhuma imagem é pintada."""

import logging
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
    result["model_versions"]["anatomia"] = ASSETS["bisenet"].metadata()
    result["quality"] = evaluate(rgb, lab, result)
    return result


def select_skin(rgb, lab, anatomy):
    modules = {key: run_module(key, rgb, anatomy) for key in DETECTORS}
    return finish(rgb, lab, anatomy, modules)
