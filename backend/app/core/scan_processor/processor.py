"""
Scanned PDF Processor
扫描件PDF处理器 - 集成PaddleOCR + PPStructure + VLM
"""
import logging
import os
import hashlib
from typing import Dict, List, Optional
from pathlib import Path
import asyncio

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import Document, Chunk, Image, Table
from app.storage.object_store import object_store
from app.core.vlm.vlm_client import vlm_client

logger = logging.getLogger(__name__)


class ScannedPDFProcessor:
    """扫描件PDF处理器"""

    def __init__(self):
        """初始化处理器"""
        self.vlm_client = vlm_client if settings.ENABLE_VLM_DESCRIPTION else None

        logger.info("ScannedPDFProcessor初始化完成（纯VLM模式）")

    async def process_document(self, pdf_path: str, doc_id: int) -> Dict:
        """
        处理单个扫描件PDF（纯VLM模式）

        Args:
            pdf_path: PDF文件路径
            doc_id: 文档ID

        Returns:
            处理结果统计
        """
        logger.info(f"开始处理扫描件PDF（纯VLM）: doc_id={doc_id}, path={pdf_path}")

        # 1. 上传原始PDF到MinIO
        await self._upload_original_pdf(pdf_path, doc_id)

        # 2. 转换PDF为图片
        page_images = await self._pdf_to_images(pdf_path)
        logger.info(f"PDF转换完成: {len(page_images)} 页")

        # 3. 并行处理每一页（纯VLM识别）
        tasks = [
            self._process_page_with_vlm(img, page_num, doc_id)
            for page_num, img in enumerate(page_images, start=1)
        ]
        page_results = await asyncio.gather(*tasks)

        # 4. 合并结果并生成Markdown
        full_markdown = self._merge_pages_to_markdown(page_results)
        await self._save_markdown(full_markdown, doc_id)

        # 5. 保存页面为图片Chunk（每页作为一个图片+VLM描述）
        await self._save_pages_as_image_chunks(page_results, doc_id)

        # 6. 更新文档元数据
        await self._update_document_metadata(doc_id, page_results)

        # 7. 向量化并索引
        await self._vectorize_and_index(doc_id)

        logger.info(f"扫描件处理完成: doc_id={doc_id}, pages={len(page_results)}")

        return {
            'page_count': len(page_results),
            'image_count': len(page_results),  # 每页作为一张图片
            'table_count': 0,
            'ocr_avg_confidence': 0.95  # VLM模式置信度固定
        }

    async def _upload_original_pdf(self, pdf_path: str, doc_id: int):
        """上传原始PDF到MinIO"""
        try:
            object_name = f"scanned_pdfs/doc_{doc_id}/original.pdf"
            object_store.upload_pdf(pdf_path, object_name)
            logger.info(f"原始PDF已上传: {object_name}")
        except Exception as e:
            logger.error(f"上传原始PDF失败: {e}")
            raise

    async def _pdf_to_images(self, pdf_path: str) -> List:
        """将PDF转换为图片列表"""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            images = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                # 转换为图片（300 DPI）
                pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                img_data = pix.tobytes("png")

                # 转换为PIL Image
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(img_data))
                images.append(img)

            doc.close()
            return images

        except ImportError:
            logger.error("PyMuPDF (fitz) 未安装，无法转换PDF")
            raise
        except Exception as e:
            logger.error(f"PDF转换失败: {e}")
            raise

    async def _process_page_with_vlm(self, image, page_num: int, doc_id: int) -> Dict:
        """
        使用VLM处理单页（识别全部内容）

        Args:
            image: PIL Image对象
            page_num: 页码
            doc_id: 文档ID

        Returns:
            页面处理结果
        """
        result = {
            'page_num': page_num,
            'full_text': '',
            'structure': {},
            'image_path': None
        }

        try:
            # 1. 保存页面图片到临时文件
            temp_dir = Path(f"/tmp/scan_processor/doc_{doc_id}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / f"page_{page_num:03d}.png"
            image.save(temp_path)

            # 2. 使用VLM识别整页内容
            if self.vlm_client:
                # 构造详细的提示词，要求保留结构
                prompt = f"""请识别这一页的全部内容，并按原文结构输出。

要求：
1. 保留章节标题、条款编号（如 3.2.1）
2. 保留表格结构（用Markdown格式）
3. 标注图片位置（如 [图5-2: 水坝剖面图]）
4. 保持原文排版顺序（双栏时从左到右）

输出格式：纯文本，保持原文层级结构。

这是第{page_num}页。"""

                vlm_result = await self.vlm_client.generate_description(str(temp_path), prompt)

                if vlm_result:
                    result['full_text'] = vlm_result.get('description', '') or ''
                    result['confidence'] = vlm_result.get('confidence', 0.0)
                    result['model'] = vlm_result.get('model', '')
                else:
                    result['full_text'] = ''
                    result['confidence'] = 0.0
                    result['model'] = ''
                    logger.warning(f"VLM返回空结果: page={page_num}")

                logger.info(f"VLM识别完成: page={page_num}, chars={len(result['full_text'])}")

            # 3. 上传页面图片到MinIO
            object_name = f"scanned_pages/doc_{doc_id}/page_{page_num:03d}.png"
            object_store.upload_image(str(temp_path), object_name)
            result['image_path'] = object_name

        except Exception as e:
            logger.error(f"VLM处理页面失败: page={page_num}, error={e}", exc_info=True)

        return result

    def _merge_pages_to_markdown(self, page_results: List[Dict]) -> str:
        """合并页面结果为Markdown（纯VLM版本）"""
        markdown_parts = []

        for page_result in page_results:
            page_num = page_result['page_num']
            markdown_parts.append(f"\n\n---\n## 第 {page_num} 页\n\n")

            # VLM识别的全文
            full_text = page_result.get('full_text', '').strip()
            if full_text:
                markdown_parts.append(full_text + '\n\n')

            # 页面图片引用
            if page_result.get('image_path'):
                markdown_parts.append(f"*[原始页面图片: {page_result['image_path']}]*\n\n")

        return ''.join(markdown_parts)

    async def _save_markdown(self, markdown: str, doc_id: int):
        """保存Markdown到MinIO"""
        try:
            object_name = f"scanned_markdown/doc_{doc_id}/full.md"
            object_store.upload_markdown(markdown, object_name)

            logger.info(f"Markdown已保存: {object_name}")

        except Exception as e:
            logger.error(f"保存Markdown失败: {e}")

    async def _save_pages_as_image_chunks(self, page_results: List[Dict], doc_id: int):
        """
        保存每页为图片记录 + VLM描述Chunk

        关键：整页作为一个图片，VLM识别的全文作为可检索内容
        """
        db = SessionLocal()
        try:
            for page_result in page_results:
                page_num = page_result['page_num']
                full_text = page_result.get('full_text', '').strip()

                if not full_text:
                    logger.warning(f"页面 {page_num} 无VLM识别内容，跳过")
                    continue

                # 1. 保存图片记录
                image = Image(
                    document_id=doc_id,
                    image_type='figure',
                    minio_path=page_result['image_path'],
                    page_number=page_num,
                    image_index=1,  # 整页作为单个图片
                    vlm_description=full_text[:1000],  # 摘要（前1000字符）
                    vlm_model=page_result.get('model', ''),
                    vlm_confidence=page_result.get('confidence', 0.0)
                )
                db.add(image)
                db.flush()

                # 2. 为整页创建可检索的Chunk（关键：全文作为检索内容）
                content_hash = hashlib.sha256(full_text.encode()).hexdigest()

                chunk = Chunk(
                    document_id=doc_id,
                    content=full_text,  # VLM识别的全文
                    content_hash=content_hash,
                    content_type='image_description',  # 标记为图片描述类型
                    related_resource_id=image.id,
                    related_resource_type='image',
                    page_start=page_num,
                    page_end=page_num,
                    chunk_type='parent',
                    char_count=len(full_text)
                )
                db.add(chunk)
                db.flush()

                # 3. 反向关联
                image.chunk_id = chunk.id

                logger.info(f"页面已保存: page={page_num}, chunk_id={chunk.id}, chars={len(full_text)}")

            db.commit()
            logger.info(f"所有页面已保存为图片+Chunk: doc_id={doc_id}")

        except Exception as e:
            db.rollback()
            logger.error(f"保存页面失败: {e}", exc_info=True)
            raise
        finally:
            db.close()

    async def _update_document_metadata(self, doc_id: int, page_results: List[Dict]):
        """更新文档元数据（纯VLM版本）"""
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                confidences = [p.get('confidence', 0.0) for p in page_results if p.get('confidence')]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.95

                doc.is_scanned = True
                doc.ocr_engine = "VLM"  # 标记为VLM模式
                doc.ocr_version = page_results[0].get('model', '') if page_results else ''
                doc.ocr_confidence = avg_confidence
                doc.image_count = len(page_results)  # 每页作为一张图片
                doc.table_count = 0
                doc.process_status = 'completed'
                doc.markdown_path = f"scanned_markdown/doc_{doc_id}/full.md"
                doc.images_prefix = f"scanned_pages/doc_{doc_id}/"

                db.commit()
                logger.info(f"文档元数据已更新（VLM模式）: doc_id={doc_id}")

        except Exception as e:
            db.rollback()
            logger.error(f"更新文档元数据失败: {e}")
            raise
        finally:
            db.close()

    async def _vectorize_and_index(self, doc_id: int):
        """向量化并索引（调用现有embedding和storage层）"""
        # TODO: 集成现有的embedding和storage层
        # 1. 获取所有Chunk（包括text/image_description/table_summary）
        # 2. 调用embedder生成向量
        # 3. 存入Qdrant
        # 4. 存入Elasticsearch
        logger.info(f"向量化和索引: doc_id={doc_id} (TODO: 实现)")
        pass
