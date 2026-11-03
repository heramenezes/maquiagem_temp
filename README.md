# Meu tom

Aplicação acadêmica de análise de tons de pele e recomendação de bases.

O frontend usa HTML, Bootstrap 5.3.8, CSS do tema e JavaScript em módulos nativos. O Flask serve a interface e a API no mesmo endereço: não há build, Node.js obrigatório, banco de dados ou configuração de CORS. O Bootstrap e a fonte Archivo são servidos localmente, com suas licenças incluídas.

## Executar no Windows

Na raiz do projeto, com Python 3.11 ou superior (validado com Python 3.13):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m backend.download_model
.venv\Scripts\python -m backend.app
```

Abra http://127.0.0.1:5000. Não abra `frontend/index.html` diretamente pelo explorador de arquivos, pois as chamadas HTTP dependem do servidor.

Em Linux/macOS, substitua `.venv\Scripts\python` por `.venv/bin/python`.

Para a seleção completa de pele, instale também acne, vitiligo e YOLOv8l-seg de barba
seguindo [backend/models/README.md](backend/models/README.md). A instalação
acima inclui somente BiSeNet; sem os especialistas a API mantém a medição e
as bases com aviso de precisão reduzida. A conversão dos pesos ocorre em ambiente separado.

## O que funciona

- Escolher uma foto, arrastar e soltar, revisar, trocar e reenviar.
- Botão de câmera nativa (`capture="user"`): no celular, depende do navegador; no computador, abre o seletor de arquivos. Não há webcam ao vivo.
- Upload de JPG, PNG ou WebP, com até 10 MiB e 24 megapixels. HEIC precisa ser convertido para JPG.
- Correção de orientação EXIF e redimensionamento proporcional até 1600 pixels antes da detecção.
- Pré-verificação de um único rosto: MediaPipe quando disponível; Haar/OpenCV como fallback quando o MediaPipe não retorna uma detecção. Um rosto é aceito sem uma segunda conferência; múltiplos rostos abortam imediatamente.
- Sem rosto ou com múltiplos rostos detectados, a API retorna 422 e a interface pede outra foto. Conversão CIELAB, segmentação e resultado não são executados. No stream, o evento de erro informa o status 422.
- Conversão real sRGB → RGB linear → XYZ → CIELAB (D65), normalizando perfis ICC para sRGB quando presentes.
- Segmentação semântica com BiSeNet ResNet18 pré-treinado, executada localmente em CPU via ONNX Runtime. Pele e nariz são selecionados pixel a pixel, sem exclusões geométricas grandes. O modelo não tem classe específica de barba.
- Seleção independente com U-Net para acne, YOLO11n para vitiligo e YOLOv8l-seg específico para barba/bigode; estados e máscaras reais por módulo.
- K-means descreve a anatomia sem remover pixels. A medição usa a seleção disponível; os critérios técnicos de qualidade geram avisos.
- Progresso real em dez etapas, recorte RGB preservado, prévias e estatísticas; toda análise concluída inclui tom e bases, mesmo com ressalvas.
- Catálogo real com 281 cores, carregado de `backend/data/bases.csv`.
- Exemplo acessível sem enviar foto, erros de conexão, nova tentativa e cancelamento de solicitações na interface.

A pré-verificação conta as detecções válidas antes do recorte: zero rostos pede outra foto, um rosto passa e mais de um aborta. Não há conferência por um segundo detector nem reagrupamento das caixas retornadas pelo detector. O Haar considera caixas a partir de 40 × 40 pixels na imagem redimensionada. A detecção ainda pode falhar em rostos muito pequenos, de perfil ou parcialmente cobertos e pode produzir falsos positivos. Ela não certifica iluminação, nitidez ou ausência de maquiagem.

## Match de tom e recomendações

Uploads usam a mediana Lab dos pixels selecionados para classificar o tom
Monk e recomendar bases. O ranking prioriza o mesmo Monk e refina por
CIEDE2000 pele/base; se necessário, completa com outros grupos pela distância
entre referências Monk. Qualidade reduzida mantém o tom e as bases com aviso.
ITA fica `null`; não participa dessa estratégia. O resultado é experimental,
sem correção de iluminação ou validação de bases aplicadas na pele.

A interface mostra o tom estimado, a cor medida da foto, a referência Monk e
as bases na ordem enviada pelo backend, com preços, links e diferenças de cor.
Análises com ressalvas mostram um único aviso no topo, explicando todos os fatores
que podem tornar o tom incorreto. A estimativa continua usando pixels reais da foto.
`/api/exemplo` continua usando fixtures de `backend/src/mock_analysis.py`,
identificadas como demonstrativas. Não há percentual de compatibilidade inventado.
Veja o [algoritmo e contrato](backend/src/tone_matching/README.md).

## Avisos de precisão e recomendação contínua

Após a confirmação de um rosto, qualidade de imagem e indisponibilidade dos
modelos não bloqueiam o tom ou as bases. Toda resposta final inclui
`status_analise: concluida`, `match.status: calculado`, `tom` e até três produtos.
O catálogo precisa conter produtos; catálogo vazio/inválido e falhas inesperadas
continuam sendo erros de serviço, sem uma tela final sem recomendações.
Arquivos inválidos e fotos sem rosto ou com múltiplos rostos continuam recusados
antes da análise de cor. Conexão, cancelamento e timeout mantêm seu tratamento.

O frontend mostra **um único aviso no topo** quando houver ressalvas:
**“O tom estimado pode estar incorreto.”** O aviso explica todos os motivos,
identifica os especialistas indisponíveis e permite expandir as medidas e os
limites recebidos do servidor. O tom e os produtos continuam visíveis.

### Limiares de qualidade

Fonte: [`QualityConfig` e `evaluate`](backend/src/skin_selection/quality.py).
São referências provisórias para gerar avisos, sem validação de acurácia.
Atingir exatamente um limite é permitido; a comparação usa a precisão original.

| Motivo na API | Gera aviso quando | Medida |
|---|---|---|
| `modulo_obrigatorio_indisponivel` | Algum especialista não conclui | Estado diferente de `executado` |
| `poucos_pixels_nativos` | Pixels válidos < 128 | Contagem na resolução do recorte |
| `cobertura_insuficiente` | Fração válida < 0,04 (4%) | Pele válida / anatomia inicial |
| `amostra_concentrada` | Extensão espacial < 0,05 (5%) | Menor razão entre extensões vertical e horizontal da seleção e da anatomia |
| `clipping_excessivo` | Fração com clipping > 0,20 (20%) | Algum canal RGB ≤ 2 ou ≥ 253 |
| `nitidez_insuficiente` | Nitidez < 2,0 | Variância do Laplaciano no interior erodido 3 × 3 da seleção |
| `iluminacao_desigual` | Amplitude de L* > 70,0 | Percentil 95 − percentil 5 |
| `cor_inconsistente` | Dispersão > 44,0 ΔE76 | Percentil 90 da distância Lab à mediana |
| `cor_sensivel_a_incerteza` | Mudança > 6,0 ΔE76 | Distância entre médias sem e com regiões incertas |
| `incerteza_excessiva` | Fração incerta > 0,70 (70%) | Incerteza não excluída / anatomia inicial |

As métricas descrevem a seleção estrita, antes de qualquer alternativa.
`quality.usable` indica ausência de ressalvas, sem impedir a medição quando
`false`. `quality.decision` é `aprovada` ou `com_ressalvas`.
`preprocessamento.medicao_utilizavel` indica medição disponível e é `true`
nos resultados. `match.motivos` lista as ressalvas e
`match.confianca_reduzida` indica se a lista é não vazia; não é uma probabilidade.

### Quando não restam pixels na seleção

A medição usa a primeira região não vazia, nesta ordem:

1. `pele_valida`: anatomia menos exclusões e incertezas.
2. `pele_com_incertezas`: anatomia sem exclusões aceitas, reincluindo incertezas.
3. `pele_antes_exclusoes`: anatomia inicial, reincluindo as exclusões.

Se o BiSeNet estiver indisponível ou não separar nenhum pixel de pele, a anatomia
inicial usa uma elipse central do recorte facial confirmado pelo detector.
`segmentacao_indisponivel` ou `pele_nao_segmentada`, junto de
`regiao_facial_aproximada`, explicam essa aproximação no aviso.
As alternativas 2 e 3 também acrescentam seus códigos aos motivos.
Não há limiar absoluto de cor que descarte tons de pele.

As máscaras `valid_mask`, `excluded_mask` e `uncertain_mask` são preservadas.
`measurement_mask` registra os pixels efetivamente medidos;
`measurement_source` e `preprocessamento.origem_medicao` identificam sua origem.
As estatísticas, a prévia RGBA e `tom.pele_utilizada` usam essa máscara.
As métricas da qualidade continuam referindo-se à seleção estrita original.

Acne, vitiligo e barba mantêm seus limiares de segmentação: acne usa 0,20/0,50;
vitiligo e barba usam confiança 0,25/0,60 e máscara 0,35/0,65. Nenhuma condição
ou falha de especialista bloqueia as recomendações. Também não existe limite
máximo de ΔE00 para rejeitar uma base. Os limites e alternativas permitem
estimar a cor observada, sem corrigir iluminação ou comprovar adequação cosmética.

## Estrutura

```text
backend/
  app.py                        Servidor HTTP e pré-verificação
  download_model.py             Downloads explícitos e verificação SHA-256
  export_models.py              Conversão offline PyTorch/ONNX com paridade
  evaluate_selection.py         Comparações offline com máscaras anotadas
  models/                       Peso ONNX local (ignorado pelo Git) e procedência
  data/bases.csv                Fonte oficial do catálogo do projeto
  src/catalog.py                Leitura e normalização do CSV
  src/mock_analysis.py          Respostas demonstrativas
  src/preprocessing/            Detectores e isolamento existentes
  src/segmentation/             Conversão, BiSeNet, estatísticas de cor e eventos
  src/skin_selection/           Especialistas, composição e qualidade
  src/tone_matching/             Monk + ranking CIEDE2000 em Lab
  src/distributed/               Etapa futura
  tests/test_api.py              Testes HTTP e integração com o detector
frontend/
  index.html                    Estrutura da página
  css/styles.css                Visual e responsividade
  js/app.js                     Estado, navegação e eventos
  js/api.js                     fetch, cancelamento, timeout e erros
  js/screens/                   Cinco telas e funções de apresentação
  assets/tonzinha.svg            Mascote original
  reference/                    Exportação original preservada
  tests/test_browser.py         Testes da interface
samples/                        Amostras originais
docs/API.md                    Contratos e ponto de integração futura
```

A cópia do CSV dentro de `frontend/reference/` é apenas parte do mock arquivado. **Atualize `backend/data/bases.csv`** para alterar o catálogo usado pela aplicação. Ele é relido a cada solicitação.

## CUDA (GPU) opcional

Os especialistas de pele (acne, vitiligo, barba) já são executados em paralelo.
Se `onnxruntime-gpu` estiver instalado, o `CUDAExecutionProvider` é selecionado
automaticamente — sem nenhuma alteração no código da aplicação.

O `onnxruntime-gpu` requer **Python 3.10–3.12** e **CUDA 12.x** instalado.
Use um ambiente virtual separado para não conflitar com o ambiente padrão:

```powershell
py -3.12 -m venv .venv-cuda
.venv-cuda\Scripts\python -m pip install -r backend/requirements-cuda.txt
.venv-cuda\Scripts\python -m backend.download_model
.venv-cuda\Scripts\python -m backend.app
```

Para confirmar que a GPU está sendo usada, observe os logs de inicialização:
`ONNX Runtime: CUDAExecutionProvider disponível — usando GPU.`

Sem `onnxruntime-gpu` (ambiente padrão com `onnxruntime`), o sistema cai
automaticamente para CPU sem nenhuma mensagem de erro — apenas o log informa.

Veja o guia completo de ativação: [docs/CUDA_SETUP.md](docs/CUDA_SETUP.md).

## MediaPipe opcional

A instalação padrão funciona com Haar/OpenCV, inclusive no Python 3.13. O import do segmentador anatômico é adiado para não impedir esse uso.

O código existente de MediaPipe usa a API legada `mp.solutions`. Para executar também o isolamento anatômico, use Python 3.10–3.12 e instale `backend/requirements-mediapipe.txt` **em outro ambiente virtual**, em lugar dos requisitos padrão:

```powershell
py -3.12 -m venv .venv-mediapipe
.venv-mediapipe\Scripts\python -m pip install -r backend/requirements-mediapipe.txt
.venv-mediapipe\Scripts\python -m backend.download_model
.venv-mediapipe\Scripts\python -m backend.app
.venv-mediapipe\Scripts\python backend/tests/test_preprocessing.py
```

Esse arquivo fixa MediaPipe 0.10.21 e usa `opencv-contrib-python`, evitando instalar duas distribuições que fornecem `cv2`. A opção requer a versão de Python indicada instalada. MediaPipe é opcional para a pré-verificação e os utilitários antigos; a segmentação web usa BiSeNet nos dois ambientes.

## Testar

API, catálogo, detector real, rejeição de imagens sem rosto ou com múltiplos rostos, limites, orientação EXIF e recuperação entre tentativas:

```powershell
.venv\Scripts\python -m unittest discover -s backend/tests -v
```

Interface automatizada (dependências opcionais para desenvolvimento):

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m unittest discover -s frontend/tests -p test_browser.py -v
```

Para usar o Edge já instalado, pode omitir a instalação do Chromium e definir `$env:BROWSER_CHANNEL='msedge'` antes do comando de testes. O teste abre um navegador isolado sem janela e inicia seu próprio servidor local em uma porta livre. As capturas ficam em `.test-artifacts/`, ignorado pelo Git.

São verificados envio real, rejeição sem rosto e nova tentativa, demonstração, alternância de marcações, erro de conexão, arquivo inválido, cancelamento e larguras de 390/320 pixels. Também são testados valores CIELAB de referência, comparação com OpenCV float, faces sintéticas claras/escuras, crescimento conectado, ordem dos eventos, interrupções do stream e área da máscara. O acionamento físico da câmera deve ser conferido em um celular real.

## Fotos e execução local

As fotos ficam em memória durante a solicitação; não são gravadas em disco ou em banco. A prévia usa uma URL temporária no navegador, liberada ao trocar a foto ou recomeçar. Cancelar interrompe a espera no navegador; uma detecção já iniciada no servidor pode terminar antes de liberar sua memória.

Para demonstrar em um celular na mesma rede, execute manualmente:

```powershell
.venv\Scripts\python -m flask --app backend.app:create_app run --host 0.0.0.0 --port 5000
```

Acesse `http://IP-DO-COMPUTADOR:5000` no celular. O Windows pode solicitar liberação de rede; use uma rede de confiança. A execução padrão fica restrita ao próprio computador. Esta é uma aplicação de demonstração com o servidor de desenvolvimento do Flask.

Detalhes dos contratos e da integração futura: [docs/API.md](docs/API.md). Documentação do processamento original: [docs/COMO_FUNCIONA.md](docs/COMO_FUNCIONA.md).

## Segmentação: método e limites

A implementação segue o fluxo das seções 4.1–4.2 do artigo do projeto. O K adaptativo é uma adaptação por variância cromática residual, não uma reprodução exata do método de Islam et al. (2024). Não há garantia de remover todos os pelos, óculos ou fundo com cor semelhante; fotos frontais, nítidas e sem maquiagem são recomendadas. A conversão CIELAB não corrige iluminação por si só.

Leia [backend/src/segmentation/README.md](backend/src/segmentation/README.md) para fórmulas, parâmetros, referências e limites. Não foram acrescentadas dependências de execução.

O backend do [plano de seleção](docs/PLANO_SELECAO_PELE.md) está implementado
com YOLOv8l-seg de prashants975 para barba/bigode. Veja o [contrato e os limites](backend/src/skin_selection/README.md) e a [instalação do especialista](docs/DETECCAO_BARBA.md).
Os limiares permanecem provisórios: faltam fotos anotadas, calibração e teste
separado por pessoa para concluir a validação e liberar a medição para Monk.
