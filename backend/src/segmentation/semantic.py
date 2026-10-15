"""BiSeNet ResNet18 pré-treinado em CelebAMask-HQ, inferência local em CPU.

Contrato de entrada/saída: github.com/yakhyo/face-parsing (licença MIT).
RGB recebido do pipeline; a normalização é exclusiva da entrada da rede.
"""

import hashlib
import threading

import cv2
import numpy as np

from .model_asset import MODEL_ID, MODEL_PATH, MODEL_SHA256
from .skin import InsufficientSkinError

SKIN_CLASSES = (1, 10)  # skin, nose. IDs específicos do modelo yakhyo.
FACE_CLASSES = (1, 2, 3, 4, 5, 6, 10, 11, 12, 13)
_session = None
_session_lock = threading.Lock()


class ModelUnavailableError(RuntimeError):
    pass


def get_session():
    global _session
    with _session_lock:
        if _session is not None:
            return _session
        if not MODEL_PATH.is_file():
            raise ModelUnavailableError('O modelo de segmentação não está instalado. Execute python -m backend.download_model no servidor.')
        if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ModelUnavailableError('O modelo de segmentação está incompleto ou inválido. Execute python -m backend.download_model novamente.')
        try:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            _session = ort.InferenceSession(str(MODEL_PATH), sess_options=options,
                                           providers=['CPUExecutionProvider'])
        except (ImportError, RuntimeError) as exc:
            raise ModelUnavailableError('Não foi possível carregar o modelo de segmentação. Confira a instalação do ONNX Runtime no servidor.') from exc
        return _session


def predict_labels(rgb):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.size == 0:
        raise ValueError('A segmentação espera uma imagem RGB uint8 não vazia.')
    if min(rgb.shape[:2]) < 16:
        raise InsufficientSkinError('Aproxime o rosto e envie uma foto com mais detalhes.')
    session = get_session()
    resized = cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_LINEAR)
    normalized = (resized.astype(np.float32) / 255 - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1)[None])
    output = session.run([session.get_outputs()[0].name], {session.get_inputs()[0].name: tensor})[0]
    if output.shape != (1, 19, 512, 512) or not np.isfinite(output).all():
        raise RuntimeError('Saída inválida do modelo de segmentação.')
    labels = output[0].argmax(axis=0).astype(np.uint8)
    return cv2.resize(labels, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)


def masks_from_labels(labels):
    """Pele + nariz, sem expansão das exclusões nem filtro de cor/textura."""
    skin = np.isin(labels, SKIN_CLASSES)
    face = np.isin(labels, FACE_CLASSES)
    if skin.sum() < 64:
        raise InsufficientSkinError('Não conseguimos separar pele suficiente. Tire outra foto de frente e com luz uniforme.')
    return {'face': face, 'allowed': skin, 'seeds': skin,
            'method': 'bisenet_resnet18_onnx', 'model': MODEL_ID,
            'warnings': ['O modelo não possui uma classe específica de barba; pelos faciais podem permanecer na máscara. Não detecta acne, rosácea ou vitiligo.']}


def facial_masks(rgb):
    return masks_from_labels(predict_labels(rgb))


def measure_skin(lab, masks):
    # Todas as regiões classificadas como pele participam, mesmo desconectadas
    # ou com cores diferentes. Não há crescimento, erosão ou corte por brilho.
    mask = masks['allowed']
    return {'mask': mask, 'mean_lab': lab[mask].mean(axis=0)}
