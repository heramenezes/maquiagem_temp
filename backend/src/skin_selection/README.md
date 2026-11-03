# Seleção independente antes da medição

Backend atualizado em 15/10/2026, usando YOLOv8l-seg específico para
barba e bigode (prashants975). O frontend exibe máscaras e estados das três categorias. O piloto de 100–200 fotos anotadas por
pessoa ainda não existe no repositório: esta implementação é experimental,
com limiares provisórios, sem declaração de acurácia ou validação do match.

## Execução

1. Preservar o RGB do recorte, após a limitação de upload a 1600 pixels.
2. BiSeNet define anatomia candidata (pele/nariz); se indisponível ou sem pele,
   uma região central aproximada do rosto detectado é usada com aviso explícito.
3. Acne (U-Net), vitiligo (YOLO11n) e barba (YOLOv8l) recebem vistas do mesmo RGB.
4. Restaurar probabilidades ao recorte antes dos limiares. YOLO registra e
   desfaz letterbox. Rótulos BiSeNet usam vizinho mais próximo.
5. Compor união e avaliar qualidade para gerar avisos. Medir `valid_mask` ou,
   se vazia, anatomia sem exclusões aceitas ou anatomia inicial, nessa ordem.
   `measurement_mask` e `measurement_source` registram a escolha real.

`excluded_mask = anatomical_mask & union(accepted_masks)`;
`valid_mask = anatomical_mask & ~excluded_mask & ~uncertain_mask`.
Motivos podem sobrepor; a área total conta a união uma vez. Componentes usam
pixels reais, não caixas preenchidas; furos nas máscaras são preservados.
Máscaras brutas, inclusive previsões externas à anatomia, ficam em `debug_masks`.
Regiões carregam motivo, origem, bbox, área e referência à evidência do módulo.

## Estados e confiança

`executado` com máscara vazia difere de `indisponivel`, `falha` e
`nao_executado`. Nestes últimos, `detected` é `null`, nunca `false`.
Falha de especialista mantém a medição e gera aviso. BiSeNet indisponível
usa a região central do rosto com motivo explícito, mantendo as recomendações.
Sessões são verificadas e carregadas uma vez por processo, com duas threads
intra-op e uma inter-op. A orquestração é sequencial.

Acne: probabilidades ≥0,50 aceitas; [0,20, 0,50) incertas. Vitiligo: confiança
de instância ≥0,60 aceita; [0,25, 0,60) incerta; máscara usa 0,65/0,35.
Esses valores são hipóteses iniciais, não calibração no conjunto do projeto.
Não são probabilidades diagnósticas. Barba usa a classe nominal `beard` (0),
ignorando `hair` (1), com os mesmos limiares provisórios de confiança/máscara
do vitiligo. Evidência: `modelo_especifico`, `nominal_beard_class: true`.
Barba branca/rala, bigode isolado, inclinação, sombras e pigmentação exigem
validação. O módulo não depende de textura, âncora nasal ou discordância de parsers.

## Qualidade e cor

Os indicadores de qualidade consideram pixels nativos (≥128), fração restante (≥4%),
extensão espacial, clipping, nitidez, dispersão, iluminação e mudança da
média ao incluir incertezas. Todos os valores e razões são retornados em
`quality`; detalhes em `QualityConfig`. Não há escolha automática do cluster
maior, testa limpa, cor mais escura ou componente único.

`quality.usable` indica ausência de ressalvas pelos critérios técnicos provisórios.
`calibration` é `provisoria_sem_validacao_anotada` e `released_for_matching` é
sempre `false`. Mesmo com ressalvas, `measure_skin` é chamada. Média Lab/RGB,
mediana Lab, desvio e dispersão usam os pixels reais de `measurement_mask`;
overlays nunca entram na medição. As exclusões estritas são preservadas para
inspeção. `quality.decision` é `aprovada` ou `com_ressalvas`; os limites completos
estão no [README principal](../../../README.md#limiares-de-qualidade).

K-means é descritivo da anatomia anterior às exclusões, limitado a uma vista
de 512 pixels e 4.000 amostras. Nenhuma alteração em `grow_skin()` foi reativada.
Rosácea não participa do backend; as bases usam Lab regional ponderado, com
fallback para a mediana global. Veja o [contrato do match](../tone_matching/README.md).

## Instalação e verificação

Veja [modelos](../../models/README.md) para downloads, exportação e hashes.
Na raiz do projeto:

```powershell
.venv\Scripts\python -m unittest discover -s backend/tests -v
```

Testes sintéticos cobrem alinhamento não quadrado, letterbox, canais, classes,
união, incertezas, falhas, cores preservadas e alternativas de medição. Integração cobre
JSON/NDJSON e garante recomendações com ressalvas e rastreabilidade da máscara medida. As fotos
locais e a equivalência PyTorch/ONNX verificam execução, não qualidade facial.

Para concluir a validação do plano faltam máscaras manuais, positivos,
negativos e confusores dos três grupos; separação por pessoa entre ajuste
e teste; calibração conjunta; avaliação por tom/luz; e comparação com seleção
manual. Até isso acontecer, a etapa de liberação do plano permanece pendente.

## Avaliação offline

Instale `backend/requirements-evaluation.txt` em ambiente separado. O comando
`python -m backend.evaluate_selection manifest.json --split test --output report.json`
compara BiSeNet, cada especialista, combinação completa e máscara manual. Produz precisão/recall/Dice/IoU, pele
válida removida, contaminação, ΔLab/ΔE00, estados, qualidade, tempos e memória.
ΔE00 usa [scikit-image](https://scikit-image.org/docs/stable/api/skimage.color.html#skimage.color.deltaE_ciede2000).
Resultados individuais preservam tom, luz e tags para estratificação.
As comparações offline de cor incluem máscaras reprovadas para pesquisar
falhas; não alteram o portão de medição da API nem aprovam modelos automaticamente.

O manifesto é uma lista JSON com caminhos relativos a ele. Cada imagem é um
recorte já orientado em sRGB (até 1600 pixels); cada máscara é PNG 0/255 no
mesmo tamanho. Não reutilize previsões do modelo como referência humana.
Negativos exigem máscara vazia explícita para cada categoria:

```json
[
  {
    "id": "foto001", "person_id": "pessoa001", "split": "validation",
    "image": "foto001.png", "valid_mask": "foto001_pele_util.png",
    "exclusions": {
      "acne": "foto001_acne.png", "vitiligo": "foto001_vitiligo.png",
      "barba": "foto001_barba.png"
    },
    "tone_group": "anotacao_manual", "lighting": "uniforme",
    "tags": ["negativo", "bigode_isolado"]
  }
]
```

A mesma pessoa não pode aparecer em divisões diferentes. Ajuste limiares na
divisão `validation` e congele-os antes de executar `test`. O relatório não
comprova cobertura dos grupos apenas pela quantidade de imagens. Tempos são
de Lab/anatomia/seleção, sem upload, detecção do recorte ou serialização; o
primeiro caso inclui carga das sessões e os demais são aquecidos. Pico de
memória Windows é do processo inteiro, inclusive avaliação.
