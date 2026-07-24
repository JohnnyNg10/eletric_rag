interface RelatedQueriesPanelProps {
  queries: string[];
  onQueryClick: (query: string) => void;
}

export function RelatedQueriesPanel({ queries, onQueryClick }: RelatedQueriesPanelProps) {
  if (!queries || queries.length === 0) {
    return null;
  }

  return (
    <div className="related-queries-section">
      <div className="section-title">相关问题推荐</div>
      <p className="section-hint">基于当前答案为您推荐以下问题</p>
      <div className="related-queries-list">
        {queries.map((query, index) => (
          <button
            key={index}
            type="button"
            className="related-query-button"
            onClick={() => onQueryClick(query)}
            title={`点击查询：${query}`}
          >
            <span className="related-query-index">{index + 1}</span>
            <span className="related-query-text">{query}</span>
            <span className="related-query-arrow">→</span>
          </button>
        ))}
      </div>
    </div>
  );
}
