import React, { useEffect, useRef } from 'react';
import { ChatMessage } from './ChatMessage';
import type { Message } from '../../hooks/useConversation';
import './ChatMessageList.css';

interface ChatMessageListProps {
  messages: Message[];
  isLoadingHistory?: boolean;
}

export function ChatMessageList({ messages, isLoadingHistory }: ChatMessageListProps) {
  const listEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      shouldAutoScrollRef.current = isNearBottom;
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (shouldAutoScrollRef.current) {
      listEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  if (isLoadingHistory) {
    return (
      <div className="chat-message-list">
        <div className="loading-history">
          <div className="spinner"></div>
          <span>加载历史记录...</span>
        </div>
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="chat-message-list">
        <div className="empty-chat">
          <div className="empty-icon">💬</div>
          <h3>开始新对话</h3>
          <p>在下方输入您的问题，我会基于电力标准知识库为您解答</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-message-list" ref={containerRef}>
      <div className="messages-container">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}
        <div ref={listEndRef} />
      </div>
    </div>
  );
}
