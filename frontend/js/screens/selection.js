import { escapeHTML as e } from './shared.js';
import { png } from './mask_previews.js';

export const format = value => typeof value === 'number' && Number.isFinite(value)
  ? value.toLocaleString('pt-BR', { maximumFractionDigits: 2 }) : '—';
const percent = value => typeof value === 'number' && Number.isFinite(value) ? `${format(value)}%` : '—';
const fraction = value => typeof value === 'number' ? percent(value * 100) : '—';
const categories = [
  ['acne', 'Acne'],
  ['vitiligo', 'Vitiligo'],
  ['barba', 'Barba e bigode'],
];
const statusNames = { indisponivel: 'Modelo indisponível', falha: 'Falha na análise', nao_executado: 'Não executado' };
const reasons = {
  modulo_obrigatorio_indisponivel: 'Uma das análises necessárias não ficou disponível.',
  poucos_pixels_nativos: 'Restaram poucos pixels com detalhes suficientes.',
  cobertura_insuficiente: 'A área restante é pequena em relação à pele inicial.',
  incerteza_excessiva: 'Muitas regiões ainda estão incertas.',
  amostra_concentrada: 'Os pixels restantes estão concentrados em uma área pequena.',
  clipping_excessivo: 'Há excesso de pixels sem detalhe nas partes muito claras ou escuras.',
  nitidez_insuficiente: 'A nitidez da pele restante é insuficiente.',
  iluminacao_desigual: 'A iluminação varia muito na pele restante.',
  cor_inconsistente: 'As cores da pele restante variam muito.',
  cor_sensivel_a_incerteza: 'Incluir as áreas incertas mudaria bastante a cor medida.',
  segmentacao_indisponivel: 'A segmentação de pele ficou indisponível.',
  pele_nao_segmentada: 'Não foi possível separar a pele do rosto.',
  regiao_facial_aproximada: 'Foi usada uma região aproximada do rosto.',
  pele_com_incertezas: 'A estimativa incluiu regiões incertas.',
  pele_antes_exclusoes: 'A estimativa usou a pele antes das exclusões.',
  regioes_insuficientes: 'Faltou pele com detalhes suficientes na testa ou nas bochechas.',
  discordancia_entre_regioes: 'A cor medida varia entre a testa e as bochechas.',
  sem_consenso_regional: 'As regiões do rosto não concordaram; usamos a medição global.',
};
export const qualityReason = code => reasons[code] || 'Um fator pode reduzir a precisão do tom.';
function metric(label, value) {
  return `<div><dt>${e(label)}</dt><dd>${e(value)}</dd></div>`;
}

export function categoryPreviews(data) {
  const selection = data.selecao;
  if (!selection) return '';
  return `<div class="selection-breakdown stack">
    <h2>Análise por região</h2>
    <div class="exclusion-grid">${categories.map(([key, name]) => {
      const status = selection.module_status?.[key];
      const executed = status?.state === 'executado';
      const available = executed && png(selection.masks?.accepted_masks?.[key]);
      const uncertain = status?.uncertain_pixels;
      const label = executed ? (status.accepted_pixels > 0 ? 'Áreas selecionadas' : uncertain > 0 ? 'Somente áreas incertas' : 'Nenhuma área selecionada')
        : statusNames[status?.state] || 'Análise não disponível';
      const regions = (selection.regions || []).filter(region => region.reason === key && region.state === 'aceita').length;
      return `<article class="card exclusion-card category-${key}" data-category="${key}" data-module-state="${e(status?.state || 'nao_executado')}">
        <div class="condition-head"><h3>${name}</h3><span class="tag ${executed ? 'neutral' : 'status-warning'}">${label}</span></div>
        <figure class="exclusion-figure"><div class="mask-render" data-render-state="${available ? 'loading' : 'unavailable'}">
          ${available ? `<img data-mask-preview="${key}" alt="${name}: exclusões destacadas sobre o recorte do rosto; áreas incertas em amarelo" hidden>` : ''}
          <p class="preview-placeholder" role="status">${available ? 'Preparando a visualização…' : executed ? 'Máscara não recebida.' : 'Não há uma máscara disponível para esta análise.'}</p>
        </div><figcaption class="mask-legend"><span><i class="legend-dot category-dot"></i>Exclusões</span><span><i class="legend-dot uncertain-dot"></i>Incertezas</span></figcaption></figure>
        <dl class="selection-metrics">
          ${metric('Pixels excluídos', executed ? format(status.accepted_pixels) : '—')}
          ${metric('Da pele inicial', executed ? percent(selection.percent_by_reason?.[key]) : '—')}
          ${metric('Pixels incertos', executed ? format(uncertain) : '—')}
          ${metric('Regiões de exclusão', executed ? format(regions) : '—')}
          ${metric('Tempo de análise', typeof status?.elapsed_ms === 'number' ? `${format(status.elapsed_ms)} ms` : '—')}
        </dl>
        ${key === 'barba' ? '<p class="small muted category-note">Pelos claros ou muito finos podem gerar regiões incertas. Confira as áreas destacadas na imagem.</p>' : ''}
      </article>`;
    }).join('')}</div>
    <p class="small muted">Os percentuais usam a pele anatômica inicial (${format(selection.anatomical_pixels)} pixels). Uma região pode aparecer em mais de um cartão; a seleção final conta cada pixel uma única vez.</p>
  </div>`;
}

export function finalSelection(data) {
  const selection = data.selecao;
  const quality = selection?.quality;
  const metrics = quality?.metrics || {};
  const fallback = data.origem_medicao !== 'pele_valida' || data.metodo_contorno === 'regiao_central_rosto';
  const lab = Array.isArray(data.media_lab) && data.media_lab.length === 3 && data.media_lab.every(Number.isFinite) ? data.media_lab : null;
  return `<section class="container section skin-section final-selection stack">
    <h2>Pele usada na estimativa</h2>
    <div class="row g-4 g-lg-5 align-items-start">
      <div class="col-lg-5"><figure class="final-skin-figure card"><div class="useful-skin-image"><img id="segmentation-overlay" src="${png(data.previas?.pele)}" alt="Pixels usados para estimar o tom da foto" width="${Number(data.dimensoes?.largura)}" height="${Number(data.dimensoes?.altura)}"></div><figcaption>${fallback ? 'Região alternativa usada na estimativa' : 'Pele anatômica − exclusões − incertezas'}</figcaption></figure></div>
      <div class="col-lg-7 stack">
        <div class="card selection-quality" data-quality="${quality?.usable ? 'approved' : 'with-warnings'}">
          <span class="tag">Medição realizada</span>
          <p>Estes pixels foram usados para estimar a cor da sua pele e comparar as cores das bases.</p>
          <dl class="selection-metrics final-metrics">
            ${metric('Pixels restantes', format(metrics.native_pixels ?? data.pixels_pele))}
            ${metric('Pixels usados na medição', format(data.pixels_pele))}
            ${metric('Da pele inicial', fraction(metrics.valid_fraction))}
            ${metric('Exclusões unificadas', percent(selection?.excluded_percent))}
            ${metric('Incerteza restante', fraction(metrics.uncertain_fraction))}
            ${metric('Média CIELAB · D65', lab ? `L* ${format(lab[0])} · a* ${format(lab[1])} · b* ${format(lab[2])}` : '—')}
            ${metric('Dispersão da cor · ΔE76 p90', format(data.dispersao_delta_e76_p90))}
          </dl>
        </div>
        <p class="small muted">Os limiares de seleção ainda estão em calibração. As imagens mostram regiões para exclusão da medição de cor e não constituem diagnóstico.</p>
      </div>
    </div>
  </section>`;
}
