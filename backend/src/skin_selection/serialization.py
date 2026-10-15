"""Contrato JSON: PNGs alinhados, denominadores explícitos e estados reais."""

import numpy as np

NAMES = {"acne": "Acne", "vitiligo": "Vitiligo", "barba": "Barba e bigode",
         "outras_regioes": "Outras regiões"}


def serialize_selection(selection, encode):
    def png(mask):
        return encode(mask.astype(np.uint8) * 255)

    total = int(selection["anatomical_mask"].sum())
    masks = {key: png(selection[key]) for key in
             ("anatomical_mask", "excluded_mask", "uncertain_mask", "valid_mask")}
    masks["accepted_masks"] = {key: png(mask) for key, mask in selection["accepted_masks"].items()}
    return {"schema_version": 1, "coordinate_space": "recorte_rgb", "masks": masks,
            "module_status": selection["module_status"], "regions": selection["regions"],
            "quality": selection["quality"], "model_versions": selection["model_versions"],
            "area_denominator": "pele_anatomica_inicial", "anatomical_pixels": total,
            "excluded_percent": round(100 * int(selection["excluded_mask"].sum()) / max(total, 1), 2),
            "percent_by_reason": {key: round(100 * int(mask.sum()) / max(total, 1), 2)
                                  for key, mask in selection["accepted_masks"].items()},
            "reasons_may_overlap": True,
            "debug_masks": {key: {name: png(mask) for name, mask in maps.items()}
                            for key, maps in selection["debug_masks"].items()}}


def conditions(selection):
    return [{"id": key, "nome": NAMES[key], "simulado": False,
             "detectada": status["detected"], "estado": status["state"],
             "descricao": ("Candidatos a pelos por EasyPortrait, localização e textura; sem classe específica de barba."
                           if key == "barba" else "Regiões candidatas à exclusão da medição de cor; não é diagnóstico."),
             "origem": status["source"], "intensidade": None, "local": None,
             "pixels_excluidos": status["accepted_pixels"], "pixels_incertos": status["uncertain_pixels"]}
            for key, status in selection["module_status"].items()]
