import { escapeHTML as e, safeColor, safeLink, money, icon } from './shared.js';
import { format } from './selection.js';
import { png } from './mask_previews.js';

const finite = value => typeof value === 'number' && Number.isFinite(value);
const signed = value => finite(value) ? `${value > 0 ? '+' : ''}${format(value)}` : '—';
const kb = bytes => finite(bytes) ? `${(bytes / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} KB` : '—';
const ms = value => finite(value) ? `${format(value)} ms` : '—';

const stageNames = {
  rosto: 'Detecção e recorte do rosto',
  cielab: 'Conversão sRGB → CIELAB (OpenMP)',
  mascara: 'Segmentação facial (BiSeNet)',
  acne: 'Especialista de acne (U-Net)',
  vitiligo: 'Especialista de vitiligo (YOLO11n)',
  barba: 'Especialista de barba (YOLOv8l)',
  selecao: 'União de máscaras e qualidade',
  clusters: 'Agrupamento descritivo (K-means)',
  medidas: 'Estimativa regional (testa e bochechas)',
  resultado: 'Ranking CIEDE2000 e montagem',
};

function deltaBadge(de00) {
  if (!finite(de00)) return { label: 'Indisponível', cls: 'neutral' };
  if (de00 < 1) return { label: 'Diferença imperceptível (< 1 ΔE00)', cls: '' };
  if (de00 < 2.5) return { label: 'Diferença sutil (1–2,5 ΔE00)', cls: 'outline' };
  return { label: 'Diferença visível de tom (≥ 2,5 ΔE00)', cls: 'status-warning' };
}

function algoRecItem(product, index) {
  const color = safeColor(product.hex);
  return `<li class="algo-rec-item">
    <span class="algo-rec-rank">${index + 1}º</span>
    <span class="mini-swatch" style="--swatch:${color}"></span>
    <div class="algo-rec-copy">
      <b>${e(product.nome)} · ${e(product.cor)}</b>
      <span class="small muted">${e(product.marca)} · ΔE00 ${format(product.delta_e00)} · ${money(product.preco)}</span>
    </div>
    <a class="algo-rec-link" href="${safeLink(product.link)}" target="_blank" rel="noopener noreferrer" aria-label="Abrir ${e(product.nome)} no site da marca">${icon('external')}</a>
  </li>`;
}

function sampledPointsList(points) {
  if (!Array.isArray(points) || !points.length) return '';
  return `<div class="sampled-points-wrap">
    <span class="small muted">Pixels sorteados na máscara:</span>
    <ul class="sampled-points-list">${points.map(pt => `<li>
      <span class="point-pin ${pt.em_pele_valida ? 'valid' : 'excluded'}">${e(pt.indice)}</span>
      <span class="mini-swatch" style="--swatch:${safeColor(pt.hex)}"></span>
      <span><code>(${e(pt.x)}, ${e(pt.y)})</code> · ${e(pt.hex)}</span>
      <span class="tag ${pt.em_pele_valida ? 'neutral' : 'status-warning'}">${pt.em_pele_valida ? 'Pele válida' : 'Região excluída/incerta'}</span>
    </li>`).join('')}</ul>
  </div>`;
}

export function algorithmComparison(data) {
  const comp = data?.comparacao_algoritmos;
  if (!comp?.pipeline_completo || !comp?.tres_pontos_aleatorios || !comp?.metricas) return '';

  const full = comp.pipeline_completo;
  const rand = comp.tres_pontos_aleatorios;
  const m = comp.metricas;
  const mc = m.estabilidade_monte_carlo || {};
  const badge = deltaBadge(m.delta_e00_entre_algoritmos);
  const faceSrc = png(data?.preprocessamento?.previas?.rosto);
  const w = Number(data?.preprocessamento?.dimensoes?.largura) || 200;
  const h = Number(data?.preprocessamento?.dimensoes?.altura) || 200;

  const fullLab = Array.isArray(full.lab) ? `L* ${format(full.lab[0])} · a* ${format(full.lab[1])} · b* ${format(full.lab[2])}` : '—';
  const randLab = Array.isArray(rand.lab) ? `L* ${format(rand.lab[0])} · a* ${format(rand.lab[1])} · b* ${format(rand.lab[2])}` : '—';
  const dLab = m.diferenca_lab || {};

  return `<section class="container section comparison-section stack" id="algorithm-comparison" aria-labelledby="algo-comparison-title">
    <div class="section-heading">
      <div class="stack tight">
        <span class="eyebrow">Avaliação experimental de método</span>
        <h2 id="algo-comparison-title">Pipeline completo vs. Média de 3 pontos aleatórios</h2>
      </div>
      <span class="tag ${badge.cls}">${e(badge.label)}</span>
    </div>
    <p class="lead-copy">Comparamos nossa estimativa completa (segmentação semântica, exclusão de condições e consenso regional) com uma linha de base simples que sorteia três pixels da máscara de pele e calcula sua média.</p>

    <div class="algo-compare-layout">
      ${faceSrc ? `<figure class="card algo-points-figure">
        <div class="algo-points-stage">
          <canvas class="random-points-canvas" width="${w}" height="${h}" aria-label="Recorte facial com os 3 pontos sorteados marcados"></canvas>
        </div>
        <figcaption class="small muted">Localização exata dos 3 pixels sorteados sobre o recorte facial.</figcaption>
      </figure>` : ''}

      <div class="algo-cards-grid">
        <article class="card algo-card featured-algo" data-algo="full-pipeline">
          <div class="condition-head">
            <h3>Pipeline completo</h3>
            <span class="tag">Método principal</span>
          </div>
          <div class="algo-tone-row">
            <div class="algo-swatch" style="--swatch:${safeColor(full.cor_pele_hex)}"></div>
            <div class="stack tight">
              <b class="algo-hex">${e(full.cor_pele_hex)}</b>
              <span class="small muted">${e(fullLab)}</span>
              <span class="small muted">${format(full.pixels_considerados)} pixels avaliados</span>
            </div>
          </div>
          <div class="algo-recs">
            <span class="small muted">Top 3 bases recomendadas:</span>
            <ol class="algo-rec-list">${(full.recomendacoes || []).map(algoRecItem).join('')}</ol>
          </div>
        </article>

        <article class="card algo-card" data-algo="random-3-points">
          <div class="condition-head">
            <h3>3 pontos aleatórios</h3>
            <span class="tag neutral">Linha de base simples</span>
          </div>
          <div class="algo-tone-row">
            <div class="algo-swatch" style="--swatch:${safeColor(rand.cor_pele_hex)}"></div>
            <div class="stack tight">
              <b class="algo-hex">${e(rand.cor_pele_hex)}</b>
              <span class="small muted">${e(randLab)}</span>
              <span class="small muted">3 de ${format(rand.pixels_candidatos)} pixels (${format(m.proporcao_amostrada_pct)}%) · ${ms(rand.tempo_execucao_ms)}</span>
            </div>
          </div>
          ${sampledPointsList(rand.pontos)}
          <div class="algo-recs">
            <span class="small muted">Top 3 bases por este método:</span>
            <ol class="algo-rec-list">${(rand.recomendacoes || []).map(algoRecItem).join('')}</ol>
          </div>
        </article>
      </div>
    </div>

    <div class="card algo-metrics-card stack tight">
      <h3>Métricas comparativas entre os dois algoritmos</h3>
      <dl class="selection-metrics algo-metrics-grid">
        <div><dt>Distância perceptual (ΔE00)</dt><dd>${format(m.delta_e00_entre_algoritmos)}</dd></div>
        <div><dt>Distância euclidiana (ΔE76)</dt><dd>${format(m.delta_e76_entre_algoritmos)}</dd></div>
        <div><dt>Desvio Lab (3 pts − pipeline)</dt><dd>ΔL* ${signed(dLab.delta_l)} · Δa* ${signed(dLab.delta_a)} · Δb* ${signed(dLab.delta_b)}</dd></div>
        <div><dt>Mesma 1ª base recomendada</dt><dd>${m.mesma_base_top1 ? 'Sim (idêntica)' : 'Não (alterou o 1º lugar)'}</dd></div>
        <div><dt>Acordo no Top 3 de bases</dt><dd>${e(m.intersecao_top3)} de 3 (${format(m.taxa_acordo_top3_pct)}%)</dd></div>
        <div><dt>Pontos fora da pele estrita</dt><dd>${e(m.pontos_fora_pele_estrita)} de 3</dd></div>
        <div><dt>Erro médio em ${e(mc.rodadas || 200)} sorteios (ΔE00)</dt><dd>${format(mc.delta_e00_medio_vs_pipeline)} (p90: ${format(mc.delta_e00_p90_vs_pipeline)})</dd></div>
        <div><dt>Estabilidade da 1ª base em ${e(mc.rodadas || 200)} sorteios</dt><dd>${format(mc.concordancia_top1_pct)}% mantêm o 1º lugar</dd></div>
      </dl>
      <p class="small muted">Enquanto o pipeline completo é determinístico (variância zero para a mesma foto), sortear apenas 3 pixels apresenta dispersão interna p90 de ${format(mc.dispersao_interna_p90_delta_e00)} ΔE00 devido a sombras, brilho local e condições de pele.</p>
    </div>
  </section>`;
}

export function performanceComparison(perf) {
  if (!perf || !finite(perf.tempo_pipeline_paralelo_ms) || !finite(perf.tempo_sequencial_equivalente_ms)) return '';

  const parMs = perf.tempo_pipeline_paralelo_ms;
  const seqMs = Math.max(parMs, perf.tempo_sequencial_equivalente_ms);
  const parWidth = Math.max(6, Math.min(100, Math.round((parMs / Math.max(seqMs, 0.01)) * 100)));

  const vision = perf.bloco_visao_concorrente || {};
  const vPar = vision.tempo_paralelo_ms || parMs;
  const vSeq = Math.max(vPar, vision.soma_sequencial_ms || seqMs);
  const vWidth = Math.max(6, Math.min(100, Math.round((vPar / Math.max(vSeq, 0.01)) * 100)));

  const omp = perf.openmp_cielab || {};
  const ompMs = omp.tempo_openmp_ms || 0;
  const npMs = Math.max(ompMs, omp.tempo_sequencial_numpy_ms || ompMs);
  const ompWidth = npMs > 0 ? Math.max(4, Math.min(100, Math.round((ompMs / npMs) * 100))) : 100;

  const wire = perf.rede_p2p || {};
  const nodes = Array.isArray(perf.nos_ativos) ? perf.nos_ativos : [];
  const stages = perf.etapas_ms || {};
  const maxStageMs = Math.max(1, ...Object.values(stages).filter(finite));

  return `<section class="performance-section" id="performance-comparison" aria-labelledby="perf-comparison-title">
    <div class="container section stack">
      <div class="section-heading">
        <div class="stack tight">
          <span class="eyebrow">Computação paralela e distribuída</span>
          <h2 id="perf-comparison-title">Desempenho: Pipeline paralelo/distribuído vs. Sequencial</h2>
        </div>
        <span class="tag">${e(perf.arquitetura_ativa || 'Execução paralela')}</span>
      </div>

      <div class="perf-kpi-grid">
        <div class="card perf-kpi-card highlight">
          <span class="small muted">Ganho global (Speedup)</span>
          <strong class="perf-kpi-value">${format(perf.speedup_total)}×</strong>
          <span class="small muted">Economia de ${ms(perf.economia_tempo_ms)} (−${format(perf.economia_percentual)}%)</span>
        </div>
        <div class="card perf-kpi-card">
          <span class="small muted">Pipeline paralelo / distribuído</span>
          <strong class="perf-kpi-value">${ms(parMs)}</strong>
          <span class="small muted">Tempo real de parede medido</span>
        </div>
        <div class="card perf-kpi-card">
          <span class="small muted">Execução sequencial equivalente</span>
          <strong class="perf-kpi-value">${ms(seqMs)}</strong>
          <span class="small muted">Soma das etapas sem sobreposição</span>
        </div>
        <div class="card perf-kpi-card">
          <span class="small muted">Kernel C/OpenMP (CIELAB)</span>
          <strong class="perf-kpi-value">${omp.ativo ? `${format(omp.speedup)}×` : 'Fallback'}</strong>
          <span class="small muted">${omp.ativo ? `${e(omp.threads)} threads CPU · ${ms(ompMs)}` : 'NumPy padrão ativo'}</span>
        </div>
      </div>

      <div class="perf-detail-grid">
        <div class="card perf-bars-card stack tight">
          <h3>Comparativo de tempo de execução</h3>
          <div class="perf-bar-group">
            <div class="perf-bar-label"><span>Pipeline completo sequencial</span><b>${ms(seqMs)}</b></div>
            <div class="perf-bar-track"><span class="perf-bar-fill sequential" style="width:100%"></span></div>
          </div>
          <div class="perf-bar-group">
            <div class="perf-bar-label"><span>Pipeline paralelo / distribuído</span><b>${ms(parMs)} (${format(perf.speedup_total)}×)</b></div>
            <div class="perf-bar-track"><span class="perf-bar-fill parallel" style="width:${parWidth}%"></span></div>
          </div>
          <div class="perf-bar-group">
            <div class="perf-bar-label"><span>Bloco concorrente (BiSeNet + 3 especialistas + Lab)</span><b>${ms(vPar)} vs. ${ms(vSeq)} (${format(vision.speedup)}×)</b></div>
            <div class="perf-bar-track"><span class="perf-bar-fill parallel" style="width:${vWidth}%"></span></div>
          </div>
          <div class="perf-bar-group">
            <div class="perf-bar-label"><span>Conversão CIELAB (C/OpenMP vs. NumPy sequencial)</span><b>${ms(ompMs)} vs. ${ms(npMs)} (${format(omp.speedup)}×)</b></div>
            <div class="perf-bar-track"><span class="perf-bar-fill omp" style="width:${ompWidth}%"></span></div>
          </div>
        </div>

        <div class="card perf-nodes-card stack tight">
          <h3>Nós de processamento e protocolo P2P</h3>
          ${nodes.length ? `<ul class="perf-node-list">${nodes.map(node => `<li>
            <div><b>${e(node.id)}</b>${node.endereco ? ` <code class="small">(${e(node.endereco)})</code>` : ''}<span class="small muted d-block">${e(node.papel)}</span></div>
            <span class="tag ${String(node.dispositivo).includes('CUDA') ? '' : 'neutral'}">${e(node.dispositivo)}</span>
          </li>`).join('')}</ul>` : ''}
          <dl class="selection-metrics perf-wire-metrics">
            <div><dt>Modo de orquestração</dt><dd>${perf.modo_execucao === 'distribuido_p2p' ? 'P2P entre processos / máquinas' : 'DAG paralelo em memória'}</dd></div>
            <div><dt>Recorte RGB compactado</dt><dd>${kb(wire.bytes_rgb_comprimido)} (bruto ${kb(wire.bytes_rgb_bruto)})</dd></div>
            <div><dt>Máscaras binárias P2P</dt><dd>${finite(wire.bytes_mascaras_p2p) ? `${format(wire.bytes_mascaras_p2p)} B` : '—'}</dd></div>
            <div><dt>Tensor Lab poupado na rede</dt><dd>${kb(wire.bytes_lab_evitados)}</dd></div>
          </dl>
        </div>
      </div>

      <details class="card perf-stage-details">
        <summary>Ver tempo individual medido nas 10 etapas</summary>
        <div class="perf-stages-list">
          ${Object.entries(stageNames).map(([key, label]) => {
            const val = stages[key];
            const wPct = finite(val) ? Math.max(2, Math.round((val / maxStageMs) * 100)) : 0;
            return `<div class="perf-stage-row">
              <div class="perf-bar-label"><span>${e(label)}</span><b>${ms(val)}</b></div>
              <div class="perf-bar-track"><span class="perf-bar-fill stage" style="width:${wPct}%"></span></div>
            </div>`;
          }).join('')}
        </div>
      </details>
    </div>
  </section>`;
}

export async function initializeRandomPointsPreview(root, data) {
  const canvas = root.querySelector('.random-points-canvas');
  const faceUrl = png(data?.preprocessamento?.previas?.rosto);
  const points = data?.comparacao_algoritmos?.tres_pontos_aleatorios?.pontos;
  if (!canvas || !faceUrl || !Array.isArray(points)) return;

  try {
    const img = new Image();
    img.src = faceUrl;
    await img.decode();
    if (!canvas.isConnected) return;
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);

    const radius = Math.max(6, Math.round(Math.min(canvas.width, canvas.height) * 0.045));
    ctx.font = `700 ${Math.max(10, Math.round(radius * 1.15))}px Archivo, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (const pt of points) {
      const x = Number(pt.x);
      const y = Number(pt.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      ctx.beginPath();
      ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.92)';
      ctx.fill();

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = pt.em_pele_valida ? '#2f8050' : '#c97a16';
      ctx.fill();

      ctx.fillStyle = '#ffffff';
      ctx.fillText(String(pt.indice), x, y + 0.5);
    }
    canvas.dataset.renderState = 'ready';
  } catch {
    canvas.dataset.renderState = 'error';
  }
}
