"""Algoritmo alternativo por média de 3 pontos aleatórios na máscara de pele e métricas comparativas."""

import hashlib
from time import perf_counter

import numpy as np
from skimage.color import lab2rgb

from ..distributed.native import ciede2000_one_to_many
from ..segmentation.color import rgb_to_lab
from .matching import rank_foundations, validate_lab


def _lab_to_hex(lab_vec) -> str:
    rgb_u8 = np.rint(lab2rgb(np.asarray(lab_vec, dtype=np.float64)) * 255).astype(np.uint8)
    return "#{:02x}{:02x}{:02x}".format(int(rgb_u8[0]), int(rgb_u8[1]), int(rgb_u8[2]))


def _derive_seed(lab_pixels: np.ndarray, shape: tuple[int, int]) -> int:
    """Gera semente determinística por foto/máscara para paridade entre JSON, NDJSON e nós P2P."""
    step = max(1, len(lab_pixels) // 512)
    sample_bytes = np.ascontiguousarray(lab_pixels[::step], dtype=np.float32).tobytes()
    digest = hashlib.blake2b(
        f"{shape[0]}x{shape[1]}:{len(lab_pixels)}:".encode("ascii") + sample_bytes,
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big")


def three_random_points_tone(
    lab_image: np.ndarray,
    skin_mask: np.ndarray,
    *,
    rgb_image: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
    seed: int | None = None,
) -> dict:
    """Seleciona 3 pontos aleatórios da máscara de pele e calcula sua média simples em CIELAB."""
    t0 = perf_counter()
    lab_arr = np.asarray(lab_image, dtype=np.float32)
    mask_arr = np.asarray(skin_mask, dtype=bool)
    if lab_arr.ndim != 3 or lab_arr.shape[2] != 3 or mask_arr.shape != lab_arr.shape[:2]:
        raise ValueError("lab_image (H, W, 3) e skin_mask bool (H, W) devem estar alinhados.")
    if not mask_arr.any():
        raise ValueError("A máscara de pele para amostragem de 3 pontos não pode estar vazia.")

    yy, xx = np.nonzero(mask_arr)
    skin_pixels_lab = lab_arr[yy, xx]
    actual_seed = _derive_seed(skin_pixels_lab, mask_arr.shape) if seed is None else int(seed)
    rng = np.random.default_rng(actual_seed)

    total_candidates = len(yy)
    chosen_idx = rng.choice(total_candidates, size=3, replace=total_candidates < 3)

    sampled_labs = skin_pixels_lab[chosen_idx].astype(np.float64)
    mean_lab = validate_lab(sampled_labs.mean(axis=0))
    elapsed_ms = (perf_counter() - t0) * 1000.0

    points = []
    for order, idx in enumerate(chosen_idx, start=1):
        py, px = int(yy[idx]), int(xx[idx])
        pt_lab = validate_lab(sampled_labs[order - 1])
        if rgb_image is not None and rgb_image.shape[:2] == mask_arr.shape:
            r, g, b = (int(v) for v in rgb_image[py, px])
            pt_hex = f"#{r:02x}{g:02x}{b:02x}"
        else:
            pt_hex = _lab_to_hex(pt_lab)
        in_strict_valid = bool(valid_mask[py, px]) if valid_mask is not None and valid_mask.shape == mask_arr.shape else True
        points.append({
            "indice": order,
            "x": px,
            "y": py,
            "lab": [round(float(v), 4) for v in pt_lab],
            "hex": pt_hex,
            "em_pele_valida": in_strict_valid,
        })

    return {
        "lab": [round(float(v), 4) for v in mean_lab],
        "_lab_raw": mean_lab,
        "cor_pele_hex": _lab_to_hex(mean_lab),
        "pixels_candidatos": int(total_candidates),
        "pixels_considerados": 3,
        "pontos": points,
        "tempo_amostragem_ms": elapsed_ms,
        "seed": actual_seed,
    }


def _resolve_masks_and_lab(skin: dict, selection: dict, full_lab: np.ndarray, lab_image: np.ndarray | None):
    candidates = (
        ("pele_anatomica_inicial", selection.get("anatomical_mask")),
        ("mascara_medicao", selection.get("measurement_mask")),
        ("pele_valida", selection.get("valid_mask")),
        ("mascara_pele", skin.get("mask")),
    )
    mask_name = "mascara_pele"
    chosen_mask = None
    for name, m in candidates:
        if isinstance(m, np.ndarray) and m.dtype == bool and m.ndim == 2 and m.any():
            mask_name = name
            chosen_mask = m
            break
    if chosen_mask is None:
        chosen_mask = np.ones((8, 8), dtype=bool)
        mask_name = "mascara_sintetica"

    valid_mask = selection.get("valid_mask")
    if not (isinstance(valid_mask, np.ndarray) and valid_mask.shape == chosen_mask.shape):
        valid_mask = chosen_mask

    if lab_image is None or lab_image.shape[:2] != chosen_mask.shape:
        synth = np.empty((*chosen_mask.shape, 3), dtype=np.float32)
        synth[:] = np.asarray(skin.get("median_lab", full_lab), dtype=np.float32)
        lab_image = synth

    return mask_name, chosen_mask, valid_mask, lab_image


def compare_tone_algorithms(
    *,
    full_lab,
    full_recommendations: list[dict],
    full_estimator: str,
    full_pixel_count: int,
    catalog: list[dict],
    skin: dict,
    selection: dict,
    lab_image: np.ndarray | None = None,
    rgb_image: np.ndarray | None = None,
    seed: int | None = None,
    monte_carlo_runs: int = 200,
) -> dict:
    """Executa o algoritmo de 3 pontos aleatórios e gera métricas comparativas completas."""
    t_total_start = perf_counter()
    full_lab_arr = validate_lab(full_lab)
    mask_source, candidate_mask, valid_mask, resolved_lab = _resolve_masks_and_lab(
        skin, selection, full_lab_arr, lab_image
    )

    sample_res = three_random_points_tone(
        resolved_lab,
        candidate_mask,
        rgb_image=rgb_image,
        valid_mask=valid_mask,
        seed=seed,
    )
    rand_lab_arr = sample_res["_lab_raw"]
    rand_recommendations = rank_foundations(rand_lab_arr, catalog, limit=3)
    total_3pt_ms = (perf_counter() - t_total_start) * 1000.0

    # Distâncias perceptuais e euclidianas entre os dois algoritmos
    de00_between = float(ciede2000_one_to_many(full_lab_arr, rand_lab_arr[None, :])[0])
    diff_lab = rand_lab_arr - full_lab_arr
    de76_between = float(np.linalg.norm(diff_lab))

    full_ids = [p["id"] for p in full_recommendations]
    rand_ids = [p["id"] for p in rand_recommendations]
    same_top1 = bool(full_ids and rand_ids and full_ids[0] == rand_ids[0])
    overlap_top3 = len(set(full_ids) & set(rand_ids))
    overlap_pct = round(100.0 * overlap_top3 / max(len(full_ids), 1), 2)
    points_outside_valid = sum(0 if pt["em_pele_valida"] else 1 for pt in sample_res["pontos"])

    # Avaliação de estabilidade por Monte Carlo (variabilidade intrínseca de sortear apenas 3 pixels)
    yy, xx = np.nonzero(candidate_mask)
    skin_pixels = resolved_lab[yy, xx].astype(np.float64)
    n_cand = len(skin_pixels)
    mc_rng = np.random.default_rng(sample_res["seed"] ^ 0xA5A5_5A5A)
    runs = max(10, int(monte_carlo_runs))
    mc_indices = mc_rng.integers(0, n_cand, size=(runs, 3))
    mc_means = np.clip(skin_pixels[mc_indices].mean(axis=1), [0.0, -500.0, -500.0], [100.0, 500.0, 500.0])

    mc_de_vs_full = ciede2000_one_to_many(full_lab_arr, mc_means)
    mc_center = np.median(mc_means, axis=0)
    mc_internal_spread = ciede2000_one_to_many(mc_center, mc_means)

    # Concordância exata Top-1 no catálogo ao longo das rodadas Monte Carlo
    rgb_rows = np.array(
        [[int(p["hex"][1:3], 16), int(p["hex"][3:5], 16), int(p["hex"][5:7], 16)] for p in catalog],
        dtype=np.uint8,
    )
    catalog_labs = rgb_to_lab(rgb_rows).astype(np.float64)
    catalog_ids = np.array([p["id"] for p in catalog], dtype=np.int64)
    order_by_id = np.argsort(catalog_ids, kind="stable")
    sorted_labs = catalog_labs[order_by_id]
    sorted_ids = catalog_ids[order_by_id]

    full_top1_id = full_ids[0] if full_ids else None
    agree_count = 0
    for row_lab in mc_means:
        dists = ciede2000_one_to_many(row_lab, sorted_labs)
        best_id = int(sorted_ids[int(np.argmin(dists))])
        if best_id == full_top1_id:
            agree_count += 1

    return {
        "metodo_referencia": "pipeline_completo_regional_v3",
        "metodo_comparado": "media_3_pontos_aleatorios_mascara",
        "mascara_amostrada": mask_source,
        "pipeline_completo": {
            "nome": "Pipeline completo (segmentação + exclusões + consenso regional)",
            "estimador": full_estimator,
            "lab": [round(float(v), 4) for v in full_lab_arr],
            "cor_pele_hex": _lab_to_hex(full_lab_arr),
            "pixels_considerados": int(full_pixel_count),
            "recomendacoes": [
                {
                    "id": p["id"],
                    "marca": p["marca"],
                    "nome": p["nome"],
                    "cor": p["cor"],
                    "hex": p["hex"],
                    "preco": p["preco"],
                    "link": p["link"],
                    "delta_e00": round(float(p["delta_e00"]), 4),
                }
                for p in full_recommendations
            ],
        },
        "tres_pontos_aleatorios": {
            "nome": "Média de 3 pontos aleatórios da máscara",
            "estimador": "media_aritmetica_3_pixels",
            "lab": sample_res["lab"],
            "cor_pele_hex": sample_res["cor_pele_hex"],
            "pixels_candidatos": sample_res["pixels_candidatos"],
            "pixels_considerados": 3,
            "pontos": sample_res["pontos"],
            "tempo_execucao_ms": round(float(total_3pt_ms), 3),
            "recomendacoes": [
                {
                    "id": p["id"],
                    "marca": p["marca"],
                    "nome": p["nome"],
                    "cor": p["cor"],
                    "hex": p["hex"],
                    "preco": p["preco"],
                    "link": p["link"],
                    "delta_e00": round(float(p["delta_e00"]), 4),
                }
                for p in rand_recommendations
            ],
        },
        "metricas": {
            "delta_e00_entre_algoritmos": round(de00_between, 4),
            "delta_e76_entre_algoritmos": round(de76_between, 4),
            "diferenca_lab": {
                "delta_l": round(float(diff_lab[0]), 4),
                "delta_a": round(float(diff_lab[1]), 4),
                "delta_b": round(float(diff_lab[2]), 4),
            },
            "mesma_base_top1": same_top1,
            "intersecao_top3": overlap_top3,
            "taxa_acordo_top3_pct": overlap_pct,
            "pontos_fora_pele_estrita": int(points_outside_valid),
            "proporcao_amostrada_pct": round(100.0 * 3 / max(sample_res["pixels_candidatos"], 1), 4),
            "estabilidade_monte_carlo": {
                "rodadas": runs,
                "delta_e00_medio_vs_pipeline": round(float(mc_de_vs_full.mean()), 4),
                "delta_e00_mediana_vs_pipeline": round(float(np.median(mc_de_vs_full)), 4),
                "delta_e00_p90_vs_pipeline": round(float(np.percentile(mc_de_vs_full, 90)), 4),
                "dispersao_interna_p90_delta_e00": round(float(np.percentile(mc_internal_spread, 90)), 4),
                "concordancia_top1_pct": round(100.0 * agree_count / runs, 2),
            },
        },
    }
