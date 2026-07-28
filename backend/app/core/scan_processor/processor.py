"""
Scanned PDF Processor
扫描件PDF处理器 - 统一使用 MinerU（带 VLM）处理所有扫描件
"""
import logging
from typing import Dict
from pathlib import Path

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Document
from app.core.document_processor.mineru_client import mineru_client
from app.core.document_processor.chunker import document_chunker
from app.core.document_processor.metadata_extractor import metadata_extractor
from app.core.embedding.embedder import get_embedder
from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store

logger = logging.getLogger(__name__)


class ScannedPDFProcessor:
    """扫描件PDF处理器（统一使用 MinerU）"""

    def __init__(self):
        """初始化处理器"""
        self.mineru_client = mineru_client
        self.embedder = get_embedder()
        self.vector_store = vector_store
        self.search_engine = search_engine
        self.object_store = object_store

        logger.info("ScannedPDFProcessor初始化完成（MinerU + VLM 模式）")

    async def process_document(self, pdf_path: str, doc_id: int) -> Dict:
        """
        处理单个扫描件PDF（使用 MinerU + VLM）

        Args:
            pdf_path: PDF文件路径
            doc_id: 文档ID

        Returns:
            处理结果统计
        """
        logger.info(f"开始处理扫描件PDF（MinerU + VLM）: doc_id={doc_id}, path={pdf_path}")

        pdf_path = Path(pdf_path)

        try:
            # 1. 健康检查 MinerU 服务
            if not self._check_mineru_availability():
                raise RuntimeError("MinerU 服务不可用，无法处理扫描件")

            # 2. 调用 MinerU 解析（启用 VLM 图像分析）
            logger.info("调用 MinerU API 解析扫描件...")
            result = self.mineru_client.parse_with_retry(
                str(pdf_path),
                mode="async",
                backend=settings.MINERU_BACKEND,
                poll_interval=settings.MINERU_ASYNC_POLL_INTERVAL,
                max_poll_time=settings.MINERU_ASYNC_MAX_POLL_TIME,
                max_retries=2,
                return_content_list=True,
                # 关键：启用图像分析（VLM）
                image_analysis=True,
                formula_enable=True,
                table_enable=True,
            )

            md_content = result["md_content"]
            content_list = result.get("content_list", [])

            logger.info(f"MinerU 解析完成: 内容长度={len(md_content)} 字符, 结构化块={len(content_list)} 个")

            # 3. 提取元数据
            db = SessionLocal()
            try:
                document = db.query(Document).filter(Document.id == doc_id).first()
                if not document:
                    raise RuntimeError(f"文档记录不存在: doc_id={doc_id}")

                metadata = metadata_extractor.extract_from_document(
                    content=md_content,
                    filename=pdf_path.name,
                    parsed_metadata={}
                )

                # 4. 上传原始 PDF 到 MinIO
                minio_pdf_path = f"scanned_pdfs/doc_{doc_id}/original.pdf"
                self.object_store.upload_pdf(str(pdf_path), minio_pdf_path)
                logger.info(f"原始PDF已上传: {minio_pdf_path}")

                # 5. 上传 Markdown 到 MinIO
                minio_md_path = f"scanned_markdown/doc_{doc_id}/full.md"
                self.object_store.upload_markdown(md_content, minio_md_path)
                logger.info(f"Markdown已保存: {minio_md_path}")

                # 6. 处理图片（从 content_list 提取）
                images_count = self._process_images_from_content_list(
                    content_list, doc_id, metadata, db, pdf_path
                )

                # 7. 文档分块
                logger.info("开始文档分块...")
                chunks = document_chunker.chunk_document(
                    content=md_content,
                    doc_metadata=metadata,
                    document_id=doc_id,
                    doc_type=metadata.get('doc_type', 'standard')
                )
                logger.info(f"分块完成: {len(chunks)} 个块")

                # 8. 向量化并索引
                indexed_count = await self._vectorize_and_index(chunks, doc_id, metadata, db)

                # 9. 更新文档元数据
                document.is_scanned = True
                document.ocr_engine = "MinerU+VLM"
                document.ocr_version = settings.MINERU_BACKEND
                document.ocr_confidence = 0.95  # MinerU+VLM 模式高置信度
                document.image_count = images_count
                document.table_count = md_content.count('<table>')  # 粗略统计
                document.process_status = 'completed'
                document.markdown_path = minio_md_path
                document.chunk_count = indexed_count

                db.commit()
                logger.info(f"文档元数据已更新: doc_id={doc_id}")

                logger.info(f"扫描件处理完成: doc_id={doc_id}, chunks={indexed_count}, images={images_count}")

                return {
                    'page_count': metadata.get('page_count', 0),
                    'image_count': images_count,
                    'table_count': document.table_count,
                    'chunk_count': indexed_count,
                    'ocr_avg_confidence': 0.95
                }

            finally:
                db.close()

        except Exception as e:
            logger.error(f"扫描件处理失败: doc_id={doc_id}, error={e}", exc_info=True)

            # 更新文档状态为失败
            db = SessionLocal()
            try:
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    doc.process_status = 'failed'
                    doc.error_message = str(e)
                    db.commit()
            finally:
                db.close()

            raise

    def _check_mineru_availability(self) -> bool:
        """检查 MinerU 服务可用性"""
        if not settings.MINERU_ENABLED:
            logger.error("MinerU 已在配置中禁用")
            return False

        is_available = self.mineru_client.health_check()
        if not is_available:
            logger.error("MinerU 服务健康检查失败")
        return is_available

    def _process_images_from_content_list(
        self,
        content_list: list,
        doc_id: int,
        metadata: Dict,
        db,
        pdf_path: Path
    ) -> int:
        """
        从 MinerU 的 content_list 中提取图片并索引

        Args:
            content_list: MinerU 返回的结构化内容列表
            doc_id: 文档ID
            metadata: 文档元数据
            db: 数据库会话
            pdf_path: PDF 文件路径

        Returns:
            处理成功的图片数量
        """
        from app.db.models import Image, Chunk as DBChunk
        import hashlib
        import tempfile
        import os

        if not content_list:
            logger.info("content_list 为空，跳过图片处理")
            return 0

        # 如果 content_list 是 JSON 字符串，先解析
        if isinstance(content_list, str):
            try:
                import json
                content_list = json.loads(content_list)
            except Exception as e:
                logger.warning(f"content_list JSON 解析失败: {e}")
                return 0

        images_count = 0

        for idx, item in enumerate(content_list):
            if not isinstance(item, dict) or item.get("type") != "image":
                continue

            try:
                img_path_str = item.get("img_path", "")
                if not img_path_str:
                    continue

                # 构造图片路径（MinerU 输出在临时目录）
                img_path = Path(img_path_str)
                if not img_path.is_absolute():
                    # 在 MinerU output 目录中递归搜索
                    mineru_output = Path("D:/dl/MinerU/output")
                    if mineru_output.exists():
                        for img_file in mineru_output.rglob(img_path.name):
                            if img_file.is_file():
                                img_path = img_file
                                break

                if not img_path.exists():
                    logger.warning(f"图片文件不存在: {img_path}")
                    continue

                # 读取图片字节
                with open(img_path, "rb") as f:
                    img_bytes = f.read()

                ext = img_path.suffix.lstrip(".") or "png"
                description = item.get("content", "")  # MinerU VLM 生成的描述
                page_number = item.get("page_number", 0)

                # 1. 上传到 MinIO
                object_name = f"scanned_images/doc_{doc_id}/page_{page_number}_{idx}.{ext}"
                with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                    tmp.write(img_bytes)
                    tmp_path = tmp.name
                try:
                    self.object_store.upload_image(tmp_path, object_name)
                finally:
                    os.unlink(tmp_path)

                # 2. 创建 Image DB 记录
                db_image = Image(
                    document_id=doc_id,
                    image_type='figure',
                    minio_path=object_name,
                    page_number=page_number,
                    image_index=idx,
                    file_size=len(img_bytes),
                    vlm_description=description,
                    vlm_model="mineru_vlm",
                    vlm_confidence=1.0 if description else 0.0
                )
                db.add(db_image)
                db.flush()

                # 3. 为图片创建可检索的 Chunk
                if description:
                    content = f"[图片描述] 第{page_number}页\n{description}"
                    content_hash = hashlib.sha256(content.encode()).hexdigest()

                    dense_vector = self.embedder.encode(content).tolist()
                    sparse_vector = self.embedder.encode_sparse(content)

                    db_chunk = DBChunk(
                        document_id=doc_id,
                        content=content,
                        content_hash=content_hash,
                        chunk_type='child',
                        content_type='image_description',
                        page_start=page_number,
                        page_end=page_number,
                        char_count=len(content),
                        token_count=len(content) // 2,
                        related_resource_id=db_image.id,
                        related_resource_type='image',
                        has_dense_vector=True,
                        has_sparse_vector=True,
                    )
                    db.add(db_chunk)
                    db.flush()

                    vector_id = str(db_chunk.id)
                    db_chunk.vector_id = vector_id

                    # 索引到 Qdrant
                    self.vector_store.upsert_points([{
                        "id": vector_id,
                        "dense_vector": dense_vector,
                        "sparse_vector": sparse_vector,
                        "payload": {
                            "chunk_id": db_chunk.id,
                            "document_id": doc_id,
                            "content": content[:500],
                            "content_type": "image_description",
                            "page_start": page_number,
                            "page_end": page_number,
                            "standard_no": metadata.get('standard_no'),
                            "title": metadata.get('title'),
                            "category": metadata.get('category'),
                        }
                    }])

                    # 索引到 Elasticsearch
                    self.search_engine.bulk_index([{
                        "chunk_id": db_chunk.id,
                        "document_id": doc_id,
                        "text": content,
                        "content_type": "image_description",
                        "standard_no": metadata.get('standard_no'),
                        "category": metadata.get('category'),
                        "page_start": page_number,
                        "page_end": page_number,
                    }])

                    db_image.chunk_id = db_chunk.id
                    db.flush()

                images_count += 1
                logger.info(f"图片处理完成: page={page_number}, index={idx}")

            except Exception as e:
                logger.error(f"图片处理失败 (index={idx}): {e}", exc_info=True)

        db.commit()
        logger.info(f"所有图片处理完成: {images_count} 张")
        return images_count

    async def _vectorize_and_index(
        self,
        chunks: list,
        doc_id: int,
        metadata: Dict,
        db
    ) -> int:
        """
        向量化并索引所有块

        Args:
            chunks: Chunk 对象列表（来自 chunker）
            doc_id: 文档ID
            metadata: 文档元数据
            db: 数据库会话

        Returns:
            索引成功的 chunk 数量
        """
        from app.db.models import Chunk as DBChunk
        import uuid

        if not chunks:
            logger.warning(f"文档无 chunks: doc_id={doc_id}")
            return 0

        logger.info(f"开始向量化 {len(chunks)} 个扫描件 chunks...")

        # 1. 批量生成稠密向量
        texts = [chunk.content for chunk in chunks]
        dense_vectors = self.embedder.encode(texts)

        # 标准化为列表格式
        if len(dense_vectors.shape) == 1:
            dense_vectors = [dense_vectors.tolist()]
        else:
            dense_vectors = [v.tolist() for v in dense_vectors]

        # 2. 准备 Qdrant 和 ES 数据
        qdrant_points = []
        es_docs = []
        indexed_count = 0

        for i, chunk in enumerate(chunks):
            try:
                # 生成稀疏向量
                sparse_vector = self.embedder.encode_sparse(chunk.content)

                # 生成向量 ID
                vector_id = f"scan_{doc_id}_{uuid.uuid4().hex[:12]}"

                # 插入 MySQL
                db_chunk = DBChunk(
                    document_id=doc_id,
                    parent_chunk_id=chunk.parent_chunk_id,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    chunk_type=chunk.chunk_type,
                    content_type=chunk.content_type or 'text',
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    clause=chunk.clause,
                    position_in_doc=chunk.position_in_doc,
                    token_count=chunk.token_count,
                    char_count=chunk.char_count,
                    meta_data=chunk.meta_data,
                    vector_id=vector_id,
                    has_dense_vector=True,
                    has_sparse_vector=True,
                )
                db.add(db_chunk)
                db.flush()

                # Qdrant payload
                qdrant_points.append({
                    "id": vector_id,
                    "dense_vector": dense_vectors[i],
                    "sparse_vector": sparse_vector,
                    "payload": {
                        "chunk_id": db_chunk.id,
                        "document_id": doc_id,
                        "content": chunk.content[:500],
                        "content_type": chunk.content_type or 'text',
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "chapter": chunk.chapter,
                        "clause": chunk.clause,
                        "standard_no": metadata.get('standard_no'),
                        "title": metadata.get('title'),
                        "category": metadata.get('category'),
                        "doc_type": metadata.get('doc_type'),
                    }
                })

                # Elasticsearch document
                es_docs.append({
                    "chunk_id": db_chunk.id,
                    "document_id": doc_id,
                    "text": chunk.content,
                    "content_type": chunk.content_type or 'text',
                    "standard_no": metadata.get('standard_no'),
                    "title": metadata.get('title'),
                    "category": metadata.get('category'),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "clause": chunk.clause,
                })

                indexed_count += 1

            except Exception as e:
                logger.error(f"Chunk 处理失败 (index={i}): {e}", exc_info=True)

        db.commit()

        # 3. 批量写入 Qdrant
        if qdrant_points:
            logger.info(f"写入 Qdrant: {len(qdrant_points)} 个向量...")
            self.vector_store.upsert_points(qdrant_points)

        # 4. 批量写入 Elasticsearch
        if es_docs:
            logger.info(f"写入 Elasticsearch: {len(es_docs)} 个文档...")
            self.search_engine.bulk_index(es_docs)

        logger.info(f"扫描件向量化完成: doc_id={doc_id}, indexed={indexed_count}")
        return indexed_count


# 全局单例
_processor_instance = None


def get_scanned_pdf_processor():
    """获取处理器单例"""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = ScannedPDFProcessor()
    return _processor_instance
