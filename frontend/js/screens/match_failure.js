import { escapeHTML as e } from './shared.js';
import { qualityReason } from './selection.js';

const numeric = value => typeof value === 'number' && Number.isFinite(value);
const number = value => numeric(value) ? value.toLocaleString('pt-BR', { maximumFractionDigits: 6 }) : 'Não disponível';
const percent = value => numeric(value) ? `${number(value * 100)}%` : 'Não disponível';
const modules = { acne: 'Acne', vitiligo: 'Vitiligo', barba: 'Barba e bigode' };
const states = { indisponivel: 'indisponível', falha: 'falhou', nao_executado: 'não executado' };
const guidance = {
  modulo_obrigatorio_indisponivel: 'Tente novamente. Se persistir, o serviço precisa ser verificado; trocar a iluminação da foto não resolve uma análise indisponível.',
  poucos_pixels_nativos: 'Aproxime o rosto e envie uma foto com mais resolução, sem ampliar artificialmente a imagem.',
  cobertura_insuficiente: 'Deixe mais pele visível, sem cabelo ou acessórios cobrindo o rosto.',
  incerteza_excessiva: 'Use uma foto nítida, sem filtros, com o rosto descoberto e luz uniforme.',
  amostra_concentrada: 'Mostre o rosto inteiro e de frente, deixando diferentes regiões de pele visíveis.',
  clipping_excessivo: 'Evite flash direto, luz estourada e sombras muito escuras; ajuste a exposição.',
  nitidez_insuficiente: 'Limpe a lente, mantenha a câmera firme e confira o foco no rosto.',
  iluminacao_desigual: 'Use luz difusa de frente e evite luz lateral forte ou sombras no rosto.',
  cor_inconsistente: 'Use luz uniforme e envie a foto sem maquiagem, filtros ou edição de cor.',
  cor_sensivel_a_incerteza: 'Tente uma foto mais nítida e uniforme, para reduzir as regiões de pele incertas.',
  medicao_ausente: 'Tente novamente. A medição não foi disponibilizada pelo serviço.',
  catalogo_vazio: 'Tente novamente mais tarde. O catálogo precisa ter produtos disponíveis; uma nova foto não preenche o catálogo.',
};

export function failureReasons(data) {
  return [...new Set([...(data.match?.motivos || []), ...(data.preprocessamento?.selecao?.quality?.reasons || [])])];
}

export function technicalIssue(data) {
  return failureReasons(data).some(reason => ['modulo_obrigatorio_indisponivel', 'medicao_ausente'].includes(reason));
}

function qualityDetails(data) {
  const quality = data.preprocessamento?.selecao?.quality;
  const t = quality?.thresholds;
  if (!t) return '';
  const m = quality.metrics || {};
  const rows = [
    ['Pixels de pele válida', m.native_pixels, t.min_pixels, number, 'pelo menos'],
    ['Pele válida / pele inicial', m.valid_fraction, t.min_fraction, percent, 'pelo menos'],
    ['Extensão espacial mínima', m.spatial_extent, t.min_spatial_extent, percent, 'pelo menos'],
    ['Pixels com canal RGB ≤ 2 ou ≥ 253', m.clipped_fraction, t.max_clipped_fraction, percent, 'no máximo'],
    ['Nitidez (variância do Laplaciano)', m.sharpness, t.min_sharpness, number, 'pelo menos'],
    ['Variação de luz (L* p95 − p5)', m.light_spread, t.max_light_spread, number, 'no máximo'],
    ['Dispersão de cor (ΔE76 p90)', m.dispersion_delta_e76_p90, t.max_dispersion, number, 'no máximo'],
    ['Mudança ao incluir incertezas (ΔE76)', m.uncertainty_shift_delta_e76, t.max_uncertainty_shift, number, 'no máximo'],
    ['Incerteza não excluída / pele inicial', m.uncertain_fraction, t.max_uncertain_fraction, percent, 'no máximo'],
  ];
  return `<details class="match-quality-details"><summary>Ver medidas e limites desta análise</summary>
    <p class="small muted">Basta um critério reprovar para bloquear a medição. Valores iguais ao limite são aceitos. Os limites vêm do servidor e ainda são provisórios.</p>
    <div class="quality-table-wrap"><table class="quality-thresholds"><caption>Critérios técnicos para medir o tom</caption><thead><tr><th scope="col">Critério</th><th scope="col">Na foto</th><th scope="col">Para medir</th></tr></thead>
    <tbody>${rows.map(([label, value, threshold, display, operator]) => `<tr><th scope="row">${e(label)}</th><td>${e(display(value))}</td><td>${e(operator)} ${e(display(threshold))}</td></tr>`).join('')}</tbody></table></div>
    <p class="small muted">Percentuais usam a pele anatômica inicial, exceto pixels sem detalhe, que usam a pele válida. Medidas indisponíveis não são tratadas como zero. Valores exibidos são arredondados; a decisão usa a precisão original.</p>
    </details>`;
}

export function matchFailure(data) {
  if (data.exemplo || (data.tom && data.match?.status === 'calculado')) return '';
  const noCatalog = data.match?.status === 'sem_candidatos';
  const reasons = failureReasons(data);
  const activeReasons = reasons.length ? reasons : ['medicao_ausente'];
  const statuses = data.preprocessamento?.selecao?.module_status || {};
  const unavailable = Object.entries(statuses).filter(([, status]) => status.state !== 'executado');
  return `<aside class="match-failure" role="alert" aria-labelledby="match-failure-title">
    <h2 id="match-failure-title">${noCatalog ? 'Por que não há bases recomendadas?' : 'Por que não foi possível identificar o tom?'}</h2>
    <p>${noCatalog ? 'Seu tom foi medido, mas o catálogo está vazio. Isso não indica um problema com sua foto.' : 'O tom e as recomendações foram bloqueados pelos motivos abaixo. Nenhum tom ou produto foi preenchido como exemplo.'}</p>
    <ul class="match-reasons">${activeReasons.map(reason => `<li data-failure-reason="${e(reason)}"><b>${e(qualityReason(reason))}</b><p>${e(guidance[reason] || 'Tente novamente; se o problema persistir, solicite a verificação do serviço.')}</p></li>`).join('')}</ul>
    ${unavailable.length ? `<p class="failed-modules"><b>Análises que não concluíram:</b> ${unavailable.map(([key, status]) => e(`${modules[key] || 'Análise necessária'}: ${states[status.state] || 'não disponível'}`)).join('; ')}.</p>` : ''}
    ${!noCatalog ? qualityDetails(data) : ''}
  </aside>`;
}
