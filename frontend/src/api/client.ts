import { getStoredApiBaseUrl, getStoredAuth, setStoredAuth } from '../utils/storage';

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

// Token 刷新状态管理
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach((callback) => callback(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(callback: (token: string) => void) {
  refreshSubscribers.push(callback);
}

async function attemptTokenRefresh(): Promise<string | null> {
  const storedAuth = getStoredAuth();
  if (!storedAuth?.refreshToken) {
    return null;
  }

  try {
    const response = await fetch(joinUrl(getStoredApiBaseUrl(), '/auth/refresh'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ refresh_token: storedAuth.refreshToken }),
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json() as { access_token: string; expires_in: number };
    const newAccessToken = data.access_token;

    // 更新存储（保留原有 refreshToken 和 user）
    setStoredAuth({
      accessToken: newAccessToken,
      refreshToken: storedAuth.refreshToken,
      user: storedAuth.user,
    });

    return newAccessToken;
  } catch {
    return null;
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
    skipRetry?: boolean;
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

    // 401 未授权：尝试刷新 token 并重试（仅重试一次）
    if (response.status === 401 && !options?.skipRetry && path !== '/auth/refresh' && path !== '/auth/login') {
      cleanup();

      if (isRefreshing) {
        // 已有刷新请求进行中，等待刷新完成后用新 token 重试
        return new Promise<Response>((resolve, reject) => {
          addRefreshSubscriber((newToken: string) => {
            requestResponse(path, init, { ...options, token: newToken, skipRetry: true })
              .then(resolve)
              .catch(reject);
          });
        });
      }

      // 发起刷新
      isRefreshing = true;
      const newToken = await attemptTokenRefresh();
      isRefreshing = false;

      if (newToken) {
        onRefreshed(newToken);
        // 用新 token 重试
        return requestResponse(path, init, { ...options, token: newToken, skipRetry: true });
      } else {
        // 刷新失败，抛出原始 401 错误
        throw await buildApiError(response);
      }
    }

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
    skipRetry?: boolean;
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
