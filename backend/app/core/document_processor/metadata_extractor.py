"""
元数据提取器

从文档中提取结构化元数据
"""
from typing import Dict, Optional, List
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """元数据提取器"""

    def extract_from_document(
        self,
        content: str,
        filename: str,
        parsed_metadata: Optional[Dict] = None
    ) -> Dict:
        """
        从文档提取元数据

        Args:
            content: 文档内容
            filename: 文件名
            parsed_metadata: PDF 解析器提取的元数据

        Returns:
            完整的元数据字典
        """
        metadata = parsed_metadata or {}

        # 从文件名提取
        filename_meta = self._extract_from_filename(filename)
        metadata.update(filename_meta)

        # 从内容提取
        content_meta = self._extract_from_content(content)
        metadata.update(content_meta)

        # 设置默认值
        metadata.setdefault("status", "valid")
        metadata.setdefault("doc_type", "standard")
        metadata.setdefault("publish_org", "未知")

        return metadata

    def _extract_from_filename(self, filename: str) -> Dict:
        """从文件名提取元数据"""
        metadata = {}

        # 提取标准号（GB 1002-2024, DL/T 621-1997, GB+1002-2024）
        patterns = [
            r"(GB|DL|NB|JB|HG)[\s_/\\+]*([T\s]*)?[\s_]*(\d+(?:\.\d+)?)[_\s\-—]*(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                prefix = match.group(1).upper()
                sub_type = match.group(2).strip() if match.group(2) else ""
                number = match.group(3)
                year = match.group(4)

                if sub_type:
                    standard_no = f"{prefix}/{sub_type} {number}-{year}"
                else:
                    standard_no = f"{prefix} {number}-{year}"

                metadata["standard_no"] = standard_no
                metadata["version"] = f"{year}版"
                metadata["publish_date"] = f"{year}-01-01"
                break

        return metadata

    def _extract_from_content(self, content: str) -> Dict:
        """从内容提取元数据"""
        metadata = {}

        # 提取标题（通常在第一行或前几行）
        lines = content.split("\n")
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 5 and len(line) < 100:
                # 移除 Markdown 标记
                title = re.sub(r"^#+\s*", "", line)
                if title and not re.match(r"^\d+\.?\s", title):
                    metadata["title"] = title
                    break

        # 提取实施日期
        implement_pattern = r"实施日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)"
        match = re.search(implement_pattern, content)
        if match:
            date_str = match.group(1)
            # 标准化日期格式
            date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "")
            metadata["implement_date"] = date_str

        # 提取发布机构
        org_patterns = [
            r"发布(?:单位|机构)[：:]\s*([^\n]+)",
            r"中华人民共和国([^\n，,。.]{2,20})",
        ]
        for pattern in org_patterns:
            match = re.search(pattern, content)
            if match:
                metadata["publish_org"] = match.group(1).strip()
                break

        # 检测替代关系
        replace_pattern = r"(?:替代|代替)(?:标准)?[：:]\s*((?:GB|DL|NB)[^\n]+)"
        match = re.search(replace_pattern, content)
        if match:
            metadata["replaces"] = match.group(1).strip()

        return metadata

    def extract_keywords(self, content: str, top_k: int = 10) -> List[str]:
        """
        提取关键词（简单的 TF-IDF 提取）

        Args:
            content: 文档内容
            top_k: 返回前 k 个关键词

        Returns:
            关键词列表
        """
        # 简单实现：提取高频专业词汇
        # TODO: 使用更复杂的 NLP 方法

        # 移除标点符号
        content = re.sub(r"[^\w\s]", " ", content)

        # 分词（简单按空格和长度）
        words = content.split()
        word_freq = {}

        for word in words:
            # 过滤：长度 2-6，不全是数字
            if 2 <= len(word) <= 6 and not word.isdigit():
                word_freq[word] = word_freq.get(word, 0) + 1

        # 排序并返回 top_k
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        keywords = [word for word, freq in sorted_words[:top_k]]

        return keywords


# 全局实例
metadata_extractor = MetadataExtractor()
