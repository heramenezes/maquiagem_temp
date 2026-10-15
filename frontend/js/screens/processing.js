import { mascot } from './shared.js';

export function processing(state) {
  return `<section class="container section processing stack" aria-busy="true"><div class="processing-heading">${mascot}<div class="stack tight"><h1>${state.example ? 'Preparando o exemplo…' : 'Verificando sua foto…'}</h1><p role="status">Aguarde a resposta do servidor.</p></div></div>
    <div class="loading-bar" aria-hidden="true"></div>
    <div><div class="processing-step"><span class="step-number">01</span><div class="stack tight"><b>${state.example ? 'Carregando uma demonstração' : 'Procurando um rosto visível'}</b><span class="small muted">${state.example ? 'Nenhuma foto pessoal será enviada.' : 'Sem rosto detectado, pediremos uma nova foto.'}</span></div></div>
    <div class="processing-step"><span class="step-number">02</span><div class="stack tight"><b>Preparando o resultado demonstrativo</b><span class="small muted">Tom, características da pele e seleção de bases simulados.</span></div></div></div>
    <div><button class="btn secondary" data-action="home">Cancelar e voltar ao início</button></div></section>`;
}
