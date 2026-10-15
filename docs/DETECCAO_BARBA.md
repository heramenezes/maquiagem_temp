# Detecção de barba e bigode — YOLOv8l-seg

Adotado em 15/10/2026 no lugar do EasyPortrait. Origem:
[prashants975/Beard-Hair-Image-Segmentation](https://github.com/prashants975/Beard-Hair-Image-Segmentation/tree/510f0ca6c66d42a1c52add09669fd36ee1e65af0).
O checkpoint `best_hair_117_epoch_v4.pt` contém `0: beard` e `1: hair`.
Bigode não é classe separada; os exemplos executados incluem bigode em `beard`.
Não se afirma cobertura geral de bigode isolado ou barba branca/rala.

## Instalação

Na raiz do projeto, a API mantém somente suas dependências ONNX/CPU.
PyTorch e Ultralytics são necessários apenas no ambiente de exportação:

```powershell
.venv\Scripts\python -m backend.download_model barba --sources
python -m venv .test-artifacts/model-export-env
.test-artifacts\model-export-env\Scripts\python -m pip install -r backend/requirements-export.txt
.test-artifacts\model-export-env\Scripts\python -m backend.export_models barba --validation-images caminho/foto_com_barba.jpg caminho/foto_com_bigode.jpg
```

Os caminhos das fotos são exemplos: use arquivos locais reais. A exportação
aborta se todas as máscaras forem vazias; isso impede aprovar equivalência
apenas pela ausência de detecção. Fotos adicionais não são enviadas à rede.
Reinicie o servidor após a instalação para substituir as sessões em cache.
O peso antigo do EasyPortrait pode permanecer no disco, mas não é carregado.

Fonte SHA-256: `6cc66194fe2ab067cced94f9831ea4ac93961d8323ce541193d4eb0aaf9e2e6a`.
Peso original: 92.276.690 bytes. Artefatos locais:
`backend/models/beard_yolov8l.pt`, `.onnx` e `.json` (ignorados pelo Git).
O download verifica a fonte; o runtime verifica versão, hash do ONNX e manifesto
de equivalência. Não há download nem fallback para EasyPortrait durante uploads.

## Inferência e composição

Entrada RGB/255, letterbox 640 × 640 com padding 114. O adaptador espera
detecções `(1,38,8400)` e protótipos `(1,32,160,160)`, verifica valores finitos
e os scores das duas classes. Somente propostas cuja classe vencedora é
`beard` são selecionadas; `hair` não gera exclusão nem incerteza de barba.

NMS IoU 0,7, limitado a 100 propostas. Confiança de instância ≥0,60 é aceita;
[0,25,0,60) é incerta. Probabilidade de máscara ≥0,65 é forte e [0,35,0,65)
é incerta. Os valores são hipóteses iniciais sem calibração anotada. As máscaras
das instâncias são reconstruídas pelos coeficientes/protótipos, recortadas às
caixas e restauradas ao recorte original antes dos limiares. Furos são preservados.
Bigode e barba desconectados podem formar várias instâncias e são unidos.

O RGB original não é modificado. `compose` intersecta exclusões com a anatomia
BiSeNet para medir apenas a pele candidata restante; máscaras brutas fora dessa
anatomia permanecem em `debug_masks`. Não recupera pele perdida pelo BiSeNet.
Fonte da API: `prashants975_yolov8l_seg`; evidência `modelo_especifico` com
`nominal_beard_class: true`. A categoria pública continua `barba`.

## Verificação local

Exportação em torch 2.7.1, Ultralytics 8.3.167, ONNX 1.18.0 e ONNX Runtime
1.31.0, opset 17. Seis entradas: ruído e cor uniforme não quadrados, duas fotos
locais de `samples/` e dois exemplos do repositório de origem (Balbo e stubble).
Duas entradas geraram máscaras não vazias. Maior erro absoluto entre saídas
PyTorch/ONNX: 0,00164794921875; menor IoU das máscaras aceitas/incertas: 1,0.
Isso verifica a conversão, não acurácia contra máscaras humanas.

Ainda é necessário medir contaminação residual, pele saudável removida, erro
de cor, negativos, diferentes tons/luzes e latência em conjunto representativo.
O YOLOv8l é a variante Large; não se promete tempo real em CPU. Acne e vitiligo
mantêm seus modelos. Os critérios de qualidade e a não liberação para Monk
continuam vigentes. O repositório de origem declara MIT; confira também os
termos de Ultralytics e dos dados antes de redistribuir os pesos.
