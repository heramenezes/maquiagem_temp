import { escapeHTML, notice, icon } from './shared.js';

export function review(state) {
  return `<section class="container section review-section"><div class="row g-4 g-lg-5 align-items-center review-layout"><div class="col-lg-5"><div class="photo-frame review-photo"><img src="${escapeHTML(state.photoURL)}" alt="Prévia da foto selecionada"><span class="photo-label tag">${icon('eye')} Prévia da sua foto</span></div><p class="photo-filename">${escapeHTML(state.file?.name)}</p></div>
    <div class="col-lg-7"><div class="stack review-copy"><span class="eyebrow">01 · Revise sua foto</span><h1>Vamos analisar esta foto?</h1><p class="lead-copy">Confira se o rosto aparece inteiro, de frente e com boa luz. Se estiver tudo certo, é só continuar.</p>${notice(state.error)}
      <div class="card review-checks"><ul class="check-list"><li>${icon('face')}<span>A foto deve conter somente um rosto visível. Fotos com mais de uma pessoa serão recusadas.</span></li><li>${icon('sun')}<span>Boa luz e nitidez fazem diferença. Confira esses detalhes na prévia.</span></li><li>${icon('sparkle')}<span>Vamos separar a pele, estimar seu tom Monk e comparar com as cores das bases do catálogo.</span></li></ul></div>
      <div class="actions"><button class="btn btn-primary" data-action="analyze">Enviar para análise ${icon('arrow')}</button><button class="btn btn-outline-primary" data-action="capture">Trocar foto</button></div>
      <p class="privacy-note">${icon('shield')} Sua foto não fica salva no servidor.</p>
    </div></div></div></section>`;
}
