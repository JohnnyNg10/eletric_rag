export type QueryState =
  | 'idle'
  | 'preprocessing'
  | 'confirming'
  | 'querying'
  | 'completed'
  | 'error';

export type Lane = 'fast' | 'slow';

export type Strategy = 'none' | 'suggest' | 'clarify_optional' | 'clarify_required';

export interface OptimizationOption {
  id: number;
  label: string;
  refined_query: string;
  standard_preview: string | null;
  doc_count: number | null;
  kb_verified: boolean;
}

export interface LaneSuggestion {
  lane: Lane;
  confidence: number;
  reason: string;
}

export interface PreprocessResponse {
  normalized_query: string;
  vagueness_score: number;
  strategy: Strategy;
  missing_dimensions: string[];
  options: OptimizationOption[];
  lane_suggestion: LaneSuggestion;
  preprocessing_time?: number;
}

export interface ClarificationContext {
  vagueness_score: number;
  strategy: Strategy;
  missing_dimensions: string[];
  options: OptimizationOption[];
}

export interface QueryExecutionRequest {
  query: string;
  stream?: boolean;
  refined_query?: string | null;
  selected_option_id?: number | null;
  user_lane?: Lane | null;
  clarification_context?: ClarificationContext;
}

export interface Citation {
  id: number;
  standard_no: string | null;
  title: string | null;
  chapter: string | null;
  clause: string | null;
  content_preview: string;
  chunk_id: string;
}

export interface QueryResultMeta {
  status: string;
  lane?: Lane | null;
  retrieval_time?: number | null;
  generation_time?: number | null;
  expanded_queries?: string[];
  query_log_id?: number | null;
}

export interface QueryResponse extends QueryResultMeta {
  answer?: string | null;
  citations?: Citation[];
  vagueness_score?: number | null;
  clarification_options?: OptimizationOption[] | null;
}

export interface QueryHistoryItem {
  query_log_id: number;
  query: string;
  answer?: string | null;
  lane: Lane;
  total_time?: number | null;
  feedback_score?: number | null;
  created_at: string;
}

export interface QueryHistoryResponse {
  items: QueryHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface QueryFeedbackRequest {
  feedback_score: number;
  feedback_text?: string | null;
}

export interface QueryFeedbackResponse {
  query_log_id: number;
  feedback_score: number;
  message: string;
}
