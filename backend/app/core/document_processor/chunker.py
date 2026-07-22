"""
文档智能分块器

支持：
- 父子块混合结构
- 标准文档：条款规则分块
- 专业书籍：语义边界检测
"""
from typing import List, Dict, Optional, Tuple
import re
import logging
import hashlib

logger = logging.getLogger(__name__)


class Chunk:
    """文档块（对应数据库 Chunk 模型）"""
    def __init__(
        self,
        content: str,
        chunk_type: str,  # "parent" or "child"
        document_id: Optional[int] = None,
        parent_chunk_id: Optional[int] = None,
        content_type: str = "text",  # "text", "table", "image_description"
        **metadata
    ):
        self.document_id = document_id
        self.parent_chunk_id = parent_chunk_id
        self.content = content
        self.content_hash = self._compute_hash(content)
        self.chunk_type = chunk_type
        self.content_type = content_type

        # 位置信息
        self.page_start = metadata.get("page_start")
        self.page_end = metadata.get("page_end")
        self.chapter = metadata.get("chapter")
        self.section = metadata.get("section")
        self.clause = metadata.get("clause")
        self.position_in_doc = metadata.get("position_in_doc")

        # 统计信息
        self.char_count = len(content)
        self.token_count = self._estimate_tokens(content)

        # 扩展元数据
        self.meta_data = metadata.get("meta_data", {})
        self.related_chunk_ids = metadata.get("related_chunk_ids", [])

        # 向量信息（稍后填充）
        self.vector_id = None
        self.has_dense_vector = False
        self.has_sparse_vector = False

        # 数据库 ID（插入后填充）
        self.id = None

    def _compute_hash(self, content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _estimate_tokens(self, text: str) -> int:
        """估算 Token 数（中文约 1.5 字符/token）"""
        return int(len(text) / 1.5)

    def to_dict(self) -> Dict:
        """转为字典（用于数据库插入）"""
        return {
            "document_id": self.document_id,
            "parent_chunk_id": self.parent_chunk_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "chunk_type": self.chunk_type,
            "content_type": self.content_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chapter": self.chapter,
            "section": self.section,
            "clause": self.clause,
            "position_in_doc": self.position_in_doc,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "meta_data": self.meta_data,
            "related_chunk_ids": self.related_chunk_ids,
            "vector_id": self.vector_id,
            "has_dense_vector": self.has_dense_vector,
            "has_sparse_vector": self.has_sparse_vector
        }


class DocumentChunker:
    """文档分块器"""

    def __init__(self):
        self.embedder = None  # 延迟加载，用于语义边界检测

    def chunk_document(
        self,
        content: str,
        doc_metadata: Dict,
        document_id: Optional[int] = None,
        doc_type: str = "standard"  # "standard" or "textbook"
    ) -> List[Chunk]:
        """
        文档分块

        Args:
            content: Markdown 格式内容
            doc_metadata: 文档元数据
            document_id: 数据库文档 ID
            doc_type: 文档类型（标准/教材）

        Returns:
            父子块列表
        """
        if doc_type == "standard":
            return self._chunk_standard(content, doc_metadata, document_id)
        else:
            return self._chunk_textbook(content, doc_metadata, document_id)

    def _chunk_standard(self, content: str, doc_metadata: Dict, document_id: Optional[int]) -> List[Chunk]:
        """
        标准文档分块（按条款规则）

        规则：
        1. 父块：章节级别（包含多个条款或整章内容）
        2. 子块：单个条款（如果有）；如果无条款，则将整章内容作为子块
        """
        chunks = []
        lines = content.split("\n")

        current_chapter = None
        current_section = None
        current_clause_lines = []
        chapter_child_chunks = []
        chapter_content_lines = []  # 收集整章内容（无条款时使用）
        position = 0

        # 调试统计
        chapter_count = 0
        section_count = 0
        clause_count = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测章（父块边界）
            if self._is_chapter(line):
                chapter_count += 1
                logger.debug(f"检测到章: {line[:50]}")

                # 保存前一章
                if current_chapter:
                    if chapter_child_chunks:
                        # 有子条款：正常处理
                        parent_chunk = self._create_parent_chunk_standard(
                            current_chapter,
                            chapter_child_chunks,
                            doc_metadata,
                            document_id,
                            position
                        )
                        chunks.append(parent_chunk)
                        chunks.extend(chapter_child_chunks)
                        position += 1
                    elif chapter_content_lines:
                        # 无子条款：将整章作为一个父块+一个子块
                        full_content = "\n".join(chapter_content_lines)
                        parent_chunk = Chunk(
                            content=current_chapter + "\n\n" + full_content,
                            chunk_type="parent",
                            document_id=document_id,
                            chapter=self._extract_chapter_number(current_chapter),
                            position_in_doc=position,
                            meta_data={
                                "doc_title": doc_metadata.get("title"),
                                "standard_no": doc_metadata.get("standard_no"),
                                "chapter_title": current_chapter
                            }
                        )
                        child_chunk = Chunk(
                            content=full_content,
                            chunk_type="child",
                            document_id=document_id,
                            chapter=self._extract_chapter_number(current_chapter),
                            position_in_doc=position,
                            meta_data={
                                "doc_title": doc_metadata.get("title"),
                                "standard_no": doc_metadata.get("standard_no"),
                                "chapter_title": current_chapter
                            }
                        )
                        chunks.append(parent_chunk)
                        chunks.append(child_chunk)
                        position += 1

                current_chapter = line
                chapter_child_chunks = []
                current_clause_lines = []
                chapter_content_lines = [line]

            # 检测节
            elif self._is_section(line):
                section_count += 1
                logger.debug(f"检测到节: {line[:50]}")
                current_section = line
                chapter_content_lines.append(line)

            # 检测条款（子块）
            elif self._is_clause(line):
                clause_count += 1
                logger.debug(f"检测到条款: {line[:50]}")
                # 保存前一条款
                if current_clause_lines:
                    child_chunk = self._create_child_chunk_standard(
                        current_clause_lines,
                        doc_metadata,
                        document_id,
                        current_chapter,
                        current_section,
                        position
                    )
                    chapter_child_chunks.append(child_chunk)
                    position += 1

                current_clause_lines = [line]
                chapter_content_lines.append(line)

            else:
                # 内容行
                chapter_content_lines.append(line)
                if current_clause_lines is not None:
                    current_clause_lines.append(line)

        # 保存最后一个条款
        if current_clause_lines and len(current_clause_lines) > 1:
            child_chunk = self._create_child_chunk_standard(
                current_clause_lines,
                doc_metadata,
                document_id,
                current_chapter,
                current_section,
                position
            )
            chapter_child_chunks.append(child_chunk)
            position += 1

        # 保存最后一章
        if current_chapter:
            if chapter_child_chunks:
                parent_chunk = self._create_parent_chunk_standard(
                    current_chapter,
                    chapter_child_chunks,
                    doc_metadata,
                    document_id,
                    position
                )
                chunks.append(parent_chunk)
                chunks.extend(chapter_child_chunks)
            elif chapter_content_lines:
                # 最后一章无条款
                full_content = "\n".join(chapter_content_lines)
                parent_chunk = Chunk(
                    content=full_content,
                    chunk_type="parent",
                    document_id=document_id,
                    chapter=self._extract_chapter_number(current_chapter),
                    position_in_doc=position,
                    meta_data={
                        "doc_title": doc_metadata.get("title"),
                        "standard_no": doc_metadata.get("standard_no"),
                        "chapter_title": current_chapter
                    }
                )
                child_content = "\n".join(chapter_content_lines[1:]) if len(chapter_content_lines) > 1 else full_content
                child_chunk = Chunk(
                    content=child_content,
                    chunk_type="child",
                    document_id=document_id,
                    chapter=self._extract_chapter_number(current_chapter),
                    position_in_doc=position,
                    meta_data={
                        "doc_title": doc_metadata.get("title"),
                        "standard_no": doc_metadata.get("standard_no"),
                        "chapter_title": current_chapter
                    }
                )
                chunks.append(parent_chunk)
                chunks.append(child_chunk)

        logger.info(f"分块统计: 章={chapter_count}, 节={section_count}, 条款={clause_count}, 最终chunks={len(chunks)}")
        return chunks

    def _chunk_textbook(self, content: str, doc_metadata: Dict, document_id: Optional[int]) -> List[Chunk]:
        """
        教材分块（语义边界检测）

        使用 bge-large-zh-v1.5 计算段落相似度
        """
        chunks = []
        paragraphs = self._split_paragraphs(content)

        if len(paragraphs) < 2:
            # 内容太少，直接作为一个父块
            chunk = Chunk(
                content=content,
                chunk_type="parent",
                document_id=document_id,
                position_in_doc=0,
                meta_data={
                    "doc_title": doc_metadata.get("title"),
                    "doc_type": "textbook"
                }
            )
            chunks.append(chunk)
            return chunks

        # 使用语义相似度检测边界
        boundaries = self._detect_semantic_boundaries(paragraphs)

        # 根据边界切分父块
        position = 0
        start_idx = 0
        for boundary in boundaries:
            parent_content = "\n\n".join(paragraphs[start_idx:boundary])
            if len(parent_content) > 100:  # 最小长度
                parent_chunk = Chunk(
                    content=parent_content,
                    chunk_type="parent",
                    document_id=document_id,
                    position_in_doc=position,
                    meta_data={
                        "doc_title": doc_metadata.get("title"),
                        "doc_type": "textbook",
                        "paragraph_range": f"{start_idx}-{boundary}"
                    }
                )
                chunks.append(parent_chunk)
                position += 1

                # 创建子块（每段作为子块）
                for i in range(start_idx, boundary):
                    if len(paragraphs[i]) > 50:
                        child_chunk = Chunk(
                            content=paragraphs[i],
                            chunk_type="child",
                            document_id=document_id,
                            parent_chunk_id=None,  # 稍后设置
                            position_in_doc=position,
                            meta_data={
                                "doc_title": doc_metadata.get("title"),
                                "doc_type": "textbook",
                                "paragraph_index": i
                            }
                        )
                        chunks.append(child_chunk)
                        position += 1

            start_idx = boundary

        return chunks

    def _split_paragraphs(self, content: str) -> List[str]:
        """将内容分割为段落"""
        paragraphs = re.split(r"\n\s*\n", content)
        return [p.strip() for p in paragraphs if p.strip()]

    def _detect_semantic_boundaries(self, paragraphs: List[str]) -> List[int]:
        """
        检测语义边界

        使用 bge-large-zh-v1.5 计算相邻段落余弦相似度
        相似度骤降点 = 语义边界
        """
        if self.embedder is None:
            from app.core.embedding import embedder
            self.embedder = embedder

        # 计算每段的向量
        embeddings = []
        for para in paragraphs:
            if len(para) > 20:
                emb = self.embedder.encode(para)
                embeddings.append(emb)

        # 计算相邻段落相似度
        import numpy as np
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = np.dot(embeddings[i], embeddings[i + 1]) / (
                np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i + 1])
            )
            similarities.append(sim)

        # 找出相似度骤降点
        threshold = np.mean(similarities) - 0.5 * np.std(similarities)
        boundaries = []
        for i, sim in enumerate(similarities):
            if sim < threshold:
                boundaries.append(i + 1)

        # 确保边界间隔不太小（至少3段）
        filtered_boundaries = []
        last_boundary = 0
        for b in boundaries:
            if b - last_boundary >= 3:
                filtered_boundaries.append(b)
                last_boundary = b

        filtered_boundaries.append(len(paragraphs))
        return filtered_boundaries

    def _is_chapter(self, line: str) -> bool:
        """判断是否为章标题"""
        patterns = [
            r"^#\s+第\s*\d+\s*章",      # # 第 5 章
            r"^第\s*\d+\s*章",           # 第 5 章
            r"^\d+\s+[^\d\.]",          # 1 范围（数字+空格+非数字非点）
            r"^#{1,2}\s+\d+\s+[^\d\.]", # ## 1 范围 / # 4 要求（带#前缀）
        ]
        for pattern in patterns:
            if re.match(pattern, line):
                return True
        return False

    def _is_section(self, line: str) -> bool:
        """判断是否为节标题"""
        patterns = [
            r"^##\s+第?\s*\d+\.\d+\s*节",
            r"^第?\s*\d+\.\d+\s*节",
        ]
        for pattern in patterns:
            if re.match(pattern, line):
                return True
        return False

    def _is_clause(self, line: str) -> bool:
        """判断是否为条款"""
        patterns = [
            r"^#{2,4}\s+\d+\.\d+",           # ## 5.2.1 (标准格式)
            r"^#{2,4}\s*\d{2,5}(?:\.\d+)?",  # ## 42 / ## 421 / ## 7314（MinerU格式，2-5位数字）
            r"^\d+\.\d+\.\d+\s",              # 5.2.1 (三级)
            r"^\d+\.\d+\s+[^\d]",             # 5.2 技术要求（二级，后面不是数字）
        ]
        for pattern in patterns:
            if re.match(pattern, line):
                return True
        return False

    def _create_parent_chunk_standard(
        self,
        chapter_title: str,
        child_chunks: List[Chunk],
        doc_metadata: Dict,
        document_id: Optional[int],
        position: int
    ) -> Chunk:
        """创建父块（章节级别）"""
        texts = [chapter_title] + [c.content for c in child_chunks]
        full_content = "\n\n".join(texts)

        chapter_no = self._extract_chapter_number(chapter_title)

        # 页码范围（从子块获取，可能为 None）
        page_starts = [c.page_start for c in child_chunks if c.page_start is not None]
        page_ends = [c.page_end for c in child_chunks if c.page_end is not None]
        page_start = min(page_starts) if page_starts else None
        page_end = max(page_ends) if page_ends else None

        return Chunk(
            content=full_content,
            chunk_type="parent",
            document_id=document_id,
            parent_chunk_id=None,
            chapter=chapter_no,
            page_start=page_start,
            page_end=page_end,
            position_in_doc=position,
            meta_data={
                "doc_title": doc_metadata.get("title"),
                "standard_no": doc_metadata.get("standard_no"),
                "chapter_title": chapter_title
            }
        )

    def _create_child_chunk_standard(
        self,
        clause_lines: List[str],
        doc_metadata: Dict,
        document_id: Optional[int],
        chapter_title: Optional[str],
        section_title: Optional[str],
        position: int
    ) -> Chunk:
        """创建子块（条款级别）"""
        content = "\n".join(clause_lines)
        clause_no = self._extract_clause_number(clause_lines[0])
        clause_title = self._extract_clause_title(clause_lines[0])
        chapter_no = self._extract_chapter_number(chapter_title) if chapter_title else None
        section_no = self._extract_section_number(section_title) if section_title else None

        return Chunk(
            content=content,
            chunk_type="child",
            document_id=document_id,
            parent_chunk_id=None,
            chapter=chapter_no,
            section=section_no,
            clause=clause_no,
            position_in_doc=position,
            meta_data={
                "doc_title": doc_metadata.get("title"),
                "standard_no": doc_metadata.get("standard_no"),
                "clause_title": clause_title,
                "chapter_title": chapter_title,
                "section_title": section_title
            }
        )

    def _extract_clause_number(self, line: str) -> Optional[str]:
        """提取条款号"""
        match = re.match(r"^#{0,4}\s*(\d+\.\d+(?:\.\d+)?)", line)
        return match.group(1) if match else None

    def _extract_clause_title(self, line: str) -> Optional[str]:
        """提取条款标题"""
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\d+\.\d+(?:\.\d+)?\s*", "", line)
        return line.strip() if line.strip() else None

    def _extract_chapter_number(self, title: str) -> Optional[str]:
        """提取章节号"""
        if not title:
            return None
        # 匹配 "第 5 章" 或 "5." 或 "1 范围" 或 "## 1 范围"
        match = re.search(r"第?\s*(\d+)\s*章", title)
        if match:
            return match.group(1)
        match = re.match(r"^#*\s*(\d+)\.", title)
        if match:
            return match.group(1)
        match = re.match(r"^#*\s*(\d+)\s+", title)
        if match:
            return match.group(1)
        return None

    def _extract_section_number(self, title: str) -> Optional[str]:
        """提取节号"""
        if not title:
            return None
        match = re.search(r"第?\s*(\d+\.\d+)\s*节", title)
        if match:
            return match.group(1)
        match = re.match(r"^##\s*(\d+\.\d+)", title)
        return match.group(1) if match else None


def compute_image_text_associations(
    text_chunks: List[Tuple[int, str, int, int]],
    image_chunks: List[Tuple[int, str, int]],
    text_vectors: List,
    image_vectors: List,
    threshold: float = 0.75
) -> Dict[int, List[int]]:
    """
    计算图文语义关联

    实现策略：
    1. 物理邻近：文本块与前后1页内的图片建立关联
    2. 语义相似：计算文本向量与图片描述向量的余弦相似度，≥ threshold 则关联

    Args:
        text_chunks: [(chunk_id, content, page_start, page_end), ...]
        image_chunks: [(chunk_id, description, page_number), ...]
        text_vectors: 文本块的稠密向量列表（与 text_chunks 顺序对应）
        image_vectors: 图片描述的稠密向量列表（与 image_chunks 顺序对应）
        threshold: 相似度阈值（默认 0.75）

    Returns:
        {text_chunk_id: [related_image_chunk_id, ...]}
    """
    import numpy as np

    associations: Dict[int, List[int]] = {}

    if not text_chunks or not image_chunks:
        return associations

    # 构建向量矩阵
    text_matrix = np.array(text_vectors)  # shape: (N_text, dim)
    image_matrix = np.array(image_vectors)  # shape: (N_img, dim)

    # 归一化
    text_norms = np.linalg.norm(text_matrix, axis=1, keepdims=True)
    image_norms = np.linalg.norm(image_matrix, axis=1, keepdims=True)
    text_matrix = text_matrix / (text_norms + 1e-8)
    image_matrix = image_matrix / (image_norms + 1e-8)

    # 计算余弦相似度矩阵 (N_text, N_img)
    similarity_matrix = np.dot(text_matrix, image_matrix.T)

    # 遍历每个文本块
    for i, (text_id, text_content, text_page_start, text_page_end) in enumerate(text_chunks):
        related_images = []

        for j, (img_id, img_desc, img_page) in enumerate(image_chunks):
            # 策略 1：物理邻近（前后1页）
            if text_page_start and text_page_end and img_page:
                if text_page_start - 1 <= img_page <= text_page_end + 1:
                    if img_id not in related_images:
                        related_images.append(img_id)
                    continue

            # 策略 2：语义相似度
            sim = similarity_matrix[i, j]
            if sim >= threshold:
                if img_id not in related_images:
                    related_images.append(img_id)

        if related_images:
            associations[text_id] = related_images

    return associations


# 全局实例
document_chunker = DocumentChunker()
