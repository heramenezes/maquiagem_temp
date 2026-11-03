import { icon } from './shared.js';

export function how() {
  return `<article class="container section how-page stack">
    <header class="how-intro stack">
      <h1>Como funciona?</h1>
    </header>

    <section class="how-guide stack" aria-labelledby="how-guide-title">
      <h2 id="how-guide-title">O que você precisa fazer</h2>
      <ol class="how-steps">
        <li class="card"><span class="how-step-index" aria-hidden="true">01</span><h3>Escolha uma foto</h3><p>Envie uma imagem da galeria ou use a câmera do celular. Prefira luz natural de frente, sem filtros, sem maquiagem e com apenas você na foto.</p><span class="how-step-note">JPG, PNG ou WebP · até 10 MB e 24 megapixels</span></li>
        <li class="card"><span class="how-step-index" aria-hidden="true">02</span><h3>Confira e envie</h3><p>Veja a prévia e confira se o rosto está inteiro, nítido e descoberto. Você pode trocar a foto antes de clicar em “Enviar para análise”.</p><span class="how-step-note">No computador, “Tirar foto” abre o seletor de arquivos.</span></li>
        <li class="card"><span class="how-step-index" aria-hidden="true">03</span><h3>Explore seu resultado</h3><p>Acompanhe o processamento e veja a cor estimada, as regiões de pele analisadas e até três bases, com cor, preço do catálogo e link para a loja.</p><span class="how-step-note">Se nenhum rosto ou vários rostos forem detectados, pedimos outra foto.</span></li>
      </ol>
      <p class="how-privacy">${icon('shield')}<span>Sem cadastro. Sua foto é processada no servidor da aplicação, em memória, e não é salva em disco nem enviada às marcas.</span></p>
    </section>

    <aside class="how-limit card stack" aria-labelledby="how-limit-title">
      <div class="how-limit-heading">${icon('info')}<h2 id="how-limit-title">Sobre as cores das bases</h2></div>
      <p>Usamos os <strong>códigos HEX que os fabricantes colocam nos sites para representar cada tom de base</strong>. Por isso, nossa recomendação só pode ser tão boa quanto a técnica do fabricante de representar o tom real em uma cor HEX na tela.</p>
      <p>Se a cor que o fabricante apresenta digitalmente não for fiel à base real, <strong>não temos como corrigir essa diferença com os dados que ele fornece</strong>.</p>
    </aside>

    <section class="how-engine stack" aria-labelledby="how-engine-title">
      <h2 id="how-engine-title">O que acontece por trás</h2>
      <div class="how-technical">
        <details><summary><span>01 · Preparar a foto e encontrar o rosto</span><span class="how-tech-label">Pillow · MediaPipe · OpenCV</span></summary><div class="how-detail"><p>O servidor corrige a orientação da foto, converte o perfil de cor para sRGB quando ele está presente e limita o maior lado a 1600 pixels. O detector procura um único rosto e recorta essa região. Usa MediaPipe quando disponível e Haar Cascades do OpenCV como alternativa. A imagem colorida é preservada para medir a pele.</p></div></details>
        <details><summary><span>02 · Selecionar pele e separar outras regiões</span><span class="how-tech-label">BiSeNet · U-Net · YOLO</span></summary><div class="how-detail"><p>O BiSeNet ResNet18 identifica pele e nariz pixel a pixel. Modelos separados apontam áreas de acne (U-Net/ResNet34), vitiligo (YOLO11n) e barba/bigode (YOLOv8l-seg). Unimos essas exclusões e retiramos também as regiões incertas da seleção estrita. As sobreposições coloridas servem para você conferir o resultado; elas não entram no cálculo da cor.</p><p>Esses modelos são pré-treinados e executados pelo ONNX Runtime no servidor. As máscaras são estimativas para selecionar pixels, sem finalidade de diagnóstico.</p></div></details>
        <details><summary><span>03 · Medir a cor da testa e das bochechas</span><span class="how-tech-label">CIELAB · Medianas · Pesos regionais</span></summary><div class="how-detail"><p>Convertendo sRGB → RGB linear → XYZ → CIELAB, separamos luminosidade (L*) e componentes de cor (a* e b*), com branco de referência D65. Medimos regiões aproximadas da testa e das duas bochechas, dentro da máscara disponível.</p><p>Em cada região, descartamos pixels com canais muito próximos dos extremos e aparamos os extremos de luminosidade. Calculamos a mediana Lab e combinamos as regiões com pesos de cobertura, estabilidade de cor e concordância entre elas. Se faltarem regiões utilizáveis ou consenso suficiente, usamos a mediana global da pele disponível e mostramos uma ressalva. Isso não corrige automaticamente a iluminação ou o balanço de branco.</p><p>O K-means apenas descreve os grupos de cor da pele inicial; ele não escolhe o tom usado nas recomendações.</p></div></details>
        <details><summary><span>04 · Comparar com as bases do catálogo</span><span class="how-tech-label">HEX · CIEDE2000 · ΔE00</span></summary><div class="how-detail"><p>Cada HEX do catálogo é convertido para o mesmo espaço Lab da foto. A fórmula CIEDE2000 calcula a diferença de cor, chamada ΔE00, entre a estimativa da pele e cada base. Ordenamos todo o catálogo da menor para a maior diferença e mostramos até três opções. Em caso de empate, o identificador do produto define a ordem.</p><p>Um ΔE00 menor significa maior proximidade entre as cores digitais comparadas. Não é uma porcentagem de compatibilidade e não garante que a base aplicada terá a mesma aparência. A comparação é direta, sem classificar a pessoa em categorias de tom.</p></div></details>
        <details><summary><span>05 · Entender os avisos e os limites</span><span class="how-tech-label">Qualidade · Alternativas de medição</span></summary><div class="how-detail"><p>Conferimos quantidade e distribuição de pixels, nitidez, iluminação, extremos dos canais de cor e diferenças entre regiões. Os limites são provisórios: os avisos indicam fatores que podem reduzir a precisão, mas não interrompem as recomendações.</p><p>Se a seleção estrita ficar vazia, o sistema pode reincluir áreas incertas ou usar a pele anterior às exclusões. Se a segmentação principal falhar, pode medir uma região central aproximada do rosto detectado. Essas alternativas e as falhas dos especialistas geram avisos no resultado. A aplicação é experimental, sem validação cosmética de acerto em bases aplicadas.</p></div></details>
        <details><summary><span>06 · Acompanhar a análise e ver os produtos</span><span class="how-tech-label">Python · Flask · JavaScript</span></summary><div class="how-detail"><p>O backend em Python/Flask executa dez etapas em sequência e envia atualizações de progresso à interface. NumPy, OpenCV, Pillow e scikit-image apoiam o tratamento das imagens e os cálculos. O front usa HTML, Bootstrap, CSS e JavaScript.</p><p>Nome, cor, HEX, preço e link vêm do catálogo CSV do projeto. Os preços não são consultados em tempo real. As fotos dos cards mostram a linha ou embalagem do produto; o nome da cor e sua amostra identificam a opção recomendada.</p></div></details>
      </div>
    </section>
  </article>`;
}
