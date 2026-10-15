"""Converte fontes verificadas para ONNX e exige paridade antes de instalar.

Uso no ambiente separado: python -m backend.export_models acne vitiligo.
Não baixa dependências, pesos ou imagens. A equivalência numérica não valida
qualidade de segmentação: o piloto anotado continua necessário.
"""

import argparse
import copy
import importlib.metadata
import json
import os
import shutil
from pathlib import Path
import tempfile

import cv2
import numpy as np

from .src.segmentation.model_asset import ASSETS, file_sha256
from .src.skin_selection.contracts import Transform
from .src.skin_selection.runtime import imagenet_tensor


def install_file(source, destination):
    """Publica com as permissões do diretório de modelos, não do temporário privado."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            with source.open('rb') as stream:
                shutil.copyfileobj(stream, output)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_model(key):
    import torch
    asset = ASSETS[key]
    source = asset.path.with_suffix('.pth' if key == 'acne' else '.pt')
    if file_sha256(source) != asset.source_sha256:
        raise ValueError('Checksum da fonte inválido; exportação cancelada.')
    torch.set_num_threads(2)
    if key == 'acne':
        import segmentation_models_pytorch as smp
        model = smp.Unet(encoder_name='resnet34', encoder_weights=None, in_channels=3, classes=1)
        model.load_state_dict(torch.load(source, map_location='cpu', weights_only=True), strict=True)
        return model.eval(), 256, {'0': 'acne'}
    os.environ.setdefault('YOLO_CONFIG_DIR', str(asset.path.parent / '.export-config'))
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    from ultralytics import YOLO
    wrapper = YOLO(str(source), task='segment')
    names = {str(k): v for k, v in wrapper.names.items()}
    if len(names) != 1 or names['0'].strip().lower() != 'vitiligo':
        raise ValueError(f'Classes de vitiligo não auditadas: {names}')
    model = copy.deepcopy(wrapper.model).cpu().float().eval().fuse(verbose=False)
    head = model.model[-1]
    if head.nc != 1 or head.nm != 32:
        raise ValueError('Cabeça YOLO incompatível.')
    head.export, head.format, head.dynamic = True, 'onnx', False
    return model, 416, names


def input_views(key, size):
    rng = np.random.default_rng(204)
    images = [rng.integers(0, 256, (71, 113, 3), dtype=np.uint8),
              np.full((113, 71, 3), [90, 58, 42], np.uint8)]
    samples = Path(__file__).resolve().parents[1] / 'samples'
    for path in sorted(samples.glob('*.jpeg')):
        image = cv2.imread(str(path))
        if image is not None:
            images.append(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    for rgb in images:
        view, transform = Transform.prepare(rgb, size, letterbox=key == 'vitiligo')
        tensor = imagenet_tensor(view) if key == 'acne' else (view.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        yield np.ascontiguousarray(tensor), transform


def export(key):
    import torch
    import onnxruntime as ort
    asset = ASSETS[key]
    model, size, names = prepare_model(key)
    views = list(input_views(key, size))
    with tempfile.TemporaryDirectory(dir=asset.path.parent) as directory:
        target = Path(directory) / asset.filename
        sample = torch.from_numpy(views[0][0])
        with torch.inference_mode():
            model(sample)  # Inicializa âncoras YOLO antes do trace.
            torch.onnx.export(model, sample, str(target), input_names=['image'],
                              output_names=['logits'] if key == 'acne' else ['detections', 'prototypes'],
                              opset_version=17, dynamo=False, do_constant_folding=True)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        session = ort.InferenceSession(str(target), sess_options=options, providers=['CPUExecutionProvider'])
        max_errors, agreements = [], []
        for tensor, transform in views:
            with torch.inference_mode():
                expected = model(torch.from_numpy(tensor))
            expected = [expected] if isinstance(expected, torch.Tensor) else list(expected)
            expected = [value.detach().cpu().numpy() for value in expected]
            actual = session.run(None, {'image': tensor})
            for first, second in zip(expected, actual, strict=True):
                np.testing.assert_allclose(first, second, rtol=2e-3, atol=2e-3)
                max_errors.append(float(np.max(np.abs(first - second))))
            if key == 'acne':
                from .src.skin_selection.runtime import sigmoid
                for threshold in (.2, .5):
                    first = transform.restore(sigmoid(expected[0][0, 0])) >= threshold
                    second = transform.restore(sigmoid(actual[0][0, 0])) >= threshold
                    union = (first | second).sum()
                    agreement = float((first & second).sum() / union) if union else 1.
                    agreements.append(agreement)
            else:
                from .src.skin_selection.vitiligo import decode
                for first, second in zip(decode(expected, transform), decode(actual, transform), strict=True):
                    union = (first | second).sum()
                    agreements.append(float((first & second).sum() / union) if union else 1.)
        if min(agreements) < .99:
            raise ValueError(f'Máscaras divergentes na exportação: {agreements}')
        manifest = {'version': asset.version, 'source_sha256': asset.source_sha256,
                    'sha256': file_sha256(target), 'classes': names, 'opset': 17,
                    'parity_passed': True, 'parity_inputs': len(views),
                    'max_absolute_error': max(max_errors), 'min_mask_iou': min(agreements),
                    'versions': {package: importlib.metadata.version(package) for package in
                                 ('torch', 'onnx', 'onnxruntime', 'segmentation-models-pytorch', 'ultralytics')},
                    'segmentation_quality_validated': False}
        manifest_path = Path(directory) / asset.path.with_suffix('.json').name
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
        del session
        install_file(target, asset.path)
        install_file(manifest_path, asset.path.with_suffix('.json'))
        print(json.dumps({'model': key, **manifest}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='+', choices=['acne', 'vitiligo'])
    for model_key in parser.parse_args().models:
        export(model_key)
