export class ApiError extends Error {
  constructor(message, code) { super(message); this.code = code; }
}

async function readEvents(response, onProgress, signal) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  let result;
  async function handle(line) {
    if (!line.trim()) return;
    if (signal.aborted) throw new DOMException('Cancelado', 'AbortError');
    const event = JSON.parse(line);
    if (event.tipo === 'erro') throw new ApiError(event.mensagem, event.codigo);
    if (event.tipo === 'etapa') await onProgress?.(event);
    if (event.tipo === 'resultado') result = event.dados;
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      let boundary;
      while ((boundary = pending.indexOf('\n')) !== -1) {
        const line = pending.slice(0, boundary);
        pending = pending.slice(boundary + 1);
        await handle(line);
      }
      if (done) break;
    }
    await handle(pending);
    if (!result) throw new ApiError('O processamento foi interrompido. Tente novamente.', 'RESPOSTA_INCOMPLETA');
    return result;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function request(url, options, signal, onProgress) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 45000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    if (response.ok && response.headers.get('content-type')?.includes('application/x-ndjson')) {
      return await readEvents(response, onProgress, controller.signal);
    }
    const body = await response.json();
    if (!response.ok) throw new ApiError(body.mensagem || 'Não foi possível concluir. Tente novamente.', body.codigo);
    return body;
  } catch (error) {
    if (timedOut) throw new ApiError('A resposta demorou mais que o esperado. Tente novamente.', 'TEMPO_ESGOTADO');
    if (error.name === 'AbortError' || error instanceof ApiError) throw error;
    throw new ApiError('Não foi possível conectar ao servidor. Verifique a conexão e tente novamente.', 'CONEXAO');
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', cancel);
  }
}

export function analyzePhoto(file, signal, onProgress) {
  const body = new FormData();
  body.append('foto', file);
  return request('/api/analises', { method: 'POST', body, headers: { Accept: 'application/x-ndjson' } }, signal, onProgress);
}

export function getExample(signal) {
  return request('/api/exemplo', { method: 'GET' }, signal);
}
