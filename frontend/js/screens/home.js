import { mascot, notice, icon } from './shared.js';

// Cores decorativas, sem classes ou numeração de tons de pele.
const COLORS = ['#F4D3C2', '#EFC0A3', '#D49C75', '#A86F50', '#694431'];

export function home(state) {
  return `${state.error ? `<div class="container section">${notice(state.error)}</div>` : ''}
    <section class="container hero-section">
      <div class="row g-0 hero">
        <div class="col-lg-7 hero-copy stack">
          <div class="tags"><span class="tag">${icon('sparkle')} Beleza em cada tom</span><span class="hero-meta">Sem cadastro, do seu jeito.</span></div>
          <h1>Encontre a base certa para o <span>seu tom de pele.</span></h1>
          <p class="hero-description">Sua pele é única. A sua base também pode ser. Comece com uma foto e descubra uma forma mais simples de encontrar sua cor.</p>
          <div class="actions hero-actions">
            <button class="btn btn-primary" data-action="capture">${icon('camera')} Tirar ou enviar foto ${icon('arrow')}</button>
            <button class="btn btn-outline-primary" data-action="how">Como funciona?</button>
          </div>
          <div class="privacy-note">${icon('shield')}<span>Sua foto é só sua. Ela não fica salva no servidor.</span></div>
        </div>
        <div class="col-lg-5 hero-art">
          <div class="hero-art-heading"><span class="eyebrow">Uma ajudinha para se encontrar</span><span class="art-star" aria-hidden="true">✳</span></div>
          <div class="mascot-stage">${mascot}<span class="mascot-caption">Oi, eu sou a Tonzinha!</span></div>
          <div class="hero-art-footer"><div class="mini-palette" aria-hidden="true">${COLORS.map(color => `<span style="--swatch:${color}"></span>`).join('')}</div><span>Todos os tons.<br>O seu também.</span></div>
        </div>
      </div>
      <p class="demo-caption">${icon('info')} <span>Estimamos seu tom pela foto e comparamos com as cores do catálogo. O resultado é experimental e depende da iluminação.</span></p>
    </section>`;
}
