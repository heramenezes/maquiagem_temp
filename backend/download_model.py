"""Instala o peso fixado: python -m backend.download_model."""

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from backend.src.segmentation.model_asset import MODEL_PATH, MODEL_SHA256, MODEL_URL


def download_model():
    if MODEL_PATH.exists() and hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256:
        print('BiSeNet já instalado e verificado.')
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=MODEL_PATH.parent, suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            print('Baixando BiSeNet ResNet18 (aproximadamente 51 MB)...', flush=True)
            with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest() != MODEL_SHA256:
            raise RuntimeError('Checksum do modelo diferente do esperado. O arquivo não foi instalado.')
        os.replace(temporary, MODEL_PATH)
        print(f'Modelo verificado e instalado em {MODEL_PATH}')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    download_model()
