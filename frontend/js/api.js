export class ApiError extends Error {
  constructor(message, code) { super(message); this.code = code; }
}

async function request(url, options, signal) {
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  if (signal?.aborted) controller.abort();
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 45000);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
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

export function analyzePhoto(file, signal) {
  const body = new FormData();
  body.append('foto', file);
  return request('/api/analises', { method: 'POST', body }, signal);
}

export function getExample(signal) {
  return request('/api/exemplo', { method: 'GET' }, signal);
}
