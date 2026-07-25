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
def ingest_text_pdf_task(self, pdf_path: str, custom_standard_no: Optional[str] = None) -> Dict:
    """
    异步处理文字版 PDF（含 VLM 解析）

    Args:
        pdf_path: 本地 PDF 文件路径
        custom_standard_no: 用户自定义标准号，优先级高于自动识别

    Returns:
        入库结果 {"status": "success", "doc_id": ..., "chunks_count": ...}
    """
    from celery.exceptions import Ignore

    try:
        self.update_state(state='PROCESSING', meta={'stage': 'ingesting'})

        from app.core.ingestion_pipeline import ingestion_pipeline
        result = ingestion_pipeline.ingest_document(pdf_path, custom_standard_no=custom_standard_no)

        if not result.get('success'):
            error_msg = result.get('error', '入库失败')
            logger.error(f"文字PDF入库失败: path={pdf_path}, error={error_msg}")
            # 用 update_state 标记失败，不 raise 异常避免 Celery worker 崩溃
            self.update_state(state='FAILURE', meta={'error': error_msg, 'path': pdf_path})
            raise Ignore()

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

    except Ignore:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"文字PDF入库失败: path={pdf_path}, error={error_msg}", exc_info=True)
        self.update_state(state='FAILURE', meta={'error': error_msg, 'path': pdf_path})
        raise Ignore()
