"""
Módulo de pré-processamento de imagem facial.
Contém detectores e segmentadores para identificação e isolamento do rosto.
"""

from .face_detector import (
    detectar_e_isolar_rosto,
    detectar_rosto_mediapipe,
    detectar_rosto_haar,
    carregar_imagem,
    recortar_regiao,
    aplicar_margem_bounding_box,
)
from .face_segmenter import (
    isolar_rosto_anatomico,
    extrair_poligono_facial,
    criar_mascara_facial,
)

__all__ = [
    "detectar_e_isolar_rosto",
    "detectar_rosto_mediapipe",
    "detectar_rosto_haar",
    "carregar_imagem",
    "recortar_regiao",
    "aplicar_margem_bounding_box",
    "isolar_rosto_anatomico",
    "extrair_poligono_facial",
    "criar_mascara_facial",
]
