export interface DocumentImportResponse {
  task_id: string | null;
  document_id: number | null;
  status: string;
  process_mode: string;
  detected_type: 'text_pdf' | 'scanned_pdf';
  is_scanned: boolean;
  message: string;
}

export interface DocumentStatusResponse {
  id: number;
  title: string;
  process_status: 'pending' | 'processing' | 'completed' | 'failed';
  process_error: string | null;
  page_count: number | null;
  chunk_count: number | null;
  image_count: number | null;
  table_count: number | null;
  created_at: string | null;
  processed_at: string | null;
}

export interface DocumentDeleteResponse {
  document_id: number;
  title: string;
  message: string;
  deleted_counts: {
    chunks: number;
    images: number;
    tables: number;
    qdrant_points: number;
    es_docs: number;
    minio_objects: number;
  };
}

export interface DocumentListItem {
  id: number;
  title: string;
  doc_type: string;
  process_status: string;
  chunk_count: number | null;
  image_count: number | null;
  table_count: number | null;
  page_count: number | null;
  created_at: string | null;
  processed_at: string | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export type ProcessMode = 'auto' | 'text_pdf' | 'scanned_pdf';
