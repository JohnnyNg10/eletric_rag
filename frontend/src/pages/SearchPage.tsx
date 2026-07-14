import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import PreprocessConfirmPanel from '../components/query/PreprocessConfirmPanel';
import AnswerDisplay from '../components/result/AnswerDisplay';
import QueryInput from '../components/search/QueryInput';
import { useAuthContext } from '../context/AuthContext';
import { useQuery } from '../hooks/useQuery';
import type { Citation } from '../types/query';

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

  const hasQueryResult = query.state === 'completed' || query.state === 'error' || query.state === 'querying';

  return (
    <section className="hero-panel">
      <div className="hero-copy">
        <h1 className="hero-title">电力标准知识库</h1>
        <p className="hero-subtitle">
          基于国家标准与行业规范的专业问答系统，零臆测、可溯源、可校验
        </p>
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
        <div className="panel-actions between" style={{ marginTop: '2rem' }}>
          <button
            type="button"
            className="ghost-button"
            onClick={() => {
              query.resetConversation();
              setSelectedCitation(null);
            }}
          >
            开始新查询
          </button>
          <div className="panel-actions no-margin">
            <button type="button" className="secondary-button" onClick={() => navigate('/history')}>
              查看历史记录
            </button>
            <button type="button" className="primary-button" onClick={() => inputRef.current?.focus()}>
              继续提问
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

