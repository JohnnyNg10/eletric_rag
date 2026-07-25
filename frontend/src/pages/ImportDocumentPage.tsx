import { useEffect, useRef, useState } from 'react';
import { importDocument, getDocumentStatus } from '../api/documents';
import { getErrorMessage } from '../api/client';
import type { DocumentImportResponse, DocumentStatusResponse, ProcessMode } from '../types/document';

type FileUploadTask = {
  file: File;
  taskId?: string | null;
  documentId?: number | null;
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'failed';
  message?: string;
  response?: DocumentImportResponse;
  statusData?: DocumentStatusResponse;
};

type UploadState =
  | { phase: 'idle' }
  | { phase: 'batch_uploading'; tasks: FileUploadTask[] }
  | { phase: 'batch_completed'; tasks: FileUploadTask[] };

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

// 当前可用的处理模式（禁用 auto 和 scanned_pdf）
const AVAILABLE_MODES: ProcessMode[] = ['text_pdf'];

export function ImportDocumentPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [processMode, setProcessMode] = useState<ProcessMode>('text_pdf');
  const [customStandardNo, setCustomStandardNo] = useState('');
  const [uploadState, setUploadState] = useState<UploadState>({ phase: 'idle' });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 清理轮询定时器
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = (tasks: FileUploadTask[]) => {
    if (pollRef.current) clearInterval(pollRef.current);

    pollRef.current = setInterval(async () => {
      const updatedTasks = await Promise.all(
        tasks.map(async (task) => {
          if (task.status === 'processing' && task.documentId) {
            try {
              const status = await getDocumentStatus(task.documentId);
              if (status.process_status === 'completed') {
                return { ...task, status: 'completed' as const, statusData: status };
              } else if (status.process_status === 'failed') {
                return { ...task, status: 'failed' as const, message: status.process_error || '处理失败' };
              }
            } catch {
              // 轮询失败不中断
            }
          }
          return task;
        })
      );

      const allDone = updatedTasks.every(t => t.status === 'completed' || t.status === 'failed');
      if (allDone && pollRef.current) {
        clearInterval(pollRef.current);
        setUploadState({ phase: 'batch_completed', tasks: updatedTasks });
      } else {
        setUploadState({ phase: 'batch_uploading', tasks: updatedTasks });
      }
    }, 3000);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setSelectedFiles(files);
    setUploadState({ phase: 'idle' });
  };

  const handleSubmit = async () => {
    if (selectedFiles.length === 0) return;

    const tasks: FileUploadTask[] = selectedFiles.map(file => ({
      file,
      status: 'pending' as const,
    }));

    setUploadState({ phase: 'batch_uploading', tasks });

    // 并行上传所有文件
    const uploadPromises = tasks.map(async (task, index) => {
      try {
        tasks[index].status = 'uploading';
        setUploadState({ phase: 'batch_uploading', tasks: [...tasks] });

        const response = await importDocument(task.file, processMode, customStandardNo || undefined);

        tasks[index].response = response;
        tasks[index].taskId = response.task_id;
        tasks[index].documentId = response.document_id || undefined;
        tasks[index].status = response.document_id ? 'processing' : 'completed';
        tasks[index].message = response.message;

        setUploadState({ phase: 'batch_uploading', tasks: [...tasks] });
      } catch (err) {
        tasks[index].status = 'failed';
        tasks[index].message = getErrorMessage(err);
        setUploadState({ phase: 'batch_uploading', tasks: [...tasks] });
      }
    });

    await Promise.all(uploadPromises);

    // 开始轮询有 document_id 的任务
    const tasksToPolll = tasks.filter(t => t.status === 'processing');
    if (tasksToPolll.length > 0) {
      startPolling(tasks);
    } else {
      setUploadState({ phase: 'batch_completed', tasks });
    }
  };

  const handleReset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setSelectedFiles([]);
    setCustomStandardNo('');
    setUploadState({ phase: 'idle' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const isSubmitting = uploadState.phase === 'batch_uploading';

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
                选择 PDF 文件（支持多选，单个最大 100 MB）
              </label>
              <input
                id="pdf-file-input"
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                multiple
                onChange={handleFileChange}
                disabled={isSubmitting}
                className="text-input"
                style={{ padding: '10px 14px', cursor: 'pointer' }}
              />

              {selectedFiles.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {selectedFiles.map((f, i) => (
                    <p key={i} className="helper-text" style={{ margin: 0 }}>
                      {f.name}（{(f.size / 1024 / 1024).toFixed(2)} MB）
                    </p>
                  ))}
                  {selectedFiles.length > 1 && (
                    <p className="helper-text" style={{ margin: 0, fontWeight: 500 }}>
                      共 {selectedFiles.length} 个文件，将并行处理
                    </p>
                  )}
                </div>
              )}

              {/* 自定义标准号 */}
              <div>
                <label className="field-label" htmlFor="custom-standard-no">
                  标准号（可选，留空自动识别）
                </label>
                <input
                  id="custom-standard-no"
                  type="text"
                  className="text-input"
                  placeholder="例：Q/CSG-2024、T/CEC 001-2023"
                  value={customStandardNo}
                  onChange={(e) => setCustomStandardNo(e.target.value)}
                  disabled={isSubmitting}
                  style={{ marginTop: 6 }}
                />
                <p className="helper-text" style={{ marginTop: 4 }}>
                  用于企业标准或系统无法自动识别的标准号，输入后将覆盖自动识别结果
                </p>
              </div>

              {/* 处理模式 */}
              <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
                <legend className="field-label" style={{ marginBottom: 10 }}>
                  处理模式
                </legend>
                <div style={{ display: 'grid', gap: 8 }}>
                  {(Object.keys(PROCESS_MODE_LABELS) as ProcessMode[]).map((mode) => {
                    const available = AVAILABLE_MODES.includes(mode);
                    return (
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
                        cursor: (!available || isSubmitting) ? 'not-allowed' : 'pointer',
                        opacity: (!available || isSubmitting) ? 0.4 : 1,
                        transition: 'all 0.15s',
                      }}
                    >
                      <input
                        type="radio"
                        name="process_mode"
                        value={mode}
                        checked={processMode === mode}
                        onChange={() => available && setProcessMode(mode)}
                        disabled={!available || isSubmitting}
                        style={{ marginTop: 2 }}
                      />
                      <span>
                        <span style={{ fontWeight: 500, fontSize: 14 }}>
                          {PROCESS_MODE_LABELS[mode]}
                          {!available && <span style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginLeft: 6 }}>（暂不可用）</span>}
                        </span>
                        <span
                          style={{ display: 'block', fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}
                        >
                          {PROCESS_MODE_DESCS[mode]}
                        </span>
                      </span>
                    </label>
                    );
                  })}
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
                disabled={selectedFiles.length === 0 || isSubmitting}
              >
                {isSubmitting
                  ? `处理中…（${
                      uploadState.phase === 'batch_uploading'
                        ? uploadState.tasks.filter(t => t.status === 'completed' || t.status === 'failed').length
                        : 0
                    }/${selectedFiles.length}）`
                  : selectedFiles.length > 1
                    ? `批量导入 ${selectedFiles.length} 个文件`
                    : '开始导入'}
              </button>
            </div>
          </div>

          {/* 批量上传状态面板 */}
          {(uploadState.phase === 'batch_uploading' || uploadState.phase === 'batch_completed') && (
            <div className="info-card compact" style={{
              marginTop: 0,
              ...(uploadState.phase === 'batch_completed' && {
                background: 'rgba(52,199,89,0.08)',
                border: '1px solid rgba(52,199,89,0.25)'
              })
            }}>
              <p style={{ margin: '0 0 8px', fontWeight: 600 }}>
                {uploadState.phase === 'batch_completed' ? '全部完成' : '正在处理…'}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {uploadState.tasks.map((task, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                    <span style={{
                      width: 64,
                      flexShrink: 0,
                      padding: '1px 6px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 500,
                      textAlign: 'center',
                      background:
                        task.status === 'completed' ? 'rgba(52,199,89,0.15)' :
                        task.status === 'failed' ? 'rgba(255,59,48,0.15)' :
                        task.status === 'processing' ? 'rgba(0,122,255,0.12)' :
                        'rgba(0,0,0,0.06)',
                      color:
                        task.status === 'completed' ? 'var(--color-success)' :
                        task.status === 'failed' ? 'var(--color-error, #ff3b30)' :
                        task.status === 'processing' ? 'var(--color-primary)' :
                        'var(--color-text-secondary)',
                    }}>
                      {task.status === 'completed' ? '完成' :
                       task.status === 'failed' ? '失败' :
                       task.status === 'processing' ? '处理中' :
                       task.status === 'uploading' ? '上传中' : '等待'}
                    </span>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {task.file.name}
                    </span>
                    {task.status === 'failed' && task.message && (
                      <span style={{ color: 'var(--color-error, #ff3b30)', fontSize: 11 }}>{task.message}</span>
                    )}
                    {task.status === 'completed' && task.statusData && (
                      <span style={{ color: 'var(--color-text-secondary)', fontSize: 11 }}>
                        {task.statusData.chunk_count ?? '—'} 块
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
