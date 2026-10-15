# Verificação de engenharia — 15/10/2026

Implementação apenas do backend, sem alterações em `frontend/`.

- 76 testes do backend passaram, incluindo inferência real de BiSeNet,
  acne, vitiligo e EasyPortrait em CPU e reutilização das sessões.
- 2 testes adicionais de avaliação offline passaram no ambiente com
  scikit-image/psutil: ΔE00, métricas de máscaras, ablações e registro de falhas.
- `compileall` e `git diff --check` passaram.
- Testes antigos do crescimento geométrico tiveram o import corrigido
  para apontar explicitamente para `skin.py`; o método não foi reativado.

## Exportação

Ambiente separado: Python 3.13, torch 2.7.1 CPU, SMP 0.5.0, Ultralytics
8.3.167, ONNX 1.18.0, ONNX Runtime 1.31.0. Quatro inputs por conversão:
ruído determinístico não quadrado, cor uniforme não quadrada e duas imagens
JPEG locais. Comparação das saídas numéricas e das máscaras após os limiares:

| Modelo | Maior erro absoluto na saída | Menor IoU entre máscaras PyTorch/ONNX |
|---|---:|---:|
| Acne | 0,0000429153 | 1,0 |
| Vitiligo | 0,0017089844 | 1,0 |

Essas máscaras não foram comparadas a anotação humana. Máscaras vazias
em ambas as implementações contam como concordância, não como evidência
de sensibilidade. A exportação preserva a rede; não comprova desempenho facial.
Manifestos locais registram SHA-256 e versões; o runtime os verifica.

## Execução local em Windows/CPU

`samples/imagem_teste.jpeg`, recorte nativo RGB de 133 × 133 pixels,
seis execuções sequenciais no Python do backend:

| Medida | Resultado |
|---|---:|
| Primeira execução, incluindo carga das redes | 1.517,70 ms |
| Cinco execuções aquecidas, p50 | 510,22 ms |
| Cinco execuções aquecidas, p95 | 517,01 ms |
| Pico de working set do processo | 863,78 MiB |

O cronômetro inclui BiSeNet, Lab e seleção; não inclui detector do recorte,
upload ou PNG/JSON. A memória inclui todo o processo. Uma foto e cinco
repetições aquecidas são um smoke test, não benchmark representativo.

Todos os módulos executaram. Dos 5.538 pixels anatômicos, ficaram 1.396
candidatos válidos; 350 foram excluídos e 3.792 ficaram incertos sem já estar
excluídos. O resultado foi **inconclusivo** por incerteza excessiva e mudança
de cor ao incluir áreas incertas. A API não emitiu média utilizável.
Isso registra o comportamento, não confirma os motivos das exclusões:
EasyPortrait apresentou forte discordância nesta foto inclinada e pequena.

## Pendências para validar o plano

Ainda faltam o piloto com anotações humanas, positivos/negativos/confusores,
divisão por pessoa, calibração de limiares e análise estratificada por tom,
luz e condição. A ferramenta `backend.evaluate_selection` está pronta para
essas comparações; não foi usada para fabricar uma referência de avaliação.

`quality.calibration` permanece provisória e `released_for_monk` permanece
`false`. Frontend e conversão para Monk continuam fora desta implementação.
