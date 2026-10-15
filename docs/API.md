# API do Meu tom

O Flask serve a interface e as rotas HTTP na mesma origem. Não há autenticação,
banco, fila de tarefas ou armazenamento de fotos. As respostas da API usam JSON
UTF-8 e `Cache-Control: no-store`.

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
3. Corrigir EXIF e reduzir proporcionalmente para até 1600 × 1600 pixels.
4. Executar `detectar_e_isolar_rosto` com a matriz BGR em memória.
5. Se o retorno for `None` ou vazio, responder 422 imediatamente.
6. Somente após aprovação, gerar os dados demonstrativos.

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

`simulado: true` indica que o resultado posterior à pré-verificação é fictício.
`precheck` é a informação real para fotos enviadas. A cor e o ITA fixos não são
calculados da imagem. A proximidade RGB usa o tom fixo de exemplo; os dados dos
produtos são reais conforme o CSV fornecido.

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
| 500 | `ERRO_INTERNO` | Manter a prévia e permitir tentar novamente |
| outros | `REQUISICAO_INVALIDA` | Exibir mensagem de erro |

Falhas de conexão e timeout de 45 segundos são tratados pelo cliente,
respectivamente como `CONEXAO` e `TEMPO_ESGOTADO`. Cancelamentos voluntários
não exibem erro. O resultado de uma solicitação antiga não altera uma tela reiniciada.

## GET /api/exemplo

Retorna a mesma estrutura, com `exemplo: true` e:

```json
{"precheck": {"executado": false, "rosto_detectado": null}}
```

Não recebe imagem e não executa o detector. A interface mostra uma silhueta
ilustrativa, identificando a ausência de pré-verificação.

## Catálogo e próximas integrações

`backend/data/bases.csv` preserva o arquivo recebido e suas colunas originais:
`id,marca,nomebase,nomecor,codigocor,preco,link`.
`catalog.py` converte nomes de campos, preços com vírgula e cores hexadecimais,
validando os links HTTP/HTTPS. A cópia arquivada no mock não é lida pela aplicação.

Quando as próximas etapas estiverem prontas, substituir a chamada a
`generate_analysis()` após a detecção em `backend/app.py` pelo pipeline real,
passando o recorte facial RGB e/ou a imagem original BGR conforme necessário.
Manter o contrato permite reaproveitar `api.js` e as telas. Nessa integração,
atualizar também os textos demonstrativos e a semântica de `simulado`; o frontend
atual foi deliberadamente escrito para o estágio acadêmico com resultados mockados.

O segmento anatômico e os módulos futuros de segmentação, cálculo de tom e
processamento distribuído não são acionados pela API atual.
