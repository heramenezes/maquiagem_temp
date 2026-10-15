"""Fotos de regressão montadas em memória a partir da amostra do projeto."""

from io import BytesIO
from pathlib import Path

from PIL import Image


def face_photo(count=2, secondary_scale=1):
    with Image.open(Path(__file__).resolve().parents[2] / 'samples/imagem_teste.jpeg') as source:
        original = source.convert('RGB')
    tiles = [original] + [original.resize((round(original.width * secondary_scale),
                                          round(original.height * secondary_scale)))
                          for _ in range(count - 1)]
    photo = Image.new('RGB', (sum(t.width for t in tiles) + 30 * (count - 1),
                             max(t.height for t in tiles)))
    x = 0
    for tile in tiles:
        photo.paste(tile, (x, 0))
        x += tile.width + 30
    output = BytesIO()
    photo.save(output, format='PNG')
    output.seek(0)
    return output
