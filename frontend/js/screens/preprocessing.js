import { escapeHTML as e } from './shared.js';
import { png } from './mask_previews.js';
import { categoryPreviews, format } from './selection.js';
export { png } from './mask_previews.js';

export function preprocessing(data) {
  if (!data || data.simulado) return '';
  const anatomy = png(data.selecao?.masks?.anatomical_mask);
  return `<section class="container section stack real-preprocessing">
    <div class="section-heading"><div class="stack tight"><span class="eyebrow">Processamento real da sua foto</span><h2>Segmentação básica do rosto</h2><p class="muted">Primeiro, o BiSeNet separa pele e nariz das demais partes do rosto. Estas três imagens mostram a seleção inicial, antes das exclusões abaixo.</p></div></div>
    <div class="preprocessing-previews">
      <figure class="card"><img src="${png(data.previas?.rosto)}" alt="Recorte do rosto" width="${Number(data.dimensoes?.largura)}" height="${Number(data.dimensoes?.altura)}"><figcaption>Recorte do rosto</figcaption></figure>
      <figure class="card"><img src="${anatomy}" alt="Máscara anatômica de pele e nariz antes das exclusões" width="${Number(data.dimensoes?.largura)}" height="${Number(data.dimensoes?.altura)}"><figcaption>Máscara de pele inicial</figcaption></figure>
      <figure class="card"><div class="mask-render" data-render-state="loading"><img data-mask-preview="anatomy" alt="Pele e nariz selecionados pelo BiSeNet antes das exclusões" hidden><p class="preview-placeholder" role="status">Preparando a visualização…</p></div><figcaption>Pele selecionada inicialmente</figcaption></figure>
    </div>
    <div class="card preprocessing-metrics"><div><span>Pixels de pele na seleção inicial</span><b>${format(data.selecao?.anatomical_pixels)}</b></div><div><span>Pixels nas regiões faciais</span><b>${format(data.pixels_contorno)}</b></div><div><span>Grupos de cor na seleção inicial</span><b>${format(data.clusters)}</b></div></div>
    <details class="preprocessing-details"><summary>Como esta máscara foi obtida</summary><p>O BiSeNet identifica as regiões do rosto pixel a pixel. Pele e nariz formam o limite inicial; os grupos de cor apenas descrevem essa área. ${(data.avisos || []).map(e).join(' ')}</p></details>
    ${categoryPreviews(data)}
  </section>`;
}
