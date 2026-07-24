import React, { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message } from '../../hooks/useConversation';
import type { Citation } from '../../types/query';
import { CitationHoverCard } from '../result/CitationHoverCard';
import { RelatedQueriesPanel } from '../result/RelatedQueriesPanel';
import './ChatMessage.css';

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
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="markdown-table-scroll">
                    <table>{children}</table>
                  </div>
                ),
              }}
            >{content}</ReactMarkdown>
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
    <div className="citation-card">
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
    </div>
  );
}
