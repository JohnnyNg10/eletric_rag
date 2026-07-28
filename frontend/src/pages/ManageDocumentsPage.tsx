import { useEffect, useState } from 'react';
import { batchDeleteDocuments, deleteDocument, listDocuments, scanOrphanData, cleanupOrphanData, type OrphanDataScanResult, type OrphanDataCleanupResult } from '../api/documents';
import { getErrorMessage } from '../api/client';
import type { DocumentBatchDeleteResponse, DocumentDeleteResponse, DocumentListItem } from '../types/document';

type DeleteState =
  | { phase: 'idle' }
  | { phase: 'deleting'; documentId: number }
  | { phase: 'success'; response: DocumentDeleteResponse }
  | { phase: 'error'; message: string }
  | { phase: 'batch_deleting'; count: number }
  | { phase: 'batch_success'; response: DocumentBatchDeleteResponse };

type OrphanState =
  | { phase: 'idle' }
  | { phase: 'scanning' }
  | { phase: 'scanned'; result: OrphanDataScanResult }
  | { phase: 'cleaning' }
  | { phase: 'cleaned'; result: OrphanDataCleanupResult }
  | { phase: 'error'; message: string };

export function ManageDocumentsPage() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteState, setDeleteState] = useState<DeleteState>({ phase: 'idle' });
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchConfirming, setBatchConfirming] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const [orphanState, setOrphanState] = useState<OrphanState>({ phase: 'idle' });
  const [showOrphanPanel, setShowOrphanPanel] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, [page]);

  const loadDocuments = async () => {
    setLoading(true);
    // 翻页/刷新后清空勾选，避免误删不可见的文档
    setSelectedIds(new Set());
    try {
      const response = await listDocuments(page, pageSize);
      setDocuments(response.items);
      setTotal(response.total);
    } catch (err) {
      console.error('加载文档列表失败:', err);
    } finally {
      setLoading(false);
    }
  };

  const allOnPageSelected = documents.length > 0 && documents.every((doc) => selectedIds.has(doc.id));
  const isBusy = deleteState.phase === 'deleting' || deleteState.phase === 'batch_deleting';

  const toggleSelect = (docId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const toggleSelectAllOnPage = () => {
    setSelectedIds(allOnPageSelected ? new Set() : new Set(documents.map((doc) => doc.id)));
  };

  const handleConfirmBatchDelete = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;

    setBatchConfirming(false);
    setDeleteState({ phase: 'batch_deleting', count: ids.length });

    try {
      const response = await batchDeleteDocuments(ids);
      setDeleteState({ phase: 'batch_success', response });

      const deletedIds = new Set(
        response.results.filter((r) => r.success).map((r) => r.document_id),
      );
      setDocuments((prev) => prev.filter((doc) => !deletedIds.has(doc.id)));
      setSelectedIds(new Set());
    } catch (err) {
      setDeleteState({ phase: 'error', message: getErrorMessage(err) });
    }
  };

  const handleDeleteClick = (docId: number) => {
    setSelectedDocId(docId);
  };

  const handleConfirmDelete = async () => {
    if (selectedDocId === null) return;

    setDeleteState({ phase: 'deleting', documentId: selectedDocId });

    try {
      const response = await deleteDocument(selectedDocId);
      setDeleteState({ phase: 'success', response });

      // 从列表中移除已删除的文档
      setDocuments((prev) => prev.filter((doc) => doc.id !== selectedDocId));

      // 2秒后重置状态
      setTimeout(() => {
        setDeleteState({ phase: 'idle' });
        setSelectedDocId(null);
      }, 2000);
    } catch (err) {
      setDeleteState({ phase: 'error', message: getErrorMessage(err) });
    }
  };

  const handleCancelDelete = () => {
    setSelectedDocId(null);
    setBatchConfirming(false);
    setDeleteState({ phase: 'idle' });
  };

  const handleScanOrphans = async () => {
    setOrphanState({ phase: 'scanning' });
    try {
      const result = await scanOrphanData();
      setOrphanState({ phase: 'scanned', result });
    } catch (err) {
      setOrphanState({ phase: 'error', message: getErrorMessage(err) });
    }
  };

  const handleCleanupOrphans = async () => {
    setOrphanState({ phase: 'cleaning' });
    try {
      const result = await cleanupOrphanData();
      setOrphanState({ phase: 'cleaned', result });
      // 清理完成后刷新文档列表
      await loadDocuments();
    } catch (err) {
      setOrphanState({ phase: 'error', message: getErrorMessage(err) });
    }
  };

  return (
    <div className="app-shell">
      <div className="app-main">
        <div style={{ width: 'min(100%, 960px)' }}>
          <div className="query-input-card" style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <div>
                <h1 className="panel-title" style={{ margin: 0 }}>文档管理</h1>
                <p className="page-description" style={{ margin: '6px 0 0' }}>
                  查看和管理已导入的文档，可以删除不需要的知识库内容。
                </p>
              </div>
              <button
                className="ghost-button"
                onClick={() => setShowOrphanPanel(!showOrphanPanel)}
                style={{ flexShrink: 0 }}
              >
                {showOrphanPanel ? '隐藏' : '显示'}孤儿数据面板
              </button>
            </div>

            {/* 孤儿数据清理面板 */}
            {showOrphanPanel && (
              <div
                style={{
                  marginBottom: 20,
                  padding: 20,
                  borderRadius: 10,
                  border: '2px solid #E2D9C8',
                  background: '#FBF7EF',
                }}
              >
                <h3 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600 }}>孤儿数据清理工具</h3>
                <p style={{ margin: '0 0 16px', fontSize: 14, color: '#8A8A80', lineHeight: 1.5 }}>
                  扫描并清理 Qdrant 和 Elasticsearch 中与 MySQL 不匹配的孤儿数据（已删除文档遗留的向量和索引）。
                </p>

                {orphanState.phase === 'error' && (
                  <div className="error-banner" style={{ marginBottom: 16 }}>
                    <strong>错误：</strong>
                    {orphanState.message}
                  </div>
                )}

                {orphanState.phase === 'scanning' && (
                  <div className="info-card compact" style={{ marginBottom: 16 }}>
                    <p style={{ margin: 0 }}>正在扫描孤儿数据...</p>
                  </div>
                )}

                {orphanState.phase === 'scanned' && (
                  <div style={{ marginBottom: 16 }}>
                    <div
                      style={{
                        padding: 16,
                        borderRadius: 8,
                        border: '1px solid #E2D9C8',
                        background: 'white',
                      }}
                    >
                      <p style={{ margin: '0 0 12px', fontWeight: 600, fontSize: 15 }}>扫描结果</p>
                      <p style={{ margin: '0 0 8px', fontSize: 14 }}>
                        MySQL 有效文档数：<strong>{orphanState.result.mysql_doc_count}</strong>
                      </p>
                      <div style={{ display: 'grid', gap: 12, marginTop: 12 }}>
                        <div
                          style={{
                            padding: 12,
                            borderRadius: 6,
                            background: orphanState.result.qdrant.orphans.length > 0 ? 'rgba(234, 179, 8, 0.08)' : 'rgba(52, 199, 89, 0.08)',
                            border: orphanState.result.qdrant.orphans.length > 0 ? '1px solid rgba(234, 179, 8, 0.25)' : '1px solid rgba(52, 199, 89, 0.25)',
                          }}
                        >
                          <p style={{ margin: 0, fontSize: 14 }}>
                            <strong>Qdrant：</strong>总计 {orphanState.result.qdrant.total} 个文档，
                            发现 <strong style={{ color: orphanState.result.qdrant.orphans.length > 0 ? '#ea8e00' : '#34c759' }}>
                              {orphanState.result.qdrant.orphans.length}
                            </strong> 个孤儿
                          </p>
                          {orphanState.result.qdrant.error && (
                            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-error)' }}>
                              扫描失败：{orphanState.result.qdrant.error}
                            </p>
                          )}
                        </div>
                        <div
                          style={{
                            padding: 12,
                            borderRadius: 6,
                            background: orphanState.result.elasticsearch.orphans.length > 0 ? 'rgba(234, 179, 8, 0.08)' : 'rgba(52, 199, 89, 0.08)',
                            border: orphanState.result.elasticsearch.orphans.length > 0 ? '1px solid rgba(234, 179, 8, 0.25)' : '1px solid rgba(52, 199, 89, 0.25)',
                          }}
                        >
                          <p style={{ margin: 0, fontSize: 14 }}>
                            <strong>Elasticsearch：</strong>总计 {orphanState.result.elasticsearch.total} 个文档，
                            发现 <strong style={{ color: orphanState.result.elasticsearch.orphans.length > 0 ? '#ea8e00' : '#34c759' }}>
                              {orphanState.result.elasticsearch.orphans.length}
                            </strong> 个孤儿
                          </p>
                          {orphanState.result.elasticsearch.error && (
                            <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-error)' }}>
                              扫描失败：{orphanState.result.elasticsearch.error}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>

                    {(orphanState.result.qdrant.orphans.length > 0 || orphanState.result.elasticsearch.orphans.length > 0) && (
                      <button
                        className="primary-button"
                        onClick={handleCleanupOrphans}
                        style={{ marginTop: 12, background: '#dc2626', borderColor: '#dc2626' }}
                      >
                        清理孤儿数据
                      </button>
                    )}
                  </div>
                )}

                {orphanState.phase === 'cleaning' && (
                  <div className="info-card compact" style={{ marginBottom: 16 }}>
                    <p style={{ margin: 0 }}>正在清理孤儿数据...</p>
                  </div>
                )}

                {orphanState.phase === 'cleaned' && (
                  <div
                    style={{
                      padding: 16,
                      borderRadius: 8,
                      border: '1px solid rgba(52, 199, 89, 0.25)',
                      background: 'rgba(52, 199, 89, 0.08)',
                      marginBottom: 16,
                    }}
                  >
                    <p style={{ margin: '0 0 12px', fontWeight: 600, color: '#34c759' }}>清理完成</p>
                    <p style={{ margin: '0 0 6px', fontSize: 14 }}>
                      Qdrant：删除 <strong>{orphanState.result.qdrant.deleted}</strong> 个
                      {orphanState.result.qdrant.failed > 0 && `，失败 ${orphanState.result.qdrant.failed} 个`}
                    </p>
                    <p style={{ margin: '0', fontSize: 14 }}>
                      Elasticsearch：删除 <strong>{orphanState.result.elasticsearch.deleted}</strong> 个
                      {orphanState.result.elasticsearch.failed > 0 && `，失败 ${orphanState.result.elasticsearch.failed} 个`}
                    </p>
                    <button
                      className="ghost-button"
                      onClick={() => setOrphanState({ phase: 'idle' })}
                      style={{ marginTop: 12 }}
                    >
                      关闭
                    </button>
                  </div>
                )}

                {orphanState.phase === 'idle' && (
                  <button className="primary-button" onClick={handleScanOrphans}>
                    开始扫描
                  </button>
                )}
              </div>
            )}

            {/* 删除确认模态框（单个 / 批量共用） */}
            {(selectedDocId !== null || batchConfirming) && deleteState.phase === 'idle' && (
              <>
                <div
                  style={{
                    position: 'fixed',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: 'rgba(0, 0, 0, 0.4)',
                    zIndex: 1000,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  onClick={handleCancelDelete}
                >
                  <div
                    className="query-input-card"
                    style={{
                      maxWidth: 480,
                      margin: 20,
                      padding: 24,
                      background: '#FBF7EF',
                      border: '2px solid rgba(200, 133, 63, 0.3)',
                      boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <h3 style={{ margin: '0 0 12px', fontSize: 18, fontWeight: 600, color: '#1F2421' }}>
                      {batchConfirming ? '确认批量删除' : '确认删除文档'}
                    </h3>
                    {batchConfirming ? (
                      <p style={{ margin: '0 0 8px', fontSize: 15, color: '#1F2421' }}>
                        已选中 <strong>{selectedIds.size}</strong> 个文档
                      </p>
                    ) : (
                      <p style={{ margin: '0 0 8px', fontSize: 15, color: '#1F2421' }}>
                        文档 ID: <strong>{selectedDocId}</strong>
                      </p>
                    )}
                    <p style={{ margin: 0, fontSize: 14, color: '#8A8A80', lineHeight: 1.6 }}>
                      此操作将永久删除{batchConfirming ? '这些文档' : '该文档'}及所有关联数据（分块、向量、图片等），删除后无法恢复。
                    </p>
                    <div style={{ display: 'flex', gap: 12, marginTop: 20, justifyContent: 'flex-end' }}>
                      <button className="ghost-button" onClick={handleCancelDelete}>
                        取消
                      </button>
                      <button
                        className="primary-button"
                        onClick={batchConfirming ? handleConfirmBatchDelete : handleConfirmDelete}
                        style={{ background: '#dc2626', borderColor: '#dc2626' }}
                      >
                        确认删除
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* 删除中状态 */}
            {deleteState.phase === 'deleting' && (
              <div className="info-card compact" style={{ marginBottom: 16 }}>
                <p style={{ margin: 0 }}>正在删除文档 {deleteState.documentId}...</p>
              </div>
            )}

            {/* 删除成功 */}
            {deleteState.phase === 'success' && (
              <div
                className="info-card compact"
                style={{
                  marginBottom: 16,
                  background: 'rgba(52, 199, 89, 0.08)',
                  border: '1px solid rgba(52, 199, 89, 0.25)',
                }}
              >
                <p style={{ margin: 0, fontWeight: 600, color: 'var(--color-success)' }}>删除成功</p>
                <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--color-text-secondary)' }}>
                  文档「{deleteState.response.title}」已删除
                </p>
                <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>
                  已删除：{deleteState.response.deleted_counts.chunks} 个分块、
                  {deleteState.response.deleted_counts.images} 张图片、
                  {deleteState.response.deleted_counts.qdrant_points} 个向量点、
                  {deleteState.response.deleted_counts.es_docs} 个搜索文档、
                  {deleteState.response.deleted_counts.minio_objects} 个存储对象
                </p>
              </div>
            )}

            {/* 批量删除中 */}
            {deleteState.phase === 'batch_deleting' && (
              <div className="info-card compact" style={{ marginBottom: 16 }}>
                <p style={{ margin: 0 }}>正在批量删除 {deleteState.count} 个文档...</p>
              </div>
            )}

            {/* 批量删除结果 */}
            {deleteState.phase === 'batch_success' && (
              <div
                className="info-card compact"
                style={{
                  marginBottom: 16,
                  background:
                    deleteState.response.failed > 0
                      ? 'rgba(234, 179, 8, 0.08)'
                      : 'rgba(52, 199, 89, 0.08)',
                  border:
                    deleteState.response.failed > 0
                      ? '1px solid rgba(234, 179, 8, 0.3)'
                      : '1px solid rgba(52, 199, 89, 0.25)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                  <p style={{ margin: 0, fontWeight: 600 }}>
                    批量删除完成：成功 {deleteState.response.succeeded} 个
                    {deleteState.response.failed > 0 && `，失败 ${deleteState.response.failed} 个`}
                  </p>
                  <button className="ghost-button" onClick={() => setDeleteState({ phase: 'idle' })}>
                    关闭
                  </button>
                </div>
                <p style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>
                  已删除：{deleteState.response.deleted_counts.chunks} 个分块、
                  {deleteState.response.deleted_counts.images} 张图片、
                  {deleteState.response.deleted_counts.qdrant_points} 个向量点、
                  {deleteState.response.deleted_counts.es_docs} 个搜索文档、
                  {deleteState.response.deleted_counts.minio_objects} 个存储对象
                </p>
                {deleteState.response.results
                  .filter((result) => !result.success)
                  .map((result) => (
                    <p
                      key={result.document_id}
                      style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--color-error)' }}
                    >
                      文档 {result.document_id}：{result.error}
                    </p>
                  ))}
              </div>
            )}

            {/* 删除失败 */}
            {deleteState.phase === 'error' && (
              <div className="error-banner" style={{ marginBottom: 16 }}>
                <strong>删除失败：</strong>
                {deleteState.message}
              </div>
            )}

            {/* 文档列表 */}
            {loading ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                加载中...
              </div>
            ) : documents.length === 0 ? (
              <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                暂无文档。请先<a href="/documents/import" style={{ color: 'var(--color-primary)' }}>导入文档</a>。
              </div>
            ) : (
              <>
                {/* 批量操作工具条 */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 14px',
                    marginBottom: 12,
                    borderRadius: 10,
                    border: '1px solid var(--color-border)',
                    background: 'rgba(0, 0, 0, 0.02)',
                  }}
                >
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={allOnPageSelected}
                      onChange={toggleSelectAllOnPage}
                      disabled={isBusy}
                      style={{ width: 16, height: 16, cursor: 'pointer' }}
                    />
                    全选本页
                  </label>
                  <span style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
                    已选 {selectedIds.size} 项
                  </span>
                  <button
                    className="ghost-button"
                    onClick={() => setBatchConfirming(true)}
                    disabled={selectedIds.size === 0 || isBusy}
                    style={{ marginLeft: 'auto', color: 'var(--color-error)' }}
                  >
                    批量删除
                  </button>
                </div>

                <div style={{ display: 'grid', gap: 12 }}>
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      style={{
                        padding: '16px 18px',
                        borderRadius: 10,
                        border: '1px solid var(--color-border)',
                        background: 'white',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 16,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(doc.id)}
                        onChange={() => toggleSelect(doc.id)}
                        disabled={isBusy}
                        style={{ width: 16, height: 16, flexShrink: 0, cursor: 'pointer' }}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ margin: 0, fontWeight: 500, fontSize: 15 }}>{doc.title}</p>
                        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--color-text-secondary)' }}>
                          ID: {doc.id}
                          &nbsp;·&nbsp;分块: {doc.chunk_count ?? '—'}
                          &nbsp;·&nbsp;图片: {doc.image_count ?? '—'}
                          &nbsp;·&nbsp;状态: {doc.process_status}
                        </p>
                        {doc.created_at && (
                          <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--color-text-tertiary)' }}>
                            导入时间: {new Date(doc.created_at).toLocaleString('zh-CN')}
                          </p>
                        )}
                      </div>
                      <button
                        className="ghost-button"
                        onClick={() => handleDeleteClick(doc.id)}
                        disabled={isBusy}
                        style={{ flexShrink: 0, color: 'var(--color-error)' }}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>

                {/* 分页 */}
                {total > pageSize && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 12,
                      marginTop: 20,
                    }}
                  >
                    <button
                      className="ghost-button"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1 || loading}
                    >
                      上一页
                    </button>
                    <span style={{ fontSize: 14, color: 'var(--color-text-secondary)' }}>
                      第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页
                    </span>
                    <button
                      className="ghost-button"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={page >= Math.ceil(total / pageSize) || loading}
                    >
                      下一页
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
