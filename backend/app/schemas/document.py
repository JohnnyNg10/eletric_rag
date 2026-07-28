"""
文档相关 Pydantic 模式
"""
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel


class DocumentImportResponse(BaseModel):
    task_id: Optional[str] = None
    document_id: Optional[int] = None
    status: Literal["processing", "completed", "failed"]
    process_mode: Literal["auto", "text_pdf", "scanned_pdf"]
    detected_type: Literal["text_pdf", "scanned_pdf"]
    is_scanned: bool
    message: str


class DocumentStatusResponse(BaseModel):
    id: int
    title: str
    process_status: Literal["pending", "processing", "completed", "failed"]
    process_error: Optional[str] = None
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    image_count: Optional[int] = None
    table_count: Optional[int] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentDeleteResponse(BaseModel):
    document_id: int
    title: str
    message: str
    deleted_counts: dict


class DocumentBatchDeleteRequest(BaseModel):
    document_ids: list[int]


class DocumentDeleteResult(BaseModel):
    document_id: int
    title: Optional[str] = None
    success: bool
    error: Optional[str] = None
    deleted_counts: Optional[dict] = None


class DocumentBatchDeleteResponse(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[DocumentDeleteResult]
    deleted_counts: dict


class DocumentListItem(BaseModel):
    id: int
    title: str
    doc_type: str
    process_status: str
    chunk_count: Optional[int] = None
    image_count: Optional[int] = None
    table_count: Optional[int] = None
    page_count: Optional[int] = None
    created_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int
