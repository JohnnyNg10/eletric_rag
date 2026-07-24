import { useEffect, useState } from 'react';
import { deleteDocument, listDocuments } from '../api/documents';
import { getErrorMessage } from '../api/client';
import type { DocumentDeleteResponse, DocumentListItem } from '../types/document';

type DeleteState =
  | { phase: 'idle' }
  | { phase: 'deleting'; documentId: number }
  | { phase: 'success'; response: DocumentDeleteResponse }
  | { phase: 'error'; message: string };

export function ManageDocumentsPage() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteState, setDeleteState] = useState<DeleteState>({ phase: 'idle' });
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  useEffect(() => {
    loadDocuments();
  }, [page]);

  const loadDocuments = async () => {
    setLoading(true);
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
    setDeleteState({ phase: 'idle' });
  };

  return (
    <div className="app-shell">
      <div className="app-main">
        <div style={{ width: 'min(100%, 960px)' }}>
          <div className="query-input-card" style={{ marginBottom: 24 }}>
            <h1 className="panel-title">文档管理</h1>
            <p className="page-description" style={{ marginBottom: 20 }}>
              查看和管理已导入的文档，可以删除不需要的知识库内容。
            </p>

            {/* 删除确认模态框 */}
            {selectedDocId !== null && deleteState.phase === 'idle' && (
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
                      确认删除文档
                    </h3>
                    <p style={{ margin: '0 0 8px', fontSize: 15, color: '#1F2421' }}>
                      文档 ID: <strong>{selectedDocId}</strong>
                    </p>
                    <p style={{ margin: 0, fontSize: 14, color: '#8A8A80', lineHeight: 1.6 }}>
                      此操作将永久删除该文档及所有关联数据（分块、向量、图片等），删除后无法恢复。
                    </p>
                    <div style={{ display: 'flex', gap: 12, marginTop: 20, justifyContent: 'flex-end' }}>
                      <button className="ghost-button" onClick={handleCancelDelete}>
                        取消
                      </button>
                      <button
                        className="primary-button"
                        onClick={handleConfirmDelete}
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
                        disabled={deleteState.phase === 'deleting'}
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
