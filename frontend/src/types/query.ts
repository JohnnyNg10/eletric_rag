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
  lane_suggestion?: Lane;
  lane_confidence?: number;
  lane_reason?: string;
}

export interface QueryExecutionRequest {
  query: string;
  conversation_id?: string;
  stream?: boolean;
  refined_query?: string | null;
  custom_refinement?: string | null;  // [方案C] 自定义补充
  selected_option_id?: number | null;
  user_lane?: Lane | null;
  clarification_context?: ClarificationContext;
  cache_strategy?: 'exact' | 'semantic';
}

export interface ImageInfo {
  image_id: number;
  url: string;
  caption?: string | null;
  figure_number?: string | null;
  vlm_description?: string | null;
  page_number: number;
}

export interface Citation {
  id: number;
  index?: number;
  standard_no: string | null;
  title: string | null;
  chapter: string | null;
  clause: string | null;
  content_preview: string;
  content_snippet?: string;
  document_title?: string;
  chunk_id: string;
  images?: ImageInfo[];
}

export interface QueryResultMeta {
  status: string;
  lane?: Lane;
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
