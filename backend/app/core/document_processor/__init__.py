"""
文档处理模块

负责将原始 PDF 文档转换为可检索的知识单元

处理流程：
1. PDF 解析 → Markdown
2. 智能分块（父子块）
3. 元数据提取
4. 术语标准化
5. 向量化
"""
from app.core.document_processor.parser import PDFParser
from app.core.document_processor.chunker import DocumentChunker
from app.core.document_processor.metadata_extractor import MetadataExtractor
from app.core.document_processor.classifier import DocumentClassifier

__all__ = [
    "PDFParser",
    "DocumentChunker",
    "MetadataExtractor",
    "DocumentClassifier",
]
