# Pesquisa: segmentação facial pré-treinada

Pesquisa em 15/10/2026. Objetivo: preservar pele próxima de olhos e boca,
sem treinamento próprio e com integração simples ao Flask existente.
Registro da pesquisa anterior à implementação. A recomendação foi integrada
em `semantic.py`; consulte o README de segmentação para o funcionamento atual.
Este documento não representa um benchmark comparativo dos modelos pesquisados.

## Diagnóstico local

Em `backend/src/segmentation/skin.py`, a instalação atual usa `geometria_frontal`:

- Elipses fixas excluem olhos, sobrancelhas e boca, independentemente da pose.
- Retângulos de olhos Haar acrescentam exclusões com margens.
- `grow_skin` nunca recupera pixels dessas exclusões. Ainda elimina pixels
  por cromaticidade, luminância, textura e conectividade.
- No caminho opcional MediaPipe, os polígonos também são dilatados.

Medição reproduzida com `samples/imagem_teste.jpeg`, sem alterar o código:

| Medida | Pixels |
|---|---:|
| Contorno estimado | 7.825 |
| Exclusões dentro desse contorno | 3.605 (46,1%) |
| Área permitida antes dos filtros de cor | 4.220 |
| Máscara final | 1.723 (22,0% do contorno) |

O recorte dessa amostra tem 133 × 133 pixels. Ampliá-lo para a entrada de um
modelo não recupera detalhes ausentes. Estes percentuais não são acurácia:
sem anotação de referência não sabemos quantos pixels descartados eram pele.

## Soluções verificadas

| Solução | Disponibilidade e avaliação para este projeto |
|---|---|
| [BiSeNet / yakhyo](https://github.com/yakhyo/face-parsing) | Pesos ResNet18 e ResNet34 em PyTorch e ONNX. Melhor ponto de partida para simplicidade. |
| [SegFace, AAAI 2025](https://github.com/Kartik-3004/SegFace) | Pesos públicos, incluindo MobileNet. Referência moderna de desempenho, com integração PyTorch mais trabalhosa que o ONNX já disponível acima. |
| [SegFormer / Jonathan Dinu](https://huggingface.co/jonathandinu/face-parsing) | Modelo MiT-B5 ajustado para CelebAMask-HQ, com exemplos Transformers e artefatos ONNX. Alternativa pronta; avaliar custo no computador do projeto. |
| [FaceXFormer, ICCV 2025](https://github.com/Kartik-3004/facexformer) | Pesos e inferência públicos para várias tarefas faciais. Abrange mais tarefas do que precisamos; não é minha primeira escolha para esta integração. |

SegFace reporta F1 médio de 88,96 no CelebAMask-HQ e 93,03 no LaPa no
trabalho; a tabela de checkpoints possui resultados próprios por variante.
Esses números não equivalem a acurácia da pele nas nossas fotos e não devem
ser comparados diretamente a medidas obtidas com outro protocolo.

Entre trabalhos de 2026, [DIME](https://arxiv.org/abs/2610.17015) propõe
representações faciais e relata avanços também em face parsing. A página
consultada não bastou para confirmar um pacote pronto de segmentação que
seja mais simples de integrar. O trabalho é um preprint recente, não motivo
suficiente para adotá-lo aqui.

## Escolha recomendada e integração

Minha recomendação de engenharia é **BiSeNet ResNet18 + ONNX Runtime em CPU**.
O [código de inferência do autor](https://github.com/yakhyo/face-parsing/blob/main/onnx_inference.py)
já documenta entrada 512 × 512, normalização RGB e saída por classe. É possível
usar o arquivo ONNX pronto sem trazer PyTorch e o treinamento para a aplicação.
O tempo e a qualidade locais ainda precisam ser medidos.

1. Fixar a versão e o checksum do peso baixado; carregar uma sessão por processo.
2. Usar o recorte facial existente como entrada. Preservar o RGB original para CIELAB;
   a normalização do modelo não deve mudar os pixels usados para medir cor.
3. Usar as classes `skin` e `nose` como pele facial. No checkpoint yakhyo,
   os IDs são 1 e 10; não copiar IDs de outros modelos, que usam outra ordem.
   [Mapa de classes](https://github.com/yakhyo/face-parsing/blob/main/utils/common.py).
4. Substituir as elipses, retângulos e margens grandes pela máscara semântica.
   Não acrescentar dilatação ou erosão geral sem evidência de necessidade.
5. Separar a segmentação anatômica da análise de cor: K-means pode analisar os
   pixels selecionados, mas não deve obrigar toda a pele a pertencer a uma única
   região de cor conectada. Isso precisa ser documentado como evolução do método
   acadêmico anterior, que usava crescimento de regiões.
6. Reaproveitar a máscara RGBA na foto final e as marcações fictícias existentes.
   Atualizar os nomes das etapas de carregamento para refletirem o fluxo real.
7. Comparar antes/depois em fotos variadas: olhos fechados, sorriso, cabeça
   inclinada, diferentes tons de pele, barba, óculos e luz desigual. Inspecionar
   bordas e contaminação por regiões excluídas; mais área, sozinha, não é sucesso.

## Barba e condições de uso

O mapa de classes do modelo recomendado **não tem classe específica de barba**.
Uma máscara de cabelo não garante a exclusão de barba. Não prometer isolamento
de pelos faciais sem avaliar esse caso separadamente.

O repositório [jseobyun/FaceParsing](https://github.com/jseobyun/FaceParsing)
documenta uma classe de barba usando VGG19 e DINOv3. Exige pesos separados e
merece verificar acesso efetivo aos checkpoints e desempenho antes de adoção;
nesta pesquisa não validei sua execução. Não é a escolha mais simples agora.

O código yakhyo tem licença MIT. O [CelebAMask-HQ](https://github.com/switchablenorms/CelebAMask-HQ)
publica condições próprias para pesquisa não comercial; a licença do código
não deve ser confundida com as condições dos dados e pesos derivados.
