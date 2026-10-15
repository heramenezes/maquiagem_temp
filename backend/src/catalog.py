"""Catálogo real: o CSV é a única fonte dos dados de produtos."""

import csv
from decimal import Decimal
from pathlib import Path
import re
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "bases.csv"


def load_catalog(path=CATALOG_PATH):
    products = []
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            color = row["codigocor"].strip()
            link = row["link"].strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError(f"Cor inválida no catálogo: {row['id']}")
            if urlparse(link).scheme not in {"http", "https"} or not urlparse(link).netloc:
                raise ValueError(f"Link inválido no catálogo: {row['id']}")
            products.append({
                "id": int(row["id"]), "marca": row["marca"].strip(),
                "nome": row["nomebase"].strip(), "cor": row["nomecor"].strip(),
                "hex": color.upper(),
                "preco": float(Decimal(row["preco"].strip().replace(",", "."))),
                "link": link,
            })
    return products
