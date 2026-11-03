import { escapeHTML as e } from './shared.js';
import { qualityReason } from './selection.js';

const numeric = value => typeof value === 'number' && Number.isFinite(value);
const number = value => numeric(value) ? value.toLocaleString('pt-BR', { maximumFractionDigits: 6 }) : 'Não disponível';
const percent = value => numeric(value) ? `${number(value * 100)}%` : 'Não disponível';
const modules = { acne: 'Acne', vitiligo: 'Vitiligo', barba: 'Barba e bigode' };
const states = { indisponivel: 'indisponível', falha: 'falhou', nao_executado: 'não executado' };
const guidance = {
  modulo_obrigatorio_indisponivel: 'Algumas regiões com acne, vitiligo ou pelos podem ter entrado na medição porque uma análise não concluiu.',
  poucos_pixels_nativos: 'Aproxime o rosto e envie uma foto com mais resolução, sem ampliar artificialmente a imagem.',
  cobertura_insuficiente: 'Deixe mais pele visível, sem cabelo ou acessórios cobrindo o rosto.',
  incerteza_excessiva: 'Use uma foto nítida, sem filtros, com o rosto descoberto e luz uniforme.',
  amostra_concentrada: 'Mostre o rosto inteiro e de frente, deixando diferentes regiões de pele visíveis.',
  clipping_excessivo: 'Evite flash direto, luz estourada e sombras muito escuras; ajuste a exposição.',
  nitidez_insuficiente: 'Limpe a lente, mantenha a câmera firme e confira o foco no rosto.',
  iluminacao_desigual: 'Use luz difusa de frente e evite luz lateral forte ou sombras no rosto.',
  cor_inconsistente: 'Use luz uniforme e envie a foto sem maquiagem, filtros ou edição de cor.',
  cor_sensivel_a_incerteza: 'Tente uma foto mais nítida e uniforme, para reduzir as regiões de pele incertas.',
  segmentacao_indisponivel: 'O modelo de segmentação ficou indisponível; usamos uma região aproximada do rosto para estimar a cor.',
  pele_nao_segmentada: 'O modelo não separou pixels de pele; usamos uma região aproximada do rosto para estimar a cor.',
  regiao_facial_aproximada: 'A região central pode incluir olhos, lábios, pelos ou outras áreas que alteram a estimativa.',
  pele_com_incertezas: 'Não restaram pixels na seleção estrita. A medição incluiu áreas que os modelos consideraram incertas.',
  pele_antes_exclusoes: 'As exclusões cobriram toda a pele selecionada. A medição usou a pele inicial, que pode incluir acne, vitiligo ou pelos.',
};

export function warningReasons(data) {
  return [...new Set([...(data.match?.motivos || []), ...(data.preprocessamento?.selecao?.quality?.reasons || [])])];
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
    <p class="small muted">Os limites indicam quando a precisão pode ser menor e não impedem a recomendação. Valores iguais ao limite são aceitos. Os limites vêm do servidor e ainda são provisórios.</p>
    <div class="quality-table-wrap"><table class="quality-thresholds"><caption>Indicadores de precisão da seleção estrita de pele</caption><thead><tr><th scope="col">Critério</th><th scope="col">Na foto</th><th scope="col">Faixa de referência</th></tr></thead>
    <tbody>${rows.map(([label, value, threshold, display, operator]) => `<tr><th scope="row">${e(label)}</th><td>${e(display(value))}</td><td>${e(operator)} ${e(display(threshold))}</td></tr>`).join('')}</tbody></table></div>
    <p class="small muted">Percentuais usam a pele anatômica inicial, exceto pixels sem detalhe, que usam a pele válida. Medidas indisponíveis não são tratadas como zero. Valores exibidos são arredondados; a decisão usa a precisão original.</p>
    </details>`;
}

export function matchWarning(data) {
  const reasons = warningReasons(data);
  if (data.exemplo || !reasons.length) return '';
  const statuses = data.preprocessamento?.selecao?.module_status || {};
  const unavailable = Object.entries(statuses).filter(([, status]) => status.state !== 'executado');
  return `<aside class="match-warning" role="alert" aria-labelledby="match-warning-title">
    <h2 id="match-warning-title">O tom estimado pode estar incorreto.</h2>
    <p>Recomendamos as bases com a estimativa disponível, mas os fatores abaixo podem reduzir a precisão do tom.</p>
    <ul class="match-reasons">${reasons.map(reason => `<li data-warning-reason="${e(reason)}"><b>${e(qualityReason(reason))}</b><p>${e(guidance[reason] || 'Este fator pode alterar a cor medida e reduzir a precisão da estimativa.')}</p></li>`).join('')}</ul>
    ${unavailable.length ? `<p class="failed-modules"><b>Análises que não concluíram:</b> ${unavailable.map(([key, status]) => e(`${modules[key] || 'Análise necessária'}: ${states[status.state] || 'não disponível'}`)).join('; ')}.</p>` : ''}
    ${qualityDetails(data)}
  </aside>`;
}
