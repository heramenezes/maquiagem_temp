"""Segmentação inicial inspirada nas seções 4.1–4.2 do artigo do projeto.

K adaptativo por variância residual em a*/b* + crescimento por conectividade.
Esta é uma adaptação acadêmica, não reprodução exata de Islam et al. (2024).
Máscaras geométricas/landmarks e limiares relativos são heurísticas; não são
um classificador semântico de barba/cabelo nem detector de doenças de pele.
"""

import cv2
import numpy as np

from backend.src.preprocessing.face_segmenter import INDICES_OVAL_FACIAL


class InsufficientSkinError(ValueError):
    pass


def ellipse(shape, center, axes):
    h, w = shape[:2]
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (round(center[0] * w), round(center[1] * h)),
                (max(1, round(axes[0] * w)), max(1, round(axes[1] * h))),
                0, 0, 360, 1, -1)
    return mask.astype(bool)


def facial_masks(rgb, *, use_landmarks=True):
    """Contorno facial, exclusões permanentes e sementes de pele provável.

    Recebe o recorte RGB com margem produzido pelo detector existente.
    No fallback, a foto precisa ser frontal: proporções são aproximadas.
    """
    shape = rgb.shape[:2]
    face = ellipse(shape, (0.5, 0.5), (0.35, 0.39))
    excluded = np.zeros(shape, bool)
    method = "geometria_frontal"
    warnings = []
    landmarks = None
    if use_landmarks:
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions"):
                with mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True, max_num_faces=1,
                    refine_landmarks=False, min_detection_confidence=0.5,
                ) as mesh:
                    result = mesh.process(rgb)
                if result.multi_face_landmarks:
                    landmarks = result.multi_face_landmarks[0].landmark
        except (ImportError, RuntimeError, AttributeError):
            pass

    if landmarks is not None:
        h, w = shape
        points = np.array([[round(p.x * w), round(p.y * h)] for p in landmarks], np.int32)
        face_u8 = np.zeros(shape, np.uint8)
        cv2.fillPoly(face_u8, [points[INDICES_OVAL_FACIAL]], 1)
        face = cv2.erode(face_u8, np.ones((3, 3), np.uint8)).astype(bool)
        exclusion_u8 = np.zeros(shape, np.uint8)
        mesh_api = mp.solutions.face_mesh
        for connections in (mesh_api.FACEMESH_LEFT_EYE, mesh_api.FACEMESH_RIGHT_EYE,
                            mesh_api.FACEMESH_LEFT_EYEBROW, mesh_api.FACEMESH_RIGHT_EYEBROW,
                            mesh_api.FACEMESH_LIPS):
            indices = sorted({idx for edge in connections for idx in edge})
            cv2.fillConvexPoly(exclusion_u8, cv2.convexHull(points[indices]), 1)
        radius = max(1, round(min(shape) * 0.015))
        excluded = cv2.dilate(exclusion_u8, np.ones((radius * 2 + 1,) * 2, np.uint8)).astype(bool)
        method = "mediapipe_face_mesh"
    else:
        # Olhos e sobrancelhas são excluídos mesmo que a cor se pareça com pele.
        for x in (0.34, 0.66):
            excluded |= ellipse(shape, (x, 0.41), (0.155, 0.085))
            excluded |= ellipse(shape, (x, 0.32), (0.17, 0.055))
        excluded |= ellipse(shape, (0.5, 0.72), (0.20, 0.095))
        # Adiciona olhos encontrados fora das regiões esperadas, sem desfazer
        # exclusões conservadoras quando o Haar não consegue detectar olhos.
        detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        for x, y, w, h in detector.detectMultiScale(gray, 1.1, 4, minSize=(8, 8)):
            if y + h / 2 < shape[0] * 0.58:
                excluded[max(0, y - h // 4):min(shape[0], y + h + h // 4),
                         max(0, x - w // 8):min(shape[1], x + w + w // 8)] = True
        warnings.append("Contorno e exclusões aproximados para rosto frontal; revise a máscara, especialmente em fotos inclinadas.")

    allowed = face & ~excluded
    seeds = np.zeros(shape, bool)
    for center, axes in [((0.30, 0.55), (0.06, 0.045)),
                         ((0.70, 0.55), (0.06, 0.045)),
                         ((0.50, 0.24), (0.07, 0.035)),
                         ((0.50, 0.54), (0.035, 0.045))]:
        seeds |= ellipse(shape, center, axes)
    seeds &= allowed
    if seeds.sum() < 12 or allowed.sum() < 64:
        raise InsufficientSkinError("Aproxime o rosto e envie uma foto frontal com mais detalhes.")
    return {"face": face, "excluded": excluded, "allowed": allowed,
            "seeds": seeds, "method": method, "warnings": warnings}


def _fit_kmeans(data, k):
    """Inicialização determinística por maior distância, sem RNG global."""
    centers = [data[np.argmin(np.sum((data - np.median(data, axis=0)) ** 2, axis=1))]]
    while len(centers) < k:
        distances = np.min(np.sum((data[:, None] - np.array(centers)) ** 2, axis=2), axis=1)
        centers.append(data[np.argmax(distances)])
    centers = np.array(centers, np.float32)
    for _ in range(30):
        distances = np.sum((data[:, None] - centers) ** 2, axis=2)
        labels = distances.argmin(axis=1)
        updated = np.array([data[labels == i].mean(axis=0) if np.any(labels == i) else centers[i]
                            for i in range(k)])
        if np.max(np.abs(updated - centers)) < 0.02:
            centers = updated
            break
        centers = updated
    inertia = float(np.min(np.sum((data[:, None] - centers) ** 2, axis=2), axis=1).mean())
    return centers, inertia


def adaptive_clusters(lab, masks):
    """Agrupa só a*/b*: L* não decide a quantidade de grupos de cor.

    Escolhe o menor K de 1..6 que explica 88% da variância cromática; regiões
    praticamente uniformes usam K=1. Amostragem limitada mantém o custo baixo.
    """
    pixels = lab[..., 1:3][masks["allowed"]]
    rng = np.random.default_rng(0)
    sample = pixels[rng.choice(len(pixels), min(4000, len(pixels)), replace=False)]
    baseline = float(np.sum((sample - sample.mean(axis=0)) ** 2, axis=1).mean())
    centers, inertia = _fit_kmeans(sample, 1)
    for k in range(2, min(6, len(np.unique(sample, axis=0))) + 1):
        if baseline <= 1 or inertia <= baseline * 0.12:
            break
        centers, inertia = _fit_kmeans(sample, k)
    labels = np.full(lab.shape[:2], -1, np.int16)
    labels[masks["allowed"]] = np.sum((pixels[:, None] - centers) ** 2, axis=2).argmin(axis=1)
    votes = np.bincount(labels[masks["seeds"]], minlength=len(centers))
    skin_cluster = int(votes.argmax())
    core = masks["seeds"] & (labels == skin_cluster)
    if core.sum() < 8:
        raise InsufficientSkinError("Não encontramos uma região de pele consistente. Tente uma foto com luz uniforme.")
    return {"labels": labels, "centers": centers, "core": core,
            "skin_cluster": skin_cluster, "k": len(centers)}


def grow_skin(lab, masks, clusters):
    """Crescimento a partir das sementes, limitado por cor e contraste.

    Componentes conexos calculam o mesmo alcance de um flood-fill sobre o
    predicado fixo. As áreas excluídas nunca podem voltar para a máscara.
    """
    core_values = lab[clusters["core"]]
    reference = np.median(core_values, axis=0)
    all_seed_values = lab[masks["seeds"]]
    chroma_distance = np.linalg.norm(lab[..., 1:] - reference[1:], axis=2)
    seed_distances = np.linalg.norm(all_seed_values[:, 1:] - reference[1:], axis=1)
    chroma_limit = float(np.clip(np.percentile(seed_distances, 75) + 4, 6, 18))
    # Referência relativa à própria face: não rejeita tons escuros por L* absoluto.
    light_spread = np.median(np.abs(core_values[:, 0] - reference[0])) * 1.4826
    light_limit = float(np.clip(3 * light_spread + 12, 18, 35))
    luminance = lab[..., 0]
    smooth = cv2.GaussianBlur(luminance, (0, 0), max(1, min(luminance.shape) / 80))
    texture = np.abs(luminance - smooth)
    # Fios/barba geralmente têm contraste local alto ou L* muito distante das sementes.
    texture_limit = max(5.0, float(np.percentile(texture[clusters["core"]], 90) + 3))
    eligible = (masks["allowed"] & (chroma_distance <= chroma_limit)
                & (np.abs(luminance - reference[0]) <= light_limit)
                & (texture <= texture_limit))
    initial = eligible & (clusters["labels"] == clusters["skin_cluster"])
    _, components = cv2.connectedComponents(eligible.astype(np.uint8), connectivity=8)
    connected_seeds = np.unique(components[clusters["core"] & eligible])
    connected_seeds = connected_seeds[connected_seeds != 0]
    grown = np.isin(components, connected_seeds) & eligible
    cleaned = cv2.morphologyEx(grown.astype(np.uint8), cv2.MORPH_OPEN,
                              np.ones((3, 3), np.uint8)).astype(bool)
    cleaned &= masks["allowed"]
    if cleaned.sum() < max(64, masks["face"].sum() * 0.04):
        raise InsufficientSkinError("Não conseguimos separar pele suficiente. Tire outra foto de frente e com luz uniforme.")
    return {"mask": cleaned, "initial": initial,
            "recovered_pixels": int((cleaned & ~initial).sum()),
            "mean_lab": lab[cleaned].mean(axis=0),
            "chroma_limit": chroma_limit}
