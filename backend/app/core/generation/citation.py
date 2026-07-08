"""
引用提取器 (Citation Extractor)

从LLM生成的答案中提取引用标注
"""
import re
from typing import List, Optional
from dataclasses import dataclass
import logging

from app.core.retrieval.rerank import RerankResult

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """引用信息"""
    index: int  # 引用编号 [1], [2], ...
    chunk_id: int  # 块ID
    standard_no: Optional[str]  # 标准号
    clause: Optional[str]  # 条款号
    content_snippet: str  # 内容片段（前100字）
    position: int  # 在答案中的位置
    document_title: Optional[str] = None  # 文档标题


class CitationExtractor:
    """
    引用提取器

    从答案中提取引用标注，格式：[1]、[2]等
    """

    def __init__(self):
        # 匹配 [数字] 格式
        self.citation_pattern = re.compile(r'\[(\d+)\]')

    def extract(
        self,
        answer: str,
        chunks: List[RerankResult]
    ) -> List[Citation]:
        """
        提取答案中的引用

        Args:
            answer: LLM生成的答案
            chunks: 参考的文档块列表

        Returns:
            List[Citation]: 引用列表
        """
        citations = []
        seen_indices = set()

        # 查找所有 [数字] 标注
        for match in self.citation_pattern.finditer(answer):
            idx = int(match.group(1))

            # 避免重复
            if idx in seen_indices:
                continue
            seen_indices.add(idx)

            # 验证索引范围
            if not (1 <= idx <= len(chunks)):
                logger.warning(f"[CitationExtractor] Invalid citation index: [{idx}], max={len(chunks)}")
                continue

            # 获取对应的chunk
            chunk = chunks[idx - 1]

            # 构造Citation对象
            citations.append(Citation(
                index=idx,
                chunk_id=chunk.chunk_id,
                standard_no=chunk.standard_no,
                clause=chunk.clause,
                content_snippet=chunk.content[:100] if chunk.content else "",
                position=match.start(),
                document_title=chunk.document_title
            ))

        # 按位置排序
        citations.sort(key=lambda c: c.position)

        logger.info(f"[CitationExtractor] Extracted {len(citations)} citations from answer")
        return citations

    def format_citation(self, citation: Citation) -> str:
        """
        格式化单个引用为可读字符串

        Returns:
            格式：[1] GB 50057-2010 第3.2.1条
        """
        parts = [f"[{citation.index}]"]

        if citation.standard_no:
            parts.append(citation.standard_no)

        if citation.clause:
            parts.append(f"第{citation.clause}条")
        elif citation.document_title:
            parts.append(citation.document_title[:30])

        return " ".join(parts)

    def validate_citations(
        self,
        answer: str,
        chunks: List[RerankResult]
    ) -> dict:
        """
        验证引用的完整性

        Returns:
            {
                "valid": bool,
                "cited_count": int,
                "total_chunks": int,
                "coverage_rate": float,
                "issues": List[str]
            }
        """
        citations = self.extract(answer, chunks)
        issues = []

        # 检查是否所有chunk都被引用
        cited_indices = {c.index for c in citations}
        total_chunks = len(chunks)
        uncited_indices = set(range(1, total_chunks + 1)) - cited_indices

        if uncited_indices:
            issues.append(f"Uncited chunks: {sorted(uncited_indices)}")

        # 检查是否有答案但无引用
        has_content = len(answer.strip()) > 50
        has_citations = len(citations) > 0

        if has_content and not has_citations:
            issues.append("Answer has content but no citations")

        coverage_rate = len(cited_indices) / total_chunks if total_chunks > 0 else 0.0

        return {
            "valid": len(issues) == 0,
            "cited_count": len(cited_indices),
            "total_chunks": total_chunks,
            "coverage_rate": coverage_rate,
            "issues": issues
        }


# 全局单例
_extractor_instance: Optional[CitationExtractor] = None


def get_citation_extractor() -> CitationExtractor:
    """获取引用提取器单例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = CitationExtractor()
    return _extractor_instance
