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
            <button class="btn btn-outline-primary" data-action="example">Ver um exemplo</button>
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
    </section>
    <section class="container section how-section">
      <div class="section-heading"><div><span class="eyebrow">Sem complicação</span><h2>Seu tom, em três passos.</h2></div><p class="muted">Uma foto é o começo de tudo.</p></div>
      <div class="row g-4 how-grid">
        <div class="col-md-4"><article class="card how-card"><div class="how-card-top"><span class="how-icon">${icon('camera')}</span><span class="how-number">01</span></div><h3>Envie sua foto</h3><p>Tire uma selfie ou escolha uma foto da galeria. De frente, com boa luz e sem maquiagem.</p><span class="how-caption">Você escolhe como começar</span></article></div>
        <div class="col-md-4"><article class="card how-card"><div class="how-card-top"><span class="how-icon">${icon('face')}</span><span class="how-number">02</span></div><h3>A gente verifica</h3><p>Conferimos se seu rosto está visível. Se precisar, ajudamos você a escolher uma foto melhor.</p><span class="how-caption">Um cuidado antes da análise</span></article></div>
        <div class="col-md-4"><article class="card how-card"><div class="how-card-top"><span class="how-icon">${icon('sparkle')}</span><span class="how-number">03</span></div><h3>Conheça suas opções</h3><p>Veja seu tom estimado e até três bases selecionadas pela cor da sua pele.</p><span class="how-caption">Cor, preço e link em um só lugar</span></article></div>
      </div>
    </section>
    <section class="container palette-section"><div class="palette-panel"><div class="row align-items-center g-4 g-lg-5"><div class="col-lg-5 stack tight"><span class="eyebrow">Beleza sem um tom só</span><h2>Uma cor que combina com você.</h2></div><div class="col-lg-7"><p>Comparamos a cor estimada pela sua foto diretamente com as cores das bases. Você recebe até três opções para conhecer e testar na pele.</p><p class="small muted">Uma boa foto ajuda: prefira luz uniforme, sem filtros e sem maquiagem.</p></div></div></div></section>`;
}
