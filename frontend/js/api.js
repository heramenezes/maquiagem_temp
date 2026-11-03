export class ApiError extends Error {
  constructor(message, code) {
    const explanations = {
      MODELO_INDISPONIVEL: 'A análise facial está indisponível no servidor. Não foi possível identificar seu tom ou recomendar bases. Tente novamente mais tarde; trocar a foto não resolve uma falha do serviço.',
      ERRO_INTERNO: 'O processamento falhou no servidor. Não foi possível concluir seu tom ou suas recomendações. Tente novamente; se persistir, o serviço precisa ser verificado.',
    };
    super(explanations[code] || message);
    this.code = code;
  }
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
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 90000);
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

export async function analyzePhoto(file, signal, onProgress) {
  const body = new FormData();
  body.append('foto', file);
  const result = await request('/api/analises', { method: 'POST', body, headers: { Accept: 'application/x-ndjson' } }, signal, onProgress);
  if (!result.preprocessamento?.previas?.rosto || !result.preprocessamento?.previas?.pele || result.preprocessamento.simulado) {
    throw new ApiError('O servidor não enviou a segmentação da foto. Reinicie o backend atualizado e tente novamente.', 'SEGMENTACAO_AUSENTE');
  }
  if (!result.preprocessamento.selecao?.masks?.anatomical_mask || !result.preprocessamento.selecao?.masks?.valid_mask) {
    throw new ApiError('O servidor não enviou as máscaras da seleção de pele. Reinicie o backend atualizado e tente novamente.', 'SELECAO_AUSENTE');
  }
  const validTone = result.tom && Number.isInteger(result.tom.monk) && result.tom.monk >= 1 && result.tom.monk <= 10
    && /^#[0-9a-f]{6}$/i.test(result.tom.cor_pele_hex) && /^#[0-9a-f]{6}$/i.test(result.tom.hex);
  const status = result.match?.status;
  const validMatch = result.schema_version === 2 && result.simulado === false && result.exemplo === false
    && Array.isArray(result.escala_monk) && result.escala_monk.length === 10 && Array.isArray(result.recomendacoes)
    && ((status === 'inconclusivo' && result.tom === null && result.recomendacoes.length === 0)
      || (validTone && result.preprocessamento.medicao_utilizavel === true
        && ((status === 'sem_candidatos' && result.recomendacoes.length === 0)
          || (status === 'calculado' && result.recomendacoes.length > 0))));
  if (!validMatch) {
    throw new ApiError('O servidor não enviou um resultado válido de tom e bases. Reinicie o backend atualizado e tente novamente.', 'MATCH_AUSENTE');
  }
  return result;
}

export function getExample(signal) {
  return request('/api/exemplo', { method: 'GET' }, signal);
}
