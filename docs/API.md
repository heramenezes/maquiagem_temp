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
   Executar acne, vitiligo e EasyPortrait em vistas do mesmo RGB, restaurar as
   máscaras e aplicar contraste residual. K-means continua apenas descritivo.
7. Anatomia insuficiente interrompe com `PELE_INSUFICIENTE`. Seleção insuficiente,
   incerta ou com especialista indisponível retorna análise inconclusiva com
   máscaras, razões e médias nulas; não chama a medição.
8. Retornar medições/máscaras reais e, separadamente, os dados demonstrativos de tom e bases.

O servidor não aceita um parâmetro que desative a pré-verificação. Cada envio
verifica a própria imagem; nenhuma aprovação anterior é reutilizada.

### Resposta 200

```json
{
  "simulado": true,
  "exemplo": false,
  "precheck": {"executado": true, "rosto_detectado": true},
  "tom": {"monk": 6, "hex": "#a07e56", "ita": 22.0, "pele_utilizada": 74},
  "escala_monk": ["#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96", "#a07e56", "#825c43", "#604134", "#3a312a", "#292420"],
  "catalogo_total": 281,
  "recomendacoes": [],
  "condicoes": [],
  "marcacoes": []
}
```

Os arrays acima estão abreviados. Fotos enviadas incluem três produtos
demonstrativos, quatro condições com estados reais e `marcacoes: []`.
As regiões reais ficam em `preprocessamento.selecao.regions`. Esquemas:

| Campo | Estrutura de cada item |
|---|---|
| `recomendacoes` | `id: number`, `marca: string`, `nome: string`, `cor: string`, `hex: string`, `preco: number`, `link: string` |
| `condicoes` | `id: string`, `nome: string`, `detectada: boolean ou null`, `estado: string`, `simulado: false`, `origem: string`, `pixels_excluidos: integer`, `pixels_incertos: integer`; `intensidade`/`local` são null |
| `marcacoes` | `nome: string`, `x: number`, `y: number`, `largura: number`, `altura: number` |

`preco` é um número decimal em reais, formatado no frontend com `Intl.NumberFormat`.
Somente `/api/exemplo` mantém marcações ilustrativas em percentuais do quadro
visual. Fotos analisadas nunca recebem essas marcações fictícias.

`simulado: true` continua indicando que tom, ITA e recomendações
são fictícios. Condições, `precheck` e `preprocessamento` são reais para
fotos enviadas. A média CIELAB calculada da foto fica nesse novo objeto;
o cartão de tom e a proximidade RGB de produtos ainda usam o exemplo fixo.

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

### Seleção independente e resultados inconclusivos

`status_analise` é `concluida` ou `inconclusiva`. Em `preprocessamento`:

- `medicao_utilizavel`: aprovação pelos critérios técnicos de qualidade.
- `media_lab`, `media_rgb`, `mediana_lab`, `desvio_lab` e
  `dispersao_delta_e76_p90`: estatísticas da seleção aprovada, ou `null`.
- `clusters_referencia: anatomia_antes_das_exclusoes`: o K-means não é o tom final.
- `selecao.schema_version: 1` e `coordinate_space: recorte_rgb`.
- `selecao.masks`: PNGs 0/255 de `anatomical_mask`, `excluded_mask`,
  `uncertain_mask`, `valid_mask` e `accepted_masks` por motivo.
- `selecao.module_status`: `acne`, `vitiligo`, `barba`, `outras_regioes`, com
  `state`, `reason`, `source`, `elapsed_ms`, `evidence`, `detected` e contagens.
- `selecao.regions`: `reason`, `source`, `state`, `bbox: [x,y,largura,altura]`,
  `area_pixels`, `evidence_ref`; coordenadas em pixels do recorte, não da foto completa.
- `selecao.quality`: `decision`, `usable`, `reasons`, `metrics`, `thresholds`,
  `calibration` e `released_for_monk`.
- `selecao.model_versions`: fontes, versões, hashes e contratos de processamento.
- `selecao.debug_masks`: previsões brutas e discordâncias preservadas.

Estados de módulo: `executado`, `indisponivel`, `nao_executado`, `falha`.
Somente um módulo executado pode devolver `detected: false`; indisponibilidade
ou falha devolve `null`. `estado_modulo` no progresso expõe a execução real,
mesmo quando a etapa de avaliação termina. `medidas` informa `nao_executado`
e `motivo: qualidade_inconclusiva` quando se abstém.

`excluded_percent` e `percent_by_reason` usam `area_denominator:
pele_anatomica_inicial`. Os motivos podem sobrepor (`reasons_may_overlap: true`);
seus percentuais não devem ser somados. `valid_mask` é anatomia menos união
de exclusões e incerteza. A prévia permanece disponível mesmo quando a
qualidade reprova a medição; `pixels_pele` não implica amostra aprovada.

EasyPortrait não possui classe nominal de barba. `barba` representa candidatos
por discordância corroborada por textura/localização; discordância isolada
permanece incerta. As quatro categorias são evidências para seleção cosmética,
sem diagnóstico. Rosácea não integra o contrato.

Os critérios estão em calibração provisória (`provisoria_sem_validacao_anotada`);
`released_for_monk` permanece `false`. O backend não implementa Monk nesta fase.
Veja [seleção de pele](../backend/src/skin_selection/README.md) e
[instalação dos modelos](../backend/models/README.md). O frontend não foi
adaptado nesta implementação e ainda não apresenta todos esses estados/campos.

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
A última etapa inclui a preparação dos resultados ainda simulados. A fração
de etapas concluídas não é uma estimativa de tempo restante.

Existe exatamente um evento terminal de sucesso (`resultado`) ou erro:

```json
{"tipo":"erro","codigo":"PELE_INSUFICIENTE","mensagem":"Não conseguimos separar pele suficiente. Tire outra foto de frente e com luz uniforme.","status":422}
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
| 422 | `PELE_INSUFICIENTE` | Solicitar foto frontal mais nítida/com iluminação uniforme |
| 500 | `ERRO_INTERNO` | Manter a prévia e permitir tentar novamente |
| 503 | `MODELO_INDISPONIVEL` | Manter a foto e informar a instalação/reparo do modelo; não usa segmentação geométrica como substituição |
| outros | `REQUISICAO_INVALIDA` | Exibir mensagem de erro |

Falhas de conexão e timeout de 90 segundos (incluindo as pausas de apresentação) são tratados pelo cliente,
respectivamente como `CONEXAO` e `TEMPO_ESGOTADO`. Cancelamentos voluntários
não exibem erro. O resultado de uma solicitação antiga não altera uma tela reiniciada.

## GET /api/exemplo

Retorna a mesma estrutura, com `exemplo: true` e:

```json
{"precheck": {"executado": false, "rosto_detectado": null}}
```

Não recebe imagem nem executa o detector/segmentação. Não inclui o objeto
`preprocessamento`. A interface mostra uma silhueta ilustrativa, identificando
a ausência de pré-verificação.

## Catálogo e próximas integrações

`backend/data/bases.csv` preserva o arquivo recebido e suas colunas originais:
`id,marca,nomebase,nomecor,codigocor,preco,link`.
`catalog.py` converte nomes de campos, preços com vírgula e cores hexadecimais,
validando os links HTTP/HTTPS. A cópia arquivada no mock não é lida pela aplicação.

Para integrar ITA/Monk/KNN, substituir a etapa `resultado` em
`backend/src/segmentation/pipeline.py`, usando `skin['mean_lab']` e a máscara
de pixels válidos, e atualizar os textos/indicadores de simulação no frontend.
O fluxo real de seleção já ocorre antes dessa etapa e bloqueia a medição se
inconclusivo. Processamento distribuído permanece futuro. Detalhes dos limiares e das
limitações estão no [README da segmentação](../backend/src/segmentation/README.md).
