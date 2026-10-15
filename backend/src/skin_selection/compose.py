"""União sem dupla contagem; evidências e previsões externas preservadas."""

import cv2
import numpy as np

from .contracts import CATEGORIES, ModuleResult


def regions_for(mask, reason, source, state):
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    return [{"reason": reason, "source": source, "state": state,
             "bbox": [int(v) for v in stats[i, :4]], "area_pixels": int(stats[i, 4]),
             "evidence_ref": f"module_status.{reason}.evidence",
             "coordinate_space": "recorte_rgb"} for i in range(1, count)]


def compose(anatomy, modules):
    if anatomy.ndim != 2 or anatomy.dtype != bool:
        raise ValueError("Anatomia deve ser máscara bool (H, W).")
    accepted = {}
    uncertainty = np.zeros_like(anatomy)
    excluded = np.zeros_like(anatomy)
    statuses, versions, regions, debug = {}, {}, [], {}
    for key in CATEGORIES:
        result = modules.get(key, ModuleResult.empty(anatomy.shape))
        result.validate(anatomy.shape)
        accepted[key] = result.accepted & anatomy
        excluded |= accepted[key]
        uncertainty |= result.uncertain & anatomy
        statuses[key] = {"state": result.status, "reason": result.reason, "source": result.source,
                         "elapsed_ms": round(result.elapsed_ms, 2), "evidence": result.evidence,
                         "detected": bool(accepted[key].any()) if result.status == "executado" else None,
                         "accepted_pixels": int(accepted[key].sum()),
                         "uncertain_pixels": int((result.uncertain & anatomy).sum())}
        versions[key] = result.version
        debug[key] = {"raw_accepted": result.accepted, "raw_uncertain": result.uncertain,
                      **result.debug_masks}
        for mask, state in ((accepted[key], "aceita"), (result.uncertain & anatomy, "incerta")):
            regions.extend(regions_for(mask, key, result.source, state))
    return {"anatomical_mask": anatomy.copy(), "accepted_masks": accepted,
            "excluded_mask": excluded, "uncertain_mask": uncertainty,
            "valid_mask": anatomy & ~excluded & ~uncertainty,
            "module_status": statuses, "regions": regions, "model_versions": versions,
            "debug_masks": debug}
