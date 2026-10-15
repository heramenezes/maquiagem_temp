import { escapeHTML, notice } from './shared.js';

export function review(state) {
  return `<section class="container section grid-two"><div class="photo-frame"><img src="${escapeHTML(state.photoURL)}" alt="Prévia da foto selecionada"></div>
    <div class="stack"><span class="eyebrow">01 · Revise sua foto</span><h1>Vamos analisar esta foto?</h1><p>Confira se o rosto aparece inteiro, de frente e com boa luz.</p>${notice(state.error)}
      <ul class="check-list"><li>A presença de um rosto será verificada ao enviar.</li><li>Iluminação e nitidez ainda não são avaliadas automaticamente.</li><li>Os demais resultados são uma demonstração.</li></ul>
      <div class="actions"><button class="btn" data-action="analyze">Enviar para análise <span aria-hidden="true">→</span></button><button class="btn secondary" data-action="capture">Trocar foto</button></div>
      <p class="small muted">${escapeHTML(state.file?.name)} · Sua foto não fica salva no servidor.</p>
    </div></section>`;
}
