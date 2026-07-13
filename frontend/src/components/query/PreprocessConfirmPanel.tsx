import { useEffect, useRef } from 'react';
import type { Lane, PreprocessResponse } from '../../types/query';
import ClarificationOptions from './ClarificationOptions';
import RouteRecommendation from './RouteRecommendation';

interface PreprocessConfirmPanelProps {
  preprocessResult: PreprocessResponse;
  selectedOptionId: number | null;
  userLane: Lane | null;
  validationMessage?: string | null;
  isSubmitting?: boolean;
  onToggleLane: () => void;
  onSelectOption: (optionId: number | null, refinedQuery: string | null) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function PreprocessConfirmPanel({
  preprocessResult,
  selectedOptionId,
  userLane,
  validationMessage,
  isSubmitting,
  onToggleLane,
  onSelectOption,
  onConfirm,
  onCancel,
}: PreprocessConfirmPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;

    const focusableElements = panel.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusableElements[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }

      if (event.key !== 'Tab' || focusableElements.length === 0) {
        return;
      }

      const first = focusableElements[0];
      const last = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement as HTMLElement | null;

      if (event.shiftKey && activeElement === first) {
        event.preventDefault();
        last.focus();
      }

      if (!event.shiftKey && activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    panel.addEventListener('keydown', handleKeyDown);
    return () => panel.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  return (
    <section
      ref={panelRef}
      className="confirm-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="confirm-title"
    >
      <div className="panel-header-row">
        <div>
          <div className="panel-eyebrow">第一次请求结果</div>
          <h2 className="panel-title" id="confirm-title">
            请确认系统建议后继续查询
          </h2>
        </div>
        {typeof preprocessResult.preprocessing_time === 'number' ? (
          <span className="meta-pill">预处理 {preprocessResult.preprocessing_time}ms</span>
        ) : null}
      </div>

      <div className="confirm-grid">
        <div className="confirm-column emphasis">
          <RouteRecommendation
            lane={preprocessResult.lane_suggestion.lane}
            confidence={preprocessResult.lane_suggestion.confidence}
            reason={preprocessResult.lane_suggestion.reason}
            userLane={userLane}
            onToggle={onToggleLane}
          />
        </div>

        <div className="confirm-column">
          <ClarificationOptions
            options={preprocessResult.options}
            strategy={preprocessResult.strategy}
            selectedId={selectedOptionId}
            onSelect={onSelectOption}
          />
        </div>
      </div>

      {validationMessage ? <div className="error-banner">{validationMessage}</div> : null}

      <div className="panel-actions end">
        <button type="button" className="ghost-button" onClick={onCancel}>
          取消
        </button>
        <button type="button" className="primary-button" onClick={onConfirm} disabled={isSubmitting}>
          {isSubmitting ? '提交中...' : '提交查询'}
        </button>
      </div>
    </section>
  );
}
