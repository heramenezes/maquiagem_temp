# Frontend Meu tom

HTML + CSS + JavaScript com módulos ES nativos. Não precisa de npm ou build.

Inicie `python -m backend.app` com as dependências instaladas e acesse http://127.0.0.1:5000. Veja os comandos completos no [README principal](../README.md).

- `index.html`: cabeçalho, navegação e ponto de montagem das telas.
- `js/app.js`: estado da sessão, seleção de foto, navegação e tratamento de eventos.
- `js/api.js`: único ponto de acesso à API; `fetch`, timeout de 45 segundos e cancelamento.
- `js/screens/`: início, captura, revisão, processamento e resultado.
- `css/styles.css`: visual derivado do mock, com layouts responsivos.
- `assets/tonzinha.svg`: mascote reaproveitado do original.
- `reference/`: mock original, preservado como referência; não é servido pela aplicação.
- `tests/test_browser.py`: testes de interface com Playwright.

Os resultados e produtos vêm da API; a escala na página inicial é uma referência visual estática. A fonte Archivo é carregada do Google Fonts, com fallback para fontes do sistema se estiver offline.

Não há persistência no navegador. Recarregar a página reinicia o fluxo. O botão de câmera usa a captura nativa quando suportada e o seletor de arquivos nos demais casos.
