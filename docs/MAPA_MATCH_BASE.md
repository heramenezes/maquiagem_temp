# Mapa para implementar o match de pele com base

Inspeção em 03/11/2026. Este documento distingue implementação existente,
validação pendente e proposta de evolução. Não altera o comportamento da aplicação.

## Diagnóstico

O projeto executa segmentação e seleção real de pele, mas ainda não recomenda
bases a partir da cor da foto. A etapa final de `analysis_events` chama
`mock_result()`, fornecido por `generate_analysis` em `backend/app.py`.
Esse gerador sempre usa Monk 6, ITA 22 e o alvo RGB `(160, 126, 86)`.
Portanto, as recomendações atuais não dependem da medição da pessoa.

Fluxo atual:

`foto → recorte RGB → Lab/D65 → anatomia → exclusões → qualidade → estatísticas reais → resultado demonstrativo`

Fluxo necessário:

`captura controlada → seleção validada → cor representativa → comparação com catálogo caracterizado → recomendação ou abstenção`

## O que existe

| Parte | Evidência | Situação |
|---|---|---|
| Upload e imagem | `backend/app.py`: limites, orientação EXIF, ICC para sRGB, resize | Implementado |
| Rosto | `backend/src/preprocessing/face_detector.py` | Implementado; sujeito a falhas de detecção |
| Conversão de cor | `backend/src/segmentation/color.py`: sRGB linearizado, XYZ, Lab/D65 | Implementado; não corrige a iluminação da cena |
| Anatomia | `backend/src/segmentation/semantic.py`: BiSeNet | Implementado |
| Acne, vitiligo e barba | `backend/src/skin_selection/` | Implementados; acurácia no domínio ainda não demonstrada |
| Composição | `compose.py`: união de exclusões e separação de incerteza | Implementado |
| Qualidade | `quality.py`: área, nitidez, clipping, dispersão, iluminação e incerteza | Implementado com limiares provisórios |
| Medição | `measure_skin`: média, mediana e desvio em Lab da máscara aprovada | Implementado |
| Avaliação offline | `backend/evaluate_selection.py`: máscaras, ablações, diferença de cor e divisão por pessoa | Ferramenta implementada; piloto anotado pendente |
| Catálogo | `backend/data/bases.csv` e `catalog.py` | 281 entradas, 272 HEX distintos, 12 marcas na inspeção |
| Match | `backend/src/tone_matching/` | Apenas documentação e inicializador |
| Interface | `frontend/js/screens/result.js` | Mostra processamento real e identifica tom/bases como demonstrativos |

`quality.usable` significa aprovação por critérios técnicos provisórios.
`quality.calibration` é `provisoria_sem_validacao_anotada` e
`released_for_monk` é sempre `false`. Implementação dos detectores não equivale
a validação da cor restante ou da recomendação final.

Mesmo quando a seleção fica inconclusiva, a etapa final atual ainda preenche
tom e produtos de demonstração. A integração real deverá retornar tom ausente
e recomendações vazias nesse caso, preservando máscaras e motivos.

## Trabalho necessário, em ordem de dependência

### 1. Definir o alvo e o protocolo de captura — prioridade alta

- Decidir se a base deve acompanhar o rosto, a transição mandíbula/pescoço ou
  outra referência. O parser atual exclui pescoço; mudar o alvo exige dados e seleção adicionais.
- Para vitiligo, explicitar que o fluxo atual estima a pele não afetada;
  cobertura de regiões despigmentadas exige outro objetivo de produto.
- Definir captura frontal sem maquiagem/filtros, luz e exposição controladas.
- Para o primeiro experimento, usar iluminação fixa e referência neutra/de cor
  com valores conhecidos; avaliar depois a captura livre por celular.
- Medir repetibilidade entre fotos, iluminação e aparelhos. Normalização ICC
  e conversão para Lab não demonstram constância de cor entre capturas.

Conclusão: protocolo documentado e erro de repetição medido em pessoas reais.
Correção automática de balanço de branco deve ser validada, sem presumir
que uma foto arbitrária permite recuperar a cor física da pele.

### 2. Validar a seleção e os critérios de qualidade — prioridade alta

- Criar piloto com máscaras humanas de pele válida e das três exclusões,
  incluindo negativos e confusores, diversidade de tons, luz e condições.
- Separar treino/ajuste, validação e teste por pessoa, como exige o manifesto
  de `evaluate_selection.py`.
- Calibrar limiares dos especialistas e `QualityConfig` na validação.
- Avaliar contaminação restante, pele válida removida e mudança na cor medida,
  além de IoU/Dice. Segmentar bem visualmente não basta para medir bem a cor.
- Reportar taxa de abstenção e erros por grupo de tom, aparelho e iluminação.

Conclusão: relatório no teste separado, critérios de aceitação previamente
definidos e política explícita de liberação do estimador. Alterar apenas
`released_for_monk` não constitui validação.

### 3. Caracterizar as cores das bases — prioridade alta

- Auditar a origem de cada `codigocor`: o CSV não informa método de medição,
  iluminante, referência branca, condições de aplicação ou procedência da cor.
- Como baseline digital, converter HEX sRGB para Lab/D65 usando a mesma
  convenção da foto e identificar o resultado como aproximação ao catálogo.
- Para avaliar match físico, obter amostras aplicadas e medidas sob protocolo
  comum; registrar quantidade/cobertura, substrato e tempo após aplicação.
- Registrar origem, versão e condições das referências; investigar cores
  duplicadas sem remover automaticamente produtos distintos.
- Examinar cobertura do espaço de cores: o produto mais próximo pode ainda
  ser inadequado, caso o catálogo não contenha um tom suficientemente próximo.

Conclusão: catálogo com referência rastreável; distinguir swatch digital de
cor de produto aplicado. Sem isso, o algoritmo pode acertar a distância e
errar a base na prática.

### 4. Implementar o estimador e o ranking — prioridade alta

- Receber somente Lab da `valid_mask` aprovada; bloquear saída real em caso
  inconclusivo ou falha de especialista obrigatório.
- Comparar média e mediana já existentes e, se necessário, agregação por região.
  Escolher o estimador por repetibilidade e erro contra referência humana/física.
- Preservar a cor contínua Lab como entrada do ranking. ITA e Monk podem ser
  saídas descritivas; não reduzir os produtos a dez classes como único critério.
- Implementar baseline de busca exaustiva por diferença de cor CIEDE2000
  (ΔE00), com desempate determinístico e retorno de até três produtos.
- Com 281 entradas, não é necessário começar treinando um classificador.
  Se KNN for exigência acadêmica, explicitar atributos, distância e objetivo,
  comparando-o ao baseline. Avaliar a*/b* antes de criar regras de subtom.
- Definir no conjunto de validação quando recusar match, devolver menos de
  três opções ou sinalizar baixa cobertura. Não impor um limiar universal
  de ΔE nem transformar distância diretamente em percentual de confiança.
- Implementar ITA com convenções/casos limites documentados e mapeamento Monk
  como aproximação validada; não presumir conversão universal ITA → Monk.

Conclusão: mudar a cor de entrada deve mudar o ranking de forma verificável;
nenhum produto deve depender do alvo fixo da demonstração.

### 5. Integrar API e interface — prioridade alta

- Substituir `mock_result()` na etapa final de
  `backend/src/segmentation/pipeline.py`; preservar `/api/exemplo` demonstrativo.
- Definir contrato com estado do match, Lab estimado, método, versão do
  catálogo, distância por produto e motivos de abstenção.
- Separar aprovação técnica da foto, medição e disponibilidade de match.
- Atualizar `result.js`, `processing.js` e demais textos de simulação somente
  quando os respectivos campos forem reais. Em abstenção, mostrar motivos e
  orientar uma nova captura ou informar falta de cor adequada no catálogo.
- Cobrir JSON e NDJSON, máscara inválida, catálogo vazio/insuficiente,
  entradas sem referência confiável, empate, mudança de foto e falha de modelo.

Conclusão: fotos reais utilizam suas próprias medições; análises inconclusivas
não apresentam base como se houvesse match válido.

### 6. Validar a recomendação de ponta a ponta — prioridade alta

- Montar referências de pessoa × base efetivamente aplicada, com avaliação
  controlada e possibilidade de mais de uma base aceitável ou nenhuma.
- Avaliar acerto entre as primeiras opções, erro de cor, repetibilidade,
  aceitação das recomendações e acerto das abstenções.
- Manter pessoas do teste fora do ajuste. Comparar resultados por tom,
  condições, aparelho e luz. Predefinir metas a partir do piloto.
- Começar com um subconjunto de bases fisicamente caracterizadas antes de
  declarar que todas as 281 entradas estão validadas.

Conclusão: evidência de que o ranking escolhe bases adequadas na pele,
além de cores próximas nas imagens.

## Paralelismo e distribuição: situação real

- `select_skin()` em `skin_selection/pipeline.py` contém `ThreadPoolExecutor`.
- A rota web usa `analysis_events()`, que chama `run_module()` uma vez por
  etapa. Ela não utiliza `select_skin()`; os especialistas da API são sequenciais.
- O runtime dos especialistas seleciona CUDA quando o provider está disponível;
  no ambiente `.venv` inspecionado, os providers disponíveis foram Azure e CPU.
- BiSeNet fixa `CPUExecutionProvider` em `segmentation/semantic.py`.
- `backend/src/distributed/` contém somente README e inicializador. Não foi
  encontrada implementação de nós P2P, transporte ou orquestração distribuída.
- `bench_pipeline.py` compara execução dos detectores; seu modo padrão simula
  latências. Mesmo `--real` não mede todo o caminho HTTP.

Se paralelismo for necessário, integrar despacho concorrente ao fluxo de
eventos e medir latência/memória reais, incluindo concorrência de requisições.
Se distribuição entre máquinas for requisito acadêmico, implementar protocolo,
identificação de tarefas, transporte de imagens/máscaras, prazos, falhas e
equivalência de resultados. Isso é uma frente própria e não desbloqueia a
precisão do match de cor.

## Entregas sugeridas

1. **Protótipo conectado:** Lab aprovado → catálogo digital em Lab → ranking
   ΔE00 → API/interface reais, com abstenção e limites explícitos.
2. **Piloto confiável:** captura controlada, máscaras anotadas, seleção calibrada,
   subconjunto de bases caracterizado e avaliação em pessoas separadas.
3. **Expansão:** novos aparelhos/luzes/bases; otimização e distribuição conforme
   os requisitos e medições de desempenho.

O protótipo conectado demonstra o funcionamento do algoritmo; o piloto mede
se ele resolve o problema físico de escolher uma base.

## Referência técnica do baseline proposto

A CIE define CIEDE2000 como uma fórmula de diferença de cor em CIELAB.
Seu uso aqui é uma proposta de baseline a validar, não garantia de match cosmético:
[ISO/CIE 11664-6:2022](https://www.cie.co.at/publications/colorimetry-part-6-ciede2000-colour-difference-formula-1).
Dados de referência para testar a implementação:
[Gaurav Sharma, CIEDE2000](https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/).
