import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchQueryHistory } from '../api/query';
import { getErrorMessage } from '../api/client';
import { useAuthContext } from '../context/AuthContext';
import type { QueryHistoryItem, QueryHistoryResponse } from '../types/query';
import { LANE_META } from '../utils/constants';

const PAGE_SIZE = 10;

function formatTime(value?: string | null) {
  if (!value) return '未知时间';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN');
}

export function HistoryPage() {
  const auth = useAuthContext();
  const navigate = useNavigate();
  const [history, setHistory] = useState<QueryHistoryResponse | null>(null);
  const [selectedItem, setSelectedItem] = useState<QueryHistoryItem | null>(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);

    fetchQueryHistory(auth.accessToken, page, PAGE_SIZE)
      .then((response) => {
        if (!active) return;
        setHistory(response);
        setSelectedItem((previous) => {
          if (!response.items.length) return null;
          if (previous) {
            return response.items.find((item) => item.query_log_id === previous.query_log_id) ?? response.items[0];
          }
          return response.items[0];
        });
      })
      .catch((requestError) => {
        if (!active) return;
        setError(getErrorMessage(requestError, '获取查询历史失败，请稍后重试'));
        setHistory(null);
        setSelectedItem(null);
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [auth.accessToken, page]);

  const hasData = Boolean(history && history.items.length > 0);
  const totalPages = useMemo(() => {
    if (!history) return 1;
    return Math.max(1, Math.ceil(history.total / history.page_size));
  }, [history]);

  return (
    <section className="page-panel">
      <div className="panel-header-row">
        <div>
          <h1 className="panel-title">查询历史</h1>
          <p className="panel-subtitle">
            {history ? `共 ${history.total} 条记录` : '查看过往的提问与答案'}
          </p>
        </div>
        <button type="button" className="primary-button" onClick={() => navigate('/search')}>
          新建查询
        </button>
      </div>

      {isLoading ? <div className="info-banner">正在加载查询历史...</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}

      {!isLoading && !error && !hasData ? (
        <div className="empty-page-state">
          <h2 className="panel-title">还没有查询记录</h2>
          <p className="page-description">发起查询后，历史记录将会显示在这里。</p>
        </div>
      ) : null}

      {hasData && history ? (
        <>
          <div className="history-layout">
            <div className="history-list">
              {history.items.map((item) => {
                const laneMeta = LANE_META[item.lane];
                const isSelected = selectedItem?.query_log_id === item.query_log_id;

                return (
                  <button
                    key={item.query_log_id}
                    type="button"
                    className={`history-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedItem(item)}
                  >
                    <div className="history-item-top">
                      <span className={`lane-badge ${laneMeta.className}`}>
                        <span aria-hidden="true">{laneMeta.icon}</span>
                        <span>{laneMeta.label}</span>
                      </span>
                      <span className="meta-pill">#{item.query_log_id}</span>
                    </div>

                    <div className="history-query">{item.query}</div>
                    <div className="history-answer-preview">{item.answer || '暂无答案内容'}</div>

                    <div className="history-item-meta">
                      <span>{formatTime(item.created_at)}</span>
                      <span>{typeof item.total_time === 'number' ? `${item.total_time}ms` : '耗时未知'}</span>
                      <span>{item.feedback_score ? `评分 ${item.feedback_score}/5` : '未评分'}</span>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="history-detail">
              {selectedItem ? (
                <>
                  <div className="history-detail-header">
                    <div className="history-detail-query">{selectedItem.query}</div>
                    <div className="history-detail-meta">
                      <span className={`lane-badge ${LANE_META[selectedItem.lane].className}`}>
                        <span aria-hidden="true">{LANE_META[selectedItem.lane].icon}</span>
                        <span>{LANE_META[selectedItem.lane].label}</span>
                      </span>
                      <span className="meta-pill">{formatTime(selectedItem.created_at)}</span>
                      <span className="meta-pill">
                        {typeof selectedItem.total_time === 'number' ? `耗时 ${selectedItem.total_time}ms` : '耗时未知'}
                      </span>
                      <span className="meta-pill">
                        {selectedItem.feedback_score ? `评分 ${selectedItem.feedback_score}/5` : '未评分'}
                      </span>
                      <span className="meta-pill">#{selectedItem.query_log_id}</span>
                    </div>
                  </div>

                  <div className="answer-article history-detail-answer">
                    <div className="section-title">答案</div>
                    <p className="page-description">{selectedItem.answer || '该条记录暂无答案文本。'}</p>
                  </div>

                  <div className="panel-actions end no-margin">
                    <button type="button" className="ghost-button" onClick={() => navigate('/search')}>
                      新建查询
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={() => navigate(`/search?q=${encodeURIComponent(selectedItem.query)}`)}
                    >
                      再次提问
                    </button>
                  </div>
                </>
              ) : (
                <div className="history-detail-empty">从左侧选择一条记录查看详情</div>
              )}
            </div>
          </div>

          <div className="panel-actions between">
            <button type="button" className="ghost-button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page <= 1}>
              上一页
            </button>
            <span className="meta-pill">第 {page} / {totalPages} 页</span>
            <button
              type="button"
              className="ghost-button"
              onClick={() => setPage((current) => current + 1)}
              disabled={!history.has_more}
            >
              下一页
            </button>
          </div>
        </>
      ) : null}
    </section>
  );
}
