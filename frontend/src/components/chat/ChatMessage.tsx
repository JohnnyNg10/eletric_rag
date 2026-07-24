import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../hooks/useConversation';
import type { Citation } from '../../types/query';
import './ChatMessage.css';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  if (message.role === 'user') {
    return <UserMessage content={message.content} />;
  }

  return (
    <AssistantMessage
      content={message.content}
      citations={message.citations}
      metadata={message.metadata}
      status={message.status}
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
}

function AssistantMessage({ content, citations, metadata, status }: AssistantMessageProps) {
  const [citationsExpanded, setCitationsExpanded] = useState(false);

  const hasCitations = citations && citations.length > 0;

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
          <div className="message-content">
            <ReactMarkdown>{content}</ReactMarkdown>
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
                  <CitationCard key={index} citation={citation} />
                ))}
              </div>
            )}
          </div>
        )}

        {metadata && status === 'completed' && (
          <div className="message-footer">
            {metadata.lane && (
              <span className={`lane-badge ${metadata.lane}`}>
                {metadata.lane === 'fast' ? '快速车道' : '慢速车道'}
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
