# Como funciona essa parte do projeto (Detecção de Rosto)

---

## 1. O jeito rápido (quadrado) — `face_detector.py`

Esse aqui faz o corte mais bruto da imagem.

* **O que ele faz:** Ele acha onde tá o rosto e recorta uma caixa (bounding box) ao redor da cabeça com uma folguinha de 15% nas bordas (pra não decepar a testa nem o queixo).
* **Como ele acha a cara:**
  1. Ele tenta usar o **MediaPipe** primeiro, que é muito rápido e quase nunca erra em foto tipo selfie.
  2. Se por acaso o MediaPipe não achar nada ou der ruim, ele ativa o plano B sozinho: o **Haar Cascades** do OpenCV.
  3. Se nenhum dos dois achar nada, ele avisa e devolve `None` (ou seja, não tem rosto).
* **O detalhe das cores (importante):** O OpenCV lê imagem em BGR. Mas a gente já configurou a função pra devolver em **RGB**, porque se mandasse em BGR pro CIELAB na próxima etapa, o vermelho e o azul iam ficar trocados e a pele ia parecer azulada, estragando o tom da base.
* **Pensando na rede P2P:** A função aceita tanto o caminho do arquivo (`.jpg`, `.jpeg`, etc.) quanto a imagem já carregada na memória (array NumPy). Assim, quando os nós da rede distribuída trocarem dados entre si, ninguém precisa ficar salvando e lendo arquivo do disco toda hora.

### Como rodar ele no terminal:
```bash
python ti6/face_detector.py ti6/imagem_teste.jpeg
```
Ele vai gerar uma imagem com o final `_rosto` do lado da original.

---

## 2. O jeito que contorna a cara certinho — `face_segmenter.py`

Esse aqui é o que a gente fez a mais pra não deixar aquela sobra de fundo nos cantos da foto.

* **Por que isso é bom pro trabalho:** Se a pessoa tirar foto numa parede bege ou marrom, o K-Means da próxima etapa pode achar que a parede é pele e estragar o cálculo do tom da base. Esse script arranca a parede e deixa só o contorno anatômico do rosto.
* **Como ele faz isso:**
  1. Ele usa o **Face Mesh** do MediaPipe, que joga centenas de pontos no rosto.
  2. A gente pega só os pontos da linha do contorno da cara (queixo, têmporas, testa).
  3. Ele desenha um polígono fechado com esses pontos e cria uma máscara: o que tá dentro da cara continua original, o que tá fora vira preto ou transparente.
  4. Depois ele recorta bem rente ao contorno.

### Como rodar ele no terminal:
```bash
# Se quiser com fundo transparente (PNG):
python ti6/face_segmenter.py ti6/imagem_teste.jpeg ti6/minha_silhueta.png

# Se só passar a imagem, ele salva automático:
python ti6/face_segmenter.py ti6/imagem_teste.jpeg
```

---

## 3. Como rodar os testes automáticos

Tem um script pronto que testa se tá tudo funcionando certinho (com rosto, sem rosto, na memória e com erro):

```bash
python ti6/test_face_detector.py
```

Se aparecer `[TODOS OS TESTES PASSARAM COM SUCESSO!]`, tá tudo 100%.

---

## Etapa seguinte: já integrada à aplicação web

O recorte RGB agora é convertido explicitamente para **CIELAB/D65 em ponto
flutuante**, seguido de máscara facial com exclusões, **K-means adaptativo**
em a*/b* e crescimento de regiões. A API transmite o progresso de cada etapa.
O frontend mostra o recorte, a máscara, a pele selecionada e sua média CIELAB.

Essa segmentação é básica: cor, contraste e posição reduzem olhos, boca,
sobrancelhas, barba e cabelo, mas não garantem remoção perfeita. Acne, rosácea
e vitiligo ainda não são detectados. ITA, Monk e KNN continuam para a fase seguinte.

Veja o [método e os limites](../backend/src/segmentation/README.md), os
[contratos HTTP](API.md) e os [comandos atuais de execução](../README.md).
