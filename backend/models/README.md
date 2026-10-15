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
```

`python -m backend.download_model` continua instalando apenas BiSeNet;
`python -m backend.download_model barba` instala EasyPortrait. A opção
`--sources` é necessária para baixar os pesos PyTorch dos dois especialistas.
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
| Barba/bigode | [EasyPortrait ONNX](https://huggingface.co/sadzip/EasyPortrait-ONNX/tree/19e22b9d1bfd87e67b82e4b2749405686aeecba2) | BGR, resize 512², normalização própria | SegFormer-B0 **fp**, oito classes; não possui classe barba |

SHA-256 das fontes:

- Acne `.pth`: `c58a6af6fb622d916e4aa788d9f620d59df4a42209f655ce4a9db49686c05697`.
- Vitiligo `.pt`: `9558d5be11e1657f6e6c9d27bc4839f5fa5b2aaeea10868837b45509608e0f09`.
- EasyPortrait `.onnx`: `6be671f5cd146ecaebc982d6f2598889e804bb3cb90a619fb95842afb7d22d0b`.

O checkpoint de vitiligo foi inspecionado: contém `yolo11n-seg.yaml` e
somente a classe `vitiligo`. Sua descrição de treino usa uma divisão de
cross-validation; isso não comprova desempenho facial no projeto.

EasyPortrait usa média BGR `[143.55267075,132.96705975,126.94924335]` e desvio
`[60.2625333,60.32740275,59.30988645]`. Classes 0/1 são fundo/pele; as demais
são sobrancelhas, olhos, lábios e dentes. A integração não transforma toda
discordância com BiSeNet em barba: requer posição inferior ancorada no nariz,
textura e alta probabilidade de fundo. O restante permanece incerto.

Procedência/licenças: o código Acnes declara Apache-2.0; a conversão EasyPortrait
declara Apache-2.0, mas a origem/dados possuem termos próprios. O checkpoint
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
