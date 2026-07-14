"""
Scanned PDF processing tasks
扫描件PDF异步处理任务
"""
import logging
import asyncio
from typing import Dict, List, Optional
from celery import shared_task
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Document, Chunk, Image, Table
from app.config import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_scanned_pdf_task(self, pdf_path: str, doc_id: int) -> Dict:
    """
    异步处理扫描件 PDF

    Args:
        pdf_path: PDF 文件路径
        doc_id: 文档 ID

    Returns:
        处理结果统计
    """
    try:
        # 更新处理状态
        self.update_state(state='PROCESSING', meta={'progress': 0, 'stage': 'initializing'})

        # 导入处理器（延迟导入以避免启动时加载重模型）
        from app.core.scan_processor.processor import ScannedPDFProcessor

        processor = ScannedPDFProcessor()

        # 处理文档（同步运行异步代码）
        result = asyncio.run(processor.process_document(pdf_path, doc_id))

        logger.info(f"扫描件处理完成: doc_id={doc_id}, pages={result['page_count']}, images={result['image_count']}")

        return {
            'status': 'success',
            'doc_id': doc_id,
            'pages_processed': result['page_count'],
            'images_extracted': result['image_count'],
            'tables_extracted': result['table_count'],
            'ocr_avg_confidence': result.get('ocr_avg_confidence', 0.0)
        }

    except Exception as e:
        logger.error(f"扫描件处理失败: doc_id={doc_id}, error={e}", exc_info=True)

        # 更新文档状态为失败
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.process_status = 'failed'
                doc.process_error = str(e)
                db.commit()
        finally:
            db.close()

        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task
def batch_process_scanned_pdfs(pdf_list: List[tuple]) -> Dict:
    """
    批量处理扫描件PDF

    Args:
        pdf_list: [(pdf_path, doc_id), ...]

    Returns:
        批量处理结果
    """
    logger.info(f"开始批量处理 {len(pdf_list)} 个扫描件PDF")

    # 分发任务到多个worker
    tasks = [
        process_scanned_pdf_task.apply_async(args=[pdf_path, doc_id])
        for pdf_path, doc_id in pdf_list
    ]

    # 收集结果
    results = []
    for task in tasks:
        try:
            result = task.get(timeout=600)  # 10分钟超时
            results.append(result)
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            results.append({'status': 'failed', 'error': str(e)})

    success_count = sum(1 for r in results if r.get('status') == 'success')

    return {
        'total': len(pdf_list),
        'success': success_count,
        'failed': len(pdf_list) - success_count,
        'results': results
    }
