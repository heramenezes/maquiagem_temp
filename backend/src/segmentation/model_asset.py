"""Peso público fixado; nenhuma foto ou modelo é enviado/baixado na análise."""

from pathlib import Path
from dataclasses import dataclass
import hashlib
import json

MODEL_PATH = Path(__file__).resolve().parents[2] / 'models' / 'resnet18.onnx'
MODEL_URL = 'https://github.com/yakhyo/face-parsing/releases/download/v0.0.1/resnet18.onnx'
MODEL_SHA256 = '0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f'
MODEL_ID = 'yakhyo/face-parsing:resnet18:v0.0.1'


@dataclass(frozen=True)
class Asset:
    key: str
    filename: str
    url: str
    sha256: str | None
    version: str
    source_sha256: str | None = None
    source_url: str | None = None

    @property
    def path(self):
        return MODEL_PATH.parent / self.filename

    def metadata(self):
        data = {"id": self.key, "version": self.version, "sha256": self.sha256,
                "source_sha256": self.source_sha256, "source": self.source_url or self.url}
        if self.source_sha256:
            try:
                manifest = json.loads(self.path.with_suffix(".json").read_text(encoding="utf8"))
                data["sha256"] = manifest["sha256"]
                data["export"] = manifest
            except (OSError, ValueError, KeyError):
                pass
        return data


EASY_REVISION = "19e22b9d1bfd87e67b82e4b2749405686aeecba2"
ACNE_REVISION = "f036e69c3a2e87ddbe4dfd4543c9d0ecc9b5ba8c"
VITILIGO_REVISION = "409da766d3deef87e41545928acac3ab815384ea"
ASSETS = {
    "bisenet": Asset("bisenet", "resnet18.onnx", MODEL_URL, MODEL_SHA256, MODEL_ID),
    "barba": Asset("barba", "segformer_b0_fp_512.onnx",
                   f"https://huggingface.co/sadzip/EasyPortrait-ONNX/resolve/{EASY_REVISION}/segformer_b0_fp_512.onnx",
                   "6be671f5cd146ecaebc982d6f2598889e804bb3cb90a619fb95842afb7d22d0b",
                   f"easyportrait-segformer-b0-fp:{EASY_REVISION}"),
    "acne": Asset("acne", "acne_unet.onnx", "", None, "acne-unet-resnet34-export-v1",
                  "c58a6af6fb622d916e4aa788d9f620d59df4a42209f655ce4a9db49686c05697",
                  f"https://huggingface.co/spaces/RihemXX/Acnes/resolve/{ACNE_REVISION}/Acnes_model.pth"),
    "vitiligo": Asset("vitiligo", "vitiligo_yolo.onnx", "", None, "vitiligo-yolo11n-export-v1",
                      "9558d5be11e1657f6e6c9d27bc4839f5fa5b2aaeea10868837b45509608e0f09",
                      f"https://raw.githubusercontent.com/rayronvictor/vitiligo-segmentation/{VITILIGO_REVISION}/models/vitiligon-seg.pt"),
}


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_asset(asset):
    expected = asset.sha256
    if asset.source_sha256:
        manifest = json.loads(asset.path.with_suffix(".json").read_text(encoding="utf8"))
        if (manifest.get("source_sha256") != asset.source_sha256 or
                manifest.get("version") != asset.version or manifest.get("parity_passed") is not True):
            raise ValueError("Manifesto de conversão incompatível ou sem equivalência verificada.")
        expected = manifest["sha256"]
    if not expected or file_sha256(asset.path) != expected:
        raise ValueError("SHA-256 do modelo diferente do esperado.")
