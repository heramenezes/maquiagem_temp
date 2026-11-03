# Match de pele e base: Monk + refinamento em Lab

Implementação local, sem treinamento ou nova rede neural. Usa as referências
digitais da [escala Monk](https://skintone.google/) e a função pronta
[`skimage.color.deltaE_ciede2000`](https://scikit-image.org/docs/0.26.x/api/skimage.color.html#skimage.color.deltaE_ciede2000).
O scikit-image faz parte dos requisitos de execução do backend.

## Algoritmo

1. A seleção precisa passar por `quality.usable`. Somente então `measure_skin`
   mede a máscara válida. Falha de especialista obrigatório impede a medição.
2. A mediana por canal Lab da seleção é a cor representativa inicial. A média
   permanece no pré-processamento para comparação. A escolha da mediana é uma
   hipótese de robustez, ainda sem validação de acurácia.
3. Converter os dez HEX Monk e os HEX das bases com o mesmo `rgb_to_lab` da foto:
   sRGB → RGB linear → XYZ → Lab/D65, observador 2°.
4. Associar pele e cada base ao swatch Monk de menor ΔE00. Em empate exato,
   favorecer o menor índice Monk. Índices públicos vão de 1 a 10.
5. Priorizar as bases do mesmo Monk e ordenar esse grupo pela menor ΔE00 entre
   a cor real da pele e a base. ID crescente desempata produtos de cor idêntica.
6. Se houver menos de três opções, visitar os demais grupos pela distância
   ΔE00 entre seus swatches Monk e o swatch Monk da pele. Cada grupo também é
   ordenado por ΔE00 pele/base. Não usar diferença numérica de índices Monk.
7. Retornar até três produtos, preservando nomes, preços, cores e links do CSV.

O agrupamento tem prioridade sobre a distância direta. Uma base de outro
Monk pode estar mais próxima em Lab e aparecer depois das bases do mesmo grupo.
Esse comportamento é deliberado e deve ser avaliado no piloto.

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
- `tom.pele_utilizada`: porcentagem de `valid_mask` sobre `face`, como nas prévias.
- `tom.ita`: `null`. ITA não é necessário para esta estratégia nem é simulado.
- Cada produto acrescenta `monk`, `lab`, `delta_e00` (pele/base), `mesmo_monk`
  e `delta_e00_monk` (distância entre swatches de grupo).
- `match.status`: `calculado`, `inconclusivo` ou `sem_candidatos`.
- `match.motivos`: razões técnicas ou `catalogo_vazio`/`medicao_ausente`.
- `match.grupos_complementares_utilizados`: se houve produtos de outro Monk.
- `match` registra método, estimador, fonte/versão da paleta e SHA-256 do
  catálogo normalizado, permitindo identificar mudanças de referência.

Qualidade reprovada ou medição ausente retorna `tom: null` e `recomendacoes: []`.
Catálogo vazio mantém o tom medido e retorna `sem_candidatos`. Catálogo inválido
gera erro explícito; nunca é substituído pelo catálogo de demonstração.
`status_analise` descreve a medição (`concluida`/`inconclusiva`), enquanto
`match.status` descreve a disponibilidade do ranking.

O upload não chama `generate_analysis`. `/api/exemplo` preserva suas fixtures
e usa a mesma paleta Monk. JSON e NDJSON usam o mesmo algoritmo.

## Limites e interface

O resultado é computado da foto, mas experimental: `match.experimental: true`
e `match.validado: false`. Não altera `quality.released_for_monk: false`, que
registra a ausência de validação da seleção. O cálculo experimental depende da
aprovação técnica provisória, não representa liberação validada do produto.

Não há correção de iluminação, recuperação de cor física, conversão automática
de ITA para Monk, inferência de subtom ou percentual de compatibilidade.
Os HEX do catálogo não são medições de bases aplicadas; isso limita a validade
física do ranking. Classificação digital Monk não substitui anotação humana.

Somente backend foi integrado. O frontend existente ainda usa textos e
pressupostos demonstrativos e precisará consumir o novo contrato, inclusive
`tom: null`, em uma etapa posterior. Não utilizar a interface antiga para
validar este resultado; inspecionar a API ou os testes.

## Testes

```powershell
.venv\Scripts\python -m unittest backend.tests.test_tone_matching -v
.venv\Scripts\python -m unittest discover -s backend/tests -v
```

Cobertura inclui as dez referências, um par CIEDE2000 publicado por Sharma,
refinamento, complemento de grupos, empates, catálogo vazio, mudança de foto,
exclusões preservadas, falha de especialista e paridade JSON/NDJSON.
São verificações de engenharia, não avaliação de precisão em pessoas reais.
