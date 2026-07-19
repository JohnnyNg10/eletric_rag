import { useEffect, useRef, useState } from 'react';
import { importDocument, getDocumentStatus } from '../api/documents';
import { getErrorMessage } from '../api/client';
import type { DocumentImportResponse, DocumentStatusResponse, ProcessMode } from '../types/document';

type UploadState =
  | { phase: 'idle' }
  | { phase: 'uploading' }
  | { phase: 'processing'; response: DocumentImportResponse }
  | { phase: 'completed'; response: DocumentImportResponse; status?: DocumentStatusResponse }
  | { phase: 'failed'; message: string };

const PROCESS_MODE_LABELS: Record<ProcessMode, string> = {
  auto: '自动识别',
  text_pdf: '文字版 PDF',
  scanned_pdf: '扫描件',
};

const PROCESS_MODE_DESCS: Record<ProcessMode, string> = {
  auto: '自动检测文字层，选择最优处理路径',
  text_pdf: '仅处理含文字层的 PDF，扫描件将报错',
  scanned_pdf: '强制使用 VLM 逐页识别',
};

const STATUS_LABEL: Record<string, string> = {
  pending: '等待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
};

export function ImportDocumentPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [processMode, setProcessMode] = useState<ProcessMode>('auto');
  const [uploadState, setUploadState] = useState<UploadState>({ phase: 'idle' });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 清理轮询定时器
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = (docId: number) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      try {
        const status = await getDocumentStatus(docId);
        setUploadState((prev) => {
          if (prev.phase !== 'processing' && prev.phase !== 'completed') return prev;
          const response = prev.phase === 'processing' ? prev.response : (prev as { response: DocumentImportResponse }).response;
          if (status.process_status === 'completed' || status.process_status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            if (status.process_status === 'failed') {
              return { phase: 'failed', message: status.process_error || '处理失败' };
            }
            return { phase: 'completed', response, status };
          }
          return { phase: 'processing', response };
        });
      } catch {
        // 轮询失败不中断，等待下次重试
      }
    }, 3000);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadState({ phase: 'idle' });
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;

    setUploadState({ phase: 'uploading' });

    try {
      const response = await importDocument(selectedFile, processMode);

      if (response.document_id) {
        setUploadState({ phase: 'processing', response });
        startPolling(response.document_id);
      } else {
        // 文字版 PDF：pipeline 内部创建文档，无法立即获得 doc_id
        setUploadState({ phase: 'completed', response });
      }
    } catch (err) {
      setUploadState({ phase: 'failed', message: getErrorMessage(err) });
    }
  };

  const handleReset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setSelectedFile(null);
    setUploadState({ phase: 'idle' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isSubmitting =
    uploadState.phase === 'uploading' || uploadState.phase === 'processing';

  return (
    <div className="app-shell">
      <div className="app-main">
        <div style={{ width: 'min(100%, 640px)' }}>
          <div className="query-input-card" style={{ marginBottom: 24 }}>
            <h1 className="panel-title">导入文档</h1>
            <p className="page-description" style={{ marginBottom: 20 }}>
              上传 PDF 文件，系统将自动解析、分块并建立向量索引，完成后可在搜索中检索其内容。
            </p>

            {/* 文件选择 */}
            <div className="stack-form">
              <label className="field-label" htmlFor="pdf-file-input">
                选择 PDF 文件（最大 100 MB）
              </label>
              <input
                id="pdf-file-input"
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                disabled={isSubmitting}
                className="text-input"
                style={{ padding: '10px 14px', cursor: 'pointer' }}
              />

              {selectedFile && (
                <p className="helper-text">
                  已选择：{selectedFile.name}（{(selectedFile.size / 1024 / 1024).toFixed(2)} MB）
                </p>
              )}

              {/* 处理模式 */}
              <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
                <legend className="field-label" style={{ marginBottom: 10 }}>
                  处理模式
                </legend>
                <div style={{ display: 'grid', gap: 8 }}>
                  {(Object.keys(PROCESS_MODE_LABELS) as ProcessMode[]).map((mode) => (
                    <label
                      key={mode}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 10,
                        padding: '12px 14px',
                        borderRadius: 10,
                        border: `1.5px solid ${processMode === mode ? 'var(--color-primary)' : 'var(--color-border)'}`,
                        background: processMode === mode ? 'rgba(0,122,255,0.04)' : 'white',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        opacity: isSubmitting ? 0.5 : 1,
                        transition: 'all 0.15s',
                      }}
                    >
                      <input
                        type="radio"
                        name="process_mode"
                        value={mode}
                        checked={processMode === mode}
                        onChange={() => setProcessMode(mode)}
                        disabled={isSubmitting}
                        style={{ marginTop: 2 }}
                      />
                      <span>
                        <span style={{ fontWeight: 500, fontSize: 14 }}>
                          {PROCESS_MODE_LABELS[mode]}
                        </span>
                        <span
                          style={{ display: 'block', fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}
                        >
                          {PROCESS_MODE_DESCS[mode]}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>

            <div className="panel-actions end" style={{ marginTop: 20 }}>
              {uploadState.phase !== 'idle' && (
                <button className="ghost-button" onClick={handleReset} disabled={isSubmitting}>
                  重置
                </button>
              )}
              <button
                className="primary-button large"
                onClick={handleSubmit}
                disabled={!selectedFile || isSubmitting}
              >
                {uploadState.phase === 'uploading'
                  ? '上传中…'
                  : uploadState.phase === 'processing'
                    ? '处理中…'
                    : '开始导入'}
              </button>
            </div>
          </div>

          {/* 状态面板 */}
          {uploadState.phase === 'processing' && (
            <div className="info-card compact" style={{ marginTop: 0 }}>
              <p style={{ margin: 0, fontWeight: 500 }}>任务已提交</p>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                task_id：{uploadState.response.task_id}
              </p>
              {uploadState.response.document_id && (
                <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                  文档 ID：{uploadState.response.document_id}，正在轮询状态…
                </p>
              )}
              <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                检测类型：{uploadState.response.detected_type === 'text_pdf' ? '文字版 PDF' : '扫描件'}
              </p>
            </div>
          )}

          {uploadState.phase === 'completed' && (
            <div
              className="info-card compact"
              style={{ marginTop: 0, background: 'rgba(52,199,89,0.08)', border: '1px solid rgba(52,199,89,0.25)' }}
            >
              {uploadState.status ? (
                <>
                  <p style={{ margin: 0, fontWeight: 600, color: 'var(--color-success)' }}>处理完成</p>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                    标题：{uploadState.status.title}
                  </p>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                    状态：{STATUS_LABEL[uploadState.status.process_status]}
                    &nbsp;·&nbsp;分块数：{uploadState.status.chunk_count ?? '—'}
                    &nbsp;·&nbsp;图片数：{uploadState.status.image_count ?? '—'}
                  </p>
                </>
              ) : (
                <>
                  <p style={{ margin: 0, fontWeight: 600, color: 'var(--color-success)' }}>任务已提交</p>
                  <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                    {uploadState.response.message}
                  </p>
                </>
              )}
            </div>
          )}

          {uploadState.phase === 'failed' && (
            <div className="error-banner">
              <strong>导入失败：</strong>
              {uploadState.message}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
