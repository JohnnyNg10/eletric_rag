"""
文档管理 API 端点
"""
import os
import uuid
import logging
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import Document, User
from app.schemas.document import DocumentImportResponse, DocumentStatusResponse, DocumentDeleteResponse, DocumentListResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_IMPORT_TMP_DIR = "/tmp/rag_import"
_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _has_text_layer(pdf_path: str) -> bool:
    """判断 PDF 是否有文字层（≥50% 的页面含有效文字）"""
    try:
        doc = fitz.open(pdf_path)
        total = len(doc)
        if total == 0:
            doc.close()
            return False
        with_text = sum(
            1 for page in doc if len(page.get_text().strip()) > 50
        )
        doc.close()
        return with_text / total >= 0.5
    except Exception as e:
        logger.warning(f"文字层检测失败: {e}")
        return False


@router.post("/import", response_model=DocumentImportResponse)
async def import_document(
    file: UploadFile = File(...),
    process_mode: str = Form("auto"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导入 PDF 文档（支持文字版 / 扫描件 / 自动识别）"""
    # 校验文件类型
    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="仅支持 PDF 文件",
            )

    # 校验 process_mode
    if process_mode not in ("auto", "text_pdf", "scanned_pdf"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="process_mode 必须为 auto / text_pdf / scanned_pdf",
        )

    # 读取文件内容并校验大小
    content = await file.read()
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件大小不能超过 100 MB",
        )

    # 保存到临时目录
    os.makedirs(_IMPORT_TMP_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{Path(filename).name}"
    tmp_path = os.path.join(_IMPORT_TMP_DIR, safe_name)
    with open(tmp_path, "wb") as fh:
        fh.write(content)

    # 检测文字层
    has_text = _has_text_layer(tmp_path)
    detected_type = "text_pdf" if has_text else "scanned_pdf"

    # text_pdf 模式强制要求文字层
    if process_mode == "text_pdf" and not has_text:
        os.unlink(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PDF 未检测到有效文字层，请选择扫描件模式或自动识别",
        )

    # 决定实际处理路径
    use_scanned = process_mode == "scanned_pdf" or (
        process_mode == "auto" and not has_text
    )

    if use_scanned:
        from app.tasks.scan_processor_tasks import process_scanned_pdf_task

        # 扫描件路径：先建 Document 记录拿到 doc_id，再派发任务
        doc = Document(
            title=Path(filename).stem,
            doc_type="standard",
            file_path=f"scanned_pdfs/pending/{safe_name}",
            is_scanned=True,
            process_status="processing",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        task = process_scanned_pdf_task.delay(tmp_path, doc.id)

        return DocumentImportResponse(
            task_id=task.id,
            document_id=doc.id,
            status="processing",
            process_mode=process_mode,
            detected_type=detected_type,
            is_scanned=True,
            message="扫描件处理任务已提交，请轮询状态接口获取进度",
        )
    else:
        from app.tasks.document_tasks import ingest_text_pdf_task

        # 文字版路径：ingestion_pipeline 内部创建 Document，只返回 task_id
        task = ingest_text_pdf_task.delay(tmp_path)

        return DocumentImportResponse(
            task_id=task.id,
            document_id=None,
            status="processing",
            process_mode=process_mode,
            detected_type=detected_type,
            is_scanned=False,
            message="文档入库任务已提交，处理完成后将出现在搜索结果中",
        )


@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取文档列表（分页）"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    # 查询总数
    total = db.query(Document).count()

    # 查询当前页数据
    offset = (page - 1) * page_size
    documents = (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return DocumentListResponse(
        items=documents,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询文档处理状态"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {document_id} 不存在",
        )
    return doc


@router.delete("/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除文档及所有关联数据（MySQL、Qdrant、Elasticsearch、MinIO）"""
    from app.db.models import Chunk, Image, Table
    from app.storage.vector_store import vector_store
    from app.storage.search_engine import search_engine
    from app.storage.object_store import object_store

    # 1. 查询文档
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档 {document_id} 不存在",
        )

    doc_title = doc.title
    deleted_counts = {
        "chunks": 0,
        "images": 0,
        "tables": 0,
        "qdrant_points": 0,
        "es_docs": 0,
        "minio_objects": 0
    }

    # 2. 删除 Qdrant 向量点
    try:
        chunk_count = db.query(Chunk).filter(Chunk.document_id == document_id).count()
        if chunk_count:
            vector_store.delete_by_doc_id(str(document_id))
            deleted_counts["qdrant_points"] = chunk_count
            logger.info(f"已删除 {chunk_count} 个 Qdrant 向量点")
    except Exception as e:
        logger.warning(f"删除 Qdrant 向量失败: {e}")

    # 3. 删除 Elasticsearch 文档
    try:
        chunks = db.query(Chunk).filter(Chunk.document_id == document_id).all()
        if chunks:
            # 使用 doc_id 删除所有关联的 chunks
            search_engine.delete_by_doc_id(str(document_id))
            deleted_counts["es_docs"] = len(chunks)
            logger.info(f"已删除 {len(chunks)} 个 ES 文档")
    except Exception as e:
        logger.warning(f"删除 ES 文档失败: {e}")

    # 4. 删除 MinIO 对象
    try:
        # 删除 PDF
        if doc.file_path:
            object_store.delete_object(object_store.pdf_bucket, doc.file_path)
            deleted_counts["minio_objects"] += 1

        # 删除 Markdown
        if doc.markdown_path:
            object_store.delete_object(object_store.markdown_bucket, doc.markdown_path)
            deleted_counts["minio_objects"] += 1

        # 删除图片
        images = db.query(Image).filter(Image.document_id == document_id).all()
        for img in images:
            if img.minio_path:
                object_store.delete_object(object_store.image_bucket, img.minio_path)
                deleted_counts["minio_objects"] += 1

        logger.info(f"已删除 {deleted_counts['minio_objects']} 个 MinIO 对象")
    except Exception as e:
        logger.warning(f"删除 MinIO 对象失败: {e}")

    # 5. 删除 MySQL 记录（级联删除 chunks/images/tables）
    deleted_counts["chunks"] = db.query(Chunk).filter(Chunk.document_id == document_id).count()
    deleted_counts["images"] = db.query(Image).filter(Image.document_id == document_id).count()
    deleted_counts["tables"] = db.query(Table).filter(Table.document_id == document_id).count()

    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    db.query(Image).filter(Image.document_id == document_id).delete()
    db.query(Table).filter(Table.document_id == document_id).delete()
    db.delete(doc)
    db.commit()

    logger.info(f"文档 {document_id} ({doc_title}) 已完全删除")

    return DocumentDeleteResponse(
        document_id=document_id,
        title=doc_title,
        message="文档及所有关联数据已删除",
        deleted_counts=deleted_counts
    )
