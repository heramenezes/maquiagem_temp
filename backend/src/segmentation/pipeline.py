"""Pipeline sequencial com eventos reais, sem jobs persistentes ou temporizadores."""

import base64
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from .color import rgb_to_lab
from .skin import InsufficientSkinError, adaptive_clusters
from .semantic import ModelUnavailableError, facial_masks, measure_skin
from ..preprocessing.face_detector import MultipleFacesError
from ..skin_selection.pipeline import run_module, finish
from ..skin_selection.serialization import serialize_selection, conditions


class PipelineError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


STAGES = [
    ("rosto", "Verificando o rosto", "Confirmação de um único rosto e recorte facial", False),
    ("cielab", "Convertendo as cores para CIELAB", "sRGB → RGB linear → XYZ → L*a*b* (D65)", False),
    ("mascara", "Segmentando o rosto com BiSeNet", "Modelo pré-treinado: pele, nariz, olhos, lábios e cabelo", False),
    ("acne", "Segmentando áreas de acne", "U-Net/ResNet34: exclusões e áreas incertas", False),
    ("vitiligo", "Segmentando áreas de vitiligo", "YOLO: máscaras de instância no recorte preservado", False),
    ("barba", "Avaliando barba e bigode", "EasyPortrait: discordância, localização e textura", False),
    ("selecao", "Compondo a seleção de pele", "União de máscaras e avaliação de qualidade", False),
    ("clusters", "Descrevendo as cores da pele", "Agrupamento em a*/b* sem remover pixels da máscara", False),
    ("medidas", "Medindo a pele selecionada", "Estatísticas somente da seleção aprovada pela qualidade", False),
    ("resultado", "Preparando o resultado", "Pré-processamento real; tom e recomendações demonstrativos", True),
]


def _png_data(image):
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def summarize(rgb, masks, clusters, skin, selection):
    mask = selection["valid_mask"]
    rgba = np.dstack((rgb, mask.astype(np.uint8) * 255))
    area = int(masks["face"].sum())
    return {
        "simulado": False,
        "espaco_cor": "CIELAB", "branco_referencia": "D65", "entrada": "sRGB",
        "metodo_contorno": masks["method"], "modelo": masks["model"], "clusters": clusters["k"],
        "pixels_pele": int(mask.sum()), "pixels_contorno": area,
        "percentual_pele": round(100 * mask.sum() / area, 2),
        "media_lab": [round(float(v), 4) for v in skin["mean_lab"]] if skin else None,
        "media_rgb": [round(float(v), 2) for v in rgb[mask].mean(axis=0)] if skin else None,
        "mediana_lab": [round(float(v), 4) for v in skin["median_lab"]] if skin else None,
        "desvio_lab": [round(float(v), 4) for v in skin["std_lab"]] if skin else None,
        "dispersao_delta_e76_p90": skin["dispersion_delta_e76_p90"] if skin else None,
        "medicao_utilizavel": selection["quality"]["usable"],
        "selecao": serialize_selection(selection, _png_data),
        "clusters_referencia": "anatomia_antes_das_exclusoes",
        "dimensoes": {"largura": rgb.shape[1], "altura": rgb.shape[0]},
        "avisos": masks["warnings"],
        "previas": {"rosto": _png_data(rgb), "pele": _png_data(rgba),
                    "mascara": _png_data(mask.astype(np.uint8) * 255)},
    }


def analysis_events(image_bgr, detect_face, mock_result):
    """Cada etapa anuncia início antes de executar e conclusão após executar.

    O consumidor pode transmitir NDJSON ou consumir tudo para produzir JSON.
    Fechar o generator ao desconectar libera referências às fotos e matrizes.
    """
    steps = [{"id": key, "nome": name, "descricao": description,
              "simulado": simulated, "estado": "aguardando"}
             for key, name, description, simulated in STAGES]
    rgb = lab = masks = clusters = skin = result = selection = None
    modules = {}
    for index, step in enumerate(steps):
        step["estado"] = "processando"
        yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
               "concluidas": index, "total": len(steps)}
        try:
            if step["id"] == "rosto":
                rgb = detect_face(image_bgr)
                if rgb is None or rgb.size == 0:
                    raise PipelineError("ROSTO_NAO_ENCONTRADO", "Não encontramos um rosto visível. Tire outra foto de frente, com boa luz e sem cobrir o rosto.")
                # Preserva pixels nativos do recorte; só as vistas das redes são reduzidas.
                rgb = rgb.copy()
            elif step["id"] == "cielab":
                lab = rgb_to_lab(rgb)
            elif step["id"] == "mascara":
                masks = facial_masks(rgb)
            elif step["id"] in ("acne", "vitiligo", "barba"):
                key = step["id"]
                modules[key] = run_module(key, rgb, masks)
                step["estado_modulo"] = modules[key].status
            elif step["id"] == "selecao":
                selection = finish(rgb, lab, masks, modules)
            elif step["id"] == "clusters":
                # K-means é apenas descritivo; limita também os arrays intermediários.
                factor = min(1, 512 / max(rgb.shape[:2]))
                size = (max(1, round(rgb.shape[1] * factor)), max(1, round(rgb.shape[0] * factor)))
                small_lab = cv2.resize(lab, size, interpolation=cv2.INTER_AREA)
                small_mask = cv2.resize(masks["allowed"].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
                clusters = adaptive_clusters(small_lab, {"allowed": small_mask, "seeds": small_mask}) if small_mask.sum() >= 64 else {"k": None}
            elif step["id"] == "medidas":
                if selection["quality"]["usable"]:
                    skin = measure_skin(lab, selection["valid_mask"])
                else:
                    step["estado_modulo"] = "nao_executado"
                    step["motivo"] = "qualidade_inconclusiva"
            else:
                result = mock_result()
                result["condicoes"] = conditions(selection)
                result["marcacoes"] = []  # Bboxes reais estão em selecao.regions, no recorte.
                result["preprocessamento"] = summarize(rgb, masks, clusters, skin, selection)
                result["status_analise"] = "concluida" if skin else "inconclusiva"
        except MultipleFacesError as exc:
            raise PipelineError("MULTIPLOS_ROSTOS", str(exc)) from exc
        except ModelUnavailableError as exc:
            raise PipelineError("MODELO_INDISPONIVEL", str(exc), status=503) from exc
        except InsufficientSkinError as exc:
            raise PipelineError("PELE_INSUFICIENTE", str(exc)) from exc
        step["estado"] = "concluida"
        yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
               "concluidas": index + 1, "total": len(steps)}
    result["etapas"] = [dict(s) for s in steps]
    yield {"tipo": "resultado", "dados": result}
