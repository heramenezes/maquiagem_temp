import { escapeHTML as e, safeColor, safeLink, money, scale, icon } from './shared.js';
import { format } from './selection.js';
import { matchWarning } from './match_warning.js';

const monkNumber = value => String(value).padStart(2, '0');
const finite = value => typeof value === 'number' && Number.isFinite(value);

export function toneSummary(data) {
  const demo = data.exemplo === true;
  const tone = data.tom;
  return `<section class="container section result-summary stack">
      ${matchWarning(data)}
      ${demo ? `<div class="alert notice demo-notice">${icon('info')}<div><b>Exemplo de resultado</b>Este exemplo não enviou uma foto. O tom e as recomendações são simulados.</div></div>` : ''}
      <div class="card tone-card tone-result" data-tone-state="${demo ? 'example' : 'measured'}">
        <div class="tone-result-main">
          <div class="tone-color-sample"><div class="tone-swatch" style="--swatch:${safeColor(demo ? tone.hex : tone.cor_pele_hex)}"></div><span>${demo ? 'Cor de exemplo' : 'Cor da foto'}</span></div>
          <div class="stack tight"><span class="eyebrow">${demo ? 'Tom demonstrativo' : 'Seu tom estimado'}</span>
            <h1 class="tone-value">Tom ${monkNumber(tone.monk)}</h1>
            <span class="small muted">na escala Monk</span>
            ${!demo ? `<span class="tone-reference"><i class="mini-swatch" style="--swatch:${safeColor(tone.hex)}"></i>Referência Monk ${monkNumber(tone.monk)}</span>` : ''}
          </div>
        </div>
        <div class="tone-scale-context">
          <p>Criada pelo sociólogo <strong>Ellis Monk, de Harvard</strong>, e disponibilizada em parceria com o <strong>Google</strong>, a escala Monk reúne 10 tons para representar melhor a diversidade de cores de pele. <a href="https://news.harvard.edu/gazette/story/2022/07/teaching-algorithms-about-colors-of-people/" target="_blank" rel="noopener noreferrer">Sobre a escala<span class="visually-hidden"> (abre em nova aba)</span></a></p>
          <div class="tone-scale-labels"><span>01 · Mais claro</span><span>${demo ? 'Tom de exemplo em destaque' : 'Seu tom estimado em destaque'}</span><span>10 · Mais escuro</span></div>
          <div class="result-scale">${scale(data.escala_monk, tone.monk, demo)}</div>
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
      ${!demo ? `<div class="product-match"><span class="small">Monk ${monkNumber(product.monk)} · ${product.mesmo_monk ? 'Mesmo grupo da sua pele' : 'Grupo complementar'}</span>${finite(product.delta_e00) ? `<span class="small muted">Diferença de cor (ΔE00): <b>${format(product.delta_e00)}</b></span>` : ''}</div>` : ''}
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
      ${!demo && data.match?.grupos_complementares_utilizados ? '<p class="small muted">A seleção pode incluir outros grupos Monk conforme a proximidade de cor com a sua pele.</p>' : ''}
      ${demo ? '<p class="small muted">Esta seleção usa um tom fixo de exemplo.</p>' : ''}
  </div></section>`;
}
