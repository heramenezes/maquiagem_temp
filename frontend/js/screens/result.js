import { escapeHTML as e, safeColor, safeLink, money, scale, icon } from './shared.js';

function productCard(product, index) {
  const color = safeColor(product.hex);
  return `<article class="card product-card ${index === 0 ? 'featured' : ''}">
    <div class="product-art" style="--swatch:${color}">
      <span class="tag ${index ? 'neutral' : ''}">${index + 1}ª opção demonstrativa</span>
      <svg class="pigment-sample" viewBox="0 0 190 140" aria-hidden="true">
        <path d="M31 51C48 24 94 18 133 30C163 39 178 65 165 91C152 118 107 126 71 116C39 107 14 81 31 51Z" fill="${color}"/>
        <path d="M42 55C61 35 96 32 123 39" fill="none" stroke="white" stroke-opacity=".2" stroke-width="5" stroke-linecap="round"/>
        <path d="M57 104C87 117 130 108 151 91" fill="none" stroke="black" stroke-opacity=".06" stroke-width="3" stroke-linecap="round"/>
      </svg>
      <small>Amostra de cor · ilustração</small>
    </div>
    <div class="card-body product-info">
      <span class="eyebrow">${e(product.marca)}</span>
      <h3>${e(product.nome)}</h3>
      <div class="shade"><span class="mini-swatch" style="--swatch:${color}"></span><span>Cor <b>${e(product.cor)}</b></span></div>
      <div class="product-price"><span class="price">${money(product.preco)}</span><span class="small muted">Preço no catálogo</span></div>
      <a class="btn btn-outline-primary" href="${safeLink(product.link)}" target="_blank" rel="noopener noreferrer">Ver no site da marca ${icon('external')}<span class="visually-hidden"> (abre em nova aba)</span></a>
    </div>
  </article>`;
}

function conditionCard(condition) {
  return `<article class="condition">
    <div class="condition-head"><h3>${e(condition.nome)}</h3><span class="tag ${condition.detectada ? 'outline' : 'neutral'}">${condition.detectada ? 'Presente no exemplo' : 'Ausente no exemplo'}</span></div>
    <p class="small muted">${e(condition.descricao)}</p>
    ${condition.detectada ? `<div class="condition-detail"><div><span>Intensidade simulada</span><b>${e(condition.intensidade)}</b></div><div><span>Local simulado</span><b>${e(condition.local)}</b></div></div>` : ''}
  </article>`;
}

export function result(state) {
  const data = state.result;
  const tone = data.tom;
  const products = data.recomendacoes.map(productCard).join('');
  const conditions = data.condicoes.map(conditionCard).join('');
  const marks = data.marcacoes.map(mark => `<div class="mark" style="left:${Number(mark.x)}%;top:${Number(mark.y)}%;width:${Number(mark.largura)}%;height:${Number(mark.altura)}%"><span>${e(mark.nome)}</span></div>`).join('');

  return `<section class="container section result-summary stack">
    <div class="alert notice demo-notice">${icon('info')}<div><b>Resultado demonstrativo</b>${data.precheck.executado ? 'A presença de um rosto foi verificada na sua foto.' : 'Este exemplo não enviou uma foto nem executou a verificação facial.'} O tom, as condições e as recomendações são simulados e não descrevem sua pele.</div></div>
    <div class="row g-4 g-lg-5 align-items-center result-title">
      <div class="col-lg-7 stack"><span class="tag">${data.precheck.rosto_detectado ? '✓ Rosto detectado · verificação real' : 'Exemplo de resultado'}</span><h1>Uma prévia das bases para o seu tom.</h1><p class="lead-copy">Um universo de cores. Três opções para você conhecer.</p></div>
      <div class="col-lg-5"><div class="card tone-card"><div class="tone-swatch" style="--swatch:${safeColor(tone.hex)}"></div><div class="stack tight"><span class="eyebrow">Tom demonstrativo</span><span class="tone-value">Tom ${String(tone.monk).padStart(2, '0')}</span><span class="small muted">na Escala Monk, de 01 a 10</span><span class="tone-metrics">ITA ${e(tone.ita)}° · ${e(tone.pele_utilizada)}% da face<br>Valores simulados</span></div></div></div>
    </div>
    <div class="result-scale">${scale(data.escala_monk, tone.monk)}</div>
  </section>
  <section class="recommendations-section"><div class="container section stack">
    <div class="section-heading"><div><span class="eyebrow">Do nosso catálogo</span><h2>Suas 3 bases</h2></div><span class="small muted">Seleção demonstrativa · ${e(data.catalogo_total)} cores no catálogo</span></div>
    <div class="product-grid">${products}</div>
    <p class="catalog-note">${icon('info')}<span>Produtos, cores e preços vêm do catálogo. Confirme os valores no site da marca. Esta seleção usa um tom fixo de exemplo.</span></p>
  </div></section>
  <section class="container section skin-section stack">
    <div class="section-heading"><div class="stack tight"><span class="eyebrow">Um olhar mais de perto</span><h2>Características da pele</h2><p class="muted">Veja como serão exibidas as áreas desconsideradas no cálculo do tom. Neste exemplo, as condições e marcações são fictícias.</p></div></div>
    <div class="row g-4 g-lg-5">
      <div class="col-lg-5"><div class="stack photo-column"><div class="photo-frame">${state.photoURL ? `<img src="${e(state.photoURL)}" alt="Foto enviada, com marcações fictícias de demonstração">` : `<div class="example-face" style="--swatch:${safeColor(tone.hex)}"></div>`}<div class="marks" id="marks" aria-hidden="true">${marks}</div><span class="photo-label tag neutral">Marcações simuladas</span></div><button class="btn btn-outline-primary" data-action="marks" aria-pressed="true" aria-controls="marks">Ocultar marcações</button></div></div>
      <div class="col-lg-7"><div class="card condition-panel">${conditions}</div><p class="medical-note">${icon('info')} Estas informações são ilustrativas e não constituem diagnóstico médico.</p></div>
    </div>
    <div class="new-analysis"><div><h3>Quer tentar com outra foto?</h3><p class="muted">Um novo começo, com o mesmo cuidado.</p></div><button class="btn btn-primary" data-action="capture">${icon('refresh')} Fazer nova análise</button></div>
  </section>`;
}
