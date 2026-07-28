import { getStoredApiBaseUrl, getStoredAuth } from '../utils/storage';
import { ApiError, requestJson } from './client';
import type { DocumentImportResponse, DocumentStatusResponse, DocumentDeleteResponse, DocumentBatchDeleteResponse, DocumentListResponse, ProcessMode } from '../types/document';

async function buildApiError(response: Response): Promise<ApiError> {
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

function joinUrl(base: string, path: string) {
  const normalizedBase = base.endsWith('/') ? base.slice(0, -1) : base;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

/**
 * 上传 PDF 文档
 *
 * 使用原生 fetch 而非 requestResponse，避免 client.ts 自动注入 Content-Type: application/json
 * 破坏 multipart/form-data 的 boundary 参数。
 */
export async function importDocument(
  file: File,
  processMode: ProcessMode,
  customStandardNo?: string,
): Promise<DocumentImportResponse> {
  const baseUrl = getStoredApiBaseUrl();
  const token = getStoredAuth()?.accessToken;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('process_mode', processMode);
  if (customStandardNo) {
    formData.append('custom_standard_no', customStandardNo);
  }

  const headers: HeadersInit = { Accept: 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(joinUrl(baseUrl, '/documents/import'), {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    throw await buildApiError(response);
  }

  return response.json() as Promise<DocumentImportResponse>;
}

export async function getDocumentStatus(documentId: number): Promise<DocumentStatusResponse> {
  return requestJson<DocumentStatusResponse>(`/documents/${documentId}/status`);
}

export async function listDocuments(page: number = 1, pageSize: number = 20): Promise<DocumentListResponse> {
  return requestJson<DocumentListResponse>(`/documents/list?page=${page}&page_size=${pageSize}`);
}

export async function deleteDocument(documentId: number): Promise<DocumentDeleteResponse> {
  return requestJson<DocumentDeleteResponse>(`/documents/${documentId}`, {
    method: 'DELETE',
  });
}

export async function batchDeleteDocuments(documentIds: number[]): Promise<DocumentBatchDeleteResponse> {
  return requestJson<DocumentBatchDeleteResponse>('/documents/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export interface OrphanDataScanResult {
  mysql_doc_count: number;
  qdrant: {
    total: number;
    orphans: number[];
    error?: string;
  };
  elasticsearch: {
    total: number;
    orphans: number[];
    error?: string;
  };
}

export interface OrphanDataCleanupResult {
  qdrant: {
    deleted: number;
    failed: number;
  };
  elasticsearch: {
    deleted: number;
    failed: number;
  };
}

export async function scanOrphanData(): Promise<OrphanDataScanResult> {
  return requestJson<OrphanDataScanResult>('/admin/orphan-data/scan');
}

export async function cleanupOrphanData(): Promise<OrphanDataCleanupResult> {
  return requestJson<OrphanDataCleanupResult>('/admin/orphan-data/cleanup', {
    method: 'DELETE',
  });
}
