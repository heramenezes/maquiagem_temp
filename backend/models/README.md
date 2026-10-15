# Modelos locais para anatomia e seleção de pele

O runtime da API usa somente ONNX Runtime em CPU. BiSeNet é preservado;
acne e vitiligo são exportados em um ambiente separado. Nenhum upload dispara
download ou exportação. Pesos e manifestos gerados não são versionados.

## Instalação completa

Na raiz, com o Python do backend:

```powershell
.venv\Scripts\python -m backend.download_model all --sources
python -m venv .test-artifacts/model-export-env
.test-artifacts\model-export-env\Scripts\python -m pip install -r backend/requirements-export.txt
.test-artifacts\model-export-env\Scripts\python -m backend.export_models acne vitiligo
.test-artifacts\model-export-env\Scripts\python -m backend.export_models barba --validation-images caminho/foto_com_barba.jpg caminho/foto_com_bigode.jpg
```

`python -m backend.download_model` continua instalando apenas BiSeNet;
`python -m backend.download_model barba --sources` baixa o YOLOv8l-seg de
barba. Depois exporte-o com `python -m backend.export_models barba
--validation-images caminho/foto_com_barba.jpg caminho/foto_com_bigode.jpg`.
A exportação de barba exige ao menos uma previsão não vazia na verificação.
A opção `--sources` é necessária para baixar os pesos PyTorch dos especialistas.
Pare o servidor antes de substituir modelos: sessões são reutilizadas até
reiniciar o processo. A exportação confere SHA-256 das fontes, compara saídas
PyTorch/ONNX e máscaras em inputs determinísticos e amostras locais, e instala
um manifesto com hash do ONNX, versões e métricas de equivalência. Um manifesto
ausente/incompatível ou hash incorreto torna o especialista indisponível.

## Especialistas

| Categoria | Origem fixada | Entrada | Saída |
|---|---|---|---|
| Acne | [RihemXX/Acnes](https://huggingface.co/spaces/RihemXX/Acnes/tree/f036e69c3a2e87ddbe4dfd4543c9d0ecc9b5ba8c) | RGB/ImageNet, 256², resize | U-Net/ResNet34, logits binários |
| Vitiligo | [rayronvictor](https://github.com/rayronvictor/vitiligo-segmentation/tree/409da766d3deef87e41545928acac3ab815384ea) | RGB/255, letterbox 416², padding 114 | YOLO11n-seg; classe 0 `vitiligo`, 32 protótipos |
| Barba/bigode | [prashants975/Beard-Hair-Image-Segmentation](https://github.com/prashants975/Beard-Hair-Image-Segmentation/tree/510f0ca6c66d42a1c52add09669fd36ee1e65af0) | RGB/255, letterbox 640², padding 114 | YOLOv8l-seg; classe 0 `beard`, classe 1 `hair` ignorada; 32 protótipos |

SHA-256 das fontes:

- Acne `.pth`: `c58a6af6fb622d916e4aa788d9f620d59df4a42209f655ce4a9db49686c05697`.
- Vitiligo `.pt`: `9558d5be11e1657f6e6c9d27bc4839f5fa5b2aaeea10868837b45509608e0f09`.
- Barba `.pt`: `6cc66194fe2ab067cced94f9831ea4ac93961d8323ce541193d4eb0aaf9e2e6a`.

O checkpoint de vitiligo foi inspecionado: contém `yolo11n-seg.yaml` e
somente a classe `vitiligo`. Sua descrição de treino usa uma divisão de
cross-validation; isso não comprova desempenho facial no projeto.

Barba usa o arquivo `best_hair_117_epoch_v4.pt` (92.276.690 bytes), instalado
como `beard_yolov8l.pt`; ONNX e manifesto são `beard_yolov8l.onnx/.json`.
Saídas: detecções `(1,38,8400)` e protótipos `(1,32,160,160)`. Somente propostas
cuja classe vencedora é `beard` entram no NMS (IoU 0,7; até 100 propostas).
Confiança ≥0,60 aceita; [0,25,0,60) incerta. Probabilidade de máscara usa
0,65/0,35. São limiares provisórios. Máscaras são restauradas antes de aplicar
limiares e a união inclui bigode quando previsto como `beard`. Não há regra
de textura ou dependência de nariz. Veja [detalhes](../../docs/DETECCAO_BARBA.md).

Procedência/licenças: o código Acnes declara Apache-2.0; o repositório de barba
declara MIT, enquanto dados e Ultralytics possuem termos próprios. O checkpoint
de vitiligo não apresenta licença clara na origem; Ultralytics tem termos
próprios. Integridade e equivalência numérica não validam qualidade ou
permissão de distribuição dos pesos. Consulte a pesquisa do projeto antes
de redistribuir modelos. O servidor não importa os apps Gradio originais.

## BiSeNet ResNet18

Instalação: `python -m backend.download_model`, a partir da raiz do projeto.
O peso é baixado uma vez; a análise de fotos funciona localmente, sem rede.

- Autor: Yakhyokhuja Valikhujaev.
- Projeto: https://github.com/yakhyo/face-parsing
- Release fixado: `v0.0.1`, arquivo `resnet18.onnx`, 53.205.364 bytes.
- Origem: https://github.com/yakhyo/face-parsing/releases/download/v0.0.1/resnet18.onnx
- SHA-256: `0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f`.
- Licença do código de referência: [MIT, Copyright (c) 2024 Yakhyokhuja Valikhujaev](https://github.com/yakhyo/face-parsing/blob/main/LICENSE).
- Dados de treinamento: [CelebAMask-HQ](https://github.com/switchablenorms/CelebAMask-HQ), com condições próprias para pesquisa não comercial.

O arquivo ONNX não é versionado. O instalador verifica a integridade antes
de substituir o arquivo local. O runtime verifica o hash antes de criar sua
primeira sessão e reutiliza essa sessão em CPU. Não há treinamento próprio,
download automático durante uploads nem fallback silencioso para geometria.

Entrada: RGB, 512 × 512, float32, normalização ImageNet conforme o autor.
Saída: 19 classes. Para este projeto, pele = `skin` (1) + `nose` (10).
Olhos, sobrancelhas, boca, lábios, óculos, cabelo, orelhas, pescoço, roupa e
fundo não entram na máscara. Não existe classe própria de barba.
