import { useCallback, useEffect, useRef, useState } from 'react';
import { executeQuery, preprocessQuery } from '../api/query';
import { getErrorMessage, isAbortError, isTimeoutError } from '../api/client';
import type { Citation, Lane, PreprocessResponse, QueryResponse, QueryResultMeta, QueryState } from '../types/query';
import {
  buildClarificationContext,
  buildVaguenessWarning,
  mergeCitation,
  normalizePreprocessResponse,
  shouldAutoSubmit,
} from '../utils/query';

interface QueryExecutionSnapshot {
  query: string;
  preprocess: PreprocessResponse;
  refinedQuery: string | null;
  customRefinement: string;  // [方案C]
  selectedOptionId: number | null;
  userLane: Lane | null;
}

function buildMetaFromResponse(response: QueryResponse): QueryResultMeta {
  return {
    status: response.status,
    lane: response.lane ?? undefined,
    retrieval_time: response.retrieval_time ?? null,
    generation_time: response.generation_time ?? null,
    expanded_queries: response.expanded_queries ?? [],
    query_log_id: response.query_log_id ?? null,
  };
}

function buildFallbackPreprocess(snapshot: QueryExecutionSnapshot, response: QueryResponse) {
  return normalizePreprocessResponse({
    normalized_query: snapshot.preprocess.normalized_query || snapshot.query,
    vagueness_score: response.vagueness_score ?? snapshot.preprocess.vagueness_score,
    strategy: response.clarification_options?.length ? 'clarify_required' : snapshot.preprocess.strategy,
    options: response.clarification_options ?? [],
    missing_dimensions: snapshot.preprocess.missing_dimensions,
    lane_suggestion: snapshot.preprocess.lane_suggestion,
    preprocessing_time: snapshot.preprocess.preprocessing_time,
  });
}

export function useQuery({ accessToken }: { accessToken: string }) {
  const [state, setState] = useState<QueryState>('idle');
  const [originalQuery, setOriginalQuery] = useState('');
  const [preprocessResult, setPreprocessResult] = useState<PreprocessResponse | null>(null);
  const [selectedOptionId, setSelectedOptionId] = useState<number | null>(null);
  const [refinedQuery, setRefinedQuery] = useState<string | null>(null);
  const [customRefinement, setCustomRefinement] = useState<string>('');  // [方案C]
  const [userLane, setUserLane] = useState<Lane | null>(null);
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<'preprocess' | 'query' | null>(null);
  const [timeoutNotice, setTimeoutNotice] = useState<string | null>(null);
  const [resultMeta, setResultMeta] = useState<QueryResultMeta | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const preprocessCacheRef = useRef(new Map<string, PreprocessResponse>());
  const lastExecutionRef = useRef<QueryExecutionSnapshot | null>(null);
  const streamBufferRef = useRef('');
  const flushTimerRef = useRef<number | null>(null);

  const clearBufferedAnswer = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    streamBufferRef.current = '';
  }, []);

  const flushBufferedAnswer = useCallback(() => {
    if (!streamBufferRef.current) return;
    const nextChunk = streamBufferRef.current;
    streamBufferRef.current = '';
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setAnswer((previous) => previous + nextChunk);
  }, []);

  const appendDelta = useCallback((delta: string) => {
    if (!delta) return;
    streamBufferRef.current += delta;
    if (flushTimerRef.current !== null) return;

    flushTimerRef.current = window.setTimeout(() => {
      const nextChunk = streamBufferRef.current;
      streamBufferRef.current = '';
      flushTimerRef.current = null;
      if (nextChunk) {
        setAnswer((previous) => previous + nextChunk);
      }
    }, 50);
  }, []);

  const cancelActiveRequest = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    clearBufferedAnswer();
  }, [clearBufferedAnswer]);

  const clearOutputState = useCallback(() => {
    setAnswer('');
    setCitations([]);
    setTimeoutNotice(null);
    setError(null);
    setErrorSource(null);
    setResultMeta(null);
    clearBufferedAnswer();
  }, [clearBufferedAnswer]);

  const executeConfirmedQuery = useCallback(
    async (snapshot: QueryExecutionSnapshot) => {
      if (!accessToken) {
        setError('请先登录或设置 access token');
        setErrorSource('query');
        setState('error');
        return;
      }

      cancelActiveRequest();
      clearOutputState();
      setState('querying');
      lastExecutionRef.current = snapshot;

      const controller = new AbortController();
      abortControllerRef.current = controller;

      const slowQueryTimer = window.setTimeout(() => {
        setTimeoutNotice('查询耗时较长，建议尝试切换检索方式后重新提交。');
      }, 150000);

      try {
        const response = await executeQuery(
          {
            query: snapshot.query,
            stream: true,
            refined_query: snapshot.refinedQuery,
            custom_refinement: snapshot.customRefinement || null,  // [方案C]
            selected_option_id: snapshot.selectedOptionId,
            user_lane: snapshot.userLane,
            clarification_context: buildClarificationContext(snapshot.preprocess),
          },
          {
            token: accessToken,
            signal: controller.signal,
            onDelta: appendDelta,
            onCitation: (citation) => {
              setCitations((previous) => mergeCitation(previous, citation));
            },
            onDone: () => {
              flushBufferedAnswer();
            },
            onMeta: (meta) => {
              setResultMeta((previous) => ({
                status: previous?.status ?? 'success',
                ...previous,
                ...meta,
              }));
            },
          },
        );

        flushBufferedAnswer();

        if (response?.status === 'need_clarification') {
          const fallbackPreprocess = buildFallbackPreprocess(snapshot, response);
          setPreprocessResult(fallbackPreprocess);
          setSelectedOptionId(null);
          setRefinedQuery(null);
          setUserLane(null);
          setWarning(buildVaguenessWarning(fallbackPreprocess));
          setError(null);
          setErrorSource(null);
          setState('confirming');
          return;
        }

        if (response) {
          setResultMeta(buildMetaFromResponse(response));
        }

        setState('completed');
      } catch (queryError) {
        if (isAbortError(queryError)) {
          return;
        }
        flushBufferedAnswer();
        setError(getErrorMessage(queryError, '查询失败，请稍后重试'));
        setErrorSource('query');
        setState('error');
      } finally {
        window.clearTimeout(slowQueryTimer);
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [accessToken, appendDelta, cancelActiveRequest, clearOutputState, flushBufferedAnswer],
  );

  const handlePreprocessReady = useCallback(
    async (query: string, result: PreprocessResponse) => {
      setPreprocessResult(result);
      setSelectedOptionId(null);
      setRefinedQuery(null);
      setUserLane(null);
      setWarning(buildVaguenessWarning(result));
      setError(null);
      setErrorSource(null);

      if (shouldAutoSubmit(result)) {
        await executeConfirmedQuery({
          query,
          preprocess: result,
          refinedQuery: null,
          customRefinement: '',  // [方案C]
          selectedOptionId: null,
          userLane: null,
        });
        return;
      }

      setState('confirming');
    },
    [executeConfirmedQuery],
  );

  const requestPreprocess = useCallback(
    async (query: string, signal: AbortSignal) => {
      try {
        return await preprocessQuery(query, accessToken, signal);
      } catch (requestError) {
        if (isTimeoutError(requestError)) {
          return preprocessQuery(query, accessToken, signal);
        }
        throw requestError;
      }
    },
    [accessToken],
  );

  const submitQuery = useCallback(
    async (query: string) => {
      const nextQuery = query.trim();
      if (!nextQuery) {
        setError('请输入查询内容');
        setErrorSource('preprocess');
        setState('error');
        return;
      }
      if (!accessToken) {
        setError('请先登录或设置 access token');
        setErrorSource('preprocess');
        setState('error');
        return;
      }

      cancelActiveRequest();
      clearOutputState();
      setOriginalQuery(nextQuery);
      setWarning(null);
      setPreprocessResult(null);
      setSelectedOptionId(null);
      setRefinedQuery(null);
      setCustomRefinement('');  // [方案C]
      setUserLane(null);
      setState('preprocessing');

      const cacheKey = nextQuery.toLowerCase();
      const cached = preprocessCacheRef.current.get(cacheKey);
      if (cached) {
        await handlePreprocessReady(nextQuery, cached);
        return;
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const result = await requestPreprocess(nextQuery, controller.signal);
        preprocessCacheRef.current.set(cacheKey, result);
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
        await handlePreprocessReady(nextQuery, result);
      } catch (preprocessError) {
        if (isAbortError(preprocessError)) {
          return;
        }
        setError(getErrorMessage(preprocessError, '预处理失败，请稍后重试'));
        setErrorSource('preprocess');
        setState('error');
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [accessToken, cancelActiveRequest, clearOutputState, handlePreprocessReady, requestPreprocess],
  );

  const confirmAndExecute = useCallback(async () => {
    if (!preprocessResult) return;

    const requiresSelection =
      preprocessResult.strategy === 'clarify_required' && preprocessResult.options.length > 0;

    const hasCustomInput = customRefinement.trim().length > 0;

    if (requiresSelection && selectedOptionId === null && refinedQuery === null && !hasCustomInput) {
      setError('请选择一个具体场景或输入自定义内容后再提交查询');
      setErrorSource('preprocess');
      setState('confirming');
      return;
    }

    await executeConfirmedQuery({
      query: originalQuery,
      preprocess: preprocessResult,
      refinedQuery,
      customRefinement,  // [方案C]
      selectedOptionId,
      userLane,
    });
  }, [executeConfirmedQuery, originalQuery, preprocessResult, refinedQuery, customRefinement, selectedOptionId, userLane]);

  const retryLastExecution = useCallback(async () => {
    if (lastExecutionRef.current) {
      await executeConfirmedQuery(lastExecutionRef.current);
      return;
    }
    if (originalQuery) {
      await submitQuery(originalQuery);
    }
  }, [executeConfirmedQuery, originalQuery, submitQuery]);

  const toggleLane = useCallback(() => {
    const suggestedLane = preprocessResult?.lane_suggestion.lane;
    if (!suggestedLane) return;
    setUserLane((previous) => {
      if (previous === null) {
        return suggestedLane === 'fast' ? 'slow' : 'fast';
      }
      return null;
    });
  }, [preprocessResult]);

  const selectOption = useCallback((optionId: number | null, nextRefinedQuery: string | null) => {
    setSelectedOptionId(optionId);
    setRefinedQuery(nextRefinedQuery);
    if (optionId !== null) {
      // [方案C] 选择系统选项时，清空自定义输入
      setCustomRefinement('');
    }
    setError(null);
    setErrorSource(null);
    if (state === 'error' && preprocessResult) {
      setState('confirming');
    }
  }, [preprocessResult, state]);

  // [方案C] 自定义输入回调
  const handleCustomInput = useCallback((input: string) => {
    setCustomRefinement(input);
    if (input.trim()) {
      // 有自定义输入时，清空系统选项
      setSelectedOptionId(null);
      setRefinedQuery(null);
    }
  }, []);

  const cancelConfirmation = useCallback(() => {
    cancelActiveRequest();
    setState('idle');
    setPreprocessResult(null);
    setWarning(null);
    setError(null);
    setErrorSource(null);
    setSelectedOptionId(null);
    setRefinedQuery(null);
    setUserLane(null);
  }, [cancelActiveRequest]);

  const resetConversation = useCallback(() => {
    cancelActiveRequest();
    clearOutputState();
    setState('idle');
    setOriginalQuery('');
    setPreprocessResult(null);
    setSelectedOptionId(null);
    setRefinedQuery(null);
    setCustomRefinement('');  // [方案C]
    setUserLane(null);
    setWarning(null);
    lastExecutionRef.current = null;
  }, [cancelActiveRequest, clearOutputState]);

  useEffect(() => {
    return () => {
      cancelActiveRequest();
    };
  }, [cancelActiveRequest]);

  return {
    state,
    originalQuery,
    preprocessResult,
    selectedOptionId,
    refinedQuery,
    customRefinement,  // [方案C]
    userLane,
    answer,
    citations,
    warning,
    error,
    errorSource,
    timeoutNotice,
    resultMeta,
    isBusy: state === 'preprocessing' || state === 'querying',
    submitQuery,
    confirmAndExecute,
    retryLastExecution,
    toggleLane,
    selectOption,
    handleCustomInput,  // [方案C]
    cancelConfirmation,
    resetConversation,
  };
}
