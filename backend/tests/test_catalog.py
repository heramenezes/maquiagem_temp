"""Integridade das fotos locais usadas pelas recomendações do catálogo."""

import json
from pathlib import Path
import unittest

from PIL import Image

from backend.src.catalog import CATALOG_PATH, load_catalog


class CatalogPhotoTests(unittest.TestCase):
    def test_every_catalog_product_has_a_valid_local_photo_and_source(self):
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads(CATALOG_PATH.with_name('product_images.json').read_text(encoding='utf-8'))
        sources = {(entry['marca'], entry['nome']): entry for entry in manifest}
        products = load_catalog()
        self.assertTrue(products)
        for product in products:
            with self.subTest(product=product['id']):
                source = sources[(product['marca'], product['nome'])]
                self.assertEqual(product['imagem'], source['imagem'])
                self.assertTrue(source['pagina_origem'].startswith('https://'))
                self.assertTrue(source['imagem_origem'].startswith('https://'))
                self.assertRegex(product['imagem'], r'^/assets/products/[0-9]+\.(png|jpg|webp)$')
        for image in {product['imagem'] for product in products}:
            with Image.open(root / 'frontend' / image.lstrip('/')) as photo:
                self.assertGreater(min(photo.size), 100)
                photo.verify()
