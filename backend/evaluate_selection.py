"""Avaliação offline com máscaras humanas no referencial do recorte RGB.

python -m backend.evaluate_selection manifest.json --split test --output report.json
Não anota fotos, não ajusta limiares e não declara validação automaticamente.
"""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from .src.segmentation.color import rgb_to_lab
from .src.segmentation.semantic import facial_masks
from .src.skin_selection.contracts import CATEGORIES
from .src.skin_selection.compose import compose
from .src.skin_selection.pipeline import run_module, finish


def validate_manifest(records):
    if not isinstance(records, list) or not records:
        raise ValueError('O manifesto deve conter uma lista não vazia.')
    people, ids = {}, set()
    for row in records:
        for field in ('id', 'person_id', 'split', 'image', 'valid_mask', 'exclusions', 'tone_group', 'lighting'):
            if field not in row:
                raise ValueError(f'Campo obrigatório ausente: {field}')
        if row['split'] not in ('train', 'validation', 'test'):
            raise ValueError('split deve ser train, validation ou test.')
        if not row['person_id'] or row['id'] in ids:
            raise ValueError('Pessoa ausente ou id duplicado.')
        ids.add(row['id'])
        person = row['person_id']
        if person in people and people[person] != row['split']:
            raise ValueError(f'Pessoa em mais de uma divisão: {person}')
        people[person] = row['split']
        if set(row['exclusions']) != set(CATEGORIES):
            raise ValueError('Anote os quatro motivos, inclusive máscaras vazias para negativos.')


def read_mask(path, shape):
    with Image.open(path) as image:
        values = np.array(image)
    if values.shape != shape or not np.isin(values, [0, 255]).all():
        raise ValueError(f'Máscara deve ser PNG binário 0/255 e alinhada: {path}')
    return values > 0


def mask_metrics(predicted, expected):
    tp = int((predicted & expected).sum())
    fp = int((predicted & ~expected).sum())
    fn = int((~predicted & expected).sum())
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None,
            'iou': tp / (tp + fp + fn) if tp + fp + fn else 1.,
            'dice': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.}


def selection_metrics(mask, reference, lab):
    from skimage.color import deltaE_ciede2000
    color = None
    if mask.any() and reference.any():
        mean = lab[mask].mean(axis=0)
        manual_mean = lab[reference].mean(axis=0)
        color = {'delta_lab': (mean - manual_mean).tolist(),
                 'delta_e00': float(deltaE_ciede2000(mean, manual_mean))}
    return {**mask_metrics(mask, reference), 'selected_pixels': int(mask.sum()),
            'valid_skin_removed_fraction': float((reference & ~mask).sum() / max(1, reference.sum())),
            'remaining_contamination_fraction': float((mask & ~reference).sum() / max(1, mask.sum())),
            'color_comparison_research_only': color}


def evaluate_record(row, root):
    with Image.open(root / row['image']) as image:
        # Manifesto exige recortes já orientados/convertidos a sRGB; não redimensiona anotações.
        rgb = np.asarray(image.convert('RGB'))
    if max(rgb.shape[:2]) > 1600:
        raise ValueError('O manifesto deve usar recortes de no máximo 1600 pixels.')
    reference = read_mask(root / row['valid_mask'], rgb.shape[:2])
    exclusions = {key: read_mask(root / path, rgb.shape[:2]) for key, path in row['exclusions'].items()}
    if any((mask & reference).any() for mask in exclusions.values()):
        raise ValueError('Pele manual válida não pode sobrepor exclusões manuais.')
    start = perf_counter()
    lab = rgb_to_lab(rgb)
    anatomy = facial_masks(rgb)
    modules = {key: run_module(key, rgb, anatomy) for key in ('acne', 'vitiligo', 'barba')}
    selected = finish(rgb, lab, anatomy, modules)
    elapsed = (perf_counter() - start) * 1000
    variants = {'bisenet': anatomy['allowed'], 'manual': reference,
                'especialistas': compose(anatomy['allowed'], modules)['valid_mask'],
                'completa': selected['valid_mask'],
                'contraste': finish(rgb, lab, anatomy, {})['valid_mask']}
    for key in modules:
        variants[key] = compose(anatomy['allowed'], {key: modules[key]})['valid_mask']
    return {'id': row['id'], 'person_id': row['person_id'], 'split': row['split'],
            'tone_group': row['tone_group'], 'lighting': row['lighting'],
            'tags': row.get('tags', []), 'elapsed_ms': elapsed,
            'module_status': selected['module_status'], 'quality': selected['quality'],
            'model_versions': selected['model_versions'],
            'by_reason': {key: mask_metrics(selected['accepted_masks'][key], mask)
                          for key, mask in exclusions.items()},
            'variants': {key: selection_metrics(mask, reference, lab) for key, mask in variants.items()}}


def report(records, root, split):
    import psutil
    validate_manifest(records)
    rows = [row for row in records if row['split'] == split]
    if not rows:
        raise ValueError(f'Nenhuma foto em {split}.')
    results = []
    for row in rows:
        try:
            results.append(evaluate_record(row, root))
        except Exception as exc:
            results.append({'id': row['id'], 'person_id': row['person_id'], 'split': split,
                            'error': f'{type(exc).__name__}: {exc}'})
    # Não chama de fria a primeira foto bem-sucedida se uma anterior falhou.
    warm = [row['elapsed_ms'] for row in results[1:] if 'elapsed_ms' in row]
    memory = psutil.Process().memory_info()
    return {'split': split, 'photos': len(rows), 'people': len({r['person_id'] for r in rows}),
            'failed_photos': sum('error' in row for row in results),
            'unavailable_or_failed_modules': sum(
                status['state'] != 'executado' for row in results
                for status in row.get('module_status', {}).values()),
            'cold_ms': results[0].get('elapsed_ms'),
            'warm_p50_ms': float(np.percentile(warm, 50)) if warm else None,
            'warm_p95_ms': float(np.percentile(warm, 95)) if warm else None,
            'process_rss_bytes': memory.rss, 'process_peak_wset_bytes': getattr(memory, 'peak_wset', None),
            'quality_validated': False,
            'note': 'Comparações de cor offline incluem máscaras reprovadas; não são medições liberadas pela API.',
            'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--split', choices=['train', 'validation', 'test'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.manifest.read_text(encoding='utf8'))
    result = report(records, args.manifest.parent, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(f"{result['photos']} fotos; {result['failed_photos']} falhas. Relatório: {args.output}")
