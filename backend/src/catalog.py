"""Catálogo real: o CSV é a única fonte dos dados de produtos."""

import csv
import json
from functools import lru_cache
from decimal import Decimal
from pathlib import Path
import re
import threading
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "bases.csv"
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")
_catalog_cache = {}
_catalog_lock = threading.Lock()


@lru_cache(maxsize=1)
def product_images():
    """Fotos locais das linhas do catálogo, com origem registrada no manifesto."""
    path = CATALOG_PATH.with_name("product_images.json")
    with path.open(encoding="utf-8") as source:
        return {(row["marca"], row["nome"]): row["imagem"] for row in json.load(source)}


def _parse_catalog(target: Path):
    products = []
    images = product_images()
    with target.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            color = row["codigocor"].strip()
            link = row["link"].strip()
            parsed = urlparse(link)
            if not _HEX_RE.fullmatch(color):
                raise ValueError(f"Cor inválida no catálogo: {row['id']}")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Link inválido no catálogo: {row['id']}")
            marca = row["marca"].strip()
            nome = row["nomebase"].strip()
            products.append({
                "id": int(row["id"]), "marca": marca,
                "nome": nome, "cor": row["nomecor"].strip(),
                "hex": color.upper(),
                "preco": float(Decimal(row["preco"].strip().replace(",", "."))),
                "link": link,
                "imagem": images.get((marca, nome)),
            })
    return tuple(products)


def load_catalog(path=CATALOG_PATH):
    target = Path(path)
    resolved = target.resolve()
    stat = target.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _catalog_lock:
        cached = _catalog_cache.get(resolved)
        if cached is None or cached[0] != stamp:
            cached = (stamp, _parse_catalog(target))
            _catalog_cache[resolved] = cached
    return [dict(item) for item in cached[1]]
