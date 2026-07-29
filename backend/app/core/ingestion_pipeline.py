"""
文档入库流水线

完整的文档处理流程：
1. PDF 解析
2. 元数据提取 + 分类
3. 文档入库到 PostgreSQL
4. 智能分块
5. 向量化（稠密 + 稀疏）
6. 存储到 Qdrant + Elasticsearch + MinIO
"""
from typing import Dict, List, Optional
import logging
import re
from pathlib import Path
from datetime import datetime

from app.core.document_processor.parser import pdf_parser
from app.core.document_processor.chunker import document_chunker, Chunk, compute_image_text_associations
from app.core.document_processor.metadata_extractor import metadata_extractor
from app.core.document_processor.classifier import document_classifier
from app.core.embedding import embedder
from app.storage.vector_store import vector_store
from app.storage.search_engine import search_engine
from app.storage.object_store import object_store
from app.db.session import get_db
from app.db.models import Document, Chunk as DBChunk, Image as DBImage, Table as DBTable

logger = logging.getLogger(__name__)


class DocumentIngestionPipeline:
    """文档入库流水线"""

    def __init__(self):
        self.embedder = embedder
        self.vector_store = vector_store
        self.search_engine = search_engine
        self.object_store = object_store
        self._storage_initialized = False

    def _ensure_storage_ready(self):
        """确保存储服务已初始化（collection/index/buckets）"""
        if self._storage_initialized:
            return
        logger.info("Initializing storage backends...")
        self.vector_store.create_collection_if_not_exists()
        self.search_engine.create_index_if_not_exists()
        self.object_store.create_buckets_if_not_exist()
        self._storage_initialized = True

    def ingest_document(
        self,
        pdf_path: str,
        use_llm_classification: bool = False,
        custom_standard_no: Optional[str] = None,
    ) -> Dict:
        """
        完整的文档入库流程

        Args:
            pdf_path: PDF 文件路径
            use_llm_classification: 是否使用 LLM 分类

        Returns:
            入库结果 {
                "success": True,
                "document_id": 1,
                "chunks_count": 23,
                "message": "Document ingested successfully"
            }
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Starting ingestion for: {pdf_path.name}")

        try:
            # Step 0: 确保存储后端就绪
            self._ensure_storage_ready()

            # Step 0.5: 检查文件是否已入库（通过文件哈希）
            import hashlib
            with open(pdf_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            db = next(get_db())
            existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
            if existing_doc:
                logger.info(f"Document already exists (ID: {existing_doc.id}), skipping...")
                return {
                    "success": True,
                    "document_id": existing_doc.id,
                    "chunks_count": existing_doc.chunk_count,
                    "message": "Document already indexed (skipped)",
                    "skipped": True
                }

            # Step 1: PDF 解析
            logger.info("Step 1: Parsing PDF...")
            parsed = pdf_parser.parse_pdf(str(pdf_path))

            # Step 1.5: 保存解析后的 Markdown 到本地（用于调试）
            from pathlib import Path as PathlibPath
            backend_dir = PathlibPath(__file__).parent.parent.parent  # backend/
            debug_md_dir = backend_dir / "debug_markdown"
            debug_md_dir.mkdir(exist_ok=True)
            debug_md_path = debug_md_dir / f"{pdf_path.stem}.md"
            try:
                with open(debug_md_path, 'w', encoding='utf-8') as f:
                    f.write(parsed['content'])
                logger.info(f"Debug: Markdown saved to {debug_md_path}")
            except Exception as e:
                logger.warning(f"Failed to save debug markdown: {e}")

            # Step 2: 元数据提取
            logger.info("Step 2: Extracting metadata...")
            metadata = metadata_extractor.extract_from_document(
                content=parsed['content'],
                filename=pdf_path.name,
                parsed_metadata=parsed['metadata']
            )

            # Step 2.5: 应用用户自定义标准号（优先级高于自动识别）
            if custom_standard_no:
                logger.info(f"Using custom standard_no: {custom_standard_no}")
                metadata['standard_no'] = custom_standard_no
                # 尝试从标准号提取年份更新版本信息
                year_match = re.search(r'-(\d{4})$', custom_standard_no)
                if year_match:
                    year = year_match.group(1)
                    metadata['version'] = f"{year}版"
                    metadata['publish_date'] = f"{year}-01-01"

            # Step 3: 文档分类
            logger.info("Step 3: Classifying document...")
            classification = document_classifier.classify(
                content=parsed['content'],
                metadata=metadata,
                use_llm=use_llm_classification
            )
            metadata.update(classification)

            # Step 4: 上传原始 PDF 到 MinIO
            logger.info("Step 4: Uploading PDF to MinIO...")
            minio_path = f"standards/{metadata.get('standard_no', 'unknown')}/{pdf_path.name}"
            object_store.upload_pdf(
                file_path=str(pdf_path),
                object_name=minio_path
            )

            # Step 5: 上传 Markdown 到 MinIO
            logger.info("Step 5: Uploading Markdown to MinIO...")
            markdown_path = f"standards/{metadata.get('standard_no', 'unknown')}/full.md"
            object_store.upload_markdown(
                content=parsed['content'],
                object_name=markdown_path
            )

            # Step 6: 文档入库到 PostgreSQL
            logger.info("Step 6: Inserting document to PostgreSQL...")
            db = next(get_db())
            try:
                document = self._create_document_record(
                    metadata=metadata,
                    pdf_path=pdf_path,
                    minio_path=minio_path,
                    pages=parsed['pages']
                )
                db.add(document)
                db.commit()
                db.refresh(document)
                document_id = document.id
                logger.info(f"Document inserted with ID: {document_id}")

            except Exception as e:
                db.rollback()
                raise e

            # Step 6.5: 处理图片（VLM 模式）
            images_count = 0
            image_chunk_data = []  # [(chunk_id, description, page, vector), ...]
            if parsed.get('images'):
                logger.info(f"Step 6.5: Processing {len(parsed['images'])} images...")
                images_count, image_chunk_data = self._process_images(parsed['images'], document_id, metadata, db)
                document.image_count = images_count
                db.commit()

            # Step 6.7: 处理表格（HTML表格提取）
            tables_count = 0
            table_chunks = []  # 表格专用chunks
            logger.info("Step 6.7: Extracting tables from markdown...")
            tables_count, table_chunks = self._process_tables(parsed['content'], document_id, metadata, db)
            document.table_count = tables_count
            db.commit()
            logger.info(f"Extracted {tables_count} tables")

            # Step 7: 文档分块
            logger.info("Step 7: Chunking document...")
            chunks = document_chunker.chunk_document(
                content=parsed['content'],
                doc_metadata=metadata,
                document_id=document_id,
                doc_type=metadata.get('doc_type', 'standard')
            )
            logger.info(f"Generated {len(chunks)} chunks")

            # 合并表格chunks到主chunk列表
            chunks.extend(table_chunks)

            # Step 8: 向量化 + 入库（含图文关联计算）
            logger.info("Step 8: Vectorizing and indexing chunks...")
            indexed_count = self._process_chunks(chunks, db, document_id, image_chunk_data)

            # Step 9: 更新文档处理状态
            document.process_status = 'completed'
            document.chunk_count = indexed_count
            db.commit()

            logger.info(f"Document ingestion completed: {indexed_count} chunks, {images_count} images indexed")

            return {
                "success": True,
                "document_id": document_id,
                "chunks_count": indexed_count,
                "images_count": images_count,
                "message": "Document ingested successfully"
            }

        except Exception as e:
            logger.error(f"Document ingestion failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "message": "Document ingestion failed"
            }

    def _create_document_record(
        self,
        metadata: Dict,
        pdf_path: Path,
        minio_path: str,
        pages: int
    ) -> Document:
        """创建文档记录"""
        import hashlib

        # 计算文件哈希
        with open(pdf_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # 转换日期格式
        publish_date = None
        if metadata.get('publish_date'):
            try:
                publish_date = datetime.strptime(metadata['publish_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid publish_date format: {metadata.get('publish_date')!r} - {e}")

        implement_date = None
        if metadata.get('implement_date'):
            try:
                implement_date = datetime.strptime(metadata['implement_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid implement_date format: {metadata.get('implement_date')!r} - {e}")

        return Document(
            title=metadata.get('title', pdf_path.stem),
            doc_type=metadata.get('doc_type', 'standard'),
            standard_no=metadata.get('standard_no'),
            version=metadata.get('version'),
            publish_org=metadata.get('publish_org'),
            publish_date=publish_date,
            implement_date=implement_date,
            status=metadata.get('status', 'valid'),
            replaced_by=metadata.get('replaced_by'),
            replaces=metadata.get('replaces'),
            category=metadata.get('category'),
            voltage_level=metadata.get('voltage_level'),
            keywords=str(metadata.get('keywords', [])),
            file_path=minio_path,
            file_size=pdf_path.stat().st_size,
            file_hash=file_hash,
            page_count=pages,
            process_status='processing'
        )

    def _process_images(
        self,
        images: List[Dict],
        document_id: int,
        metadata: Dict,
        db
    ) -> tuple:
        """
        处理 VLM 解析出的图片：MinIO 上传 + DB 记录 + 向量索引

        Returns:
            (images_count, image_chunk_data)
            image_chunk_data: [(chunk_id, description, page, dense_vector), ...]
        """
        import tempfile
        import os
        import hashlib

        count = 0
        image_chunk_data = []

        for img_info in images:
            try:
                ext = img_info.get('ext', 'png')
                description = img_info.get('description', '')
                caption = img_info.get('caption', '')
                figure_number = img_info.get('figure_number')

                # 1. 写临时文件，上传到 MinIO
                object_name = (
                    f"images/{metadata.get('standard_no', 'unknown')}"
                    f"/p{img_info['page']}_{img_info['index']}.{ext}"
                )
                with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as tmp:
                    tmp.write(img_info['bytes'])
                    tmp_path = tmp.name
                try:
                    self.object_store.upload_image(tmp_path, object_name)
                finally:
                    os.unlink(tmp_path)

                # 2. 创建 Image DB 记录
                db_image = DBImage(
                    document_id=document_id,
                    image_type='figure',
                    minio_path=object_name,
                    page_number=img_info.get('page'),
                    image_index=img_info.get('index'),
                    figure_number=figure_number,
                    caption=caption,
                    file_size=len(img_info['bytes']),
                    vlm_description=description,
                    vlm_model=img_info.get('vlm_model', ''),
                    vlm_confidence=img_info.get('vlm_confidence', 0.0)
                )
                db.add(db_image)
                db.flush()

                # 3. 为图片创建可检索的 image_description Chunk
                if description:
                    # 组装内容：图号 + 图注 + VLM 描述
                    content_parts = [f"[图片描述] 第{img_info['page']}页"]
                    if figure_number:
                        content_parts.append(f"{figure_number}")
                    if caption:
                        content_parts.append(f"：{caption}")
                    content_parts.append(f"\n{description}")
                    content = " ".join(content_parts)

                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                    dense_vector = self.embedder.encode(content).tolist()
                    sparse_vector = self.embedder.encode_sparse(content)

                    db_chunk = DBChunk(
                        document_id=document_id,
                        content=content,
                        content_hash=content_hash,
                        chunk_type='child',
                        content_type='image_description',
                        page_start=img_info.get('page'),
                        page_end=img_info.get('page'),
                        char_count=len(content),
                        token_count=len(content) // 2,
                        related_resource_id=db_image.id,
                        related_resource_type='image',
                        has_dense_vector=True,
                        has_sparse_vector=True,
                        meta_data={
                            'document_title': metadata.get('title'),
                            'standard_no': metadata.get('standard_no'),
                            'category': metadata.get('category'),
                            'voltage_level': metadata.get('voltage_level'),
                        }
                    )
                    db.add(db_chunk)
                    db.flush()
                    vector_id = str(db_chunk.id)
                    db_chunk.vector_id = vector_id

                    self.vector_store.upsert_points([{
                        "id": vector_id,
                        "dense_vector": dense_vector,
                        "sparse_vector": sparse_vector,
                        "payload": {
                            "doc_id": document_id,
                            "chunk_id": db_chunk.id,
                            "chunk_type": "child",
                            "content_type": "image_description",
                            "text": content,
                            "minio_path": object_name,
                            "image_id": db_image.id,
                            **{k: v for k, v in (metadata or {}).items() if v is not None}
                        }
                    }])

                    self.search_engine.bulk_index([{
                        "chunk_id": vector_id,
                        "doc_id": document_id,
                        "text": content,
                        "content_type": "image_description",
                        "standard_no": metadata.get('standard_no'),
                        "category": metadata.get('category'),
                        "voltage_level": metadata.get('voltage_level')
                    }])

                    db_image.chunk_id = db_chunk.id
                    db.flush()

                    # 记录用于后续图文关联
                    image_chunk_data.append((
                        db_chunk.id,
                        description,
                        img_info.get('page'),
                        dense_vector
                    ))

                count += 1
            except Exception as e:
                logger.error(
                    f"图片处理失败 (页{img_info.get('page')}, 图{img_info.get('index')}): {e}"
                )

        db.commit()
        return count, image_chunk_data

    def _process_tables(
        self,
        markdown_content: str,
        document_id: int,
        metadata: Dict,
        db
    ) -> tuple:
        """
        从 markdown 中提取 HTML 表格，使用 pandas 解析为结构化文本并入库。

        MinerU 输出格式：表格标题单独占一行，紧接着下一行是 <table>…</table>（整行）。

        Returns:
            (tables_count, table_chunks)
            table_chunks: List[Chunk]，content_type='table'，待后续向量化
        """
        import pandas as pd
        from io import StringIO

        # 匹配"表 编号 标题"，支持：表1/表A2/表 2/续表A2/续表1 等形式
        _TITLE_RE = re.compile(
            r'^(?:续\s*)?表\s*'
            r'([A-Za-z0-9０-９][A-Za-z0-9０-９\.\-]*)'  # 编号
            r'(?:\s+(.+))?$'                               # 可选标题文字
        )
        # 仅编号无标题文字的降级匹配（如"表1"后无文字）
        _TITLE_NO_TEXT_RE = re.compile(r'^(?:续\s*)?表\s*([A-Za-z0-9０-９][A-Za-z0-9０-９\.\-]*)$')

        def html_table_to_gfm(html: str, title: str = None) -> str:
            """将 HTML 表格用 pandas 解析并转为 GFM Markdown 文本"""
            try:
                dfs = pd.read_html(StringIO(html), flavor='lxml', header=None)
                if not dfs:
                    return ''
                df = dfs[0].fillna('').astype(str)

                lines = []
                if title:
                    lines.append(title)
                    lines.append('')

                for row_idx, row in df.iterrows():
                    cells = [str(c).strip().replace('\n', ' ').replace('|', '\\|') for c in row]
                    lines.append('| ' + ' | '.join(cells) + ' |')
                    if row_idx == 0:
                        lines.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')

                return '\n'.join(lines)
            except Exception as e:
                logger.warning(f"pandas 解析表格失败: {e}")
                return ''

        total_chars = len(markdown_content)
        total_pages = metadata.get('page_count') or 1
        doc_lines = markdown_content.split('\n')

        table_chunks = []
        tables_count = 0

        # 逐行扫描：找到 <table> 行，向上找最近的非空标题行
        for line_no, line in enumerate(doc_lines):
            stripped = line.strip()
            if not re.match(r'(?i)<table[\s>]', stripped):
                continue

            # 取出完整 HTML（单行或跨行都处理）
            html = stripped

            # 向上最多扫描 8 行找标题
            title = None
            table_number = None
            for prev_no in range(line_no - 1, max(line_no - 9, -1), -1):
                prev = doc_lines[prev_no].strip()
                if not prev:
                    continue
                m = _TITLE_RE.match(prev)
                if m:
                    table_number = m.group(1)
                    title = prev
                else:
                    m2 = _TITLE_NO_TEXT_RE.match(prev)
                    if m2:
                        table_number = m2.group(1)
                        title = prev
                break  # 找到第一个非空行即停止，无论是否匹配标题

            # 用字符位置估算页码
            char_pos = sum(len(doc_lines[i]) + 1 for i in range(line_no))
            estimated_page = max(1, int(char_pos / total_chars * total_pages))

            text_content = html_table_to_gfm(html, title)
            if not text_content or len(text_content) < 20:
                continue

            try:
                db_table = DBTable(
                    document_id=document_id,
                    table_number=table_number,
                    title=title,
                    page_number=estimated_page,
                    table_index=tables_count,
                    markdown_content=text_content,
                    minio_path=f"tables/{metadata.get('standard_no', 'unknown')}/table_{tables_count}.txt",
                )
                db.add(db_table)
                db.flush()

                table_chunk = Chunk(
                    content=text_content,
                    chunk_type='parent',
                    document_id=document_id,
                    content_type='table',
                    page_start=estimated_page,
                    page_end=estimated_page,
                    position_in_doc=tables_count,
                    meta_data={
                        'table_number': table_number,
                        'table_title': title,
                        'table_id': db_table.id,
                        # 文档级过滤字段（供 Qdrant/ES 按文档过滤）
                        'standard_no': metadata.get('standard_no'),
                        'category': metadata.get('category'),
                        'voltage_level': metadata.get('voltage_level'),
                        'document_title': metadata.get('title'),
                    }
                )
                # chunk_id 在 _process_chunks() 完成后回写
                db_table.chunk_id = None

                table_chunks.append(table_chunk)
                tables_count += 1
                logger.debug(f"提取表格: {title or f'table_{tables_count}'}, 页码{estimated_page}")

            except Exception as e:
                logger.error(f"表格处理失败 (line={line_no}): {e}", exc_info=True)

        if tables_count > 0:
            db.commit()
            logger.info(f"表格提取完成: {tables_count} 个表格")

        return tables_count, table_chunks

    def _process_chunks(
        self,
        chunks: List[Chunk],
        db,
        document_id: int,
        image_chunk_data: List[tuple] = None
    ) -> int:
        """
        处理所有块：向量化 + 图文关联计算 + 三库入库

        Args:
            chunks: 文档分块列表
            db: 数据库会话
            document_id: 文档 ID
            image_chunk_data: [(chunk_id, description, page, dense_vector), ...]

        Returns:
            入库成功的 chunk 数量
        """
        indexed_count = 0
        image_chunk_data = image_chunk_data or []

        # 先插入父块，获取 ID
        parent_chunks = [c for c in chunks if c.chunk_type == "parent"]
        child_chunks = [c for c in chunks if c.chunk_type == "child"]

        parent_id_map = {}  # chunk.content_hash -> db_id

        # === 阶段 1：批量向量化所有块 ===
        logger.info(f"Batch vectorizing {len(chunks)} chunks...")

        # 收集所有文本
        parent_texts = [c.content for c in parent_chunks]
        child_texts = [c.content for c in child_chunks]

        # 批量编码
        parent_dense_vectors = []
        if parent_texts:
            parent_dense_vectors = self.embedder.encode(parent_texts)
            if len(parent_dense_vectors.shape) == 1:
                parent_dense_vectors = [parent_dense_vectors.tolist()]
            else:
                parent_dense_vectors = [v.tolist() for v in parent_dense_vectors]

        child_dense_vectors = []
        if child_texts:
            child_dense_vectors = self.embedder.encode(child_texts)
            if len(child_dense_vectors.shape) == 1:
                child_dense_vectors = [child_dense_vectors.tolist()]
            else:
                child_dense_vectors = [v.tolist() for v in child_dense_vectors]

        # 组装 (chunk, vector) 对
        parent_vectors = list(zip(parent_chunks, parent_dense_vectors))
        child_vectors = list(zip(child_chunks, child_dense_vectors))

        # === 阶段 2：计算图文关联 ===
        associations = {}
        if image_chunk_data and (parent_vectors or child_vectors):
            logger.info("Computing image-text associations...")

            # 收集文本块信息（父块 + 子块）
            text_chunk_info = []
            text_vectors_list = []

            for chunk, vec in parent_vectors:
                text_chunk_info.append((
                    id(chunk),  # 临时 ID，后面替换为 db_id
                    chunk.content,
                    chunk.page_start,
                    chunk.page_end
                ))
                text_vectors_list.append(vec)

            for chunk, vec in child_vectors:
                text_chunk_info.append((
                    id(chunk),
                    chunk.content,
                    chunk.page_start,
                    chunk.page_end
                ))
                text_vectors_list.append(vec)

            # 收集图片块信息
            image_chunk_info = [(cid, desc, page) for cid, desc, page, _ in image_chunk_data]
            image_vectors_list = [vec for _, _, _, vec in image_chunk_data]

            # 计算关联
            temp_associations = compute_image_text_associations(
                text_chunks=text_chunk_info,
                image_chunks=image_chunk_info,
                text_vectors=text_vectors_list,
                image_vectors=image_vectors_list,
                threshold=0.75
            )

            # 将临时 ID 映射构建为查找字典（稍后替换为真实 db_id）
            temp_id_to_chunk = {}
            for chunk, _ in parent_vectors + child_vectors:
                temp_id_to_chunk[id(chunk)] = chunk

            associations = temp_associations

        # === 阶段 3：写入 MySQL，收集向量点 ===
        logger.info("Indexing chunks to database...")

        qdrant_points = []
        es_docs = []

        def _insert_chunk_record(chunk: Chunk, dense_vector: list, is_parent: bool) -> Optional[tuple]:
            """插入单个 chunk 到 MySQL，返回 (db_chunk, vector_id) 或 None"""
            # 用保存点隔离：单个 chunk 失败只回滚到保存点，不影响已提交的其他 chunks
            savepoint = db.begin_nested()
            try:
                sparse_vector = self.embedder.encode_sparse(chunk.content)

                db_chunk = DBChunk(
                    document_id=chunk.document_id,
                    parent_chunk_id=chunk.parent_chunk_id,
                    content=chunk.content,
                    content_hash=chunk.content_hash,
                    chunk_type=chunk.chunk_type,
                    content_type=chunk.content_type,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chapter=chunk.chapter,
                    section=chunk.section,
                    clause=chunk.clause,
                    position_in_doc=chunk.position_in_doc,
                    token_count=chunk.token_count,
                    char_count=chunk.char_count,
                    meta_data=chunk.meta_data,
                    related_chunk_ids=chunk.related_chunk_ids,
                    related_resource_id=chunk.meta_data.get('table_id') if chunk.content_type == 'table' else None,
                    related_resource_type='table' if chunk.content_type == 'table' else None,
                    has_dense_vector=True,
                    has_sparse_vector=True
                )
                db.add(db_chunk)
                db.flush()
                vector_id = str(db_chunk.id)
                db_chunk.vector_id = vector_id
                savepoint.commit()

                qdrant_points.append({
                    "id": vector_id,
                    "dense_vector": dense_vector,
                    "sparse_vector": sparse_vector,
                    "payload": {
                        "doc_id": chunk.document_id,
                        "chunk_id": db_chunk.id,
                        "chunk_type": chunk.chunk_type,
                        "content_type": chunk.content_type,
                        "text": chunk.content,
                        "chapter": chunk.chapter,
                        "clause": chunk.clause,
                        "related_chunk_ids": chunk.related_chunk_ids or [],
                        **chunk.meta_data
                    }
                })
                es_docs.append({
                    "chunk_id": vector_id,
                    "doc_id": chunk.document_id,
                    "text": chunk.content,
                    "content_type": chunk.content_type,
                    "related_chunk_ids": chunk.related_chunk_ids or [],
                    "standard_no": chunk.meta_data.get('standard_no'),
                    "clause": chunk.clause,
                    "category": chunk.meta_data.get('category'),
                    "voltage_level": chunk.meta_data.get('voltage_level')
                })
                return db_chunk, vector_id
            except Exception as e:
                logger.error(f"Failed to insert {'parent' if is_parent else 'child'} chunk: {e}")
                savepoint.rollback()  # 只回滚到保存点，不影响外层事务中已有的 chunks
                return None

        # 处理父块
        for chunk, dense_vector in parent_vectors:
            temp_id = id(chunk)
            if temp_id in associations:
                chunk.related_chunk_ids = associations[temp_id]

            result = _insert_chunk_record(chunk, dense_vector, is_parent=True)
            if result:
                db_chunk, _ = result
                parent_id_map[chunk.content_hash] = db_chunk.id
                if temp_id in associations:
                    associations[db_chunk.id] = associations.pop(temp_id)

                # 回写 Table.chunk_id（表格块创建后关联回 DBTable）
                if chunk.content_type == 'table' and chunk.meta_data.get('table_id'):
                    table_id = chunk.meta_data['table_id']
                    db_table = db.get(DBTable, table_id)
                    if db_table:
                        db_table.chunk_id = db_chunk.id

                indexed_count += 1

        # 处理子块（设置 parent_chunk_id）
        for chunk, dense_vector in child_vectors:
            parent_db_id = self._find_parent_id(chunk, parent_id_map, parent_chunks)
            if parent_db_id:
                chunk.parent_chunk_id = parent_db_id

            temp_id = id(chunk)
            if temp_id in associations:
                chunk.related_chunk_ids = associations[temp_id]

            result = _insert_chunk_record(chunk, dense_vector, is_parent=False)
            if result:
                indexed_count += 1

        # === 阶段 4：批量写入 Qdrant 和 Elasticsearch ===
        if qdrant_points:
            logger.info(f"Batch upserting {len(qdrant_points)} points to Qdrant...")
            self.vector_store.upsert_points(qdrant_points)

        if es_docs:
            logger.info(f"Batch indexing {len(es_docs)} docs to Elasticsearch...")
            self.search_engine.bulk_index(es_docs)

        # 提交 Table.chunk_id 更新
        db.flush()

        logger.info(f"Indexed {indexed_count} chunks with associations")
        return indexed_count

    def _find_parent_id(
        self,
        child_chunk: Chunk,
        parent_id_map: Dict,
        parent_chunks: List[Chunk]
    ) -> Optional[int]:
        """查找子块对应的父块 ID"""
        # 通过章节号匹配
        for parent in parent_chunks:
            if parent.chapter == child_chunk.chapter:
                return parent_id_map.get(parent.content_hash)
        return None

    def _index_single_chunk(self, chunk: Chunk, db, dense_vector: List[float] = None) -> tuple:
        """
        单个块的完整索引流程

        Args:
            chunk: 要索引的块
            db: 数据库会话
            dense_vector: 预计算的稠密向量（可选）

        Returns:
            (db_chunk, vector_id)
        """
        # 1. 生成稠密向量（如果未提供）
        if dense_vector is None:
            dense_vector = self.embedder.encode(chunk.content).tolist()

        # 2. 生成稀疏向量（使用 SPLADE）
        sparse_vector = self.embedder.encode_sparse(chunk.content)

        # 3. 插入 MySQL
        db_chunk = DBChunk(
            document_id=chunk.document_id,
            parent_chunk_id=chunk.parent_chunk_id,
            content=chunk.content,
            content_hash=chunk.content_hash,
            chunk_type=chunk.chunk_type,
            content_type=chunk.content_type,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            chapter=chunk.chapter,
            section=chunk.section,
            clause=chunk.clause,
            position_in_doc=chunk.position_in_doc,
            token_count=chunk.token_count,
            char_count=chunk.char_count,
            meta_data=chunk.meta_data,
            related_chunk_ids=chunk.related_chunk_ids,
            has_dense_vector=True,
            has_sparse_vector=True
        )
        db.add(db_chunk)
        db.flush()  # 获取 ID
        vector_id = str(db_chunk.id)
        db_chunk.vector_id = vector_id

        # 4. 插入 Qdrant
        self.vector_store.upsert_points([{
            "id": vector_id,
            "dense_vector": dense_vector,
            "sparse_vector": sparse_vector,
            "payload": {
                "doc_id": chunk.document_id,
                "chunk_id": db_chunk.id,
                "chunk_type": chunk.chunk_type,
                "content_type": chunk.content_type,
                "text": chunk.content,
                "chapter": chunk.chapter,
                "clause": chunk.clause,
                "related_chunk_ids": chunk.related_chunk_ids or [],
                **chunk.meta_data
            }
        }])

        # 5. 插入 Elasticsearch
        self.search_engine.bulk_index([{
            "chunk_id": vector_id,
            "doc_id": chunk.document_id,
            "text": chunk.content,
            "content_type": chunk.content_type,
            "related_chunk_ids": chunk.related_chunk_ids or [],
            "standard_no": chunk.meta_data.get('standard_no'),
            "clause": chunk.clause,
            "category": chunk.meta_data.get('category'),
            "voltage_level": chunk.meta_data.get('voltage_level')
        }])

        return db_chunk, vector_id

    def batch_ingest(
        self,
        pdf_dir: str,
        use_llm_classification: bool = False
    ) -> Dict:
        """
        批量入库

        Args:
            pdf_dir: PDF 文件目录
            use_llm_classification: 是否使用 LLM 分类

        Returns:
            批量处理结果
        """
        pdf_dir = Path(pdf_dir)
        pdf_files = list(pdf_dir.glob("*.pdf"))

        logger.info(f"Starting batch ingestion for {len(pdf_files)} files")

        results = {
            "total": len(pdf_files),
            "success": 0,
            "failed": 0,
            "details": []
        }

        for pdf_file in pdf_files:
            result = self.ingest_document(
                pdf_path=str(pdf_file),
                use_llm_classification=use_llm_classification
            )

            if result['success']:
                results['success'] += 1
            else:
                results['failed'] += 1

            results['details'].append({
                "file": pdf_file.name,
                "success": result['success'],
                "document_id": result.get('document_id'),
                "chunks_count": result.get('chunks_count'),
                "error": result.get('error')
            })

        logger.info(f"Batch ingestion completed: {results['success']} success, {results['failed']} failed")
        return results


# 全局实例
ingestion_pipeline = DocumentIngestionPipeline()
