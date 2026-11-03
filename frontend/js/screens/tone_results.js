import { escapeHTML as e, safeColor, safeLink, money, icon } from './shared.js';
import { format } from './selection.js';
import { matchWarning } from './match_warning.js';

const finite = value => typeof value === 'number' && Number.isFinite(value);

export function toneSummary(data) {
  const demo = data.exemplo === true;
  const tone = data.tom;
  return `<section class="container section result-summary stack">
      ${matchWarning(data)}
      ${demo ? `<div class="alert notice demo-notice">${icon('info')}<div><b>Exemplo de resultado</b>Este exemplo não enviou uma foto. O tom e as recomendações são simulados.</div></div>` : ''}
      <div class="card tone-card tone-result" data-tone-state="${demo ? 'example' : 'measured'}">
        <div class="tone-result-main">
          <div class="tone-color-sample"><div class="tone-swatch" style="--swatch:${safeColor(tone.cor_pele_hex)}"></div><span>${demo ? 'Cor de exemplo' : 'Cor da foto'}</span></div>
          <div class="stack tight"><span class="eyebrow">${demo ? 'Exemplo de análise' : 'Sua análise de cor'}</span>
            <h1 class="tone-value">${demo ? 'Cor demonstrativa' : 'Cor estimada da pele'}</h1>
            <span class="small muted">${e(tone.cor_pele_hex)}</span>
          </div>
        </div>
        <div class="tone-context">
          <p>${demo ? 'Este exemplo usa uma cor fixa para ilustrar as recomendações.' : 'Comparamos a cor estimada da sua pele diretamente com as cores das bases do catálogo.'}</p>
          <p>A iluminação e a câmera podem alterar a cor da foto. As opções abaixo são um ponto de partida para testar na pele.</p>
        </div>
      </div>
    </section>`;
}

function productCard(product, index, demo) {
  const color = safeColor(product.hex);
  const image = /^\/assets\/products\/[a-z0-9._-]+$/i.test(product.imagem || '') ? e(product.imagem) : null;
  return `<article class="card product-card ${index === 0 ? 'featured' : ''}" data-product-id="${e(product.id)}">
    <div class="product-art" style="--swatch:${color}">
      <span class="tag ${index ? 'neutral' : ''}">${index + 1}ª opção${demo ? ' demonstrativa' : ''}</span>
      ${image ? `<img class="product-image" src="${image}" alt="Foto de ${e(product.nome)} — ${e(product.marca)}" width="240" height="160" loading="lazy" decoding="async">` : ''}
      <span class="product-image-fallback small muted" ${image ? 'hidden' : ''}>Foto indisponível</span>
    </div>
    <div class="card-body product-info"><span class="eyebrow">${e(product.marca)}</span><h3>${e(product.nome)}</h3>
      <div class="shade"><span class="mini-swatch" style="--swatch:${color}"></span><span>Cor <b>${e(product.cor)}</b></span></div>
      ${!demo && finite(product.delta_e00) ? `<div class="product-match"><span class="small muted">Diferença de cor (ΔE00): <b>${format(product.delta_e00)}</b></span></div>` : ''}
      <div class="product-price"><span class="price">${money(product.preco)}</span><span class="small muted">Preço no catálogo</span></div>
      <a class="btn btn-outline-primary" href="${safeLink(product.link)}" target="_blank" rel="noopener noreferrer">Ver no site da marca ${icon('external')}<span class="visually-hidden"> (abre em nova aba)</span></a>
    </div></article>`;
}

export function recommendations(data) {
  const demo = data.exemplo === true;
  const products = data.recomendacoes;
  const title = `${products.length === 1 ? 'Sua opção' : `Suas ${products.length} opções`} de base`;
  return `<section class="recommendations-section"><div class="container section stack">
    <div class="section-heading"><h2>${title}</h2><span class="small muted">${demo ? 'Seleção demonstrativa' : 'Seleção pela sua foto'} · ${e(data.catalogo_total)} cores no catálogo</span></div>
    <div class="product-grid">${products.map((product, index) => productCard(product, index, demo)).join('')}</div>
      ${demo ? '<p class="small muted">Esta seleção usa um tom fixo de exemplo.</p>' : ''}
  </div></section>`;
}
