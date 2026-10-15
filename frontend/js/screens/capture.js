import { notice, icon } from './shared.js';

export function capture(state) {
  return `<section class="container section"><div class="intro stack tight"><span class="eyebrow">01 · Sua foto</span><h1>Vamos começar pela sua foto.</h1><p>Escolha uma imagem da galeria ou use a câmera do seu celular.</p></div>
    <div class="row g-4 g-lg-5"><div class="col-lg-7 stack">${notice(state.error)}
      <div class="card upload-card"><div class="drop-zone" id="drop-zone"><span class="upload-icon">${icon('upload')}</span><h2>Uma foto, seu primeiro passo.</h2><p>Arraste sua foto para cá<br>ou escolha uma opção abaixo.</p>
        <div class="actions"><button class="btn btn-primary" data-action="choose">${icon('upload')} Escolher foto</button><button class="btn btn-outline-primary" data-action="camera">${icon('camera')} Tirar foto</button></div>
        <p class="small muted">JPG, PNG ou WebP · até 10 MB e 24 megapixels</p>
      </div><div class="upload-card-footer">${icon('shield')} Você revisa a foto antes de enviar.</div></div>
      <input type="file" id="gallery-input" accept="image/jpeg,image/png,image/webp" hidden aria-label="Selecionar foto da galeria">
      <input type="file" id="camera-input" accept="image/*" capture="user" hidden aria-label="Tirar uma selfie">
      <p id="file-status" class="small muted" role="status"></p>
      <p class="small muted capture-help">No celular, “Tirar foto” pode abrir a câmera. No computador, abre o seletor de arquivos. Sua foto não fica salva no servidor.</p>
    </div><div class="col-lg-5"><aside class="tips stack"><div class="tips-heading">${icon('sun')}<span class="eyebrow">Vale a dica</span></div><h3>Uma boa foto faz<br>toda a diferença.</h3><ul class="tip-list">
      <li><span><b>Luz natural de frente.</b> Perto de uma janela é o ideal. Evite sombras no rosto.</span></li>
      <li><span><b>Rosto sem maquiagem.</b> Base ou pó mudam a cor da pele na imagem.</span></li>
      <li><span><b>Sem óculos e com o cabelo preso.</b> Deixe o rosto visível.</span></li>
      <li><span><b>Olhe direto para a câmera.</b> Centralize o rosto, na altura dos olhos.</span></li>
      <li><span><b>Sem filtros.</b> Envie a foto original, sem edição.</span></li>
    </ul></aside></div></div></section>`;
}
