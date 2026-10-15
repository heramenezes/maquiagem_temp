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
5. Se o retorno for `None` ou vazio, responder 422 imediatamente.
6. Reduzir o recorte proporcionalmente até 512 pixels, converter RGB para CIELAB/D65,
   construir exclusões faciais, executar K-means adaptativo e crescimento de regiões.
7. Se houver pele insuficiente, interromper com `PELE_INSUFICIENTE`.
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

Os arrays acima estão abreviados; a resposta atual inclui três produtos, três
condições e quatro marcações. Esquemas de seus itens:

| Campo | Estrutura de cada item |
|---|---|
| `recomendacoes` | `id: number`, `marca: string`, `nome: string`, `cor: string`, `hex: string`, `preco: number`, `link: string` |
| `condicoes` | `id: string`, `nome: string`, `detectada: boolean`, `descricao: string`, `intensidade: string ou null`, `local: string ou null` |
| `marcacoes` | `nome: string`, `x: number`, `y: number`, `largura: number`, `altura: number` |

`preco` é um número decimal em reais, formatado no frontend com `Intl.NumberFormat`.
As coordenadas das marcações são percentuais do quadro visual, de 0 a 100,
puramente ilustrativos: não representam coordenadas detectadas na foto.

`simulado: true` continua indicando que tom, ITA, condições e recomendações
são fictícios. `precheck` e o novo objeto `preprocessamento` são reais para
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
    "metodo_contorno": "geometria_frontal",
    "clusters": 5,
    "pixels_pele": 1723,
    "pixels_contorno": 7825,
    "percentual_pele": 22.02,
    "pixels_recuperados": 31,
    "media_lab": [76.2696, 13.022, 19.6245],
    "media_rgb": [224.34, 178.8, 152.9],
    "dimensoes": {"largura": 133, "altura": 133},
    "avisos": [],
    "previas": {"rosto": "data:image/png;base64,...", "mascara": "data:image/png;base64,...", "pele": "data:image/png;base64,..."}
  },
  "etapas": []
}
```

Os números ilustram uma execução com a amostra do repositório; variam conforme
a foto e o método. `media_lab` usa L*/a*/b* físicos, não Lab uint8 do OpenCV.
`percentual_pele` é relativo ao contorno estimado, e as prévias se referem ao
recorte processado. `pele` tem alfa zero nos pixels excluídos. Os arrays
`avisos` e `etapas` foram abreviados; a execução informa limites e seis etapas.

### Progresso incremental usado pelo frontend

O mesmo POST aceita `Accept: application/x-ndjson`. A resposta é uma sequência
de objetos JSON, separados por `\n`, transmitidos antes/depois de cada operação.
Não é SSE, não exige uma segunda requisição nem armazena jobs em memória global.

```json
{"tipo":"etapa","concluidas":0,"total":6,"etapas":[{"id":"rosto","nome":"Verificando o rosto","descricao":"Detecção e recorte facial","simulado":false,"estado":"processando"}]}
{"tipo":"resultado","dados":{"precheck":{"executado":true,"rosto_detectado":true}}}
```

Neste exemplo, `etapas` e `dados` foram abreviados. Cada evento de etapa contém
os seis itens, nos estados `aguardando`, `processando` ou `concluida`. IDs:
`rosto`, `cielab`, `mascara`, `clusters`, `refinamento`, `resultado`.
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
O fluxo real de segmentação já ocorre antes dessa etapa. Condições da pele e
processamento distribuído permanecem futuros. Detalhes dos limiares e das
limitações estão no [README da segmentação](../backend/src/segmentation/README.md).
