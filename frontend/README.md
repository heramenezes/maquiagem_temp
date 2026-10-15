# Frontend Meu tom

HTML + Bootstrap 5.3.8 + CSS do tema + JavaScript com módulos ES nativos. Não precisa de npm ou build.

Inicie `python -m backend.app` com as dependências instaladas e acesse http://127.0.0.1:5000. Veja os comandos completos no [README principal](../README.md).

- `index.html`: cabeçalho, navegação e ponto de montagem das telas.
- `js/app.js`: estado da sessão, seleção de foto, navegação e tratamento de eventos.
- `js/api.js`: único ponto de acesso à API; `fetch`, leitura incremental de NDJSON, timeout de 90 segundos (inclui as pausas de apresentação) e cancelamento. Respostas de upload sem segmentação geram uma mensagem para reiniciar o backend atualizado, preservando a foto para tentar novamente.
- `js/screens/`: início, captura, revisão, processamento e resultado.
- Na foto final, o recorte analisado e a prévia RGBA de pele são sobrepostos com o mesmo tamanho: pele selecionada em cor e regiões excluídas escurecidas. Os botões de segmentação e marcações fictícias são independentes. Exemplos sem segmentação real mantêm apenas as marcações.
- `css/styles.css`: visual derivado do mock, com layouts responsivos.
- `css/vendor/`: Bootstrap 5.3.8 e licença MIT, servidos localmente.
- `assets/tonzinha.svg`: mascote reaproveitado do original.
- `assets/fonts/`: fonte Archivo extraída do mock, com licença SIL OFL.
- `reference/`: mock original, preservado como referência; não é servido pela aplicação.
- `tests/test_browser.py`: testes de interface com Playwright.

Os resultados e produtos vêm da API; a escala na página inicial é uma referência visual estática. Bootstrap e a fonte Archivo são carregados do próprio servidor, inclusive sem internet. O Bootstrap é usado apenas pelo CSS: não há dependência de seu JavaScript.

O tema usa a paleta verde e o mascote do mock original, uma escala consistente de espaçamento, cartões e botões Bootstrap personalizados, ícones SVG locais, estados de foco visíveis e adaptação para movimento reduzido. O CSS de terceiros deve vir antes de `styles.css`. Os templates ficam em `js/screens/`; os estilos específicos de cada tela estão agrupados e comentados no tema.

Não há persistência no navegador. Recarregar a página reinicia o fluxo. O botão de câmera usa a captura nativa quando suportada e o seletor de arquivos nos demais casos.

O upload usa `Accept: application/x-ndjson` para receber início e conclusão de cada etapa real. A barra representa a fração de etapas concluídas (não tempo restante). Para facilitar a demonstração, cada etapa em processamento permanece visível por pelo menos 4 segundos, com mais 500 ms ao concluir: cerca de 27 segundos de pausas no fluxo completo. O atraso é artificial e afeta apenas a apresentação no frontend; o backend continua processando normalmente. Os tempos podem ser ajustados nas constantes `PROCESSING_STAGE_DELAY_MS` e `COMPLETED_STAGE_DELAY_MS` de `js/app.js`. Cancelar invalida os eventos pendentes. `screens/preprocessing.js` exibe máscaras e medições reais, separadas dos resultados ainda demonstrativos.

O servidor iniciado com `python -m backend.app` recarrega o código Python automaticamente ao editar arquivos. HTML, JS e CSS usam `Cache-Control: no-store` para evitar versões antigas durante o desenvolvimento. Após mudar a configuração de inicialização, reinicie o processo existente uma vez.
