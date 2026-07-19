"""
Celery Tasks Module
"""
from app.tasks.celery_app import celery
from app.tasks.scan_processor_tasks import process_scanned_pdf_task
from app.tasks.document_tasks import ingest_text_pdf_task

__all__ = ['celery', 'process_scanned_pdf_task', 'ingest_text_pdf_task']
