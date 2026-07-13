import { requestJson, requestResponse } from './client';
import type {
  Citation,
  OptimizationOption,
  PreprocessResponse,
  QueryExecutionRequest,
  QueryFeedbackRequest,
  QueryFeedbackResponse,
  QueryHistoryItem,
  QueryHistoryResponse,
  QueryResponse,
  QueryResultMeta,
} from '../types/query';
import { normalizeCitation, normalizePreprocessResponse } from '../utils/query';

interface StreamHandlers {
  token: string;
  signal?: AbortSignal;
  onDelta: (delta: string) => void;
  onCitation: (citation: Citation) => void;
  onDone: () => void;
  onMeta?: (meta: Partial<QueryResultMeta>) => void;
}

function toOptionalNumber(value: unknown) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }

  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  return undefined;
}

function normalizeOption(raw: any, index: number): OptimizationOption {
  return {
    id: Number(raw?.id ?? index + 1),
    label: String(raw?.label ?? ''),
    refined_query: String(raw?.refined_query ?? raw?.label ?? ''),
    standard_preview: raw?.standard_preview ? String(raw.standard_preview) : null,
    doc_count:
      typeof raw?.doc_count === 'number'
        ? raw.doc_count
        : raw?.doc_count != null
          ? Number(raw.doc_count)
          : null,
    kb_verified: Boolean(raw?.kb_verified),
  };
}

function normalizeQueryResponse(raw: any): QueryResponse {
  return {
    status: String(raw?.status ?? 'success'),
    answer: typeof raw?.answer === 'string' ? raw.answer : null,
    citations: Array.isArray(raw?.citations) ? raw.citations.map((item: any) => normalizeCitation(item)) : [],
    lane: raw?.lane === 'slow' ? 'slow' : raw?.lane === 'fast' ? 'fast' : undefined,
    retrieval_time: toOptionalNumber(raw?.retrieval_time) ?? null,
    generation_time: toOptionalNumber(raw?.generation_time) ?? null,
    expanded_queries: Array.isArray(raw?.expanded_queries) ? raw.expanded_queries.map(String) : [],
    query_log_id: toOptionalNumber(raw?.query_log_id) ?? null,
    vagueness_score: toOptionalNumber(raw?.vagueness_score) ?? null,
    clarification_options: Array.isArray(raw?.clarification_options)
      ? raw.clarification_options.map((item: any, index: number) => normalizeOption(item, index))
      : null,
  };
}

function emitMeta(payload: any, handlers: Pick<StreamHandlers, 'onMeta'>) {
  if (!handlers.onMeta || !payload) return;

  const nextMeta: Partial<QueryResultMeta> = {};

  if (typeof payload.status === 'string') {
    nextMeta.status = payload.status;
  }
  if (payload.lane === 'fast' || payload.lane === 'slow') {
    nextMeta.lane = payload.lane;
  }

  const retrievalTime = toOptionalNumber(payload.retrieval_time);
  const generationTime = toOptionalNumber(payload.generation_time);
  const queryLogId = toOptionalNumber(payload.query_log_id);

  if (retrievalTime !== undefined) {
    nextMeta.retrieval_time = retrievalTime;
  }
  if (generationTime !== undefined) {
    nextMeta.generation_time = generationTime;
  }
  if (queryLogId !== undefined) {
    nextMeta.query_log_id = queryLogId;
  }
  if (Array.isArray(payload.expanded_queries)) {
    nextMeta.expanded_queries = payload.expanded_queries.map(String);
  }

  if (Object.keys(nextMeta).length > 0) {
    handlers.onMeta(nextMeta);
  }
}

function emitFromPayload(
  payload: any,
  handlers: Pick<StreamHandlers, 'onDelta' | 'onCitation' | 'onDone' | 'onMeta'>,
) {
  if (!payload) return;

  emitMeta(payload, handlers);

  if (typeof payload.delta === 'string') {
    handlers.onDelta(payload.delta);
  }

  if (typeof payload.answer === 'string') {
    handlers.onDelta(payload.answer);
  }

  if (Array.isArray(payload.citations)) {
    payload.citations.forEach((item: any) => handlers.onCitation(normalizeCitation(item)));
  }

  if (payload.citation) {
    handlers.onCitation(normalizeCitation(payload.citation));
  }

  if (payload.chunk_id || payload.standard_no || payload.document_title || payload.content_snippet) {
    handlers.onCitation(normalizeCitation(payload));
  }

  if (payload.done === true) {
    handlers.onDone();
  }
}

function parseEventBlock(
  rawBlock: string,
  handlers: Pick<StreamHandlers, 'onDelta' | 'onCitation' | 'onDone' | 'onMeta'>,
) {
  const lines = rawBlock.split(/\r?\n/).filter(Boolean);
  if (lines.length === 0) return;

  let eventName = 'message';
  const dataLines: string[] = [];

  lines.forEach((line) => {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
      return;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  });

  if (dataLines.length === 0) return;

  const payloadText = dataLines.join('\n');
  let payload: any = null;

  try {
    payload = JSON.parse(payloadText);
  } catch {
    payload = { delta: payloadText };
  }

  if (eventName === 'citation') {
    emitMeta(payload, handlers);
    handlers.onCitation(normalizeCitation(payload?.citation ?? payload));
    return;
  }

  if (eventName === 'done') {
    emitMeta(payload, handlers);
    handlers.onDone();
    return;
  }

  emitFromPayload(payload, handlers);
}

export async function preprocessQuery(query: string, token: string, signal?: AbortSignal) {
  const raw = await requestJson<any>(
    '/query/preprocess',
    {
      method: 'POST',
      body: JSON.stringify({ query }),
      signal,
    },
    {
      token,
      timeoutMs: 100000,
    },
  );

  return normalizePreprocessResponse(raw) as PreprocessResponse;
}

export async function executeQuery(request: QueryExecutionRequest, handlers: StreamHandlers) {
  const response = await requestResponse(
    '/query',
    {
      method: 'POST',
      body: JSON.stringify(request),
      signal: handlers.signal,
    },
    {
      token: handlers.token,
    },
  );

  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    const json = normalizeQueryResponse(await response.json());

    if (json.status === 'need_clarification') {
      return json;
    }

    emitFromPayload(json, handlers);
    handlers.onDone();
    return json;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    handlers.onDone();
    return null;
  }

  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    handlers.onDone();
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.search(/\r?\n\r?\n/);
    while (separatorIndex !== -1) {
      const rawBlock = buffer.slice(0, separatorIndex);
      const separatorLength = buffer[separatorIndex] === '\r' ? 4 : 2;
      buffer = buffer.slice(separatorIndex + separatorLength);
      parseEventBlock(rawBlock, {
        onDelta: handlers.onDelta,
        onCitation: handlers.onCitation,
        onDone: finish,
        onMeta: handlers.onMeta,
      });
      separatorIndex = buffer.search(/\r?\n\r?\n/);
    }
  }

  if (buffer.trim()) {
    parseEventBlock(buffer, {
      onDelta: handlers.onDelta,
      onCitation: handlers.onCitation,
      onDone: finish,
      onMeta: handlers.onMeta,
    });
  }

  finish();
  return null;
}

export async function fetchQueryHistory(token: string, page = 1, pageSize = 10) {
  const raw = await requestJson<any>(`/query/history?page=${page}&page_size=${pageSize}`, { method: 'GET' }, { token, timeoutMs: 100000 });

  const items: QueryHistoryItem[] = Array.isArray(raw?.items)
    ? raw.items.map((item: any) => ({
        query_log_id: Number(item?.query_log_id ?? item?.id ?? 0),
        query: String(item?.query ?? ''),
        answer: typeof item?.answer === 'string' ? item.answer : null,
        lane: item?.lane === 'slow' ? 'slow' : 'fast',
        total_time: toOptionalNumber(item?.total_time) ?? null,
        feedback_score: toOptionalNumber(item?.feedback_score) ?? null,
        created_at: String(item?.created_at ?? ''),
      }))
    : [];

  return {
    items,
    total: Number(raw?.total ?? items.length ?? 0),
    page: Number(raw?.page ?? page),
    page_size: Number(raw?.page_size ?? pageSize),
    has_more: Boolean(raw?.has_more),
  } as QueryHistoryResponse;
}

export async function submitQueryFeedback(
  queryLogId: number,
  data: QueryFeedbackRequest,
  token: string,
) {
  const raw = await requestJson<any>(
    `/query/${queryLogId}/feedback`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    },
    {
      token,
      timeoutMs: 100000,
    },
  );

  return {
    query_log_id: Number(raw?.query_log_id ?? queryLogId),
    feedback_score: Number(raw?.feedback_score ?? data.feedback_score),
    message: String(raw?.message ?? '反馈已记录'),
  } as QueryFeedbackResponse;
}
