import { mascot, notice, scale } from './shared.js';

// Referência visual da escala, não um resultado de análise.
const MONK = ['#f6ede4','#f3e7db','#f7ead0','#eadaba','#d7bd96','#a07e56','#825c43','#604134','#3a312a','#292420'];

export function home(state) {
  return `${state.error ? `<div class="container section">${notice(state.error)}</div>` : ''}
    <section class="border-bottom"><div class="hero">
      <div class="hero-copy stack"><div class="tags"><span class="tag">Sem cadastro</span><span class="tag">Projeto acadêmico</span></div>
        <h1>Encontre a base certa para o seu tom de pele.</h1>
        <p>Tire uma selfie ou envie uma foto. Explore como será a análise da sua pele e a indicação de 3 bases que combinam com você.</p>
        <div class="actions"><button class="btn" data-action="capture">Tirar ou enviar foto <span aria-hidden="true">↗</span></button><button class="btn secondary" data-action="example">Ver um exemplo</button></div>
        <p class="small muted">Nesta versão, a verificação do rosto é real. O tom de pele e as recomendações são demonstrativos.</p>
      </div>
      <div class="hero-art"><span class="eyebrow">Oi! Eu sou a Tonzinha</span>${mascot}<p>Sua foto é usada só nesta solicitação e não fica salva no servidor.</p></div>
    </div></section>
    <section class="border-bottom"><div class="container section"><h2>Como funciona</h2><div class="how-grid">
      <article class="how-card"><span class="how-number">01</span><h3>Envie sua foto</h3><p>Tire uma selfie ou escolha uma foto da galeria. De frente, com boa luz e sem maquiagem.</p></article>
      <article class="how-card"><span class="how-number">02</span><h3>A gente verifica</h3><p>Primeiro, confirmamos se há um rosto visível. Se não encontrarmos, pedimos uma nova foto.</p></article>
      <article class="how-card"><span class="how-number">03</span><h3>Explore o resultado</h3><p>Veja uma simulação do tom e de 3 recomendações, com produtos do nosso catálogo de bases.</p></article>
    </div></div></section>
    <section class="container section grid-two"><div class="stack tight"><h2>Feito para todos os tons</h2><p>O projeto usa a Escala Monk, com 10 tons que vão do mais claro ao mais escuro.</p></div>${scale(MONK)}</section>`;
}
