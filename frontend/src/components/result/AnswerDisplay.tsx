import ReactMarkdown from 'react-markdown';
import type { Citation } from '../../types/query';

interface AnswerDisplayProps {
  answer: string;
  isStreaming: boolean;
  citations: Citation[];
  error?: string | null;
  timeoutNotice?: string | null;
  selectedCitation: Citation | null;
  onRetry: () => void;
  onCitationClick: (citation: Citation) => void;
}

export default function AnswerDisplay({
  answer,
  isStreaming,
  citations,
  error,
  timeoutNotice,
  selectedCitation,
  onRetry,
  onCitationClick,
}: AnswerDisplayProps) {
  const hasResult = Boolean(answer.trim()) || citations.length > 0 || isStreaming || Boolean(error);

  if (!hasResult) {
    return (
      <section className="answer-panel empty-state" aria-label="答案展示区域">
        <h2 className="panel-title">准备开始查询</h2>
        <p>
          完成登录后，输入问题即可先看到预处理结果，再决定是否采纳系统建议的车道与补充选项。
        </p>
      </section>
    );
  }

  return (
    <section className="answer-panel" aria-label="答案展示区域">
      <div className="panel-header-row">
        <h2 className="panel-title">答案展示</h2>
        {isStreaming ? <span className="meta-pill">生成中...</span> : null}
      </div>

      {timeoutNotice ? <div className="warning-banner">{timeoutNotice}</div> : null}

      {error ? (
        <div className="error-card">
          <div className="error-card-title">查询失败</div>
          <p>{error}</p>
          <button type="button" className="secondary-button" onClick={onRetry}>
            重新提交
          </button>
        </div>
      ) : null}

      {!error ? (
        <article className="answer-article" role="article" aria-live="polite">
          <div className="answer-markdown">
            {answer ? <ReactMarkdown>{answer}</ReactMarkdown> : <p className="muted-text">正在等待模型返回内容...</p>}
            {isStreaming ? <span className="typing-indicator">▋</span> : null}
          </div>
        </article>
      ) : null}

      {citations.length > 0 ? (
        <div className="citation-section">
          <div className="section-title">引用来源</div>
          <div className="citation-list">
            {citations.map((citation) => (
              <button
                key={`${citation.chunk_id}-${citation.id}`}
                type="button"
                className={`citation-card ${selectedCitation?.chunk_id === citation.chunk_id ? 'selected' : ''}`}
                onClick={() => onCitationClick(citation)}
                aria-label="查看引用详情"
              >
                <div className="citation-index">[{citation.id}]</div>
                <div className="citation-body">
                  <div className="citation-title">
                    {citation.standard_no || '未提供标准号'}
                    {citation.title ? ` · ${citation.title}` : ''}
                  </div>
                  <div className="citation-meta">
                    {citation.chapter ? `${citation.chapter} > ` : ''}
                    {citation.clause || '未提供条款号'}
                  </div>
                  <div className="citation-preview">{citation.content_preview || '暂无片段预览'}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {selectedCitation ? (
        <div className="citation-detail">
          <div className="section-title">引用详情</div>
          <div className="info-card">
            <div><strong>标准号：</strong>{selectedCitation.standard_no || '未提供'}</div>
            <div><strong>标题：</strong>{selectedCitation.title || '未提供'}</div>
            <div><strong>条款：</strong>{selectedCitation.clause || '未提供'}</div>
            <div><strong>Chunk ID：</strong>{selectedCitation.chunk_id || '未提供'}</div>
            <div className="citation-preview detail">{selectedCitation.content_preview || '暂无预览内容'}</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
