import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { useState, useRef } from 'react';
import type { Citation } from '../../types/query';
import { CitationHoverCard } from './CitationHoverCard';
import { preprocessAnswer } from '../../utils/query';

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
  const [hoveredCitation, setHoveredCitation] = useState<Citation | null>(null);
  const [hoverAnchorRect, setHoverAnchorRect] = useState<DOMRect | null>(null);
  const hoverTimerRef = useRef<number | null>(null);

  const handleCitationMouseEnter = (citation: Citation, e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    hoverTimerRef.current = window.setTimeout(() => {
      setHoveredCitation(citation);
      setHoverAnchorRect(rect);
    }, 300);
  };

  const handleCitationMouseLeave = () => {
    if (hoverTimerRef.current !== null) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  };

  const closeHoverCard = () => {
    setHoveredCitation(null);
    setHoverAnchorRect(null);
  };

  const handleCitationLinkClick = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    e.preventDefault();
    const match = href.match(/#citation-(\d+)/);
    if (match) {
      const citationId = match[1];
      const element = document.getElementById(`citation-card-${citationId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.classList.add('citation-highlight');
        setTimeout(() => element.classList.remove('citation-highlight'), 2000);
      }
    }
  };

  if (!hasResult) {
    return (
      <section className="answer-panel empty-state" aria-label="答案展示区域">
        <h2 className="panel-title">准备开始查询</h2>
        <p>
          完成登录后，输入问题即可先看到预处理结果，再决定是否采纳系统建议的检索方式与补充选项。
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
            {answer ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
                components={{
                  table: ({ children }) => (
                    <div className="markdown-table-scroll">
                      <table>{children}</table>
                    </div>
                  ),
                  a: ({ href, children }) => {
                    if (href?.startsWith('#citation-')) {
                      return (
                        <a
                          href={href}
                          className="citation-inline-link"
                          onClick={(e) => handleCitationLinkClick(e, href)}
                        >
                          {children}
                        </a>
                      );
                    }
                    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                  },
                }}
              >
                {preprocessAnswer(answer)}
              </ReactMarkdown>
            ) : (
              <p className="muted-text">正在等待模型返回内容...</p>
            )}
            {isStreaming ? <span className="typing-indicator">▋</span> : null}
          </div>
        </article>
      ) : null}

      {citations.length > 0 ? (
        <div className="citation-section">
          <div className="section-title">引用来源</div>
          <div className="citation-list">
            {citations.map((citation) => (
              <div
                key={`${citation.chunk_id}-${citation.id}`}
                id={`citation-card-${citation.id}`}
                role="button"
                tabIndex={0}
                className={`citation-card ${selectedCitation?.chunk_id === citation.chunk_id ? 'selected' : ''}`}
                onClick={() => onCitationClick(citation)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onCitationClick(citation); }}
                onMouseEnter={(e) => handleCitationMouseEnter(citation, e)}
                onMouseLeave={handleCitationMouseLeave}
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

                  {/* 图片展示 */}
                  {citation.images && citation.images.length > 0 && (
                    <div className="citation-images">
                      {citation.images.map((img, idx) => (
                        <div key={img.image_id || idx} className="citation-image-item">
                          <img
                            src={img.url}
                            alt={img.caption || img.figure_number || '引用图片'}
                            className="citation-image"
                            loading="lazy"
                          />
                          {(img.figure_number || img.caption) && (
                            <div className="citation-image-caption">
                              {img.figure_number && <span className="image-figure-number">{img.figure_number}</span>}
                              {img.caption && <span className="image-caption-text">{img.caption}</span>}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* PDF 打开按钮 */}
                  {citation.pdf_url && (
                    <div className="citation-actions">
                      <a
                        href={`${citation.pdf_url}#page=${citation.page_number || 1}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="citation-pdf-link"
                        onClick={(e) => e.stopPropagation()}
                      >
                        📄 打开原文{citation.page_number ? ` (第${citation.page_number}页)` : ''}
                      </a>
                    </div>
                  )}
                </div>
              </div>
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

            {/* 引用详情中的图片展示 */}
            {selectedCitation.images && selectedCitation.images.length > 0 && (
              <div className="citation-detail-images">
                <div><strong>相关图片：</strong></div>
                {selectedCitation.images.map((img, idx) => (
                  <div key={img.image_id || idx} className="citation-detail-image-item">
                    <img
                      src={img.url}
                      alt={img.caption || img.figure_number || '引用图片'}
                      className="citation-detail-image"
                    />
                    {(img.figure_number || img.caption) && (
                      <div className="citation-detail-image-info">
                        {img.figure_number && <div><strong>图号：</strong>{img.figure_number}</div>}
                        {img.caption && <div><strong>图注：</strong>{img.caption}</div>}
                        {img.page_number && <div><strong>页码：</strong>第 {img.page_number} 页</div>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}

      {hoveredCitation && hoverAnchorRect && (
        <CitationHoverCard
          citation={hoveredCitation}
          anchorRect={hoverAnchorRect}
          onClose={closeHoverCard}
        />
      )}
    </section>
  );
}
