import { getStoredApiBaseUrl, getStoredAuth } from '../utils/storage';

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function joinUrl(base: string, path: string) {
  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function createScopedSignal(parentSignal?: AbortSignal | null, timeoutMs?: number) {

  const controller = new AbortController();

  const abortFromParent = () => {
    controller.abort(parentSignal?.reason ?? new DOMException('请求已取消', 'AbortError'));
  };

  if (parentSignal) {
    if (parentSignal.aborted) {
      abortFromParent();
    } else {
      parentSignal.addEventListener('abort', abortFromParent, { once: true });
    }
  }

  const timeoutId =
    typeof timeoutMs === 'number' && timeoutMs > 0
      ? window.setTimeout(() => {
          controller.abort(new DOMException('请求超时', 'TimeoutError'));
        }, timeoutMs)
      : null;

  return {
    signal: controller.signal,
    cleanup: () => {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      parentSignal?.removeEventListener('abort', abortFromParent);
    },
  };
}

async function buildApiError(response: Response) {
  const contentType = response.headers.get('content-type') || '';
  let detail: unknown = null;

  try {
    detail = contentType.includes('application/json') ? await response.json() : await response.text();
  } catch {
    detail = null;
  }

  const message =
    typeof detail === 'string'
      ? detail
      : (detail as { detail?: string; message?: string } | null)?.detail ||
        (detail as { detail?: string; message?: string } | null)?.message ||
        `请求失败（${response.status}）`;

  return new ApiError(response.status, message, detail);
}

export async function requestResponse(
  path: string,
  init: RequestInit = {},
  options?: {
    token?: string;
    timeoutMs?: number;
  },
) {
  const baseUrl = getStoredApiBaseUrl();
  const storedAuth = getStoredAuth();
  const accessToken = options?.token ?? storedAuth?.accessToken;
  const headers = new Headers(init.headers);

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json, text/event-stream');
  }
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const { signal, cleanup } = createScopedSignal(init.signal, options?.timeoutMs);

  try {
    const response = await fetch(joinUrl(baseUrl, path), {
      ...init,
      headers,
      signal,
    });

    if (!response.ok) {
      throw await buildApiError(response);
    }

    return response;
  } finally {
    cleanup();
  }
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options?: {
    token?: string;
    timeoutMs?: number;
  },
) {
  const response = await requestResponse(path, init, options);
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }

  return (await response.text()) as T;
}

export function isAbortError(error: unknown): error is DOMException {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function isTimeoutError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'TimeoutError';
}

export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试') {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof DOMException && error.name === 'TimeoutError') {
    return '请求超时，请稍后重试';
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
