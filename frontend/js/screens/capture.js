import { notice } from './shared.js';

export function capture(state) {
  return `<section class="container section"><div class="intro stack tight"><span class="eyebrow">01 · Sua foto</span><h1>Vamos começar pela sua foto.</h1><p>Escolha uma imagem da galeria ou use a câmera do seu celular.</p></div>
    <div class="grid-two"><div class="stack">${notice(state.error)}
      <div class="drop-zone" id="drop-zone"><span class="upload-icon" aria-hidden="true">↑</span><h2>Uma foto, seu primeiro passo.</h2><p>Arraste sua foto para cá ou escolha uma opção abaixo.</p>
        <div class="actions"><button class="btn" data-action="choose">Escolher foto</button><button class="btn secondary" data-action="camera">Tirar foto</button></div>
        <p class="small muted">JPG, PNG ou WebP · até 10 MB e 24 megapixels</p>
        <p class="small muted">No celular, “Tirar foto” pode abrir a câmera. No computador, abre a seleção de arquivos.</p>
      </div>
      <input type="file" id="gallery-input" accept="image/jpeg,image/png,image/webp" hidden aria-label="Selecionar foto da galeria">
      <input type="file" id="camera-input" accept="image/*" capture="user" hidden aria-label="Tirar uma selfie">
      <p id="file-status" class="small muted" role="status"></p>
      <p class="small muted">Sua foto será enviada apenas quando você confirmar a análise. Ela não fica salva no servidor.</p>
    </div><aside class="tips stack"><h3>Uma boa foto faz a diferença</h3><ul class="tip-list">
      <li><span><b>Luz natural de frente.</b> Perto de uma janela é o ideal. Evite sombras no rosto.</span></li>
      <li><span><b>Rosto sem maquiagem.</b> Base ou pó mudam a cor da pele na imagem.</span></li>
      <li><span><b>Sem óculos e com o cabelo preso.</b> Deixe o rosto visível.</span></li>
      <li><span><b>Olhe direto para a câmera.</b> Centralize o rosto, na altura dos olhos.</span></li>
      <li><span><b>Sem filtros.</b> Envie a foto original, sem edição.</span></li>
    </ul></aside></div></section>`;
}
