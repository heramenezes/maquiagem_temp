"""
===============================================================================
 MÓDULO DE DETECÇÃO E ISOLAMENTO FACIAL
===============================================================================
 Sistema: Pipeline de Análise de Tons de Pele (Escala Monk)
 Camada: Backend — Pré-processamento de Imagem
 Arquitetura: Nós descentralizados (P2P) com suporte futuro a CUDA/OpenMP

 Descrição:
     Este módulo é responsável por detectar e isolar a região facial em uma
     imagem de entrada. Utiliza o MediaPipe Face Detection como motor
     principal, com fallback automático para OpenCV Haar Cascades.

     A saída é uma matriz NumPy (BGR) contendo exclusivamente a região do
     rosto recortada, pronta para conversão RGB → CIELAB no próximo estágio
     do pipeline.

 Autor: Pipeline TI6
 Data: Outubro/2026
===============================================================================
"""

import sys
import os
import logging
from typing import Optional, Tuple, Union

import cv2
import numpy as np

# ============================================================================
# Configuração de logging para depuração em ambiente distribuído
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("FaceDetector")


# ============================================================================
# Constantes do módulo
# ============================================================================

# Confiança mínima do MediaPipe para aceitar uma detecção
MEDIAPIPE_CONFIDENCE_THRESHOLD: float = 0.5

# Fator de escala aplicado ao Haar Cascade durante a detecção multiscale
HAAR_SCALE_FACTOR: float = 1.1

# Número mínimo de vizinhos para validar detecção no Haar Cascade
HAAR_MIN_NEIGHBORS: int = 5

# Margem percentual adicionada ao redor da bounding box para capturar
# a região completa do rosto (testa, queixo, laterais)
BOUNDING_BOX_MARGIN: float = 0.15


# ============================================================================
# Funções utilitárias (carregamento e validação de imagem)
# ============================================================================

def carregar_imagem(origem: Union[str, np.ndarray]) -> np.ndarray:
    """
    Carrega ou valida uma imagem a partir de um caminho em disco ou matriz em memória.

    Suporta tanto caminhos de arquivos locais quanto arrays já carregados
    em memória (comum ao receber payloads via rede P2P / gRPC).

    Parâmetros
    ----------
    origem : Union[str, np.ndarray]
        Caminho do arquivo de imagem ou matriz NumPy já existente (BGR).

    Retorna
    -------
    np.ndarray
        Matriz da imagem no espaço de cor BGR (padrão OpenCV), com memória contígua.

    Levanta
    -------
    FileNotFoundError
        Se a string de caminho não apontar para um arquivo existente.
    ValueError
        Se o arquivo não puder ser decodificado ou se a matriz for inválida.
    """
    if isinstance(origem, np.ndarray):
        if origem.ndim != 3 or origem.shape[2] != 3:
            raise ValueError(
                f"Matriz de imagem inválida. Formato esperado (H, W, 3), recebido {origem.shape}."
            )
        return np.ascontiguousarray(origem)

    if not isinstance(origem, str):
        raise TypeError(f"Origem deve ser str ou np.ndarray, recebido {type(origem).__name__}")

    caminho_absoluto = os.path.abspath(origem)

    if not os.path.isfile(caminho_absoluto):
        raise FileNotFoundError(
            f"Arquivo não encontrado: '{caminho_absoluto}'"
        )

    imagem = cv2.imread(caminho_absoluto, cv2.IMREAD_COLOR)

    if imagem is None:
        raise ValueError(
            f"Não foi possível decodificar a imagem: '{caminho_absoluto}'. "
            "Verifique se o formato é suportado (JPEG, PNG, BMP, TIFF)."
        )

    logger.info(
        "Imagem carregada: %s (dimensões: %dx%d, canais: %d)",
        caminho_absoluto,
        imagem.shape[1],
        imagem.shape[0],
        imagem.shape[2],
    )
    return np.ascontiguousarray(imagem)


def aplicar_margem_bounding_box(
    x: int, y: int, w: int, h: int,
    largura_img: int, altura_img: int,
    margem: float = BOUNDING_BOX_MARGIN,
) -> Tuple[int, int, int, int]:
    """
    Expande a bounding box por uma margem percentual, respeitando os limites
    da imagem original. Isso garante que a testa, queixo e laterais do rosto
    sejam capturados integralmente.

    Parâmetros
    ----------
    x, y : int
        Coordenadas do canto superior esquerdo da bounding box original.
    w, h : int
        Largura e altura da bounding box original.
    largura_img, altura_img : int
        Dimensões da imagem original (para clamping).
    margem : float
        Percentual de expansão (0.15 = 15%).

    Retorna
    -------
    Tuple[int, int, int, int]
        (x, y, largura, altura) da bounding box expandida e clampada.
    """
    delta_w = int(w * margem)
    delta_h = int(h * margem)

    x_novo = max(0, x - delta_w)
    y_novo = max(0, y - delta_h)
    w_novo = min(largura_img - x_novo, w + 2 * delta_w)
    h_novo = min(altura_img - y_novo, h + 2 * delta_h)

    return x_novo, y_novo, w_novo, h_novo


def recortar_regiao(imagem: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Recorta a região de interesse (ROI) da imagem com base na bounding box,
    garantindo que o array de saída seja C-contíguo em memória para compatibilidade
    otimizada com kernels paralelos (CUDA/OpenMP).

    Parâmetros
    ----------
    imagem : np.ndarray
        Imagem de origem.
    bbox : Tuple[int, int, int, int]
        (x, y, largura, altura) da região a ser recortada.

    Retorna
    -------
    np.ndarray
        Sub-matriz contígua contendo apenas a região do rosto.
    """
    x, y, w, h = bbox
    recorte = imagem[y : y + h, x : x + w]
    return np.ascontiguousarray(recorte)


# ============================================================================
# Motor de detecção 1: MediaPipe Face Detection
# ============================================================================

def detectar_rosto_mediapipe(
    imagem: np.ndarray,
    confianca_minima: float = MEDIAPIPE_CONFIDENCE_THRESHOLD,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Detecta o rosto mais proeminente na imagem usando o MediaPipe
    Face Detection (modelo curto, otimizado para rostos a até 2 metros).

    Parâmetros
    ----------
    imagem : np.ndarray
        Imagem de entrada no espaço BGR.
    confianca_minima : float
        Limiar mínimo de confiança para aceitar uma detecção.

    Retorna
    -------
    Optional[Tuple[int, int, int, int]]
        Bounding box (x, y, w, h) do rosto detectado, ou None se nenhum
        rosto for encontrado.
    """
    try:
        import mediapipe as mp
    except ImportError:
        logger.warning(
            "MediaPipe não instalado. Pulando detector MediaPipe. "
            "Instale com: pip install mediapipe"
        )
        return None

    try:
        logger.info("Executando detecção com MediaPipe (confiança ≥ %.2f)...", confianca_minima)

        mp_face_detection = mp.solutions.face_detection
        altura, largura, _ = imagem.shape

        # MediaPipe requer imagem em RGB
        imagem_rgb = cv2.cvtColor(imagem, cv2.COLOR_BGR2RGB)

        with mp_face_detection.FaceDetection(
            model_selection=0,  # 0 = curto alcance (até 2m), ideal para selfies/retratos
            min_detection_confidence=confianca_minima,
        ) as detector:
            resultados = detector.process(imagem_rgb)

        if not resultados.detections:
            logger.info("MediaPipe: nenhum rosto detectado.")
            return None

        # Selecionar a detecção com maior confiança
        melhor_deteccao = max(
            resultados.detections,
            key=lambda d: d.score[0],
        )
        score = melhor_deteccao.score[0]
        logger.info("MediaPipe: rosto detectado com confiança %.4f.", score)

        # Converter coordenadas relativas (0-1) para absolutas (pixels)
        bbox_relativa = melhor_deteccao.location_data.relative_bounding_box
        x = int(bbox_relativa.xmin * largura)
        y = int(bbox_relativa.ymin * altura)
        w = int(bbox_relativa.width * largura)
        h = int(bbox_relativa.height * altura)

        # Aplicar margem e clampar nos limites da imagem
        return aplicar_margem_bounding_box(x, y, w, h, largura, altura)

    except Exception as exc:
        logger.warning("Falha na execução do MediaPipe: %s. Tentando fallback.", exc)
        return None


# ============================================================================
# Motor de detecção 2: OpenCV Haar Cascades (fallback)
# ============================================================================

def detectar_rosto_haar(
    imagem: np.ndarray,
    fator_escala: float = HAAR_SCALE_FACTOR,
    min_vizinhos: int = HAAR_MIN_NEIGHBORS,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Detecta o rosto mais proeminente na imagem usando o classificador
    Haar Cascade do OpenCV. Serve como fallback quando o MediaPipe não
    está disponível ou falha na detecção.

    Parâmetros
    ----------
    imagem : np.ndarray
        Imagem de entrada no espaço BGR.
    fator_escala : float
        Fator de redução da imagem em cada escala da pirâmide.
    min_vizinhos : int
        Número mínimo de detecções vizinhas para validar o resultado.

    Retorna
    -------
    Optional[Tuple[int, int, int, int]]
        Bounding box (x, y, w, h) do rosto detectado, ou None se nenhum
        rosto for encontrado.
    """
    logger.info("Executando detecção com Haar Cascade (OpenCV)...")

    # Carregar o classificador pré-treinado (frontal face)
    caminho_cascade = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    classificador = cv2.CascadeClassifier(caminho_cascade)

    if classificador.empty():
        logger.error(
            "Falha ao carregar Haar Cascade de: %s", caminho_cascade
        )
        return None

    # Converter para escala de cinza (requisito do Haar Cascade)
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

    # Equalizar histograma para melhorar contraste em condições variáveis
    cinza = cv2.equalizeHist(cinza)

    deteccoes = classificador.detectMultiScale(
        cinza,
        scaleFactor=fator_escala,
        minNeighbors=min_vizinhos,
        minSize=(60, 60),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )

    if len(deteccoes) == 0:
        logger.info("Haar Cascade: nenhum rosto detectado.")
        return None

    # Selecionar a maior detecção (maior área = rosto mais próximo)
    maior_deteccao = max(deteccoes, key=lambda d: d[2] * d[3])
    x, y, w, h = maior_deteccao
    logger.info("Haar Cascade: rosto detectado em (%d, %d, %d, %d).", x, y, w, h)

    altura, largura, _ = imagem.shape
    return aplicar_margem_bounding_box(x, y, w, h, largura, altura)


# ============================================================================
# Função orquestradora principal
# ============================================================================

def detectar_e_isolar_rosto(
    origem_imagem: Union[str, np.ndarray],
    retornar_rgb: bool = True,
) -> Optional[np.ndarray]:
    """
    Pipeline completo de detecção e isolamento facial.

    Identifica a bounding box do rosto (tentando MediaPipe e fallback Haar),
    recorta a região excluindo o fundo e retorna a matriz facial isolada.

    Parâmetros
    ----------
    origem_imagem : Union[str, np.ndarray]
        Caminho do arquivo de imagem ou matriz NumPy (BGR) já carregada em memória.
    retornar_rgb : bool, default=True
        Se True, converte a imagem recortada para o espaço de cor RGB, pronta
        para a etapa seguinte do pipeline (conversão RGB -> CIELAB).
        Se False, mantém no padrão BGR do OpenCV.

    Retorna
    -------
    Optional[np.ndarray]
        Matriz NumPy (C-contígua) contendo exclusivamente a região do rosto
        recortada (em RGB ou BGR). Retorna None se nenhum rosto for detectado.

    Exemplo de uso no pipeline:
        >>> # Entrada por caminho de arquivo
        >>> rosto_rgb = detectar_e_isolar_rosto("amostra.jpg", retornar_rgb=True)
        >>> if rosto_rgb is not None:
        ...     # Próximo estágio do pipeline (Seção 4.1 do artigo):
        ...     # Conversão RGB -> CIELAB para posterior K-Means e cálculo de ITA
        ...     rosto_lab = cv2.cvtColor(rosto_rgb, cv2.COLOR_RGB2LAB)
    """
    logger.info("=" * 60)
    logger.info("INICIANDO PIPELINE DE DETECÇÃO FACIAL")
    logger.info("=" * 60)

    # --- Etapa 1: Carregar/Validar a imagem (garante BGR em memória) ---
    imagem_bgr = carregar_imagem(origem_imagem)

    # --- Etapa 2: Tentar detecção com MediaPipe ---
    bbox = detectar_rosto_mediapipe(imagem_bgr)

    # --- Etapa 3: Fallback para Haar Cascade se necessário ---
    if bbox is None:
        logger.info("Ativando fallback: Haar Cascade.")
        bbox = detectar_rosto_haar(imagem_bgr)

    # --- Etapa 4: Verificar se algum rosto foi detectado ---
    if bbox is None:
        origem_str = origem_imagem if isinstance(origem_imagem, str) else "<array_em_memoria>"
        logger.warning(
            "RESULTADO: Nenhum rosto detectado na imagem '%s'.",
            origem_str,
        )
        return None

    # --- Etapa 5: Recortar a região facial ---
    rosto_recortado = recortar_regiao(imagem_bgr, bbox)

    # --- Etapa 6: Ajuste de espaço de cor para a próxima etapa (RGB -> CIELAB) ---
    if retornar_rgb:
        rosto_saida = cv2.cvtColor(rosto_recortado, cv2.COLOR_BGR2RGB)
        rosto_saida = np.ascontiguousarray(rosto_saida)
        espaco_cor = "RGB"
    else:
        rosto_saida = rosto_recortado
        espaco_cor = "BGR"

    logger.info(
        "RESULTADO: Rosto isolado com sucesso. "
        "Dimensões do recorte: %dx%d pixels (espaço: %s).",
        rosto_saida.shape[1],
        rosto_saida.shape[0],
        espaco_cor,
    )
    logger.info("=" * 60)

    return rosto_saida


# ============================================================================
# Ponto de entrada para execução direta (teste/depuração)
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Uso: python face_detector.py <caminho_da_imagem> [caminho_saida]"
        )
        print("  caminho_da_imagem  - Arquivo de imagem de entrada")
        print("  caminho_saida      - (Opcional) Salvar o recorte facial")
        sys.exit(1)

    caminho_entrada = sys.argv[1]
    caminho_saida = sys.argv[2] if len(sys.argv) >= 3 else None

    resultado = detectar_e_isolar_rosto(caminho_entrada, retornar_rgb=True)

    if resultado is not None:
        print(f"[SUCESSO] Rosto detectado - Dimensoes: {resultado.shape[1]}x{resultado.shape[0]} px (RGB)")

        # cv2.imwrite espera imagem em BGR
        resultado_bgr = cv2.cvtColor(resultado, cv2.COLOR_RGB2BGR)

        if caminho_saida:
            cv2.imwrite(caminho_saida, resultado_bgr)
            print(f"[OK] Recorte salvo em: {caminho_saida}")
        else:
            # Salvar ao lado da imagem original com sufixo _rosto
            base, ext = os.path.splitext(caminho_entrada)
            saida_padrao = f"{base}_rosto{ext}"
            cv2.imwrite(saida_padrao, resultado_bgr)
            print(f"[OK] Recorte salvo em: {saida_padrao}")
    else:
        print("[AVISO] Nenhum rosto foi detectado na imagem fornecida.")
        sys.exit(2)
