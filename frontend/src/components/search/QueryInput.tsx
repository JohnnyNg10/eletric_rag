import { forwardRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';


interface QueryInputProps {
  query: string;
  disabled?: boolean;
  loading?: boolean;
  warning?: string | null;
  error?: string | null;
  helperText?: string | null;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onClearCache?: () => Promise<void>;
}

const QueryInput = forwardRef<HTMLTextAreaElement, QueryInputProps>(function QueryInput(
  { query, disabled, loading, warning, error, helperText, onChange, onSubmit, onClearCache },
  ref,
) {
  const [clearing, setClearing] = useState(false);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {


    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && !loading) {
        onSubmit();
      }
    }
  };

  const handleClearCache = async () => {
    if (!onClearCache || clearing) return;

    try {
      setClearing(true);
      await onClearCache();
      alert('缓存已清理');
    } catch (err) {
      alert(`清理缓存失败: ${err}`);
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="query-input-card">
      <label className="field-label sr-only" htmlFor="query-input">
        输入查询问题
      </label>
      <textarea
        ref={ref}
        id="query-input"
        className="query-textarea"
        aria-label="输入查询问题"
        placeholder="请输入电力标准相关问题，例如：隔离开关安全距离要求"
        rows={3}
        value={query}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
      />

      <div className="query-toolbar">
        <div className="helper-text">{helperText || 'Enter 提交，Shift + Enter 换行'}</div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {onClearCache && (
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || loading || clearing}
              onClick={handleClearCache}
              title="清空所有RAG缓存（调试用）"
            >
              {clearing ? '清理中...' : '清理缓存'}
            </button>
          )}
          <button
            type="button"
            className="primary-button large"
            disabled={disabled || loading}
            onClick={onSubmit}
          >
            {loading ? '分析中...' : '提交查询'}
          </button>
        </div>
      </div>

      {warning ? <div className="warning-banner">{warning}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
    </div>
  );
});

export default QueryInput;
