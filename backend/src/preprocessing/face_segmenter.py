import os
import sys
from typing import Optional, Tuple, Union

import cv2
import numpy as np
import mediapipe as mp

# Indices ordenados do perimetro oval da face no MediaPipe Face Mesh
INDICES_OVAL_FACIAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
    397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
    172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109
]


def carregar_imagem(origem: Union[str, np.ndarray]) -> np.ndarray:
    if isinstance(origem, np.ndarray):
        return np.ascontiguousarray(origem)

    caminho = os.path.abspath(origem)
    if not os.path.isfile(caminho):
        raise FileNotFoundError(f"Arquivo nao encontrado: {caminho}")

    imagem = cv2.imread(caminho, cv2.IMREAD_COLOR)
    if imagem is None:
        raise ValueError(f"Nao foi possivel decodificar a imagem: {caminho}")

    return np.ascontiguousarray(imagem)


def extrair_poligono_facial(imagem_bgr: np.ndarray) -> Optional[np.ndarray]:
    altura, largura, _ = imagem_bgr.shape
    imagem_rgb = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2RGB)

    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
    ) as detector:
        resultado = detector.process(imagem_rgb)

    if not resultado.multi_face_landmarks:
        return None

    marcos = resultado.multi_face_landmarks[0].landmark
    pontos = []
    for idx in INDICES_OVAL_FACIAL:
        px = int(marcos[idx].x * largura)
        py = int(marcos[idx].y * altura)
        pontos.append([px, py])

    return np.array(pontos, dtype=np.int32)


def criar_mascara_facial(formato_imagem: Tuple[int, int], poligono: np.ndarray) -> np.ndarray:
    altura, largura = formato_imagem[:2]
    mascara = np.zeros((altura, largura), dtype=np.uint8)
    cv2.fillPoly(mascara, [poligono], 255)
    return mascara


def isolar_rosto_anatomico(
    origem: Union[str, np.ndarray],
    retornar_rgb: bool = True,
    fundo_transparente: bool = False,
) -> Optional[np.ndarray]:
    """
    Isola estritamente a silhueta da face, removendo fundo, cabelo e roupas.
    Retorna a regiao facial ajustada (RGB ou RGBA transparente), ou None se nao detectar rosto.
    """
    imagem = carregar_imagem(origem)
    poligono = extrair_poligono_facial(imagem)

    if poligono is None:
        return None

    mascara = criar_mascara_facial(imagem.shape, poligono)
    x, y, w, h = cv2.boundingRect(poligono)

    if fundo_transparente:
        imagem_rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB) if retornar_rgb else imagem
        canal_r, canal_g, canal_b = cv2.split(imagem_rgb)
        imagem_rgba = cv2.merge([canal_r, canal_g, canal_b, mascara])
        recorte = imagem_rgba[y : y + h, x : x + w]
    else:
        imagem_mascarada = cv2.bitwise_and(imagem, imagem, mask=mascara)
        if retornar_rgb:
            imagem_mascarada = cv2.cvtColor(imagem_mascarada, cv2.COLOR_BGR2RGB)
        recorte = imagem_mascarada[y : y + h, x : x + w]

    return np.ascontiguousarray(recorte)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python face_segmenter.py <caminho_imagem> [caminho_saida]")
        sys.exit(1)

    caminho_in = sys.argv[1]
    caminho_out = sys.argv[2] if len(sys.argv) >= 3 else None

    # Se for salvar com extensao PNG, habilita fundo transparente
    usar_transparencia = bool(caminho_out and caminho_out.lower().endswith(".png"))
    resultado = isolar_rosto_anatomico(
        caminho_in,
        retornar_rgb=False,
        fundo_transparente=usar_transparencia,
    )

    if resultado is not None:
        print(f"[SUCESSO] Rosto isolado - Dimensoes: {resultado.shape[1]}x{resultado.shape[0]} px")
        if caminho_out:
            cv2.imwrite(caminho_out, resultado)
            print(f"[OK] Salvo em: {caminho_out}")
        else:
            base, ext = os.path.splitext(caminho_in)
            saida_padrao = f"{base}_silhueta.png"
            # Salva como PNG com canal alfa
            res_png = isolar_rosto_anatomico(caminho_in, retornar_rgb=False, fundo_transparente=True)
            cv2.imwrite(saida_padrao, res_png)
            print(f"[OK] Silhueta salva em: {saida_padrao}")
    else:
        print("[AVISO] Nenhum rosto detectado.")
        sys.exit(2)
