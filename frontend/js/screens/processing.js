import { mascot, icon, escapeHTML as e } from './shared.js';

const descriptions = {
  rosto: ['Verificando o rosto', 'Confirmamos um único rosto e preservamos o recorte da foto.'],
  cielab: ['Preparando as cores', 'Convertemos as cores para comparar e medir a pele.'],
  mascara: ['Separando a pele do rosto', 'Identificamos pele e nariz com o BiSeNet.'],
  acne: ['Analisando regiões de acne', 'Separamos as áreas apontadas pelo modelo e suas incertezas.'],
  vitiligo: ['Analisando regiões de vitiligo', 'Localizamos áreas candidatas à exclusão da medição.'],
  barba: ['Analisando barba e bigode', 'Identificamos os pelos faciais para separar a pele disponível.'],
  selecao: ['Unindo as máscaras', 'Reunimos as exclusões e verificamos a qualidade.'],
  clusters: ['Descrevendo as cores da pele', 'Contamos os grupos de cor sem alterar a seleção.'],
  medidas: ['Avaliando a medição de cor', 'Medimos somente se os pixels restantes passarem pelos critérios de qualidade.'],
  resultado: ['Preparando as imagens e métricas', 'Organizamos as máscaras reais. Tom e bases continuam demonstrativos.'],
};
const moduleStates = { indisponivel: 'Indisponível', falha: 'Falha na análise', nao_executado: 'Não executada' };

function stepsHTML(progress) {
  return progress.etapas.map((step, index) => {
    const done = step.estado === 'concluida';
    const active = step.estado === 'processando';
    const limited = done && moduleStates[step.estado_modulo];
    const [name, description] = descriptions[step.id] || [step.nome, step.descricao];
    return `<div class="processing-step ${limited ? 'partial' : done ? 'completed' : active ? 'active' : 'pending'}" data-step="${e(step.id)}" data-state="${e(step.estado)}" data-module-state="${e(step.estado_modulo || '')}" ${active ? 'aria-current="step"' : ''}>
      <span class="step-number">${limited ? icon('info') : done ? icon('check') : String(index + 1).padStart(2, '0')}</span>
      <div class="stack tight"><b>${e(name)}</b><span class="small muted">${step.motivo === 'qualidade_inconclusiva' ? 'A seleção ficou inconclusiva; a cor não foi medida.' : e(description)}</span></div>
      ${active ? '<span class="spinner-border spinner-border-sm" aria-label="Em processamento"></span>' : `<span class="step-status">${limited || (done ? 'Concluída' : 'Aguardando')}</span>`}
    </div>`;
  }).join('');
}

export function updateProcessing(progress) {
  const target = document.querySelector('#processing-steps');
  if (!target) return;
  target.innerHTML = stepsHTML(progress);
  const pct = Math.round(100 * progress.concluidas / progress.total);
  const bar = document.querySelector('#processing-progress');
  bar.classList.add('determinate');
  bar.setAttribute('aria-valuenow', String(pct));
  bar.setAttribute('aria-valuetext', `${progress.concluidas} de ${progress.total} etapas concluídas`);
  bar.querySelector('span').style.width = `${pct}%`;
  document.querySelector('#processing-count').textContent = `${progress.concluidas} de ${progress.total} etapas concluídas · ${pct}%`;
  const active = progress.etapas.find(step => step.estado === 'processando');
  document.querySelector('#processing-status').textContent = active ? (descriptions[active.id]?.[0] || active.nome) : 'Etapa avaliada. Preparando a próxima atualização.';
}

export function processing(state) {
  return `<section class="container section processing" aria-busy="true"><div class="card processing-card stack"><div class="processing-mascot">${mascot}</div>
    <div class="processing-heading stack tight"><span class="eyebrow">Um instante para cuidar dos detalhes</span><h1>${state.example ? 'Preparando o exemplo…' : 'Processando sua foto…'}</h1><p class="muted" id="processing-status" role="status">${state.example ? 'Carregando a demonstração.' : 'Enviando a foto e aguardando o servidor.'}</p></div>
    <div class="processing-progress-label" id="processing-count">${state.example ? 'Exemplo demonstrativo' : 'Aguardando o início das etapas'}</div>
    <div class="loading-bar" id="processing-progress" role="progressbar" aria-label="Etapas de processamento" aria-valuemin="0" aria-valuemax="100"><span></span></div>
    <div class="processing-steps" id="processing-steps">${state.example ? '<p class="small muted">Nenhuma foto pessoal será enviada. Este exemplo não executa o processamento real.</p>' : '<p class="small muted">Vamos separar a pele, analisar acne, vitiligo e barba e reunir os pixels restantes.</p>'}</div>
    <div><button class="btn btn-outline-primary" data-action="home">Cancelar e voltar ao início</button></div><p class="privacy-note">${icon('shield')} Sua foto não fica salva no servidor.</p></div></section>`;
}
