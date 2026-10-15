"""Instala modelos fixados; padrão BiSeNet, ou all --sources para a seleção."""

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
import argparse

from backend.src.segmentation.model_asset import ASSETS


def download_asset(url, destination, expected):
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
        print(f'{destination.name} já instalado e verificado.')
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            print(f'Baixando {destination.name}...', flush=True)
            with urllib.request.urlopen(url, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError('Checksum do modelo diferente do esperado. O arquivo não foi instalado.')
        os.replace(temporary, destination)
        print(f'Modelo verificado e instalado em {destination}')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_model(key="bisenet", *, sources=False):
    asset = ASSETS[key]
    if asset.source_sha256:
        if not sources:
            raise ValueError(f'{key}: use --sources e depois python -m backend.export_models {key}.')
        suffix = '.pth' if key == 'acne' else '.pt'
        download_asset(asset.source_url, asset.path.with_suffix(suffix), asset.source_sha256)
    else:
        download_asset(asset.url, asset.path, asset.sha256)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='*', metavar='MODEL', help='bisenet, barba, acne, vitiligo ou all; padrão: bisenet')
    parser.add_argument('--sources', action='store_true', help='Baixar pesos PyTorch para conversão offline.')
    args = parser.parse_args()
    if any(key not in (*ASSETS, 'all') for key in args.models):
        parser.error('Modelo desconhecido. Use bisenet, barba, acne, vitiligo ou all.')
    for key in (ASSETS if 'all' in args.models else (args.models or ['bisenet'])):
        download_model(key, sources=args.sources)
