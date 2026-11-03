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
acima inclui somente BiSeNet; sem os especialistas a API informa análise
inconclusiva e não emite medição. A conversão dos pesos ocorre em ambiente separado.

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
- K-means descreve a anatomia sem remover pixels. A medição recebe somente a máscara válida aprovada pelos critérios técnicos de qualidade.
- Progresso real em dez etapas, recorte RGB preservado, prévias e estatísticas; análise inconclusiva mantém máscaras/razões e retorna médias nulas.
- Catálogo real com 281 cores, carregado de `backend/data/bases.csv`.
- Exemplo acessível sem enviar foto, erros de conexão, nova tentativa e cancelamento de solicitações na interface.

A pré-verificação conta as detecções válidas antes do recorte: zero rostos pede outra foto, um rosto passa e mais de um aborta. Não há conferência por um segundo detector nem reagrupamento das caixas retornadas pelo detector. O Haar considera caixas a partir de 40 × 40 pixels na imagem redimensionada. A detecção ainda pode falhar em rostos muito pequenos, de perfil ou parcialmente cobertos e pode produzir falsos positivos. Ela não certifica iluminação, nitidez ou ausência de maquiagem.

## Match de tom e recomendações

Uploads usam a mediana Lab da pele válida aprovada para classificar o tom
Monk e recomendar bases. O ranking prioriza o mesmo Monk e refina por
CIEDE2000 pele/base; se necessário, completa com outros grupos pela distância
entre referências Monk. Seleção inconclusiva retorna `tom: null` e nenhuma base.
ITA fica `null`; não participa dessa estratégia. O resultado é experimental,
sem correção de iluminação ou validação de bases aplicadas na pele.

A interface mostra o tom estimado, a cor medida da foto, a referência Monk e
as bases na ordem enviada pelo backend, com preços, links e diferenças de cor.
Análises inconclusivas mostram os motivos e permitem uma nova captura sem
exibir tom ou produtos fictícios. Catálogo sem candidatos mantém o tom medido.
`/api/exemplo` continua usando fixtures de `backend/src/mock_analysis.py`,
identificadas como demonstrativas. Não há percentual de compatibilidade inventado.
Veja o [algoritmo e contrato](backend/src/tone_matching/README.md).

## Quando o tom e as recomendações são bloqueados

O site mostra um aviso **“Por que não foi possível identificar o tom?”**,
com todos os motivos retornados, orientação para cada motivo e identificação
dos especialistas que falharam. Em **“Ver medidas e limites desta análise”**,
é possível comparar as medidas da foto aos limiares enviados pelo servidor.
Falha de modelo/serviço é distinguida de qualidade da foto: trocar a foto não
resolve um modelo indisponível. O botão “Tentar novamente” permite reenviar a
foto nesses casos. O modo de exemplo não executa essas verificações.

### 1. Interrupções antes da medição

- Arquivo ausente, ilegível ou fora de JPG/PNG/WebP; perfil ICC inválido;
  arquivo maior que **10 MiB = 10.485.760 bytes** ou imagem maior que
  **24.000.000 pixels**. O envelope HTTP tem limite de **11 MiB**. No navegador,
  um MIME declarado incompatível também é recusado. HEIC exige conversão.
- **Nenhum rosto ou mais de um rosto detectado:** HTTP 422, antes de converter
  as cores. Não há decisão por percentual de “confiança do tom”.
- Recorte facial com menor dimensão **< 16 pixels** ou anatomia de pele/nariz
  com **< 64 pixels**: `PELE_INSUFICIENTE`/422, antes da seleção final.
- BiSeNet ausente/inválido ou sem runtime: `MODELO_INDISPONIVEL`/503. Outras
  falhas inesperadas retornam erro de processamento. Não são rejeições da cor
  da pessoa. O site exibe o erro, sem fabricar tom ou recomendação.
- Falha de conexão, resposta incompleta ou espera superior a **90.000 ms** no
  navegador: aviso de comunicação e possibilidade de tentar novamente. O timeout
  inclui as pausas de apresentação das etapas; não é critério de qualidade.

A imagem aceita é reduzida proporcionalmente para no máximo 1600 × 1600 pixels
antes do recorte. Os testes de área abaixo usam essa resolução de processamento,
sem aumentar artificialmente a imagem.

### 2. Limiares exatos da qualidade da pele selecionada

Fonte: [`QualityConfig` e `evaluate`](backend/src/skin_selection/quality.py).
**Qualquer uma das condições abaixo reprova a medição.** Os comparadores são
estritos: atingir exatamente um mínimo/máximo é permitido.

| Motivo na API | Bloqueia quando | Como a medida é calculada |
|---|---|---|
| `modulo_obrigatorio_indisponivel` | Qualquer especialista de acne, vitiligo ou barba tem estado diferente de `executado` | Inclui `indisponivel`, `falha` e `nao_executado`. Executar com máscara vazia é permitido. |
| `poucos_pixels_nativos` | Pixels válidos **< 512** | Contagem após exclusões e retirada das áreas incertas. |
| `cobertura_insuficiente` | Fração válida **< 0,15 (15%)** | Pixels válidos / pixels da anatomia inicial de pele/nariz. |
| `amostra_concentrada` | Extensão espacial **< 0,20 (20%)** | Menor razão entre a extensão vertical e horizontal da máscara válida e a extensão correspondente da anatomia inicial; extensão = coordenada máxima − mínima, denominador no mínimo 1. |
| `clipping_excessivo` | Fração com clipping **> 0,08 (8%)** | Entre os pixels válidos, fração com qualquer canal RGB **≤ 2 ou ≥ 253**, na escala 0–255. |
| `nitidez_insuficiente` | Nitidez **< 8,0** | Variância do Laplaciano OpenCV `CV_32F` da imagem em cinza, apenas no interior da máscara válida após erosão 3 × 3. Se não houver interior, nitidez = 0. Não é porcentagem. |
| `iluminacao_desigual` | Amplitude de L* **> 35,0** | Percentil 95 de L* − percentil 5 de L* nos pixels válidos. |
| `cor_inconsistente` | Dispersão **> 22,0 ΔE76** | Percentil 90 da distância euclidiana Lab de cada pixel válido à mediana Lab por canal. |
| `cor_sensivel_a_incerteza` | Mudança **> 3,0 ΔE76** | Distância entre a média Lab dos pixels válidos e a média da anatomia sem exclusões aceitas, reincluindo os pixels incertos. |
| `incerteza_excessiva` | Fração incerta **> 0,35 (35%)** | Pixels incertos que não estão na exclusão aceita / pixels da anatomia inicial. |

Para as frações, o denominador é protegido por `max(total, 1)`. As métricas
espaciais, de clipping, nitidez e cor só são calculadas quando há algum pixel
válido; indisponível não significa zero. A comparação usa valores sem
arredondamento; a interface arredonda apenas a apresentação.

O percentual **“da face usada na medição”** no cartão do tom usa a máscara facial
como denominador; ele não é o mesmo denominador de pele/nariz usado nos limites
de 15% e 35%.

**Acne, vitiligo ou barba detectados não bloqueiam automaticamente o resultado.**
Eles retiram regiões da medição. O bloqueio ocorre se um especialista não
concluir ou se a pele restante reprovar algum critério acima. Limiares dos
especialistas que influenciam essa seleção:

- Acne: probabilidade **≥ 0,50** é exclusão aceita; **[0,20; 0,50)** é incerta;
  abaixo de 0,20 não gera exclusão.
- Vitiligo e barba: confiança de instância **≥ 0,60** pode produzir exclusão
  aceita; **[0,25; 0,60)** permanece incerta. As probabilidades da máscara usam
  **0,65** para aceitação e **0,35** como limite inferior de incerteza. Em
  instância aceita, máscara **≥ 0,65** é aceita e **[0,35; 0,65)** é incerta;
  em instância intermediária, pixels de máscara **≥ 0,35** são apenas incertos.
  Máscaras são restauradas ao recorte antes dos limiares; barba considera apenas
  a classe `beard`, ignorando `hair`.

Esses limites são **provisórios, sem calibração em um conjunto humano anotado**.
Uma seleção aprovada permite o cálculo experimental, não comprova acurácia.
O frontend usa `quality.thresholds` da resposta, em vez de fixar cópias dos
números no JavaScript. Alterações devem ser feitas no backend e documentadas aqui.

### 3. Diferença entre ausência de tom e ausência de bases

- Seleção reprovada: `status_analise: inconclusiva`, `match.status: inconclusivo`,
  `tom: null`, `recomendacoes: []`. O site mostra motivos, medidas disponíveis e
  orientações; as máscaras continuam visíveis.
- Seleção aprovada, mas sem medição entregue ao match: `medicao_ausente`, sem
  tom/produtos. É uma indisponibilidade do processamento.
- Catálogo vazio: o tom é mantido, `match.status: sem_candidatos` e nenhuma base.
  O site explica que é ausência de catálogo, não defeito da foto.
- Catálogo inválido ou erro inesperado: erro explícito, sem fallback para bases
  de exemplo. A foto é preservada no navegador para nova tentativa quando possível.

**Não existe atualmente limiar máximo de ΔE00 para rejeitar uma recomendação.**
Uma medição aprovada com catálogo não vazio produz até três opções, ainda que
as cores disponíveis estejam distantes. A ausência de bases no mesmo Monk não
bloqueia o ranking: ele usa grupos complementares. Margem entre categorias Monk
também não bloqueia a classificação. Distância de cor não é probabilidade de
acerto nem garantia de adequação da base aplicada.

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
