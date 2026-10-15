# Frontend Meu tom

HTML + Bootstrap 5.3.8 + CSS do tema + JavaScript com módulos ES nativos. Não precisa de npm ou build.

Inicie `python -m backend.app` com as dependências instaladas e acesse http://127.0.0.1:5000. Veja os comandos completos no [README principal](../README.md).

- `index.html`: cabeçalho, navegação e ponto de montagem das telas.
- `js/app.js`: estado da sessão, seleção de foto, navegação e tratamento de eventos.
- `js/api.js`: único ponto de acesso à API; `fetch`, leitura incremental de NDJSON, timeout de 90 segundos (inclui as pausas de apresentação) e cancelamento. Respostas de upload sem segmentação ou sem as máscaras da seleção geram uma mensagem para reiniciar o backend atualizado, preservando a foto para tentar novamente.
- `js/screens/`: início, captura, revisão, processamento e resultado.
- `js/screens/preprocessing.js`: preserva as três imagens básicas — recorte, máscara anatômica e pele inicial — antes das exclusões.
- `js/screens/selection.js`: cartões de acne, vitiligo e barba/bigode, com pixels, percentuais, regiões, tempo e disponibilidade. A imagem final mostra somente a prévia RGBA de pele útil do backend, sobre fundo quadriculado, com a qualidade e as métricas da seleção consolidada. Medições nulas são apresentadas como não calculadas.
- `js/screens/mask_previews.js`: monta as sobreposições com Canvas no referencial do recorte, sem redimensionar as máscaras. Cada categoria tem uma cor; amarelo indica incerteza. Máscaras incertas são limitadas à anatomia. Os pixels usados na medição continuam sendo os originais do backend.
- Fotos analisadas não recebem marcações fictícias. O fluxo de exemplo preserva as marcações demonstrativas e seu botão de visibilidade.
- `css/styles.css`: visual derivado do mock, com layouts responsivos.
- `css/vendor/`: Bootstrap 5.3.8 e licença MIT, servidos localmente.
- `assets/tonzinha.svg`: mascote reaproveitado do original.
- `assets/fonts/`: fonte Archivo extraída do mock, com licença SIL OFL.
- `reference/`: mock original, preservado como referência; não é servido pela aplicação.
- `tests/test_browser.py`: testes de interface com Playwright.

Os resultados e produtos vêm da API; a escala na página inicial é uma referência visual estática. Bootstrap e a fonte Archivo são carregados do próprio servidor, inclusive sem internet. O Bootstrap é usado apenas pelo CSS: não há dependência de seu JavaScript.

O tema usa a paleta verde e o mascote do mock original, uma escala consistente de espaçamento, cartões e botões Bootstrap personalizados, ícones SVG locais, estados de foco visíveis e adaptação para movimento reduzido. O CSS de terceiros deve vir antes de `styles.css`. Os templates ficam em `js/screens/`; os estilos específicos de cada tela estão agrupados e comentados no tema.

Não há persistência no navegador. Recarregar a página reinicia o fluxo. O botão de câmera usa a captura nativa quando suportada e o seletor de arquivos nos demais casos.

O upload usa `Accept: application/x-ndjson` para receber início e conclusão de dez etapas: rosto, cores, anatomia, acne, vitiligo, barba, união das máscaras/qualidade, grupos de cor, medição e resultado. A barra representa a fração de etapas concluídas (não tempo restante). Modelos indisponíveis, falhas e medição não executada têm indicadores próprios. Cada evento em processamento fica visível por 350 ms, com mais 75 ms ao concluir: aproximadamente 4,25 segundos de apresentação no fluxo completo. O backend continua processando normalmente. Os tempos podem ser ajustados em `PROCESSING_STAGE_DELAY_MS` e `COMPLETED_STAGE_DELAY_MS`, em `js/app.js`. Cancelar invalida os eventos pendentes.

Os testes cobrem o envio real, desktop e celular (390/320 px), disponibilidade dos módulos, seleção inconclusiva, falhas nas prévias e compatibilidade do contrato. Uma imagem sintética não quadrada permite conferir pixel a pixel o alinhamento, as sobreposições, os vazios nas máscaras, o limite anatômico da incerteza e o canal alfa da seleção final. Veja o comando de execução no [README principal](../README.md).

O servidor iniciado com `python -m backend.app` recarrega o código Python automaticamente ao editar arquivos. HTML, JS e CSS usam `Cache-Control: no-store` para evitar versões antigas durante o desenvolvimento. Após mudar a configuração de inicialização, reinicie o processo existente uma vez.
