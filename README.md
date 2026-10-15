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

## O que funciona

- Escolher uma foto, arrastar e soltar, revisar, trocar e reenviar.
- Botão de câmera nativa (`capture="user"`): no celular, depende do navegador; no computador, abre o seletor de arquivos. Não há webcam ao vivo.
- Upload de JPG, PNG ou WebP, com até 10 MiB e 24 megapixels. HEIC precisa ser convertido para JPG.
- Correção de orientação EXIF e redimensionamento proporcional até 1600 pixels antes da detecção.
- Pré-verificação de um único rosto: MediaPipe quando disponível; Haar/OpenCV como fallback quando o MediaPipe não retorna uma detecção. Um rosto é aceito sem uma segunda conferência; múltiplos rostos abortam imediatamente.
- Sem rosto ou com múltiplos rostos detectados, a API retorna 422 e a interface pede outra foto. Conversão CIELAB, segmentação e resultado não são executados. No stream, o evento de erro informa o status 422.
- Conversão real sRGB → RGB linear → XYZ → CIELAB (D65), normalizando perfis ICC para sRGB quando presentes.
- Segmentação semântica com BiSeNet ResNet18 pré-treinado, executada localmente em CPU via ONNX Runtime. Pele e nariz são selecionados pixel a pixel, sem exclusões geométricas grandes. O modelo não tem classe específica de barba.
- K-means descreve as cores selecionadas, sem remover pixels. A média CIELAB usa toda a máscara semântica.
- Progresso real em seis etapas, prévias do recorte, máscara e pele selecionada, com média CIELAB e área calculadas da imagem.
- Catálogo real com 281 cores, carregado de `backend/data/bases.csv`.
- Exemplo acessível sem enviar foto, erros de conexão, nova tentativa e cancelamento de solicitações na interface.

A pré-verificação conta as detecções válidas antes do recorte: zero rostos pede outra foto, um rosto passa e mais de um aborta. Não há conferência por um segundo detector nem reagrupamento das caixas retornadas pelo detector. O Haar considera caixas a partir de 40 × 40 pixels na imagem redimensionada. A detecção ainda pode falhar em rostos muito pequenos, de perfil ou parcialmente cobertos e pode produzir falsos positivos. Ela não certifica iluminação, nitidez ou ausência de maquiagem.

## O que continua simulado

Tom Monk, ITA, porcentagem exibida no cartão de tom demonstrativo, acne, rosácea, vitiligo e marcações de condições são fixtures de `backend/src/mock_analysis.py`, independentes da foto. A seção separada de pré-processamento mostra a máscara, a média CIELAB e a porcentagem reais de pele nas regiões faciais identificadas pelo modelo.

As três recomendações usam proximidade RGB a um **tom fixo de exemplo**, sem implementar o pipeline futuro de ITA/KNN. Os nomes, cores, preços e links são lidos do CSV real. O CSV não contém fotos ou acabamento; os cartões mostram uma amostra de cor e não inventam esses dados. Não há percentual fictício de compatibilidade.

## Estrutura

```text
backend/
  app.py                        Servidor HTTP e pré-verificação
  download_model.py             Download explícito e verificação SHA-256 do BiSeNet
  models/                       Peso ONNX local (ignorado pelo Git) e procedência
  data/bases.csv                Fonte oficial do catálogo do projeto
  src/catalog.py                Leitura e normalização do CSV
  src/mock_analysis.py          Respostas demonstrativas
  src/preprocessing/            Detectores e isolamento existentes
  src/segmentation/             Conversão, BiSeNet, estatísticas de cor e eventos
  src/tone_matching/             Etapa futura
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
.venv\Scripts\python -m unittest backend.tests.test_semantic backend.tests.test_face_detector backend.tests.test_api backend.tests.test_segmentation -v
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
