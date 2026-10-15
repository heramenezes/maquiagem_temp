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
export const notice = message => message ? `<div class="notice error" role="alert">${escapeHTML(message)}</div>` : '';
export const mascot = '<img src="/assets/tonzinha.svg" alt="Tonzinha, nosso frasco de base sorridente">';
export function scale(colors, selected = 0) {
  return `<div class="scale" aria-label="Escala Monk, dez tons">${colors.map((color, i) => `<div class="scale-item ${i + 1 === selected ? 'selected' : ''}" ${i + 1 === selected ? 'aria-label="Tom demonstrativo selecionado"' : ''}><div class="scale-color" style="--swatch:${safeColor(color)}"></div><span>${String(i + 1).padStart(2, '0')}</span></div>`).join('')}</div>`;
}
