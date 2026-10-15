# Frontend Meu tom

HTML + Bootstrap 5.3.8 + CSS do tema + JavaScript com módulos ES nativos. Não precisa de npm ou build.

Inicie `python -m backend.app` com as dependências instaladas e acesse http://127.0.0.1:5000. Veja os comandos completos no [README principal](../README.md).

- `index.html`: cabeçalho, navegação e ponto de montagem das telas.
- `js/app.js`: estado da sessão, seleção de foto, navegação e tratamento de eventos.
- `js/api.js`: único ponto de acesso à API; `fetch`, timeout de 45 segundos e cancelamento.
- `js/screens/`: início, captura, revisão, processamento e resultado.
- `css/styles.css`: visual derivado do mock, com layouts responsivos.
- `css/vendor/`: Bootstrap 5.3.8 e licença MIT, servidos localmente.
- `assets/tonzinha.svg`: mascote reaproveitado do original.
- `assets/fonts/`: fonte Archivo extraída do mock, com licença SIL OFL.
- `reference/`: mock original, preservado como referência; não é servido pela aplicação.
- `tests/test_browser.py`: testes de interface com Playwright.

Os resultados e produtos vêm da API; a escala na página inicial é uma referência visual estática. Bootstrap e a fonte Archivo são carregados do próprio servidor, inclusive sem internet. O Bootstrap é usado apenas pelo CSS: não há dependência de seu JavaScript.

O tema usa a paleta verde e o mascote do mock original, uma escala consistente de espaçamento, cartões e botões Bootstrap personalizados, ícones SVG locais, estados de foco visíveis e adaptação para movimento reduzido. O CSS de terceiros deve vir antes de `styles.css`. Os templates ficam em `js/screens/`; os estilos específicos de cada tela estão agrupados e comentados no tema.

Não há persistência no navegador. Recarregar a página reinicia o fluxo. O botão de câmera usa a captura nativa quando suportada e o seletor de arquivos nos demais casos.
