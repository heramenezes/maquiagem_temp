// Todo texto vindo da API é escapado antes de entrar em templates HTML.
export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));
export const safeColor = value => /^#[0-9a-f]{6}$/i.test(value) ? value : '#e9efe6';
export const safeLink = value => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? escapeHTML(url.href) : '#'; }
  catch { return '#'; }
};
export const money = value => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
export const notice = message => message ? `<div class="alert notice error" role="alert">${icon('info')}<div>${escapeHTML(message)}</div></div>` : '';
export const mascot = '<img src="/assets/tonzinha.svg" alt="Tonzinha, nosso frasco de base sorridente">';
// Ícones SVG locais: sem biblioteca de JavaScript ou requisições externas.
export function icon(name, className = '') {
  const paths = {
    camera: '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
    upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    external: '<path d="M14 3h7v7m0-7L10 14m0-11H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    face: '<path d="M4 10V8a8 8 0 0 1 16 0v2c0 7-4 12-8 12S4 17 4 10Z"/><path d="M8 10h.01M16 10h.01M9 15q3 3 6 0"/>',
    sparkle: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    refresh: '<path d="M3 10a9 9 0 0 1 15-5l3 3M21 2v6h-6m6 6A9 9 0 0 1 6 19l-3-3m0 6v-6h6"/>',
    eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  };
  return `<svg class="icon ${className}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.sparkle}</svg>`;
}
export function scale(colors, selected = 0) {
  return `<div class="scale" aria-label="Escala Monk, dez tons">${colors.map((color, i) => `<div class="scale-item ${i + 1 === selected ? 'selected' : ''}" ${i + 1 === selected ? 'aria-label="Tom demonstrativo selecionado"' : ''}><div class="scale-color" style="--swatch:${safeColor(color)}"></div><span>${String(i + 1).padStart(2, '0')}</span></div>`).join('')}</div>`;
}
