# Match de pele e base: medição regional + ranking direto em Lab

Implementação local, sem treinamento ou nova rede neural. Usa as referências
digitais da [escala Monk](https://skintone.google/) e a função pronta
[`skimage.color.deltaE_ciede2000`](https://scikit-image.org/docs/0.26.x/api/skimage.color.html#skimage.color.deltaE_ciede2000).
O scikit-image faz parte dos requisitos de execução do backend.

## Algoritmo

1. `measure_skin` mede a seleção disponível, independentemente de `quality.usable`.
   Qualidade reduzida e falhas de especialista geram avisos. Se a seleção estrita
   estiver vazia, usa pele com incertezas ou pele antes das exclusões. BiSeNet
   indisponível ou sem pele usa região central aproximada do rosto detectado.
2. Medir testa e duas bochechas em regiões geométricas relativas ao bounding box
   do contorno facial, intersectadas com a máscara efetivamente medida. Essas
   posições aproximam rostos frontais e não são landmarks anatômicos detectados.
   Em cada região, retirar pixels com algum canal RGB ≤2 ou ≥253 e aparar os
   percentis 10/90 de L*. Exigir pelo menos 32 pixels restantes para usá-la.
   Calcular mediana Lab e dispersão P90 por ΔE00 de cada região.
   O peso de qualidade é cobertura (saturada em 50%) × fração sem clipping /
   (1 + (dispersão/8)²). Um medoide das medianas regionais define o consenso;
   multiplicar o peso por 1/(1 + (ΔE00 ao medoide/5)⁴), normalizar e combinar
   as medianas. Não há preferência por regiões mais claras nem corte absoluto
   de L*: duas regiões escuras concordantes também têm apoio.
   Com menos de duas regiões utilizáveis ou sem nenhum par com ΔE00 ≤6,
   manter a mediana global e registrar ressalvas. Discordância máxima >6 gera
   ressalva mesmo quando há consenso parcial. Todos os limiares são heurísticos.
   Média, mediana e desvio globais permanecem no pré-processamento para auditoria;
   a máscara original e os pixels não são modificados pelo estimador.
3. Converter os dez HEX Monk e os HEX das bases com o mesmo `rgb_to_lab` da foto:
   sRGB → RGB linear → XYZ → Lab/D65, observador 2°.
4. Associar pele e cada base ao swatch Monk de menor ΔE00. Em empate exato,
   favorecer o menor índice Monk. Índices públicos vão de 1 a 10.
5. Ordenar todas as bases pela menor ΔE00 direta entre pele e base, sem prioridade
   de grupo Monk. ID crescente desempata produtos de cor idêntica.
6. Calcular também o top 3 a partir de cada região utilizável e registrar se a
   sequência de IDs difere do ranking final. É uma análise de sensibilidade,
   não uma probabilidade de acerto.
7. Retornar até três produtos, preservando nomes, preços, cores e links do CSV.

Monk é descritivo: uma base de outro grupo pode ser a primeira colocada se
estiver mais próxima da cor medida. A distância entre referências Monk permanece
nos metadados dos produtos para compatibilidade, sem influenciar a ordenação.

Não há descarte por distância máxima: `limiar_aceitacao_delta_e00` é `null`.
O primeiro colocado é o mais próximo conforme a regra, sem garantia de ser
adequado. Ainda não existe um limiar cosmético calibrado para recusar candidatos.

## Contrato

`matching.py` disponibiliza `classify_monk(lab)` e
`rank_foundations(lab, catalog, limit=3)` para uso independente do Flask.
As funções não alteram entradas e rejeitam vetores não finitos, cores inválidas
e IDs duplicados. As distâncias sem arredondamento determinam a ordem.

`analysis.py` integra medições e catálogo na resposta HTTP `schema_version: 2`:

- `simulado: false`, `exemplo: false` para uploads.
- `tom.monk`, `tom.hex`: índice e swatch Monk selecionados.
- `tom.lab`, `tom.cor_pele_hex`: cor medida e sua aproximação sRGB para exibição.
- `tom.delta_e00`, `tom.distancias_monk`: distância à referência selecionada e
  vetor com as dez distâncias, na ordem Monk 1–10.
- `tom.margem_delta_e00`: diferença entre segunda e primeira distâncias;
  é uma medida de ambiguidade, não confiança estatística.
- `tom.pele_utilizada`: porcentagem de `measurement_mask` sobre `face`, como nas prévias.
- `tom.ita`: `null`. ITA não é necessário para esta estratégia nem é simulado.
- Cada produto acrescenta `monk`, `lab`, `delta_e00` (pele/base), `mesmo_monk`
  e `delta_e00_monk` (distância entre swatches de grupo).
- `match.status`: sempre `calculado` nos resultados.
- `match.metodo`: `regional-ciede2000-lab-v2`.
- `match.estimador`: `lab_regional_ponderado` ou fallback `mediana_lab`.
- `match.criterio_ranking`: `delta_e00_pele_base_depois_id`.
- `match.motivos`: ressalvas técnicas, incluindo a origem alternativa da medição,
  `regioes_insuficientes`, `discordancia_entre_regioes` e `sem_consenso_regional`.
- `match.sensibilidade_regional`: `avaliada`, `top3_por_regiao` e `ranking_varia`;
  a avaliação exige pelo menos duas regiões utilizáveis e inclui ordem dos IDs.
- `preprocessamento.medicao_regional`: estimador, cor final Lab, geometria,
  dispersão entre regiões, motivos e métricas por região (bbox no recorte RGB,
  contagens, clipping, mediana, dispersão e peso). Peso zero indica região fora
  da combinação; no fallback todos os pesos são zero.
- `match.confianca_reduzida`: indica motivos presentes; não é probabilidade de acerto.
- `match.grupos_complementares_utilizados`: se houve produtos de outro Monk,
  independentemente de haver opções no mesmo grupo.
- `match` registra método, estimador, fonte/versão da paleta e SHA-256 do
  catálogo normalizado, permitindo identificar mudanças de referência.

Qualidade reduzida mantém o tom e as recomendações. Catálogo vazio/inválido
gera erro de serviço; nunca é substituído pelo catálogo de demonstração.
Todo resultado inclui `status_analise: concluida` e pelo menos uma base.

O upload não chama `generate_analysis`. `/api/exemplo` preserva suas fixtures
e usa a mesma paleta Monk. JSON e NDJSON usam o mesmo algoritmo.

## Limites e interface

O resultado é computado da foto, mas experimental: `match.experimental: true`
e `match.validado: false`. Não altera `quality.released_for_monk: false`, que
registra a ausência de validação da seleção. Os critérios técnicos provisórios
geram ressalvas, sem impedir o cálculo experimental.

O estimador reduz influência de extremos e regiões discrepantes; não corrige
uma dominante de iluminação uniforme nem recupera cor física. Não há conversão automática
de ITA para Monk, inferência de subtom ou percentual de compatibilidade.
Os HEX do catálogo não são medições de bases aplicadas; isso limita a validade
física do ranking. Classificação digital Monk não substitui anotação humana.

O frontend só aceita resultados com tom e bases. Mostra a cor medida da foto
separada do swatch Monk, preserva a ordem
do ranking e identifica grupos complementares. `/api/exemplo` permanece
explicitamente demonstrativo. Um único aviso no topo explica todos os fatores
que podem tornar o tom incorreto, mantendo produtos e tom visíveis.
Distâncias nunca são apresentadas como confiança.

## Testes

```powershell
.venv\Scripts\python -m unittest backend.tests.test_tone_matching -v
.venv\Scripts\python -m unittest discover -s backend/tests -v
```

Cobertura inclui as dez referências, um par CIEDE2000 publicado por Sharma,
ranking direto entre grupos, empates, catálogo vazio, mudança de foto,
exclusões preservadas, falha de especialista e paridade JSON/NDJSON.
`backend.tests.test_regional_measurement` verifica regiões claras/escuras,
sombras e reflexos discrepantes, clipping, fallback, máscara e bbox preservados,
ressalvas e sensibilidade do ranking.
São verificações de engenharia, não avaliação de precisão em pessoas reais.
