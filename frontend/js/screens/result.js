import { escapeHTML as e, safeColor, icon } from './shared.js';

import { preprocessing, png } from './preprocessing.js';
import { finalSelection } from './selection.js';
import { toneSummary, recommendations } from './tone_results.js';

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
  const conditions = data.condicoes.map(conditionCard).join('');
  const segmentation = data.preprocessamento;
  const face = !segmentation?.simulado && png(segmentation?.previas?.rosto);
  const skin = !segmentation?.simulado && png(segmentation?.previas?.pele);
  const hasSegmentation = Boolean(face && skin);
  const marks = data.marcacoes.map(mark => `<div class="mark" style="left:${Number(mark.x)}%;top:${Number(mark.y)}%;width:${Number(mark.largura)}%;height:${Number(mark.altura)}%"><span>${e(mark.nome)}</span></div>`).join('');

  return `${toneSummary(data)}
  ${preprocessing(data.preprocessamento)}
  ${recommendations(data)}
  ${hasSegmentation ? finalSelection(segmentation) : `<section class="container section skin-section stack">
    <div class="section-heading"><div class="stack tight"><span class="eyebrow">Um olhar mais de perto</span><h2>Características da pele</h2><p class="muted">Veja como serão exibidas as áreas desconsideradas no cálculo do tom. Neste exemplo, as condições e marcações são fictícias.</p></div></div>
    <div class="row g-4 g-lg-5">
      <div class="col-lg-5"><div class="stack photo-column">
        <div class="photo-frame">
          <div class="example-face" style="--swatch:${safeColor(tone?.hex)}"></div>
          <div class="marks" id="marks" aria-hidden="true">${marks}</div>
          <span class="photo-label tag neutral">Marcações simuladas</span>
        </div>
        <button class="btn btn-outline-primary" data-action="marks" aria-pressed="true" aria-controls="marks">Ocultar marcações</button>
      </div></div>
      <div class="col-lg-7"><div class="card condition-panel">${conditions}</div><p class="medical-note">${icon('info')} Estas informações são ilustrativas e não constituem diagnóstico médico.</p></div>
    </div>
  </section>`}
  `;
}
