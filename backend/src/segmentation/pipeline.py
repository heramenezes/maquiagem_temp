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


class PipelineError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


STAGES = [
    ("rosto", "Verificando o rosto", "Confirmação de um único rosto e recorte facial", False),
    ("cielab", "Convertendo as cores para CIELAB", "sRGB → RGB linear → XYZ → L*a*b* (D65)", False),
    ("mascara", "Segmentando o rosto com BiSeNet", "Modelo pré-treinado: pele, nariz, olhos, lábios e cabelo", False),
    ("clusters", "Descrevendo as cores da pele", "Agrupamento em a*/b* sem remover pixels da máscara", False),
    ("medidas", "Medindo a pele selecionada", "Área e média CIELAB dos pixels de pele e nariz", False),
    ("resultado", "Preparando o resultado", "Pré-processamento real; tom e recomendações demonstrativos", True),
]


def _png_data(image):
    buffer = BytesIO()
    Image.fromarray(image).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def summarize(rgb, masks, clusters, skin):
    mask = skin["mask"]
    rgba = np.dstack((rgb, mask.astype(np.uint8) * 255))
    area = int(masks["face"].sum())
    return {
        "simulado": False,
        "espaco_cor": "CIELAB", "branco_referencia": "D65", "entrada": "sRGB",
        "metodo_contorno": masks["method"], "modelo": masks["model"], "clusters": clusters["k"],
        "pixels_pele": int(mask.sum()), "pixels_contorno": area,
        "percentual_pele": round(100 * mask.sum() / area, 2),
        "media_lab": [round(float(v), 4) for v in skin["mean_lab"]],
        "media_rgb": [round(float(v), 2) for v in rgb[mask].mean(axis=0)],
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
    rgb = lab = masks = clusters = skin = result = None
    for index, step in enumerate(steps):
        step["estado"] = "processando"
        yield {"tipo": "etapa", "etapas": [dict(s) for s in steps],
               "concluidas": index, "total": len(steps)}
        try:
            if step["id"] == "rosto":
                rgb = detect_face(image_bgr)
                if rgb is None or rgb.size == 0:
                    raise PipelineError("ROSTO_NAO_ENCONTRADO", "Não encontramos um rosto visível. Tire outra foto de frente, com boa luz e sem cobrir o rosto.")
                # Redução explícita, sem distorcer o rosto, limita o K-means.
                factor = min(1, 512 / max(rgb.shape[:2]))
                if factor < 1:
                    rgb = cv2.resize(rgb, (round(rgb.shape[1] * factor), round(rgb.shape[0] * factor)), interpolation=cv2.INTER_AREA)
            elif step["id"] == "cielab":
                lab = rgb_to_lab(rgb)
            elif step["id"] == "mascara":
                masks = facial_masks(rgb)
            elif step["id"] == "clusters":
                clusters = adaptive_clusters(lab, masks)
            elif step["id"] == "medidas":
                skin = measure_skin(lab, masks)
            else:
                result = mock_result()
                result["preprocessamento"] = summarize(rgb, masks, clusters, skin)
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
