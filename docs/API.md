# API do Meu tom

O Flask serve a interface e as rotas HTTP na mesma origem. Não há autenticação,
banco, fila de tarefas ou armazenamento de fotos. As respostas usam JSON ou
NDJSON UTF-8, com `Cache-Control: no-store`.

## POST /api/analises

Envie uma imagem no campo `foto` de um formulário `multipart/form-data`.
O navegador define o `Content-Type` e o boundary automaticamente ao usar `FormData`.

```javascript
const body = new FormData();
body.append('foto', file);
const response = await fetch('/api/analises', { method: 'POST', body });
const result = await response.json();
```

Regras:

1. Arquivo de até 10 MiB (10 × 1024 × 1024 bytes); limite HTTP de 11 MiB para
   acomodar o envelope multipart. A interface mostra “10 MB”.
2. JPEG, PNG ou WebP decodificável, com até 24 milhões de pixels.
   A extensão e o MIME declarados pelo cliente não substituem a validação do conteúdo.
3. Corrigir EXIF, normalizar ICC para sRGB quando presente e reduzir proporcionalmente para até 1600 × 1600 pixels.
4. Executar `detectar_e_isolar_rosto` com a matriz BGR em memória.
5. Se não houver rosto ou forem detectados múltiplos rostos, responder 422 antes da segmentação.
6. Preservar o recorte RGB, converter para CIELAB/D65 e executar BiSeNet ONNX.
   Executar acne, vitiligo e YOLOv8l-seg de barba em vistas do mesmo RGB, restaurar as
   máscaras e compor a seleção de pele. K-means continua apenas descritivo.
7. Avaliar a qualidade para gerar ressalvas, sem impedir a medição. Seleção vazia
   usa pele com incertezas ou pele antes das exclusões. BiSeNet indisponível ou
   sem pixels de pele usa região central aproximada do rosto, com motivo explícito.
8. Combinar as medianas Lab da testa e das bochechas por qualidade e consenso,
   com fallback para a mediana global. Ordenar todo o catálogo diretamente por
   CIEDE2000 pele/base, sem classes intermediárias.
   Toda análise concluída retorna `tom` e pelo menos uma recomendação.

O servidor não aceita um parâmetro que desative a pré-verificação. Cada envio
verifica a própria imagem; nenhuma aprovação anterior é reutilizada.

### Resposta 200

```json
{
  "schema_version": 3,
  "simulado": false,
  "exemplo": false,
  "precheck": {"executado": true, "rosto_detectado": true},
  "tom": {"lab": [55.96, 20.05, 26.01], "cor_pele_hex": "#b4785a", "pele_utilizada": 74},
  "catalogo_total": 281,
  "recomendacoes": [],
  "match": {"status": "calculado", "experimental": true, "validado": false},
  "condicoes": [],
  "marcacoes": []
}
```

O objeto e os arrays acima estão abreviados e ilustram o formato, não valores
fixos de resposta. Fotos aprovadas incluem até três produtos do ranking,
três condições com estados reais e `marcacoes: []`.
As regiões reais ficam em `preprocessamento.selecao.regions`. Esquemas:

| Campo | Estrutura de cada item |
|---|---|
| `recomendacoes` | Dados do catálogo: `id`, `marca`, `nome`, `cor`, `hex`, `preco`, `link`, `imagem`; acrescenta `lab` e `delta_e00` pele/base |
| `condicoes` | `id: string`, `nome: string`, `detectada: boolean ou null`, `estado: string`, `simulado: false`, `origem: string`, `pixels_excluidos: integer`, `pixels_incertos: integer`; `intensidade`/`local` são null |
| `marcacoes` | `nome: string`, `x: number`, `y: number`, `largura: number`, `altura: number` |

`preco` é um número decimal em reais, formatado no frontend com `Intl.NumberFormat`.
Somente `/api/exemplo` mantém marcações ilustrativas em percentuais do quadro
visual. Fotos analisadas nunca recebem essas marcações fictícias.

Uploads retornam `simulado: false`: tom e produtos dependem da medição real.
Isso não implica validação de acurácia: `match.experimental` é `true` e
`match.validado` é `false`. `tom.cor_pele_hex` representa a aproximação sRGB da
cor estimada. `tom.lab` contém a combinação regional ou a mediana global usada
no fallback; `tom.pele_utilizada` informa a proporção da máscara efetivamente medida.

O ranking usa somente ΔE00 pele/base e ID para desempate. O contrato v3 remove
Monk, sua escala e seus metadados, além de ITA. Veja a
[justificativa do abandono](../README.md#por-que-abandonamos-monk).
`match.metodo` é `regional-ciede2000-lab-v3` e `criterio_ranking` é
`delta_e00_pele_base_depois_id`. `match.sensibilidade_regional` inclui
`avaliada`, `top3_por_regiao` e `ranking_varia`, comparando os IDs e sua ordem.
`match.catalogo_sha256` identifica o catálogo normalizado usado na comparação.
Não há limiar máximo de adequação calibrado ou porcentagem de compatibilidade.
`match.status` é sempre `calculado`. `match.motivos` preserva todas as ressalvas;
`match.confianca_reduzida` indica se existem motivos, sem representar probabilidade.
Qualidade reduzida mantém o tom e as bases. Catálogo vazio/inválido é erro de serviço.
O contrato completo está no [módulo de match](../backend/src/tone_matching/README.md).
As ressalvas, comparadores e limiares numéricos estão no
[README principal](../README.md#avisos-de-precisão-e-recomendação-contínua).
Um único aviso no topo explica os motivos e compara `quality.metrics` com
`quality.thresholds`, mantendo o tom e os produtos visíveis.

A interface exige `schema_version: 3`, cor estimada e bases com Lab e ΔE00
finitos. Respostas antigas, simuladas em uploads ou sem recomendações são
recusadas antes da tela final. `/api/exemplo` continua demonstrativo.

### Pré-processamento real

Além dos campos anteriores, uploads bem-sucedidos incluem:

```json
{
  "preprocessamento": {
    "simulado": false,
    "espaco_cor": "CIELAB",
    "branco_referencia": "D65",
    "entrada": "sRGB",
    "metodo_contorno": "bisenet_resnet18_onnx",
    "modelo": "yakhyo/face-parsing:resnet18:v0.0.1",
    "clusters": 6,
    "pixels_pele": 5538,
    "pixels_contorno": 5937,
    "percentual_pele": 93.28,
    "media_lab": [71.1756, 12.8755, 18.1303],
    "media_rgb": [209.17, 165.86, 142.72],
    "dimensoes": {"largura": 133, "altura": 133},
    "avisos": [],
    "previas": {"rosto": "data:image/png;base64,...", "mascara": "data:image/png;base64,...", "pele": "data:image/png;base64,..."}
  },
  "etapas": []
}
```

Os números ilustram uma execução com a amostra do repositório; variam conforme
a foto e o método. `media_lab` usa L*/a*/b* físicos, não Lab uint8 do OpenCV.
`pixels_contorno` agora conta as regiões faciais previstas (pele, nariz,
olhos, sobrancelhas, óculos, boca e lábios), excluindo orelhas e pescoço.
`percentual_pele` divide os pixels restantes de `valid_mask` por essas regiões.
Não é uma medida de acurácia e não é diretamente comparável ao percentual
do método geométrico. `clusters` é descritivo: não remove pixels. O campo
antigo `pixels_recuperados` foi removido, pois não há crescimento de regiões.
As prévias se referem ao recorte processado. `pele` tem alfa zero nos pixels excluídos. Os arrays
`avisos` e `etapas` foram abreviados; a execução informa limites e dez etapas.

### Seleção independente e ressalvas de precisão

`status_analise` é sempre `concluida` nos resultados. Em `preprocessamento`:

- `medicao_utilizavel`: medição disponível, sempre `true` nos resultados.
- `origem_medicao`: `pele_valida`, `pele_com_incertezas` ou `pele_antes_exclusoes`.
- `media_lab`, `media_rgb`, `mediana_lab`, `desvio_lab` e
  `dispersao_delta_e76_p90`: estatísticas dos pixels efetivamente medidos.
- `medicao_regional`: estimador, cor final Lab, geometria, dispersão entre regiões,
  motivos e métricas por região (bbox no recorte, pixels, clipping, mediana,
  dispersão e peso). No fallback para a mediana global, os pesos são zero.
- `clusters_referencia: anatomia_antes_das_exclusoes`: o K-means não é o tom final.
- `selecao.schema_version: 1` e `coordinate_space: recorte_rgb`.
- `selecao.masks`: PNGs 0/255 de `anatomical_mask`, `excluded_mask`,
  `uncertain_mask`, `valid_mask`, `measurement_mask` e `accepted_masks` por motivo.
- `selecao.measurement_source`: mesma origem de `origem_medicao`.
- `selecao.module_status`: `acne`, `vitiligo`, `barba`, com
  `state`, `reason`, `source`, `elapsed_ms`, `evidence`, `detected` e contagens.
- `selecao.regions`: `reason`, `source`, `state`, `bbox: [x,y,largura,altura]`,
  `area_pixels`, `evidence_ref`; coordenadas em pixels do recorte, não da foto completa.
- `selecao.quality`: `decision`, `usable`, `reasons`, `metrics`, `thresholds`,
  `calibration` e `released_for_matching`. `decision` é `aprovada` ou `com_ressalvas`;
  `usable` indica ausência de ressalvas, sem controlar a execução da medição.
- `selecao.model_versions`: fontes, versões, hashes e contratos de processamento.
- `selecao.debug_masks`: previsões brutas e discordâncias preservadas.

Estados de módulo: `executado`, `indisponivel`, `nao_executado`, `falha`.
Somente um módulo executado pode devolver `detected: false`; indisponibilidade
ou falha devolve `null`. `estado_modulo` no progresso expõe a execução real,
mesmo quando a etapa de avaliação termina. `medidas` sempre executa após o rosto
confirmado; falhas de especialista são expostas como ressalvas do resultado.

`excluded_percent` e `percent_by_reason` usam `area_denominator:
pele_anatomica_inicial`. Os motivos podem sobrepor (`reasons_may_overlap: true`);
seus percentuais não devem ser somados. `valid_mask` é anatomia menos união
de exclusões e incerteza. `measurement_mask` registra a região realmente medida,
podendo reincluir incertezas ou exclusões se necessário. A prévia RGBA `pele`,
`pixels_pele` e as estatísticas usam essa máscara. `quality.metrics` mantém
as medidas da seleção estrita. A região central aproximada é identificada por
`metodo_contorno: regiao_central_rosto` e razões explícitas.

`barba` usa YOLOv8l-seg de prashants975, classe nominal `beard` (0); a classe
`hair` (1) é ignorada. A evidência informa `nominal_beard_class: true`, fonte
`prashants975_yolov8l_seg` e limiares provisórios de confiança 0,25/0,60 e
de máscara 0,35/0,65. Bigode participa quando previsto como `beard`.
As três categorias são evidências para seleção cosmética,
sem diagnóstico. Rosácea não integra o contrato.

Os critérios estão em calibração provisória (`provisoria_sem_validacao_anotada`);
`released_for_matching` permanece `false`: ainda não há validação anotada do match.
Veja [seleção de pele](../backend/src/skin_selection/README.md) e
[instalação dos modelos](../backend/models/README.md). O frontend mostra as
prévias anatômicas, três cartões de exclusão com incertezas e a seleção final
RGBA. Cada cartão distingue ausência de exclusões de indisponibilidade/falha;
as ressalvas aparecem no aviso único no topo, sem bloquear tom ou produtos.

### Progresso incremental usado pelo frontend

O mesmo POST aceita `Accept: application/x-ndjson`. A resposta é uma sequência
de objetos JSON, separados por `\n`, transmitidos antes/depois de cada operação.
Não é SSE, não exige uma segunda requisição nem armazena jobs em memória global.

```json
{"tipo":"etapa","concluidas":0,"total":10,"etapas":[{"id":"rosto","nome":"Verificando o rosto","descricao":"Detecção e recorte facial","simulado":false,"estado":"processando"}]}
{"tipo":"resultado","dados":{"precheck":{"executado":true,"rosto_detectado":true}}}
```

Neste exemplo, `etapas` e `dados` foram abreviados. Cada evento de etapa contém
os dez itens, nos estados `aguardando`, `processando` ou `concluida`. IDs:
`rosto`, `cielab`, `mascara`, `acne`, `vitiligo`, `barba`, `selecao`,
`clusters`, `medidas`, `resultado`.
A última etapa calcula o match experimental direto pele/base em Lab. A fração
de etapas concluídas não é uma estimativa de tempo restante.

Existe exatamente um evento terminal de sucesso (`resultado`) ou erro:

```json
{"tipo":"erro","codigo":"ROSTO_NAO_ENCONTRADO","mensagem":"Não encontramos um rosto visível. Tire outra foto de frente, com boa luz e sem cobrir o rosto.","status":422}
```

Erros de arquivo anteriores à abertura do stream usam o HTTP 400/413 usual.
Depois que o stream começa, o HTTP já é 200: o cliente deve tratar o objeto
`tipo: erro`, incluindo `status`, e nunca confundir ausência de `resultado`
com sucesso. Na desconexão, o gerador encerra as etapas restantes ao ser fechado;
uma operação já iniciada pode terminar antes disso. O consumidor deve tolerar
linhas e caracteres UTF-8 divididos entre chunks de rede.

### Erros

Todos usam a estrutura:

```json
{
  "codigo": "ROSTO_NAO_ENCONTRADO",
  "mensagem": "Não encontramos um rosto visível. Tire outra foto de frente, com boa luz e sem cobrir o rosto."
}
```

| HTTP | Código | Comportamento da interface |
|---|---|---|
| 400 | `FOTO_OBRIGATORIA` | Solicitar foto |
| 400 | `FOTO_INVALIDA` | Voltar à seleção com explicação |
| 413 | `FOTO_MUITO_GRANDE` | Pedir arquivo menor |
| 422 | `ROSTO_NAO_ENCONTRADO` | Descartar a foto selecionada e solicitar outra |
| 422 | `MULTIPLOS_ROSTOS` | Descartar a foto e solicitar outra com somente uma pessoa; interrompe antes de converter cores ou segmentar |
| 500 | `ERRO_INTERNO` | Manter a prévia e permitir tentar novamente |
| outros | `REQUISICAO_INVALIDA` | Exibir mensagem de erro |

Falhas de conexão e timeout de 90 segundos (incluindo as pausas de apresentação) são tratados pelo cliente,
respectivamente como `CONEXAO` e `TEMPO_ESGOTADO`. Cancelamentos voluntários
não exibem erro. O resultado de uma solicitação antiga não altera uma tela reiniciada.

## GET /api/exemplo

Retorna a mesma estrutura, com `exemplo: true` e:

```json
{"precheck": {"executado": false, "rosto_detectado": null}}
```

Usa `schema_version: 3`, `simulado: true`, uma cor fixa ilustrativa em
`tom.lab`/`tom.cor_pele_hex` e o mesmo ranking direto por ΔE00. Não inclui `match`.
Não recebe imagem nem executa o detector/segmentação. Não inclui o objeto
`preprocessamento`. A interface mostra uma silhueta ilustrativa, identificando
a ausência de pré-verificação.

## Catálogo e próximas integrações

`backend/data/bases.csv` preserva o arquivo recebido e suas colunas originais:
`id,marca,nomebase,nomecor,codigocor,preco,link`.
`catalog.py` converte nomes de campos, preços com vírgula e cores hexadecimais,
validando os links HTTP/HTTPS. A cópia arquivada no mock não é lida pela aplicação.

O ranking CIEDE2000 está integrado à etapa `resultado` em
`backend/src/segmentation/pipeline.py`, usando a medição regional ponderada ou a
mediana global no fallback. O frontend apresenta
os resultados reais e preserva a distinção entre foto e exemplo demonstrativo.
O fluxo real mantém a medição e o match mesmo com ressalvas de qualidade.
Processamento distribuído permanece futuro. Detalhes dos limiares e das
limitações estão no [README da segmentação](../backend/src/segmentation/README.md).
