import { useEffect, useRef } from 'react';
import type { Citation } from '../../types/query';

interface CitationHoverCardProps {
  citation: Citation;
  anchorRect: DOMRect;
  onClose: () => void;
}

function formatPreviewContent(content: string | undefined): string {
  if (!content) return '暂无原文内容';

  // 规范化空白字符：连续空格压缩为单个空格，保留单个换行
  let formatted = content
    .replace(/[ \t]+/g, ' ')  // 多个空格/tab → 单空格
    .replace(/\n{3,}/g, '\n\n')  // 连续3+换行 → 双换行
    .trim();

  // 限制长度为 200 字符
  const maxLength = 200;
  if (formatted.length > maxLength) {
    // 在最后一个句号、问号或感叹号处截断（200字符内）
    const lastPunctuation = Math.max(
      formatted.lastIndexOf('。', maxLength),
      formatted.lastIndexOf('？', maxLength),
      formatted.lastIndexOf('！', maxLength),
      formatted.lastIndexOf('.', maxLength)
    );

    if (lastPunctuation > 100) {
      formatted = formatted.substring(0, lastPunctuation + 1) + '...';
    } else {
      formatted = formatted.substring(0, maxLength) + '...';
    }
  }

  return formatted;
}

export function CitationHoverCard({ citation, anchorRect, onClose }: CitationHoverCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const formattedContent = formatPreviewContent(citation.content_preview);

  // 计算卡片位置：优先在引用卡片右侧，溢出则在左侧
  const cardStyle = (() => {
    const viewportWidth = window.innerWidth;
    const cardWidth = 360;
    const gap = 8;
    const spaceRight = viewportWidth - anchorRect.right;
    const spaceLeft = anchorRect.left;

    let left: number;
    if (spaceRight >= cardWidth + gap) {
      left = anchorRect.right + gap;
    } else if (spaceLeft >= cardWidth + gap) {
      left = anchorRect.left - cardWidth - gap;
    } else {
      // 居中显示（小屏）
      left = Math.max(8, (viewportWidth - cardWidth) / 2);
    }

    const top = Math.min(
      anchorRect.top,
      window.innerHeight - 300,
    );

    return {
      position: 'fixed' as const,
      top,
      left,
      width: cardWidth,
      zIndex: 2000,
    };
  })();

  return (
    <>
      <div className="citation-hover-overlay" onClick={onClose} />
      <div
        ref={cardRef}
        className="citation-hover-card"
        style={cardStyle}
        onMouseLeave={onClose}
      >
        <div className="hover-card-header">
          <span className="hover-card-standard">{citation.standard_no || '未知标准'}</span>
          {citation.clause && (
            <span className="hover-card-clause">{citation.clause}</span>
          )}
        </div>
        {citation.title && (
          <div className="hover-card-title">{citation.title}</div>
        )}
        {citation.chapter && (
          <div className="hover-card-chapter">{citation.chapter}</div>
        )}
        <div className="hover-card-content">
          {formattedContent}
        </div>
        {citation.images && citation.images.length > 0 && (
          <div className="hover-card-images-hint">
            包含 {citation.images.length} 张图片
          </div>
        )}
        {citation.pdf_url && (
          <div className="hover-card-pdf-action">
            <a
              href={`${citation.pdf_url}#page=${citation.page_number || 1}`}
              target="_blank"
              rel="noopener noreferrer"
              className="hover-card-pdf-link"
              onClick={(e) => e.stopPropagation()}
            >
              📄 打开原文{citation.page_number ? ` (第${citation.page_number}页)` : ''}
            </a>
          </div>
        )}
        <div className="hover-card-footer">
          <span className="hover-card-hint">按 ESC 或移开鼠标关闭</span>
        </div>
      </div>
    </>
  );
}
