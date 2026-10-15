# Pesquisa: acne, vitiligo e barba antes do tom Monk

> Atualização de implementação em 15/10/2026: foi adotado o YOLOv8l-seg de
> prashants975, com classes explícitas `beard`/`hair`, substituindo EasyPortrait.
> A pesquisa abaixo registra as alternativas anteriores. Consulte
> [a implementação atual e sua verificação](DETECCAO_BARBA.md).

Revisão de **15/10/2026**. Escopo acordado: manter BiSeNet e acrescentar seleção independente de pele para excluir acne, vitiligo, barba e bigode. **Rosácea saiu do escopo.** Não haverá análise específica de maquiagem.

Esta revisão substitui a recomendação anterior. Inclui novas buscas, inspeção de scripts, árvores de arquivos, ponteiros Git LFS e cabeçalhos HTTP. **Não houve execução dos novos modelos, download integral dos pesos ou benchmark local.** Arquivo disponível, qualidade da máscara e adequação ao rosto são evidências diferentes. O planejamento está em [PLANO_SELECAO_PELE.md](PLANO_SELECAO_PELE.md).

## Arquitetura e escolhas

| Responsabilidade | Candidato prioritário para avaliar | Alternativa | Prontidão |
|---|---|---|---|
| Anatomia facial | BiSeNet atual | Nenhuma troca planejada | Já integrado. |
| Acne | U-Net/ResNet34 de `rihem-bs02/Acnes` | SegFormer-B1; SA-RPN | Peso publicado; qualidade local desconhecida. |
| Vitiligo | YOLO de `rayronvictor/vitiligo-segmentation` | GloW-VSNet; treinamento próprio | Peso localizado nesta revisão; falta validação facial. |
| Barba, incluindo bigode | SAM ajustado de `HkKhan/beard` | EasyPortrait como auxiliar; segmentador leve treinado | Checkpoint SAM acessível, mas pesado; EasyPortrait não identifica barba nominalmente. |
| Composição e qualidade | União de exclusões aceitas, incerteza e cobertura | Comparação entre regiões e sensibilidade da cor | Nova lógica do projeto. |

A tabela define **ordem de experimentação**, não adoção incondicional. Cada especialista recebe o recorte original, sem áreas pintadas de preto pelas etapas anteriores. As máscaras são alinhadas e combinadas depois.

## 1. Acne

### Candidato principal: U-Net/ResNet34

[Acnes](https://github.com/rihem-bs02/Acnes) separa segmentação e severidade. A primeira usa U-Net/ResNet34, entrada 256×256 e limiar demonstrativo 0,20. O peso [`Acnes_model.pth`](https://huggingface.co/spaces/RihemXX/Acnes/tree/main), de 97,9 MB, está listado publicamente. O README reconhece ausência de protocolo reproduzível para as métricas divulgadas; o Space consultado mostrava erro de execução.

**Integração:** extrair apenas a segmentação, obter probabilidades, desfazer o redimensionamento e produzir `mask_acne`. Calibrar limiar com fotos positivas e negativas. Testar PyTorch separado e depois exportar para ONNX, se compatível, comparando as saídas. Gradio e o classificador de severidade não são necessários.

**Tradeoffs:** implementação relativamente simples, mas resolução baixa pode apagar lesões pequenas. Blocos ou entrada maior alteram contexto/escala e precisam de experimento. Não copiar o limiar da demonstração nem usar sua métrica como garantia local.

| Alternativa | Evidência | Avaliação |
|---|---|---|
| [Merligus/acne-detection](https://github.com/Merligus/acne-detection) | README lista pesos externos de SegFormer-B1, YOLO e DINOv3. | Comparar SegFormer se U-Net falhar; auditar acesso e origem das máscaras. Contagem/severidade não substituem segmentação. |
| [SA-RPN / Kumario1](https://github.com/Kumario1/sa-rpn-acne-detection) | [Release v1.0](https://github.com/Kumario1/sa-rpn-acne-detection/releases/tag/v1.0) com `epoch_15.pth`, 357.770.711 bytes. | Mask R-CNN com stack MMDetection/MMCV antiga; integração CPU/Windows e exportação mais complexas. A API ilustrada retorna caixas: extrair máscaras reais. |
| [VL-AcneSeg](https://github.com/sukjuoh/VL-AcneSeg) | Código oficial de CLIP em blocos e refinamento Transformer; checkpoint treinado não confirmado. | Referência científica recente; não primeira opção operacional. |

O [artigo VL-AcneSeg, setembro de 2026](https://arxiv.org/abs/2609.34472), reporta Dice 0,5082 e IoU 0,3407 com prompt global no conjunto clínico interno. É relevante por tratar pequenas lesões na face completa. Não comparar diretamente com métricas em outras bases ou prompts que já informem localização.

**Dados:** [ACNE04](https://github.com/xpwu95/LDL) e [Acne04-v2](https://github.com/AIpourlapeau/acne04v2) ajudam em localização, mas caixas/centros/raios não equivalem a contornos exatos. [AcneSCU/SA-RPN dos autores](https://github.com/pingguokiller/acnedetection) tem dados mediante contato e restrição comercial. Verificar termos de código, dados e pesos separadamente.

## 2. Vitiligo

### Novo candidato prático: YOLO com peso incluído

A inspeção encontrou [`models/vitiligon-seg.pt`](https://github.com/rayronvictor/vitiligo-segmentation/tree/main/models), **5.982.116 bytes**, não confirmado na pesquisa anterior. O [`app.py`](https://github.com/rayronvictor/vitiligo-segmentation/blob/main/app.py) carrega esse arquivo via Ultralytics com `imgsz=416`. Os requisitos fixam Ultralytics 8.3.167. O app também contém medição em mãos com adesivo de referência; isso não comprova adequação facial. Não foi localizada licença identificável pela API nem avaliação facial reproduzível.

**Integração:** isolar a inferência e as máscaras de instância. Tratar `r.masks is None`; unir máscaras por OR lógico, evitando soma com conversão para uint8 do exemplo. Conferir classes, padding e escala. Não trazer `rembg`, adesivo ou Gradio. O treino usa `yolo11x-seg.pt`, mas isso não basta para identificar a variante do peso distribuído: confirmar no artefato.

**Decisão:** primeiro experimento de vitiligo, pela existência de peso e chamada concreta. A [exportação ONNX do Ultralytics](https://docs.ultralytics.com/modes/export/) é uma rota possível, ainda não testada nesse arquivo. Fixar versão e conferir máscaras após conversão. Verificar [licenciamento Ultralytics](https://www.ultralytics.com/license) e permissões/procedência do checkpoint.

### Estado da arte e alternativas

[GloW-VSNet](https://pubmed.ncbi.nlm.nih.gov/41468636/) é uma referência recente de supervisão fraca com agrupamento e atenção espacial. O [repositório oficial](https://github.com/YuhanZheng0327/Weakly-Supervised-Vitiligo-Lesion-Segmentation) tem checkpoint, mas seu `demo.py` reorganiza a saída em 50 canais, faz `argmax` e aplica cores aleatórias, sem mapear lesão. A demonstração não solicita rabiscos na inferência. Esclarecer o significado dos rótulos antes de usar; não escolher um ID pela aparência em uma única imagem.

| Alternativa | Contribuição | Limite |
|---|---|---|
| [BLVS](https://github.com/JcWang20/BLVS) | Código relacionado a segmentação semissupervisionada e dados bimodais. | Não confirmado pacote completo de dados/peso pronto; avaliar RGB comum. |
| [AFDAN, dezembro de 2025](https://arxiv.org/abs/2512.16393) | Preprint com alinhamento no domínio de frequências e resultados em VITILIGO2025. | Não confirmado pacote oficial de inferência com peso nesta busca. |
| [HDA-Synthetic Vitiligo Faces, WACV Workshop 2026](https://github.com/dasec/HDA-Synthetic-Vitiligo-Faces) | Faces sintéticas com padrões e referências; acesso mediante solicitação. | Ajuda potencial ao treinamento, sem substituir teste em fotos reais. |

O resultado [Uncertainty-Aware Domain Adaptation](https://arxiv.org/abs/2512.11791), encontrado nas buscas, foi retirado pelos autores em junho de 2026. Suas métricas não fundamentam esta recomendação.

**Limite:** região clara não é automaticamente vitiligo. Brilho e diferenças de iluminação/pigmentação confundem regras de cor. Não escolher o grupo mais escuro como referência obrigatória. Se não restar referência suficiente, o cálculo fica inconclusivo. Vitiligo continua sendo pele; a exclusão atende ao objetivo cosmético definido.

## 3. Barba, incluindo bigode

### Candidato específico: SAM ajustado

[HkKhan/beard](https://github.com/HkKhan/beard) contém SAM ajustado e prompts derivados de Face Mesh. `checkpoints/sam_beard_best.pth` é um ponteiro Git LFS: o objeto declarado tem **407.639.119 bytes**, e a consulta HTTP HEAD retornou 200 com esse tamanho. Não foi baixado/executado. A documentação indica 139 imagens de treino e 55 em cada divisão de validação/teste, o que não estabelece cobertura ampla de tons ou tipos de barba.

**Integração:** testar máscara específica com prompts automáticos e casos sem barba, bigode isolado, barba branca e rala. Extrair a segmentação do fluxo de captura/projeção. Face Mesh exige avaliar dependências compatíveis com o ambiente alvo; não tornar o MediaPipe legado obrigatório silenciosamente.

**Tradeoffs:** fornece candidato semanticamente específico, mas é pesado e depende da qualidade dos prompts. Um teste com marcação manual não valida automação. Não foi identificada licença do repositório pela API. Medir CPU/RAM antes de decidir sua permanência.

### Alternativa auxiliar: EasyPortrait

O [EasyPortrait oficial](https://github.com/hukenovs/easyportrait) publica modelos de face parsing. Sua [política de anotação](https://www.scitepress.org/Papers/2025/131353/131353.pdf) exclui barba visível da pele, mas pode manter fios isolados/pouco perceptíveis. **Não tem classe explícita de barba.**

Existem [conversões ONNX de terceiro](https://huggingface.co/sadzip/EasyPortrait-ONNX/tree/main), incluindo `segformer_b0_fp_512.onnx`, listado com 15,2 MB. A [model card](https://huggingface.co/sadzip/EasyPortrait-ONNX) especifica BGR e normalização própria. O [manifesto](https://huggingface.co/sadzip/EasyPortrait-ONNX/blob/main/manifest.json) contém diferentes contagens de classes entre variantes: auditar a escolhida, sem copiar IDs do dataset/BiSeNet. Usar `fp`, não modelos `ps` de pessoa/fundo. A conversão declara Apache-2.0; a origem remete a licença específica baseada em CC BY-SA. Conferir permissões na origem.

**Uso proposto:** diferenças entre `pele_BiSeNet` e `pele_EasyPortrait` geram candidatos corroborados por textura e localização. **Essa diferença não é `mask_barba`**: também contém erros e bordas. Uma interseção global pode remover pele válida ou regiões de vitiligo; medir esse efeito antes de adotar. Se a prioridade for exclusão, essa alternativa pode ser útil; para afirmar “barba”, é necessário modelo específico ou evidência validada.

Se os modelos prontos não atenderem, treinar segmentador binário leve com as [anotações de pelos do trabalho FG 2025](https://github.com/kaganozturk/Effects-of-Facial-Hair-on-Face-Recognition) e exemplos locais. [Segmentation Models PyTorch](https://github.com/qubvel-org/segmentation_models.pytorch) fornece arquiteturas/encoders, não pesos de barba prontos. O custo é anotação/treinamento, com potencial de inferência mais adequada a CPU.

O [jseobyun/FaceParsing](https://github.com/jseobyun/FaceParsing), VGG19/DINOv3 com classe de barba, continua sem peso localizado na árvore auditada e não é a primeira opção.

## Combinação e custos

Vários módulos não significam instalar todos os candidatos. A configuração pretendida tem BiSeNet, uma solução aprovada para cada uma das três categorias específicas.

| Estratégia | Benefício | Custo/risco |
|---|---|---|
| Especialistas separados | Substituição e avaliação por categoria. | Mais RAM, latência e adaptadores. |
| Modelo único multiclasses | Uma inferência especializada. | Dataset comum e treinamento; não confirmado peso pronto adequado. |

Unir somente exclusões aceitas; manter incerteza separada. Não somar probabilidades de redes como se fossem calibradas/independentes. A mesma região pode ter vários motivos e conta uma única vez na área total removida. Qualidade da captura é estado técnico, não categoria adicional.

Preservar RGB para medição; normalizações ficam nas entradas das redes. Seleção não corrige iluminação, um problema documentado em [pesquisa de estimação sob diferentes luzes](https://pubmed.ncbi.nlm.nih.gov/38786563/). O plano inclui cobertura, estabilidade e avaliação da cor antes de Monk.

## Evidência da auditoria

SHA das árvores retornadas pela API do GitHub, não hashes dos pesos:

| Repositório | SHA da árvore | Achado |
|---|---|---|
| `rayronvictor/vitiligo-segmentation` | `409da766d3deef87e41545928acac3ab815384ea` | Peso e chamada no app. |
| `HkKhan/beard` | `d8cae784e0d69d81b97b2862819428e436187bca` | Ponteiro LFS e HEAD do objeto com 200. |
| `jseobyun/FaceParsing` | `bb649e99424ea988ca2bec8b5a3c8e8ca33f3f2e` | Sem arquivo de peso localizado. |
| `hukenovs/easyportrait` | `1b3d3e508813f57f585bd8943b4af9d61268d359` | Código e links externos de checkpoints. |

O ponteiro SAM declara SHA-256 `7521604608986d119ddd49e8c19aa8e867c5aae0137b74a00a82776170840ec5`, ainda não conferido contra download integral. Tamanho de arquivo não mede RAM/latência. A busca foi direcionada, não uma revisão sistemática; métricas de diferentes tarefas/datasets não estabelecem um vencedor universal.
