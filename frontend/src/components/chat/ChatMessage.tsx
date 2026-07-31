import React, { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import type { Message } from '../../hooks/useConversation';
import type { Citation } from '../../types/query';
import { CitationHoverCard } from '../result/CitationHoverCard';
import { RelatedQueriesPanel } from '../result/RelatedQueriesPanel';
import { preprocessAnswer } from '../../utils/query';
import './ChatMessage.css';

/**
 * 渲染带图片引用的答案文本
 * 识别 __IMAGE_REF_N__ 占位符并替换为图片组件
 */
function renderAnswerWithImages(text: string, citations: Citation[]) {
  const parts: (string | JSX.Element)[] = [];
  const pattern = /__IMAGE_REF_(\d+)__/g;
  let lastIndex = 0;
  let match;
  let imageKey = 0;

  while ((match = pattern.exec(text)) !== null) {
    // 添加占位符前的文本
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }

    // 获取引用编号（匹配 citation.id 而不是数组索引）
    const citationId = parseInt(match[1]);
    const citation = citations?.find(c => c.id === citationId || c.index === citationId);

    // 渲染图片
    if (citation?.images && citation.images.length > 0) {
      const image = citation.images[0];
      parts.push(
        <div key={`inline-img-${imageKey++}`} className="inline-image-container">
          <img
            src={image.url}
            alt={image.caption || image.figure_number || '配图'}
            className="inline-image"
            loading="lazy"
          />
          {(image.figure_number || image.caption) && (
            <div className="inline-image-caption">
              {image.figure_number && <span className="image-figure-number">{image.figure_number}</span>}
              {image.caption && <span className="image-caption-text">: {image.caption}</span>}
            </div>
          )}
        </div>
      );
    } else {
      // 如果没找到图片，保留文本提示
      parts.push(<span key={`missing-img-${imageKey++}`} className="missing-image-ref">[图片引用:{match[1]}]</span>);
    }

    lastIndex = pattern.lastIndex;
  }

  // 添加剩余文本
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

interface ChatMessageProps {
  message: Message;
  onRelatedQueryClick?: (query: string) => void;
}

export function ChatMessage({ message, onRelatedQueryClick }: ChatMessageProps) {
  if (message.role === 'user') {
    return <UserMessage content={message.content} />;
  }

  return (
    <AssistantMessage
      content={message.content}
      citations={message.citations}
      metadata={message.metadata}
      status={message.status}
      onRelatedQueryClick={onRelatedQueryClick}
    />
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="chat-message user-message">
      <div className="message-bubble user-bubble">{content}</div>
    </div>
  );
}

interface AssistantMessageProps {
  content: string;
  citations?: Citation[];
  metadata?: Message['metadata'];
  status: Message['status'];
  onRelatedQueryClick?: (query: string) => void;
}

function AssistantMessage({ content, citations, metadata, status, onRelatedQueryClick }: AssistantMessageProps) {
  const [citationsExpanded, setCitationsExpanded] = useState(false);
  const [hoveredCitation, setHoveredCitation] = useState<Citation | null>(null);
  const [hoverAnchorRect, setHoverAnchorRect] = useState<DOMRect | null>(null);
  const hoverTimerRef = useRef<number | null>(null);

  const hasCitations = citations && citations.length > 0;
  const hasRelatedQueries = metadata?.expanded_queries && metadata.expanded_queries.length > 0;

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
      const element = document.getElementById(`citation-card-chat-${match[1]}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        element.classList.add('citation-highlight');
        setTimeout(() => element.classList.remove('citation-highlight'), 2000);
      }
    }
  };

  return (
    <div className="chat-message assistant-message">
      <div className="message-bubble assistant-bubble">
        {status === 'streaming' && !content && (
          <div className="streaming-indicator">
            <span className="dot"></span>
            <span className="dot"></span>
            <span className="dot"></span>
          </div>
        )}

        {content && (
          <div className="message-content answer-markdown">
            {renderAnswerWithImages(preprocessAnswer(content), citations || []).map((part, index) => {
              if (typeof part === 'string') {
                return (
                  <ReactMarkdown
                    key={index}
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
                  >{part}</ReactMarkdown>
                );
              } else {
                // 直接渲染图片组件
                return part;
              }
            })}
          </div>
        )}

        {status === 'error' && (
          <div className="error-indicator">
            <span className="error-icon">⚠</span>
            查询失败
          </div>
        )}

        {hasCitations && (
          <div className="citations-section">
            <button
              className="citations-toggle"
              onClick={() => setCitationsExpanded(!citationsExpanded)}
            >
              <span className="toggle-icon">{citationsExpanded ? '▼' : '▶'}</span>
              引用来源 ({citations.length})
            </button>

            {citationsExpanded && (
              <div className="citations-list">
                {citations.map((citation, index) => (
                  <div
                    key={index}
                    onMouseEnter={(e) => handleCitationMouseEnter(citation, e)}
                    onMouseLeave={handleCitationMouseLeave}
                  >
                    <CitationCard citation={citation} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {metadata && status === 'completed' && (
          <div className="message-footer">
            {metadata.lane && (
              <span className={`lane-badge ${metadata.lane}`}>
                {metadata.lane === 'fast' ? '标准检索' : '智能检索'}
              </span>
            )}
            {metadata.retrieval_time !== null && metadata.retrieval_time !== undefined && (
              <span className="time-info">检索 {metadata.retrieval_time}ms</span>
            )}
            {metadata.generation_time !== null && metadata.generation_time !== undefined && (
              <span className="time-info">生成 {metadata.generation_time}ms</span>
            )}
          </div>
        )}

        {hasRelatedQueries && status === 'completed' && onRelatedQueryClick && (
          <RelatedQueriesPanel
            queries={metadata.expanded_queries!}
            onQueryClick={onRelatedQueryClick}
          />
        )}

        {hoveredCitation && hoverAnchorRect && (
          <CitationHoverCard
            citation={hoveredCitation}
            anchorRect={hoverAnchorRect}
            onClose={closeHoverCard}
          />
        )}
      </div>
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="citation-card" id={`citation-card-chat-${citation.id || citation.index}`}>
      <div className="citation-header">
        {citation.index && <span className="citation-index">[{citation.index}]</span>}
        {citation.standard_no && <span className="standard-no">{citation.standard_no}</span>}
        {citation.clause && <span className="clause">第{citation.clause}条</span>}
      </div>
      {citation.content_snippet && (
        <div className="citation-content">{citation.content_snippet}</div>
      )}
      {citation.document_title && (
        <div className="citation-title">{citation.document_title}</div>
      )}
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
  );
}
