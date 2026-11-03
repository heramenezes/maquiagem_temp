import { escapeHTML as e, safeColor, safeLink, money, scale, icon } from './shared.js';
import { format } from './selection.js';
import { matchFailure, technicalIssue } from './match_failure.js';

const monkNumber = value => String(value).padStart(2, '0');
const finite = value => typeof value === 'number' && Number.isFinite(value);

export function toneSummary(data) {
  const demo = data.exemplo === true;
  const tone = data.tom;
  const measured = Boolean(tone && Number.isInteger(tone.monk) && tone.monk >= 1 && tone.monk <= 10);
  const technical = technicalIssue(data);
  if (measured) {
    return `<section class="container section result-summary stack">
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
      ${matchFailure(data)}
    </section>`;
  }
  const notice = demo
    ? '<b>Resultado demonstrativo</b>Este exemplo não enviou uma foto nem executou a verificação facial. O tom, as condições e as recomendações são simulados.'
    : '<b>Análise inconclusiva</b>Não foi possível medir o tom com qualidade suficiente. As regiões analisadas continuam disponíveis abaixo.';
  const title = demo ? 'Uma prévia das bases para o seu tom.' : technical ? 'Não foi possível concluir a análise.' : 'Precisamos de outra foto.';
  const description = demo ? 'Conheça um exemplo de como seu resultado será apresentado.'
    : technical ? 'Uma análise necessária não ficou disponível. Confira o aviso e tente novamente.' : 'Tente uma foto nítida, de frente, sem filtros e com luz uniforme.';
  const card = `<div class="card tone-card tone-unavailable" data-tone-state="unavailable"><span class="tone-empty-icon">${icon('sun')}</span><div class="stack tight"><span class="eyebrow">Tom não calculado</span><h2>Vamos tentar de novo</h2><p class="small muted">${technical ? 'A análise precisa concluir antes de medir o tom.' : 'Uma nova captura pode melhorar a medição.'}</p></div></div>`;
  return `<section class="container section result-summary stack">
    <div class="alert notice ${demo ? 'demo-notice' : 'match-notice'}">${icon('info')}<div>${notice}</div></div>
    ${matchFailure(data)}
    <div class="row g-4 g-lg-5 align-items-center result-title">
      <div class="col-lg-7 stack"><h1>${title}</h1><p class="lead-copy">${description}</p>
      </div><div class="col-lg-5">${card}</div>
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
  // Mesmo uma resposta inconsistente não deve mostrar produtos sem medição válida.
  const available = demo || (data.tom && data.match?.status === 'calculado' && data.preprocessamento?.medicao_utilizavel === true);
  const products = available && Array.isArray(data.recomendacoes) ? data.recomendacoes : [];
  const title = products.length ? `${products.length === 1 ? 'Sua opção' : `Suas ${products.length} opções`} de base` : 'Bases ainda não disponíveis';
  const noTone = !data.tom;
  return `<section class="recommendations-section"><div class="container section stack">
    <div class="section-heading"><div><span class="eyebrow">Do nosso catálogo</span><h2>${title}</h2></div><span class="small muted">${demo ? 'Seleção demonstrativa' : 'Seleção pela sua foto'} · ${e(data.catalogo_total)} cores no catálogo</span></div>
    ${products.length ? `<div class="product-grid">${products.map((product, index) => productCard(product, index, demo)).join('')}</div>
      ${!demo && data.match?.grupos_complementares_utilizados ? '<p class="small muted">Incluímos grupos Monk complementares porque havia poucas opções no mesmo grupo da sua pele.</p>' : ''}
      ${demo ? '<p class="small muted">Esta seleção usa um tom fixo de exemplo.</p>' : ''}`
      : `<div class="card match-empty" data-match-state="${noTone ? 'inconclusive' : 'no-candidates'}"><h3>${noTone ? 'Precisamos concluir a medição antes de recomendar' : 'Seu tom foi estimado, mas não há opções disponíveis'}</h3><p class="muted">${noTone ? 'Sem uma medição de tom utilizável, não selecionamos bases. Confira os motivos acima e tente novamente.' : 'O catálogo está vazio. Você pode tentar novamente mais tarde; não é necessário trocar a foto.'}</p>${noTone ? `${technicalIssue(data) ? '<button class="btn btn-primary" data-action="analyze">Tentar novamente</button>' : ''}<button class="btn btn-outline-primary" data-action="capture">Escolher outra foto</button>` : ''}</div>`}
  </div></section>`;
}
