import { useState } from 'react';
import type { OptimizationOption, Strategy } from '../../types/query';

interface ClarificationOptionsProps {
  options: OptimizationOption[];
  strategy: Strategy;
  selectedId: number | null;
  customInput: string;  // [方案C]
  originalQuery: string;
  onSelect: (optionId: number | null, refinedQuery: string | null) => void;
  onCustomInput: (input: string) => void;  // [方案C]
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
  customInput,
  originalQuery,
  onSelect,
  onCustomInput,
}: ClarificationOptionsProps) {
  const [isCustomExpanded, setIsCustomExpanded] = useState(false);

  if (strategy === 'none') {
    return (
      <section className="options-card">
        <div className="clarity-status">
          <span className="clarity-icon">✓</span>
          <span className="clarity-text">问题清晰，可直接查询</span>
        </div>
      </section>
    );
  }

  const allowSkip = true;
  const hasCustomInput = customInput.trim().length > 0;

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
          className={`option-item skip-option ${selectedId === null && !hasCustomInput ? 'selected' : ''}`}
          onClick={() => onSelect(null, originalQuery)}
        >
          <div className="option-head">
            <span className="radio-indicator" aria-hidden="true">
              {selectedId === null && !hasCustomInput ? '●' : '○'}
            </span>
            <span className="option-label">跳过，使用原始查询</span>
          </div>
        </button>
      ) : null}

      {/* [方案C] 自定义输入折叠区域 */}
      <div className="custom-input-section">
        <button
          type="button"
          className="custom-toggle"
          onClick={() => setIsCustomExpanded(!isCustomExpanded)}
        >
          📝 以上选项都不符合？
          <span className="toggle-icon">{isCustomExpanded ? '▲' : '▼'}</span>
        </button>

        {isCustomExpanded && (
          <div className="custom-input-area">
            <label htmlFor="custom-refinement" className="custom-label">
              请描述您的具体需求（最多200字）
            </label>
            <textarea
              id="custom-refinement"
              className="custom-textarea"
              placeholder="例如：220kV变电站室外隔离开关"
              maxLength={200}
              value={customInput}
              onChange={(e) => onCustomInput(e.target.value)}
              rows={3}
            />
            <div className="custom-hint">
              💡 提示：输入自定义内容后，系统选项会自动取消
            </div>
            <div className="custom-counter">
              {customInput.length} / 200
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
