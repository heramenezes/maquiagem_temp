"""Peso público fixado; nenhuma foto ou modelo é enviado/baixado na análise."""

from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parents[2] / 'models' / 'resnet18.onnx'
MODEL_URL = 'https://github.com/yakhyo/face-parsing/releases/download/v0.0.1/resnet18.onnx'
MODEL_SHA256 = '0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f'
MODEL_ID = 'yakhyo/face-parsing:resnet18:v0.0.1'
