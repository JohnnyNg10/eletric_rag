import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import PreprocessConfirmPanel from '../components/query/PreprocessConfirmPanel';
import QueryInput from '../components/search/QueryInput';
import { ConversationSidebar } from '../components/conversation/ConversationSidebar';
import { ChatMessageList } from '../components/chat/ChatMessageList';
import { useAuthContext } from '../context/AuthContext';
import { useConversation } from '../hooks/useConversation';
import { clearCache } from '../api/query';
import './SearchPage.css';

export function SearchPage() {
  const auth = useAuthContext();
  const conversation = useConversation({ accessToken: auth.accessToken });
  const [searchParams, setSearchParams] = useSearchParams();
  const [draftQuery, setDraftQuery] = useState('');
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const conversationIdParam = searchParams.get('conversation_id');
    if (conversationIdParam && conversationIdParam !== conversation.conversationId) {
      conversation.loadConversation(conversationIdParam);
    }
  }, [searchParams]);

  const handleSubmit = async () => {
    if (!draftQuery.trim()) return;
    await conversation.sendQuery(draftQuery);
    setDraftQuery('');
  };

  const handleClearCache = async () => {
    if (!auth.accessToken) {
      throw new Error('未登录');
    }
    await clearCache(auth.accessToken);
  };

  const handleSelectConversation = (id: string) => {
    setSearchParams({ conversation_id: id });
    conversation.loadConversation(id);
  };

  const handleNewConversation = () => {
    setSearchParams({});
    conversation.startNewConversation();
    setDraftQuery('');
    inputRef.current?.focus();
  };

  const helperText = auth.accessToken
    ? 'Enter 提交查询，Shift + Enter 换行。'
    : '请先在右上角登录，或粘贴 access token 后再查询。';

  return (
    <div className="chat-layout">
      <ConversationSidebar
        accessToken={auth.accessToken}
        activeConversationId={conversation.conversationId}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        refreshTrigger={conversation.conversationListRefreshTrigger}
      />

      <div className="chat-main">
        <ChatMessageList
          messages={conversation.messages}
          isLoadingHistory={conversation.isLoadingHistory}
        />

        <div className="chat-input-area">
          <div className="cache-strategy-bar">
            <span className="cache-strategy-label">缓存策略</span>
            <button
              className={`cache-strategy-btn${conversation.cacheStrategy === 'exact' ? ' active' : ''}`}
              onClick={() => conversation.setCacheStrategy('exact')}
              title="精确匹配：仅当查询完全一致时命中缓存"
            >
              精确
            </button>
            <button
              className={`cache-strategy-btn${conversation.cacheStrategy === 'semantic' ? ' active' : ''}`}
              onClick={() => conversation.setCacheStrategy('semantic')}
              title="语义匹配：语义相似的查询也可命中缓存"
            >
              语义
            </button>
          </div>
          <QueryInput
            ref={inputRef}
            query={draftQuery}
            disabled={!auth.accessToken || auth.isLoading || auth.isLoggingIn || conversation.isBusy}
            loading={conversation.state === 'preprocessing'}
            warning={conversation.warning}
            error={conversation.errorSource === 'preprocess' ? conversation.error : null}
            helperText={helperText}
            onChange={setDraftQuery}
            onSubmit={handleSubmit}
            onClearCache={handleClearCache}
          />
        </div>
      </div>

      {conversation.preprocessResult && conversation.state === 'confirming' && (
        <div className="preprocess-overlay">
          <PreprocessConfirmPanel
            preprocessResult={conversation.preprocessResult}
            originalQuery={conversation.originalQuery}
            selectedOptionId={conversation.selectedOptionId}
            customInput={conversation.customRefinement}  // [方案C]
            userLane={conversation.userLane}
            validationMessage={conversation.errorSource === 'preprocess' ? conversation.error : null}
            onToggleLane={conversation.toggleLane}
            onSelectOption={conversation.selectOption}
            onCustomInput={conversation.handleCustomInput}  // [方案C]
            onConfirm={conversation.confirmAndExecute}
            onCancel={() => {
              conversation.cancelConfirmation();
              inputRef.current?.focus();
            }}
          />
        </div>
      )}
    </div>
  );
}

