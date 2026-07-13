import type { OptimizationOption, Strategy } from '../../types/query';

interface ClarificationOptionsProps {
  options: OptimizationOption[];
  strategy: Strategy;
  selectedId: number | null;
  originalQuery: string;
  onSelect: (optionId: number | null, refinedQuery: string | null) => void;
}

function getSectionTitle(strategy: Strategy) {
  if (strategy === 'clarify_required') return '请选择具体场景';
  if (strategy === 'clarify_optional') return '建议补充（可选）';
  if (strategy === 'suggest') return '补充信息（可选）';
  return '补充信息';
}

export default function ClarificationOptions({
  options,
  strategy,
  selectedId,
  originalQuery,
  onSelect,
}: ClarificationOptionsProps) {
  if (strategy === 'none') {
    return null;
  }

  const allowSkip = true;

  return (
    <section className="options-card">
      <div className="section-title">{getSectionTitle(strategy)}</div>

      {options.length === 0 ? (
        <div className="empty-options">当前没有可展示的补充选项，您可以直接提交原始查询。</div>
      ) : (
        <div className="option-list" role="radiogroup" aria-label={getSectionTitle(strategy)}>
          {options.map((option) => {
            const isSelected = selectedId === option.id;
            return (
              <button
                key={option.id}
                type="button"
                className={`option-item ${isSelected ? 'selected' : ''}`}
                role="radio"
                aria-checked={isSelected}
                onClick={() => onSelect(option.id, option.refined_query)}
              >
                <div className="option-head">
                  <span className="radio-indicator" aria-hidden="true">
                    {isSelected ? '●' : '○'}
                  </span>
                  <span className="option-label">{option.label}</span>
                </div>
                <div className="option-description">{option.refined_query}</div>
                <div className="option-meta">
                  {option.kb_verified ? (
                    <span className="verification-badge is-verified">
                      ✓ 基于知识库：{option.standard_preview || '已验证'}
                      {typeof option.doc_count === 'number' ? `，${option.doc_count} 篇文档` : ''}
                    </span>
                  ) : (
                    <span className="verification-badge is-unverified">ⓘ 仅供参考（未在知识库验证）</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {allowSkip ? (
        <button
          type="button"
          className={`option-item skip-option ${selectedId === null ? 'selected' : ''}`}
          onClick={() => onSelect(null, originalQuery)}
        >
          <div className="option-head">
            <span className="radio-indicator" aria-hidden="true">
              {selectedId === null ? '●' : '○'}
            </span>
            <span className="option-label">跳过，使用原始查询</span>
          </div>
        </button>
      ) : null}
    </section>
  );
}
