import { mascot, icon, escapeHTML as e } from './shared.js';

function stepsHTML(progress) {
  return progress.etapas.map((step, index) => {
    const done = step.estado === 'concluida';
    const active = step.estado === 'processando';
    return `<div class="processing-step ${done ? 'completed' : active ? 'active' : 'pending'}" data-step="${e(step.id)}" data-state="${e(step.estado)}" ${active ? 'aria-current="step"' : ''}>
      <span class="step-number">${done ? icon('check') : String(index + 1).padStart(2, '0')}</span>
      <div class="stack tight"><b>${e(step.nome)}</b><span class="small muted">${e(step.descricao)}</span></div>
      ${active ? '<span class="spinner-border spinner-border-sm" aria-label="Em processamento"></span>' : `<span class="step-status">${done ? 'Concluída' : 'Aguardando'}</span>`}
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
  document.querySelector('#processing-status').textContent = active?.nome || 'Etapa concluída.';
}

export function processing(state) {
  return `<section class="container section processing" aria-busy="true"><div class="card processing-card stack"><div class="processing-mascot">${mascot}</div>
    <div class="processing-heading stack tight"><span class="eyebrow">Um instante para cuidar dos detalhes</span><h1>${state.example ? 'Preparando o exemplo…' : 'Processando sua foto…'}</h1><p class="muted" id="processing-status" role="status">${state.example ? 'Carregando a demonstração.' : 'Enviando a foto e aguardando o servidor.'}</p></div>
    <div class="processing-progress-label" id="processing-count">${state.example ? 'Exemplo demonstrativo' : 'Aguardando o início das etapas'}</div>
    <div class="loading-bar" id="processing-progress" role="progressbar" aria-label="Etapas de processamento" aria-valuemin="0" aria-valuemax="100"><span></span></div>
    <div class="processing-steps" id="processing-steps">${state.example ? '<p class="small muted">Nenhuma foto pessoal será enviada. Este exemplo não executa o processamento real.</p>' : '<p class="small muted">Primeiro verificamos o rosto; depois convertemos as cores e separamos a pele.</p>'}</div>
    <div><button class="btn btn-outline-primary" data-action="home">Cancelar e voltar ao início</button></div><p class="privacy-note">${icon('shield')} Sua foto não fica salva no servidor.</p></div></section>`;
}
