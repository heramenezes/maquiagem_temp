# Match direto de pele e base em Lab

Implementação local, sem treinamento ou nova rede neural, com
[`skimage.color.deltaE_ciede2000`](https://scikit-image.org/docs/0.26.x/api/skimage.color.html#skimage.color.deltaE_ciede2000).
O scikit-image já faz parte dos requisitos do backend.

## Abandono da escala Monk

O projeto abandonou Monk no backend e no frontend. A classificação do HEX da
foto por proximidade a dez swatches não foi validada como classificação do tom
da pessoa e pode apresentar um número enganoso sob variações de iluminação,
câmera e vermelhidão. Essas categorias não são necessárias para recomendar
bases por proximidade de cor. A decisão e os limites estão no
[README principal](../../../README.md#por-que-abandonamos-monk).

O ranking já era direto na versão anterior; remover a classificação descritiva
preserva as distâncias e a ordem dos produtos para a mesma cor medida e catálogo.
Não há referências digitais da escala, classificador ou agrupamento no código
ativo. Isso não calibra a captura nem as cores do catálogo.

## Algoritmo

1. `measure_skin` mede a seleção disponível, independentemente de `quality.usable`.
   Qualidade reduzida e falhas de especialistas geram avisos. Se a seleção estrita
   estiver vazia, usa pele com incertezas ou pele antes das exclusões. BiSeNet
   indisponível ou sem pele usa uma região central aproximada do rosto detectado.
2. Medir testa e bochechas em regiões geométricas relativas ao bbox facial,
   intersectadas com a máscara efetivamente medida. São aproximações para rosto
   frontal, sem landmarks anatômicos detectados. Em cada região, retirar pixels
   com algum canal RGB ≤2 ou ≥253 e aparar os percentis 10/90 de L*. Exigir
   pelo menos 32 pixels restantes. Calcular mediana Lab e dispersão ΔE00 P90.
   O peso de qualidade é cobertura (saturada em 50%) × fração sem clipping /
   (1 + (dispersão/8)²). Usar um medoide das medianas como consenso e multiplicar
   os pesos por 1/(1 + (ΔE00 ao medoide/5)⁴), normalizar e combinar as medianas.
   Não há preferência por regiões claras. Com menos de duas regiões utilizáveis
   ou nenhum par com ΔE00 ≤6, usar a mediana global e registrar ressalvas.
   Discordância máxima >6 gera ressalva mesmo com consenso parcial. Os limiares
   são heurísticos. As estatísticas globais, pixels e máscara são preservados.
3. Converter os HEX das bases pelo mesmo caminho da foto: sRGB → RGB linear →
   XYZ → Lab/D65, observador 2°.
4. Ordenar todo o catálogo por ΔE00 pele/base sem arredondamento; ID crescente
   desempata cores idênticas. Retornar até três produtos com os dados do CSV.
5. Calcular também o top 3 por região utilizável e registrar se os IDs ou sua
   ordem diferem do ranking final. Essa sensibilidade não é confiança estatística.

Não há descarte por distância máxima: `limiar_aceitacao_delta_e00` é `null`.
O primeiro colocado é o mais próximo segundo a regra, sem garantia de adequação.

## Contrato v3

`matching.rank_foundations(lab, catalog, limit=3)` retorna apenas a lista de
produtos ordenados. `color.hex_to_lab` converte o HEX do catálogo. As funções
não alteram entradas e rejeitam Lab não finito, cores inválidas e IDs duplicados.

`analysis.build_analysis` gera a resposta HTTP `schema_version: 3`:

- `simulado: false`, `exemplo: false` para uploads.
- `tom.lab`: cor estimada em Lab/D65.
- `tom.cor_pele_hex`: aproximação sRGB dessa cor para exibição.
- `tom.pele_utilizada`: porcentagem de `measurement_mask` sobre `face`.
- Produtos preservam dados do catálogo e acrescentam `lab` e `delta_e00` pele/base.
- `match.metodo`: `regional-ciede2000-lab-v3`.
- `match.status`: `calculado`; `criterio_ranking`: `delta_e00_pele_base_depois_id`.
- `match.estimador`: `lab_regional_ponderado` ou fallback `mediana_lab`.
- `match.motivos`: ressalvas da seleção e da medição regional, incluindo
  `regioes_insuficientes`, `discordancia_entre_regioes` e `sem_consenso_regional`.
- `match.confianca_reduzida`: presença de ressalvas; não é probabilidade de acerto.
- `match.sensibilidade_regional`: `avaliada`, `top3_por_regiao` e `ranking_varia`;
  exige pelo menos duas regiões utilizáveis e compara também a ordem dos IDs.
- `match.catalogo_sha256`: hash do catálogo normalizado para auditoria.
- `preprocessamento.medicao_regional`: estimador, Lab final, geometria, dispersão,
  motivos e métricas por região (bbox no recorte RGB, contagens, clipping, mediana,
  dispersão e peso). Peso zero indica ausência na combinação; no fallback todos
  os pesos são zero.

O contrato remove campos da escala, referências, grupos, distâncias às
referências e ITA. Não há aliases de compatibilidade para o contrato v2.
`quality.released_for_matching: false` registra a ausência de validação anotada.

Qualidade reduzida mantém a cor e as recomendações. Catálogo vazio/inválido gera
erro; nunca é substituído pela demonstração. Todo resultado concluído inclui
`status_analise: concluida` e pelo menos uma base. JSON e NDJSON usam o mesmo
algoritmo. A demonstração e seu endpoint `/api/exemplo` foram removidos;
`/como-funciona` documenta o funcionamento sem gerar um resultado fictício.

## Limites e interface

`match.experimental: true` e `match.validado: false` permanecem. A medição regional
reduz extremos e discrepâncias; não corrige uma dominante de iluminação uniforme,
não recupera cor física e não infere subtom. HEX de catálogo não são medições de
bases aplicadas. Não há percentual de compatibilidade ou limiar cosmético validado.

O frontend exige o contrato v3, exibe a cor estimada e preserva a ordem das bases.
Um único aviso no topo reúne as ressalvas. A demonstração é identificada.

## Testes

```powershell
.venv\Scripts\python -m unittest backend.tests.test_tone_matching backend.tests.test_regional_measurement -v
.venv\Scripts\python -m unittest discover -s backend/tests -v
```

Cobertura: referência CIEDE2000 de Sharma, conversão HEX, ranking global,
empates, catálogo inválido/vazio, ausência da classificação antiga no payload,
mudança de foto, exclusões, falha de especialista e paridade JSON/NDJSON.
As cenas regionais cobrem pele clara/escura, sombras, reflexos, clipping,
fallback, preservação de máscaras/bbox e sensibilidade do ranking.
São verificações de engenharia, não validação cosmética em pessoas reais.
