import { analyzePhoto, getExample } from './api.js';
import { home } from './screens/home.js';
import { capture } from './screens/capture.js';
import { review } from './screens/review.js';
import { processing } from './screens/processing.js';
import { result } from './screens/result.js';

const state = { screen: 'home', file: null, photoURL: null, result: null, error: '', example: false };
const screens = { home, capture, review, processing, result };
const main = document.querySelector('#main');
let revision = 0;
let pendingRequest = null;

function releasePhoto() {
  if (state.photoURL) URL.revokeObjectURL(state.photoURL);
  state.file = null;
  state.photoURL = null;
  state.result = null;
}

function render(focus = true) {
  main.innerHTML = screens[state.screen](state);
  const stage = { capture: 0, review: 0, processing: 1, result: 2 }[state.screen];
  document.querySelector('#flow').innerHTML = stage === undefined ? '' : ['Foto', 'Análise', 'Resultado'].map((label, i) => `<span class="flow-step ${i === stage ? 'active' : i < stage ? 'done' : ''}" ${i === stage ? 'aria-current="step"' : ''}>${i < stage ? '✓' : i + 1} ${label}</span>`).join('');
  const headerAction = document.querySelector('#header-action');
  headerAction.textContent = state.screen === 'home' ? 'Começar' : 'Recomeçar';
  headerAction.dataset.action = state.screen === 'home' ? 'capture' : 'home';
  document.title = `${{ home: 'Encontre sua base', capture: 'Sua foto', review: 'Revisar foto', processing: 'Verificando foto', result: 'Resultado demonstrativo' }[state.screen]} · Meu tom`;
  if (focus) { main.focus(); window.scrollTo(0, 0); }
}

function reset(screen) {
  revision++;
  pendingRequest?.abort();
  pendingRequest = null;
  releasePhoto();
  Object.assign(state, { screen, error: '', example: false });
  render();
}

async function selectFile(file) {
  if (!file) return;
  const current = ++revision;
  releasePhoto();
  state.error = '';
  const status = document.querySelector('#file-status');
  if (status) status.textContent = 'Preparando a prévia…';
  let photoURL;
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('A foto deve ter no máximo 10 MB. Escolha um arquivo menor.');
    if (file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Use uma foto JPG, PNG ou WebP. Se a foto estiver em HEIC, exporte-a como JPG.');
    photoURL = URL.createObjectURL(file);
    const preview = new Image();
    preview.src = photoURL;
    await preview.decode();
    if (preview.naturalWidth * preview.naturalHeight > 24_000_000) throw new Error('Escolha uma foto com até 24 megapixels.');
    if (current !== revision) { URL.revokeObjectURL(photoURL); return; }
    Object.assign(state, { file, photoURL, screen: 'review', error: '', example: false });
    render();
  } catch (error) {
    if (photoURL) URL.revokeObjectURL(photoURL);
    if (current !== revision) return;
    state.error = error.name === 'EncodingError' ? 'Não foi possível abrir esta imagem. Escolha outra foto JPG, PNG ou WebP.' : error.message;
    state.screen = 'capture';
    render();
  }
}

async function runAnalysis(example = false) {
  if (state.screen === 'processing' || (!example && !state.file)) return;
  const current = ++revision;
  pendingRequest?.abort();
  pendingRequest = new AbortController();
  if (example) releasePhoto();
  Object.assign(state, { screen: 'processing', error: '', example, result: null });
  render();
  try {
    const data = await (example ? getExample(pendingRequest.signal) : analyzePhoto(state.file, pendingRequest.signal));
    if (current !== revision) return;
    state.result = data;
    state.screen = 'result';
  } catch (error) {
    if (current !== revision || error.name === 'AbortError') return;
    state.error = error.message;
    if (['ROSTO_NAO_ENCONTRADO', 'FOTO_INVALIDA', 'FOTO_MUITO_GRANDE'].includes(error.code)) {
      releasePhoto();
      state.screen = 'capture';
    } else state.screen = example ? 'home' : 'review';
  } finally {
    if (current === revision) { pendingRequest = null; render(); }
  }
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  switch (button.dataset.action) {
    case 'home': reset('home'); break;
    case 'capture': reset('capture'); break;
    case 'choose': document.querySelector('#gallery-input')?.click(); break;
    case 'camera': document.querySelector('#camera-input')?.click(); break;
    case 'analyze': runAnalysis(); break;
    case 'example': runAnalysis(true); break;
    case 'marks': {
      const marks = document.querySelector('#marks');
      marks.hidden = !marks.hidden;
      button.textContent = marks.hidden ? 'Mostrar marcações' : 'Ocultar marcações';
      button.setAttribute('aria-pressed', String(!marks.hidden));
      break;
    }
  }
});

main.addEventListener('change', event => {
  if (event.target.matches('input[type="file"]')) selectFile(event.target.files[0]);
});
document.addEventListener('dragover', event => {
  event.preventDefault();
  event.target.closest?.('#drop-zone')?.classList.add('dragover');
});
document.addEventListener('dragleave', event => {
  const zone = event.target.closest?.('#drop-zone');
  if (zone && !zone.contains(event.relatedTarget)) zone.classList.remove('dragover');
});
document.addEventListener('drop', event => {
  event.preventDefault();
  document.querySelector('#drop-zone')?.classList.remove('dragover');
  if (state.screen !== 'capture' || !event.target.closest?.('#drop-zone')) return;
  if (event.dataTransfer.files.length !== 1) {
    revision++;
    releasePhoto();
    state.error = 'Escolha uma foto por vez.';
    render();
  } else selectFile(event.dataTransfer.files[0]);
});

render(false);
