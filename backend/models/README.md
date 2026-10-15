# BiSeNet ResNet18

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
