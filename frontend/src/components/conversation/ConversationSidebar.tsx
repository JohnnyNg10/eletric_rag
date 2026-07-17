import React, { useEffect, useState } from 'react';
import { getConversations, type ConversationItem } from '../../api/query';
import './ConversationSidebar.css';

interface ConversationSidebarProps {
  accessToken: string;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  refreshTrigger?: number;  // 用于触发刷新的时间戳
}

export function ConversationSidebar({
  accessToken,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  refreshTrigger,
}: ConversationSidebarProps) {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  useEffect(() => {
    loadConversations(1);
  }, [accessToken, refreshTrigger]);

  const loadConversations = async (pageNum: number) => {
    if (!accessToken) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await getConversations(accessToken, pageNum, 20);
      if (pageNum === 1) {
        setConversations(response.conversations);
      } else {
        setConversations((prev) => [...prev, ...response.conversations]);
      }
      setHasMore(response.has_more);
      setPage(pageNum);
    } catch (err) {
      setError('加载会话列表失败');
      console.error('Failed to load conversations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLoadMore = () => {
    if (!isLoading && hasMore) {
      loadConversations(page + 1);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 60) {
        return diffMins <= 1 ? '刚刚' : `${diffMins}分钟前`;
      }
      if (diffHours < 24) {
        return `${diffHours}小时前`;
      }
      if (diffDays < 7) {
        return `${diffDays}天前`;
      }

      const month = date.getMonth() + 1;
      const day = date.getDate();
      return `${month}月${day}日`;
    } catch {
      return '';
    }
  };

  return (
    <div className="conversation-sidebar">
      <div className="conversation-sidebar-header">
        <button className="new-conversation-btn" onClick={onNewConversation}>
          <span className="icon">+</span>
          新对话
        </button>
      </div>

      <div className="conversation-list">
        {conversations.length === 0 && !isLoading && (
          <div className="empty-state">
            <p>暂无会话记录</p>
            <p className="empty-hint">开始新对话吧</p>
          </div>
        )}

        {conversations.map((conv) => (
          <div
            key={conv.conversation_id}
            className={`conversation-item ${activeConversationId === conv.conversation_id ? 'active' : ''}`}
            onClick={() => onSelectConversation(conv.conversation_id)}
          >
            <div className="conversation-title">{conv.title}</div>
            <div className="conversation-meta">
              <span className="message-count">{conv.message_count} 条消息</span>
              <span className="dot">·</span>
              <span className="timestamp">{formatDate(conv.last_message_at)}</span>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>加载中...</span>
          </div>
        )}

        {error && <div className="error-message">{error}</div>}

        {hasMore && !isLoading && conversations.length > 0 && (
          <button className="load-more-btn" onClick={handleLoadMore}>
            加载更多
          </button>
        )}
      </div>
    </div>
  );
}
