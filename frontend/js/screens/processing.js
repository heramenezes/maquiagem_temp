import { mascot, icon } from './shared.js';

export function processing(state) {
  return `<section class="container section processing" aria-busy="true"><div class="card processing-card stack"><div class="processing-mascot">${mascot}</div><div class="processing-heading stack tight"><span class="eyebrow">Um instante para cuidar dos detalhes</span><h1>${state.example ? 'Preparando o exemplo…' : 'Verificando sua foto…'}</h1><p class="muted" role="status">A Tonzinha já está cuidando disso.</p></div>
    <div class="loading-bar" aria-hidden="true"></div>
    <div class="processing-steps"><div class="processing-step"><span class="step-number">01</span><div class="stack tight"><b>${state.example ? 'Carregando uma demonstração' : 'Procurando um rosto visível'}</b><span class="small muted">${state.example ? 'Nenhuma foto pessoal será enviada.' : 'Se o rosto não estiver visível, pediremos outra foto.'}</span></div><span class="spinner-border spinner-border-sm" aria-hidden="true"></span></div>
    <div class="processing-step pending"><span class="step-number">02</span><div class="stack tight"><b>Preparando suas opções</b><span class="small muted">Um exemplo de tom, características da pele e bases.</span></div></div></div>
    <div><button class="btn btn-outline-primary" data-action="home">Cancelar e voltar ao início</button></div><p class="privacy-note">${icon('shield')} Sua foto não fica salva no servidor.</p></div></section>`;
}
