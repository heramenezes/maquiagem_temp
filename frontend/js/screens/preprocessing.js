import { escapeHTML as e } from './shared.js';

export const png = value => typeof value === 'string' && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(value) ? value : '';
const format = value => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 });

export function preprocessing(data) {
  if (!data || data.simulado) return '';
  return `<section class="container section stack real-preprocessing">
    <div class="section-heading"><div class="stack tight"><span class="eyebrow">Processamento real da sua foto</span><h2>Pele separada para a próxima etapa</h2><p class="muted">O branco na máscara indica os pixels selecionados. As regiões transparentes foram excluídas.</p></div></div>
    <div class="preprocessing-previews">
      ${[['rosto', 'Recorte do rosto'], ['mascara', 'Máscara de pele'], ['pele', 'Pele selecionada']].map(([key, label]) => `<figure class="card"><img src="${png(data.previas[key])}" alt="${e(label)}" width="${Number(data.dimensoes.largura)}" height="${Number(data.dimensoes.altura)}"><figcaption>${e(label)}</figcaption></figure>`).join('')}
    </div>
    <div class="card preprocessing-metrics"><div><span>Pele selecionada no contorno estimado</span><b>${format(data.percentual_pele)}%</b></div><div><span>Média CIELAB · D65</span><b>L* ${format(data.media_lab[0])} · a* ${format(data.media_lab[1])} · b* ${format(data.media_lab[2])}</b></div><div><span>Grupos de cor encontrados</span><b>${Number(data.clusters)}</b></div></div>
    <p class="small muted">A conversão de cor e esta máscara são reais. A máscara é uma estimativa inicial; luz, pose, pelos e acessórios podem afetar a seleção.</p>
    <details class="preprocessing-details"><summary>Como esta máscara foi obtida</summary><p>${data.metodo_contorno === 'mediapipe_face_mesh' ? 'Contorno e exclusões a partir de pontos faciais do MediaPipe.' : 'Contorno e exclusões aproximados para uma foto frontal.'} K-means adaptativo em a*/b* e crescimento de regiões. ${data.avisos.map(e).join(' ')}</p></details>
  </section>`;
}
