# Conversão CIELAB e segmentação semântica de pele

O fluxo atual usa conversão CIELAB, BiSeNet pré-treinado e agrupamento descritivo
de cores. A segmentação semântica substitui a adaptação anterior por geometria
e crescimento de regiões das seções 4.1–4.2 do artigo. A seleção independente
em [skin_selection](../skin_selection/README.md) acrescenta acne, vitiligo,
YOLOv8l-seg específico para barba/bigode e qualidade.
ITA, Monk e recomendações continuam demonstrativos. Rosácea saiu do escopo.

## Arquivos

- `color.py`: conversão numérica explícita sRGB → RGB linear → XYZ → CIELAB.
- `semantic.py`: inferência ONNX em CPU, máscara de pele/nariz e medições.
- `model_asset.py`: versão, caminho, URL e SHA-256 do peso fixado.
- `skin.py`: K-means compartilhado e método geométrico anterior, preservado para comparação acadêmica.
- `pipeline.py`: execução sequencial, eventos de início/conclusão e prévias PNG.

O detector existente entrega um recorte RGB, não BGR. O pipeline preserva esse
recorte após o limite global de 1600 pixels do upload. Somente as vistas das
redes e o descritor K-means são reduzidos; a medição usa os pixels preservados.

## Conversão de cor

`rgb_to_lab` aceita arrays `(..., 3)` em RGB `uint8` [0,255] ou float [0,1].
Retorna `float32`, preservando o formato: L* aproximadamente [0,100], a* e b*
com sinal. Não usa a representação Lab uint8 do OpenCV, que desloca a*/b* em
128 e escala L* para [0,255]. Isso evita erros no futuro cálculo de ITA.

1. Normalizar RGB uint8 dividindo por 255.
2. Linearizar cada canal `c`:

   ```text
   c_linear = c / 12.92                       se c <= 0.04045
   c_linear = ((c + 0.055) / 1.055) ** 2.4     caso contrário
   ```

3. Converter RGB linear para XYZ com a matriz sRGB/D65:

   ```text
   [X]   [0.4124564  0.3575761  0.1804375] [R_linear]
   [Y] = [0.2126729  0.7151522  0.0721750] [G_linear]
   [Z]   [0.0193339  0.1191920  0.9503041] [B_linear]
   ```

4. Normalizar XYZ por `[0.95047, 1.0, 1.08883]`, o branco D65 na mesma escala.
   Com `delta = 6/29`, aplicar `f(t) = cbrt(t)` acima de `delta³`;
   abaixo, `f(t) = t/(3*delta²) + 4/29`.
5. Calcular:

   ```text
   L* = 116*f(Y/Yn) - 16
   a* = 500*(f(X/Xn) - f(Y/Yn))
   b* = 200*(f(Y/Yn) - f(Z/Zn))
   ```

As fórmulas seguem o [conversor indicado](https://geratools.com/rgb-to-lab),
com coeficientes de matriz mais precisos. A escala XYZ 0–1 é equivalente à
escala 0–100 quando o branco é escalado junto. A referência sRGB é D65,
conforme a [especificação publicada pelo W3C](https://www.w3.org/Graphics/Color/srgb).
Não confundir com CSS `lab()`, que usa D50 e exige adaptação cromática,
conforme [CSS Color 4](https://www.w3.org/TR/css-color/#color-conversion-code).

O upload aplica orientação EXIF e transforma o perfil ICC incorporado para
sRGB usando Pillow/ImageCms. Arquivos sem perfil são presumidos sRGB.
CIELAB separa luminância e cromaticidade, mas não remove sombras nem corrige
balanço de branco/iluminação automaticamente.

## Segmentação atual: BiSeNet ResNet18

Execute `python -m backend.download_model` após instalar os requisitos.
O peso público [yakhyo/face-parsing](https://github.com/yakhyo/face-parsing)
é carregado uma vez por processo, com verificação SHA-256. A inferência é local,
em CPU, sem treinar nem enviar fotos a terceiros. A procedência está em
[models/README.md](../../models/README.md). Peso ausente/inválido gera
`MODELO_INDISPONIVEL`, sem trocar silenciosamente por outro algoritmo.

A rede recebe RGB 512 × 512 normalizado conforme o modelo e prevê 19 classes.
A máscara de classes é restaurada ao tamanho do recorte com vizinho mais próximo.
Os pixels de `skin` (1) e `nose` (10) formam a máscara anatômica inicial, sem dilatação,
erosão, geometria fixa, filtro de brilho ou exigência de conectividade.
O RGB original é preservado para conversão CIELAB e prévias; o tensor
normalizado da rede nunca é usado para medir a cor da pele.

K-means continua descrevendo a anatomia antes das exclusões, em uma vista de
até 512 pixels. Não escolhe a cor válida nem altera máscaras. Somente a
`valid_mask` da seleção aprovada entra em `measure_skin(lab, valid_mask)`.
Resultados inconclusivos mantêm máscaras e razões, com médias nulas.

`pixels_pele` conta a seleção restante; `pixels_contorno` conta as regiões faciais
previstas (classes 1–6 e 10–13), sem orelhas, pescoço, cabelo e fundo.
O percentual representa a proporção entre essas duas contagens, não acurácia.
O campo antigo de pixels recuperados foi removido. As prévias continuam sendo
recorte RGB, máscara binária e pele RGBA, alinhadas para a sobreposição no frontend.

Na comparação histórica anterior à seleção independente, a amostra de
133 × 133 pixels passou de 1.723 para 5.538 pixels anatômicos. Isso não é
uma avaliação anotada de acurácia nem a área da nova máscara válida.
A rede não possui classe específica de barba, pode errar nas bordas e não
recupera detalhes ausentes em fotos pequenas. O modelo não detecta doenças.

## Histórico: máscaras e sementes geométricas

As seções históricas a seguir descrevem apenas `skin.py`. A API não usa mais
essas exclusões nem o crescimento; o K-means é reaproveitado como descritor.

Com MediaPipe legado disponível, Face Mesh fornece o contorno facial e os
polígonos de olhos, sobrancelhas e lábios. Estes são dilatados antes da exclusão,
evitando que a etapa de crescimento volte a incluí-los.

Na instalação padrão (OpenCV), utiliza-se um contorno elíptico conservador e
exclusões proporcionais para fotos frontais. O Haar de olhos acrescenta áreas
detectadas fora das posições previstas. As sementes são pequenas regiões de
bochechas, testa e nariz, intersectadas com a máscara permitida. A resposta
informa `geometria_frontal` ou `mediapipe_face_mesh`.

Essas sementes são uma hipótese geométrica, não uma anotação semântica. Pose,
oclusão e maquiagem podem invalidá-las. Fotos inclinadas podem perder muita
pele ou incluir regiões incorretas; a prévia permite inspecionar o resultado.

### Agrupamento e crescimento anteriores

O [trabalho de Islam et al. (2024)](https://www.sciencedirect.com/science/article/pii/S1047320324000014)
usa cromaticidade a*/b*, número de clusters definido pelas propriedades da
imagem e recuperação por crescimento de regiões. A implementação aqui é uma
**adaptação inicial**, não uma reprodução do algoritmo completo: o artigo
original determina K por propriedades de conectividade; aqui adotamos um
critério simples de variância residual.

- Agrupar somente a*/b*, com até 4.000 amostras e inicialização determinística.
- Escolher o menor K entre 1 e 6 que explique 88% da variância cromática;
  variância total menor ou igual a 1 usa um único grupo.
- Selecionar o grupo predominante nas sementes de pele provável.
- Comparar os pixels com a mediana desse núcleo. O limite cromático é adaptado
  às sementes, entre 6 e 18 unidades a*/b*.
- Aplicar um limite de L* relativo à própria face (18–35 unidades), além do
  contraste local. Não há corte absoluto que classifique pele escura como
  cabelo. Fios, barba, reflexos e sombras podem ser reduzidos por esses filtros,
  mas não são classificados semanticamente.
- Crescer por conectividade de oito vizinhos a partir do núcleo. Componentes
  conexos calculam o alcance do flood-fill sob esse predicado fixo: uma ilha
  desconectada não entra apenas por ter cor parecida.
- Aplicar abertura morfológica 3×3 e intersectar novamente com as exclusões.

Os limiares são escolhas desta implementação, não parâmetros extraídos de
Islam et al. Exige-se no mínimo 64 pixels e 4% do contorno selecionados;
caso contrário, a API responde `PELE_INSUFICIENTE` e pede outra foto.

### Saídas e limites do método anterior

`grow_skin` entrega máscara booleana, média CIELAB dos pixels efetivamente
selecionados e quantidade de pixels recuperados fora do grupo inicial.
O resumo HTTP inclui também média RGB, K, área, método, avisos e três PNGs
em memória: recorte, máscara binária e pele RGBA com fundo transparente.

O percentual divide pixels selecionados por pixels do **contorno estimado**,
não pela imagem inteira nem por uma anotação verdadeira de pele. As condições
da pele e o cartão de tom demonstrativo não usam essas medições ainda.

Pelos claros, barba com cor semelhante à pele, óculos, sombras e poses fora
do padrão podem continuar na seleção. Não existe promessa de isolamento
perfeito ou qualidade equivalente para todos os rostos. Antes da próxima
fase, a máscara pode ser avaliada em um conjunto de fotos anotadas.

## Testes

```powershell
.venv\Scripts\python -m unittest backend.tests.test_semantic backend.tests.test_segmentation backend.tests.test_api -v
```

Verificam o modelo real, IDs de pele/nariz, alinhamento da máscara, preservação
do RGB, integridade do peso, erros de instalação e estatísticas sem eliminar
regiões de outra cor. Também verificam valores de referência D65, conversão independente OpenCV float,
validação dos arrays, exclusões em faces sintéticas claras/escuras,
conectividade, K adaptativo, PNGs/área e eventos de progresso. Os testes com
foto real usam a amostra do repositório; não constituem avaliação de acurácia
em uma base de rostos. O caminho MediaPipe requer o ambiente opcional descrito
no README principal.
