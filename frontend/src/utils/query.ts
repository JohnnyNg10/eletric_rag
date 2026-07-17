import { DIMENSION_LABELS } from './constants';
import type {
  Citation,
  ClarificationContext,
  Lane,
  OptimizationOption,
  PreprocessResponse,
  Strategy,
} from '../types/query';

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

export function normalizePreprocessResponse(raw: any): PreprocessResponse {
  const laneObject =
    raw?.lane_suggestion && typeof raw.lane_suggestion === 'object'
      ? raw.lane_suggestion
      : {
          lane: raw?.lane_suggestion ?? 'fast',
          confidence: raw?.lane_confidence ?? 0.7,
          reason: raw?.lane_reason ?? '',
        };

  return {
    normalized_query: String(raw?.normalized_query ?? raw?.query ?? ''),
    vagueness_score: Number(raw?.vagueness_score ?? 0),
    strategy: String(raw?.strategy ?? 'none') as Strategy,
    missing_dimensions: Array.isArray(raw?.missing_dimensions)
      ? raw.missing_dimensions.map(String)
      : Array.isArray(raw?.missing_dimension_keys)
        ? raw.missing_dimension_keys.map(String)
        : [],
    options: Array.isArray(raw?.options)
      ? raw.options.map((item: any, index: number) => normalizeOption(item, index))
      : [],
    lane_suggestion: {
      lane: String(laneObject?.lane ?? 'fast') as Lane,
      confidence: Number(laneObject?.confidence ?? laneObject?.lane_confidence ?? 0.7),
      reason: String(laneObject?.reason ?? laneObject?.lane_reason ?? ''),
    },
    preprocessing_time:
      typeof raw?.preprocessing_time === 'number' ? raw.preprocessing_time : undefined,
  };
}

export function normalizeCitation(raw: any): Citation {
  return {
    id: Number(raw?.id ?? raw?.index ?? 1),
    standard_no: raw?.standard_no ? String(raw.standard_no) : null,
    title: raw?.title ? String(raw.title) : raw?.document_title ? String(raw.document_title) : null,
    chapter: raw?.chapter ? String(raw.chapter) : null,
    clause: raw?.clause ? String(raw.clause) : null,
    content_preview: String(raw?.content_preview ?? raw?.content_snippet ?? ''),
    chunk_id: String(raw?.chunk_id ?? raw?.id ?? ''),
  };
}

export function shouldAutoSubmit(result: PreprocessResponse) {
  return result.lane_suggestion.confidence > 0.85 && result.vagueness_score < 0.3;
}

export function buildVaguenessWarning(result: PreprocessResponse) {
  if (result.vagueness_score <= 0.8 || result.missing_dimensions.length === 0) {
    return '✓ 问题清晰，可直接查询';
  }

  const labels = result.missing_dimensions.map((item) => DIMENSION_LABELS[item] ?? item);
  return `查询较笼统，可能影响回答质量。建议补充：${labels.join('、')}`;
}

export function buildClarificationContext(result: PreprocessResponse): ClarificationContext {
  return {
    vagueness_score: result.vagueness_score,
    strategy: result.strategy,
    missing_dimensions: result.missing_dimensions,
    options: result.options,
    lane_suggestion: result.lane_suggestion.lane,
    lane_confidence: result.lane_suggestion.confidence,
    lane_reason: result.lane_suggestion.reason,
  };
}

export function getEffectiveLane(suggestedLane: Lane, userLane: Lane | null) {
  return userLane ?? suggestedLane;
}

export function mergeCitation(list: Citation[], citation: Citation) {
  const exists = list.some(
    (item) => item.chunk_id === citation.chunk_id || (item.id === citation.id && item.id !== 0),
  );
  if (exists) {
    return list;
  }
  return [...list, citation];
}
