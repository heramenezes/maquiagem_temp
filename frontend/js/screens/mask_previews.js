// Composição visual; a medição usa os pixels originais no backend.
export const png = value => typeof value === 'string' && /^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(value) ? value : '';
const colors = { acne: [219, 76, 90], vitiligo: [142, 91, 205], barba: [43, 120, 194], outras_regioes: [19, 139, 122] };
const uncertainColor = [244, 181, 57];

async function loadPixels(url) {
  if (!png(url)) throw new Error('Prévia ausente.');
  const image = new Image();
  image.src = url;
  await image.decode();
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d');
  context.drawImage(image, 0, 0);
  return context.getImageData(0, 0, canvas.width, canvas.height);
}

export function composePreview(source, anatomy, accepted, uncertain, color) {
  for (const mask of [anatomy, accepted, uncertain].filter(Boolean)) {
    if (mask.width !== source.width || mask.height !== source.height) throw new Error('Máscaras desalinhadas.');
  }
  const output = new ImageData(new Uint8ClampedArray(source.data), source.width, source.height);
  for (let i = 0; i < output.data.length; i += 4) {
    const inside = anatomy.data[i] > 127;
    if (!color) {
      output.data[i + 3] = inside ? 255 : 0;
      continue;
    }
    const tint = inside && accepted.data[i] > 127 ? color
      : inside && uncertain?.data[i] > 127 ? uncertainColor : null;
    if (tint) {
      for (let c = 0; c < 3; c++) output.data[i + c] = Math.round(source.data[i + c] * .3 + tint[c] * .7);
    }
  }
  return output;
}

export async function initializeMaskPreviews(root, data) {
  const targets = [...root.querySelectorAll('[data-mask-preview]')];
  if (!targets.length) return;
  const cache = new Map();
  const pixels = url => {
    if (!cache.has(url)) cache.set(url, loadPixels(url));
    return cache.get(url);
  };
  await Promise.all(targets.map(async target => {
    const container = target.closest('.mask-render');
    const message = container.querySelector('.preview-placeholder');
    try {
      const key = target.dataset.maskPreview;
      const masks = data.selecao.masks;
      const [source, anatomy, accepted, uncertain] = await Promise.all([
        pixels(data.previas.rosto), pixels(masks.anatomical_mask),
        key === 'anatomy' ? null : pixels(masks.accepted_masks[key]),
        key === 'anatomy' ? null : pixels(data.selecao.debug_masks?.[key]?.raw_uncertain),
      ]);
      if (!target.isConnected) return;
      const result = composePreview(source, anatomy, accepted, uncertain, colors[key]);
      const canvas = document.createElement('canvas');
      canvas.width = result.width;
      canvas.height = result.height;
      canvas.getContext('2d').putImageData(result, 0, 0);
      target.src = canvas.toDataURL('image/png');
      await target.decode();
      if (!target.isConnected) return;
      target.hidden = false;
      message.hidden = true;
      container.dataset.renderState = 'ready';
    } catch {
      if (!target.isConnected) return;
      container.dataset.renderState = 'error';
      message.textContent = 'Não foi possível montar esta prévia. As métricas recebidas estão abaixo.';
    }
  }));
}
