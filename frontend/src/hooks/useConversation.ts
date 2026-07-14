import { useCallback, useEffect, useRef, useState } from 'react';
import { executeQuery, getConversationHistory, preprocessQuery } from '../api/query';
import { getErrorMessage, isAbortError, isTimeoutError } from '../api/client';
import type { Citation, Lane, PreprocessResponse, QueryResultMeta } from '../types/query';
import {
  buildClarificationContext,
  buildVaguenessWarning,
  mergeCitation,
  normalizePreprocessResponse,
  shouldAutoSubmit,
} from '../utils/query';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  metadata?: {
    lane?: Lane;
    retrieval_time?: number | null;
    generation_time?: number | null;
    expanded_queries?: string[];
    query_log_id?: number | null;
  };
  status: 'streaming' | 'completed' | 'error';
  timestamp: Date;
}

type ConversationState = 'idle' | 'preprocessing' | 'confirming' | 'querying' | 'completed' | 'error';

interface QueryExecutionSnapshot {
  query: string;
  preprocess: PreprocessResponse;
  refinedQuery: string | null;
  selectedOptionId: number | null;
  userLane: Lane | null;
}

function buildFallbackPreprocess(snapshot: QueryExecutionSnapshot, response: any) {
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

export function useConversation({ accessToken }: { accessToken: string }) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [state, setState] = useState<ConversationState>('idle');
  const [originalQuery, setOriginalQuery] = useState('');
  const [preprocessResult, setPreprocessResult] = useState<PreprocessResponse | null>(null);
  const [selectedOptionId, setSelectedOptionId] = useState<number | null>(null);
  const [refinedQuery, setRefinedQuery] = useState<string | null>(null);
  const [userLane, setUserLane] = useState<Lane | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorSource, setErrorSource] = useState<'preprocess' | 'query' | null>(null);
  const [timeoutNotice, setTimeoutNotice] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

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
    setMessages((prev) => {
      const updated = [...prev];
      const lastMsg = updated[updated.length - 1];
      if (lastMsg && lastMsg.role === 'assistant' && lastMsg.status === 'streaming') {
        lastMsg.content += nextChunk;
      }
      return updated;
    });
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
        setMessages((prev) => {
          const updated = [...prev];
          const lastMsg = updated[updated.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.status === 'streaming') {
            lastMsg.content += nextChunk;
          }
          return updated;
        });
      }
    }, 50);
  }, []);

  const cancelActiveRequest = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    clearBufferedAnswer();
  }, [clearBufferedAnswer]);

  const loadConversation = useCallback(
    async (id: string) => {
      if (!accessToken) return;

      setIsLoadingHistory(true);
      setConversationId(id);
      setMessages([]);
      setState('idle');
      setError(null);
      setWarning(null);
      setPreprocessResult(null);

      try {
        const history = await getConversationHistory(accessToken, id);
        const loadedMessages: Message[] = [];

        history.forEach((item) => {
          loadedMessages.push({
            id: `${item.query_log_id}-q`,
            role: 'user',
            content: item.query,
            status: 'completed',
            timestamp: new Date(item.created_at),
          });

          if (item.answer) {
            loadedMessages.push({
              id: `${item.query_log_id}-a`,
              role: 'assistant',
              content: item.answer,
              citations: item.citations,
              metadata: {
                lane: item.lane,
                query_log_id: item.query_log_id,
              },
              status: 'completed',
              timestamp: new Date(item.created_at),
            });
          }
        });

        setMessages(loadedMessages);
      } catch (err) {
        setError(getErrorMessage(err, '加载会话历史失败'));
      } finally {
        setIsLoadingHistory(false);
      }
    },
    [accessToken],
  );

  const startNewConversation = useCallback(() => {
    cancelActiveRequest();
    setConversationId(null);
    setMessages([]);
    setState('idle');
    setOriginalQuery('');
    setPreprocessResult(null);
    setSelectedOptionId(null);
    setRefinedQuery(null);
    setUserLane(null);
    setWarning(null);
    setError(null);
    setErrorSource(null);
    setTimeoutNotice(null);
    lastExecutionRef.current = null;
  }, [cancelActiveRequest]);

  const executeConfirmedQuery = useCallback(
    async (snapshot: QueryExecutionSnapshot) => {
      if (!accessToken) {
        setError('请先登录或设置 access token');
        setErrorSource('query');
        setState('error');
        return;
      }

      cancelActiveRequest();
      setState('querying');
      lastExecutionRef.current = snapshot;

      const userMsg: Message = {
        id: `temp-${Date.now()}-q`,
        role: 'user',
        content: snapshot.refinedQuery || snapshot.query,
        status: 'completed',
        timestamp: new Date(),
      };

      const assistantMsg: Message = {
        id: `temp-${Date.now()}-a`,
        role: 'assistant',
        content: '',
        citations: [],
        status: 'streaming',
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      const slowQueryTimer = window.setTimeout(() => {
        setTimeoutNotice('查询耗时较长，建议尝试切换车道后重新提交。');
      }, 150000);

      try {
        if (!conversationId) {
          const newId = crypto.randomUUID();
          setConversationId(newId);
        }

        const response = await executeQuery(
          {
            query: snapshot.query,
            conversation_id: conversationId || undefined,
            stream: true,
            refined_query: snapshot.refinedQuery,
            selected_option_id: snapshot.selectedOptionId,
            user_lane: snapshot.userLane,
            clarification_context: buildClarificationContext(snapshot.preprocess),
          },
          {
            token: accessToken,
            signal: controller.signal,
            onDelta: appendDelta,
            onCitation: (citation) => {
              setMessages((prev) => {
                const updated = [...prev];
                const lastMsg = updated[updated.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.citations = mergeCitation(lastMsg.citations || [], citation);
                }
                return updated;
              });
            },
            onDone: () => {
              flushBufferedAnswer();
              setMessages((prev) => {
                const updated = [...prev];
                const lastMsg = updated[updated.length - 1];
                if (lastMsg && lastMsg.role === 'assistant' && lastMsg.status === 'streaming') {
                  lastMsg.status = 'completed';
                }
                return updated;
              });
            },
            onMeta: (meta) => {
              setMessages((prev) => {
                const updated = [...prev];
                const lastMsg = updated[updated.length - 1];
                if (lastMsg && lastMsg.role === 'assistant') {
                  lastMsg.metadata = {
                    ...lastMsg.metadata,
                    ...meta,
                  };
                }
                return updated;
              });
            },
          },
        );

        flushBufferedAnswer();

        if (response?.status === 'need_clarification') {
          setMessages((prev) => prev.slice(0, -1));
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

        setState('completed');
      } catch (queryError) {
        if (isAbortError(queryError)) {
          return;
        }
        flushBufferedAnswer();
        setMessages((prev) => {
          const updated = [...prev];
          const lastMsg = updated[updated.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.status = 'error';
            lastMsg.content = getErrorMessage(queryError, '查询失败，请稍后重试');
          }
          return updated;
        });
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
    [accessToken, appendDelta, cancelActiveRequest, conversationId, flushBufferedAnswer],
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

  const sendQuery = useCallback(
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
      setOriginalQuery(nextQuery);
      setWarning(null);
      setPreprocessResult(null);
      setSelectedOptionId(null);
      setRefinedQuery(null);
      setUserLane(null);
      setError(null);
      setErrorSource(null);
      setTimeoutNotice(null);
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
    [accessToken, cancelActiveRequest, handlePreprocessReady, requestPreprocess],
  );

  const confirmAndExecute = useCallback(async () => {
    if (!preprocessResult) return;

    const requiresSelection =
      preprocessResult.strategy === 'clarify_required' && preprocessResult.options.length > 0;

    if (requiresSelection && selectedOptionId === null && refinedQuery === null) {
      setError('请选择一个具体场景后再提交查询');
      setErrorSource('preprocess');
      setState('confirming');
      return;
    }

    await executeConfirmedQuery({
      query: originalQuery,
      preprocess: preprocessResult,
      refinedQuery,
      selectedOptionId,
      userLane,
    });
  }, [executeConfirmedQuery, originalQuery, preprocessResult, refinedQuery, selectedOptionId, userLane]);

  const retryLastExecution = useCallback(async () => {
    if (lastExecutionRef.current) {
      await executeConfirmedQuery(lastExecutionRef.current);
      return;
    }
    if (originalQuery) {
      await sendQuery(originalQuery);
    }
  }, [executeConfirmedQuery, originalQuery, sendQuery]);

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
    setError(null);
    setErrorSource(null);
    if (state === 'error' && preprocessResult) {
      setState('confirming');
    }
  }, [preprocessResult, state]);

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

  useEffect(() => {
    return () => {
      cancelActiveRequest();
    };
  }, [cancelActiveRequest]);

  return {
    conversationId,
    messages,
    state,
    originalQuery,
    preprocessResult,
    selectedOptionId,
    refinedQuery,
    userLane,
    warning,
    error,
    errorSource,
    timeoutNotice,
    isLoadingHistory,
    isBusy: state === 'preprocessing' || state === 'querying',
    sendQuery,
    confirmAndExecute,
    retryLastExecution,
    toggleLane,
    selectOption,
    cancelConfirmation,
    loadConversation,
    startNewConversation,
  };
}
