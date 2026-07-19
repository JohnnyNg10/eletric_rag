"""
文字版 PDF 入库任务
"""
import logging
from typing import Dict, Optional
from celery import shared_task

from app.db.session import SessionLocal
from app.db.models import Document

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def ingest_text_pdf_task(self, pdf_path: str) -> Dict:
    """
    异步处理文字版 PDF（含 VLM 解析）

    Args:
        pdf_path: 本地 PDF 文件路径

    Returns:
        入库结果 {"status": "success", "doc_id": ..., "chunks_count": ...}
    """
    try:
        self.update_state(state='PROCESSING', meta={'stage': 'ingesting'})

        from app.core.ingestion_pipeline import ingestion_pipeline
        result = ingestion_pipeline.ingest_document(pdf_path)

        if not result.get('success'):
            raise RuntimeError(result.get('error', '入库失败'))

        logger.info(
            f"文字PDF入库完成: doc_id={result['document_id']}, chunks={result['chunks_count']}"
        )
        return {
            'status': 'success',
            'doc_id': result['document_id'],
            'chunks_count': result['chunks_count'],
            'images_count': result.get('images_count', 0),
            'skipped': result.get('skipped', False),
        }

    except Exception as e:
        logger.error(f"文字PDF入库失败: path={pdf_path}, error={e}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
