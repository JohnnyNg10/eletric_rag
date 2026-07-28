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

        # 从文件名提取（优先级最高）
        filename_meta = self._extract_from_filename(filename)
        metadata.update(filename_meta)

        # 从内容提取（只填充缺失字段）
        content_meta = self._extract_from_content(content)
        for key, value in content_meta.items():
            metadata.setdefault(key, value)

        # 设置默认值
        metadata.setdefault("status", "valid")
        metadata.setdefault("doc_type", "standard")
        metadata.setdefault("publish_org", "未知")

        return metadata

    def _extract_from_filename(self, filename: str) -> Dict:
        """从文件名提取元数据"""
        metadata = {}

        # 提取标准号（GB 1002-2024, DL/T 621-1997, GBT+36278-2018, Q/XXX-2024）
        patterns = [
            r"(GB|DL|NB|JB|HG)[\s_/\\+]*(/T|T)?[\s_]*(\d+(?:\.\d+)?)[_\s\-—]*(\d{4})",
            r"(Q/[A-Za-z0-9]+)[_\s\-—]*(\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                groups = match.groups()

                # 第一个正则：4 组（prefix, sub_type, number, year）
                if len(groups) == 4:
                    prefix = groups[0].upper()
                    sub_type = groups[1].strip() if groups[1] else ""
                    number = groups[2]
                    year = groups[3]

                    if sub_type:
                        standard_no = f"{prefix}/{sub_type} {number}-{year}"
                    else:
                        standard_no = f"{prefix} {number}-{year}"

                    metadata["standard_no"] = standard_no
                    metadata["version"] = f"{year}版"
                    metadata["publish_date"] = f"{year}-01-01"
                    break

                # 第二个正则：2 组（Q/XXX, year）
                elif len(groups) == 2:
                    standard_no = f"{groups[0]}-{groups[1]}"
                    metadata["standard_no"] = standard_no
                    metadata["version"] = f"{groups[1]}版"
                    metadata["publish_date"] = f"{groups[1]}-01-01"
                    break

        return metadata

    def _extract_from_content(self, content: str) -> Dict:
        """从内容提取元数据"""
        metadata = {}

        # 从内容提取标准号（兜底，当文件名解析失败时）
        standard_patterns = [
            r"(GB|DL|NB|JB|HG)[\s/]*(/T|T)?[\s]*(\d+(?:\.\d+)?)[\s—\-~～]+(\d{4})",
            r"(Q/[A-Za-z0-9]+)[\s—\-~～]+(\d{4})",
        ]
        for pattern in standard_patterns:
            match = re.search(pattern, content[:500])  # 只在前500字符查找
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    prefix = groups[0].upper()
                    sub_type = groups[1]
                    number = groups[2]
                    year = groups[3]

                    if sub_type and sub_type.startswith("/"):
                        standard_no = f"{prefix}{sub_type} {number}-{year}"
                    elif sub_type:
                        standard_no = f"{prefix}/{sub_type} {number}-{year}"
                    else:
                        standard_no = f"{prefix} {number}-{year}"

                    metadata["standard_no"] = standard_no
                    metadata["version"] = f"{year}版"
                    if "publish_date" not in metadata:
                        metadata["publish_date"] = f"{year}-01-01"
                    break
                elif len(groups) == 2:
                    standard_no = f"{groups[0]}-{groups[1]}"
                    metadata["standard_no"] = standard_no
                    metadata["version"] = f"{groups[1]}版"
                    if "publish_date" not in metadata:
                        metadata["publish_date"] = f"{groups[1]}-01-01"
                    break

        # 提取标题（跳过封面标题）
        lines = content.split("\n")
        skip_titles = {"中华人民共和国国家标准", "国家标准", "行业标准", "电力行业标准"}
        for line in lines[:15]:
            line = line.strip()
            if line and len(line) > 5 and len(line) < 100:
                # 移除 Markdown 标记
                title = re.sub(r"^#+\s*", "", line)
                # 跳过封面标题、标准号、数字编号开头的行
                if title and not re.match(r"^\d+\.?\s", title) and title not in skip_titles:
                    # 跳过标准号格式的行
                    if not re.match(r"^(GB|DL|NB|JB|HG|Q)/", title):
                        metadata["title"] = title
                        break

        # 提取发布日期和实施日期（支持多种格式）
        date_patterns = [
            (r"(\d{4}[-年]\d{1,2}[-月]\d{1,2})\s*发布", "publish_date"),
            (r"发布日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)", "publish_date"),
            (r"(\d{4}[-年]\d{1,2}[-月]\d{1,2})\s*实施", "implement_date"),
            (r"实施日期[：:]\s*(\d{4}[-年]\d{1,2}[-月]\d{1,2}日?)", "implement_date"),
        ]
        for pattern, key in date_patterns:
            match = re.search(pattern, content[:1000])  # 在前1000字符查找
            if match:
                date_str = match.group(1)
                # 标准化日期格式
                date_str = date_str.replace("年", "-").replace("月", "-").replace("日", "")
                metadata[key] = date_str

        # 提取发布机构
        org_patterns = [
            r"发布(?:单位|机构)[：:]\s*([^\n]+)",
            r"本标准由([^提]+)提出",
            r"中华人民共和国([^\n，,。.]{2,20})",
        ]
        for pattern in org_patterns:
            match = re.search(pattern, content[:2000])
            if match:
                metadata["publish_org"] = match.group(1).strip()
                break

        # 检测替代关系
        replace_pattern = r"(?:替代|代替|本标准替代)(?:标准)?[：:]*\s*((?:GB|DL|NB)[^\n]+)"
        match = re.search(replace_pattern, content[:2000])
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
