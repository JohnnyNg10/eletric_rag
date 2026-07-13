import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PreprocessConfirmPanel from '../components/query/PreprocessConfirmPanel';
import AnswerDisplay from '../components/result/AnswerDisplay';
import QueryInput from '../components/search/QueryInput';
import { useAuthContext } from '../context/AuthContext';
import { useQuery } from '../hooks/useQuery';
import type { Citation } from '../types/query';
import { LANE_META } from '../utils/constants';

export function SearchPage() {
  const auth = useAuthContext();
  const query = useQuery({ accessToken: auth.accessToken });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [draftQuery, setDraftQuery] = useState(searchParams.get('q')?.trim() ?? '');
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (query.state === 'confirming') {
      return;
    }
    if (query.citations.length === 0) {
      setSelectedCitation(null);
    }
  }, [query.citations, query.state]);

  useEffect(() => {
    const nextQuery = searchParams.get('q')?.trim() ?? '';
    if (nextQuery && nextQuery !== draftQuery) {
      setDraftQuery(nextQuery);
      inputRef.current?.focus();
    }
  }, [draftQuery, searchParams]);

  const handleSubmit = async () => {
    setSelectedCitation(null);
    await query.submitQuery(draftQuery);
  };

  const helperText = auth.accessToken
    ? 'Enter 提交查询，Shift + Enter 换行。'
    : '请先在右上角登录，或粘贴 access token 后再查询。';

  const laneMeta = query.resultMeta?.lane ? LANE_META[query.resultMeta.lane] : null;
  const hasQueryResult = query.state === 'completed' || query.state === 'error' || query.state === 'querying';
  const resultStats = useMemo(
    () => [
      {
        label: '实际车道',
        value: laneMeta ? `${laneMeta.icon} ${laneMeta.label}` : '待返回',
      },
      {
        label: '检索耗时',
        value:
          typeof query.resultMeta?.retrieval_time === 'number'
            ? `${query.resultMeta.retrieval_time}ms`
            : '待返回',
      },
      {
        label: '生成耗时',
        value:
          typeof query.resultMeta?.generation_time === 'number'
            ? `${query.resultMeta.generation_time}ms`
            : '待返回',
      },
      {
        label: '查询记录 ID',
        value: query.resultMeta?.query_log_id ? `#${query.resultMeta.query_log_id}` : '未写入',
      },
    ],
    [laneMeta, query.resultMeta],
  );

  return (
    <section className="hero-panel">
      <div className="hero-copy">
        <span className="hero-badge">实际联调模式</span>
        <h1 className="hero-title">电力标准知识库阶段 B 查询台</h1>
        <p className="hero-subtitle">
          当前页面已对接真实后端认证、预处理、执行查询与历史接口，并补齐登录页、查询页、历史页之间的页面跳转。
        </p>
      </div>

      <div className="feature-grid">
        <div className="feature-card">
          <h3>真实预处理</h3>
          <p>直接调用 `POST /api/v1/query/preprocess`，兼容 `missing_dimension_keys` 与路由建议字段。</p>
        </div>
        <div className="feature-card">
          <h3>真实查询结果</h3>
          <p>直接调用 `POST /api/v1/query`，兼容当前 JSON 返回，并保留后续 SSE 流式扩展能力。</p>
        </div>
        <div className="feature-card">
          <h3>页面联动</h3>
          <p>查询完成后可跳转到历史页，历史记录也能带着原问题回填到查询输入框。</p>
        </div>
      </div>

      <QueryInput
        ref={inputRef}
        query={draftQuery}
        disabled={!auth.accessToken || auth.isLoading || auth.isLoggingIn || query.isBusy}
        loading={query.state === 'preprocessing'}
        warning={query.warning}
        error={query.errorSource === 'preprocess' ? query.error : null}
        helperText={helperText}
        onChange={setDraftQuery}
        onSubmit={handleSubmit}
      />

      {query.preprocessResult && query.state === 'confirming' ? (
        <PreprocessConfirmPanel
          preprocessResult={query.preprocessResult}
          originalQuery={query.originalQuery}
          selectedOptionId={query.selectedOptionId}
          userLane={query.userLane}
          validationMessage={query.errorSource === 'preprocess' ? query.error : null}
          onToggleLane={query.toggleLane}
          onSelectOption={query.selectOption}
          onConfirm={query.confirmAndExecute}
          onCancel={() => {
            query.cancelConfirmation();
            inputRef.current?.focus();
          }}
        />
      ) : null}

      <AnswerDisplay
        answer={query.answer}
        isStreaming={query.state === 'querying'}
        citations={query.citations}
        error={query.errorSource === 'query' ? query.error : null}
        timeoutNotice={query.timeoutNotice}
        selectedCitation={selectedCitation}
        onRetry={query.retryLastExecution}
        onCitationClick={setSelectedCitation}
      />

      {hasQueryResult ? (
        <section className="page-panel result-summary-panel">
          <div className="panel-header-row">
            <div>
              <div className="panel-eyebrow">后端返回摘要</div>
              <h2 className="panel-title">当前联调状态</h2>
            </div>
            {query.resultMeta?.status ? <span className="meta-pill">状态：{query.resultMeta.status}</span> : null}
          </div>

          <div className="result-meta-grid">
            {resultStats.map((item) => (
              <div key={item.label} className="info-card compact">
                <div className="section-title">{item.label}</div>
                <div>{item.value}</div>
              </div>
            ))}
          </div>

          <div className="panel-actions between">
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                query.resetConversation();
                setSelectedCitation(null);
              }}
            >
              清空结果
            </button>
            <div className="panel-actions no-margin">
              <button type="button" className="secondary-button" onClick={() => navigate('/history')}>
                查看查询历史
              </button>
              <button type="button" className="primary-button" onClick={() => inputRef.current?.focus()}>
                继续提问
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}

