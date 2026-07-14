"""
跨标准引用提取器

从查询结果的文本块或信息缺口中提取被引用的标准号，
用于补充检索被引用标准的实际内容。

示例：
  文本："需符合 GB/T 14549 的要求"
  提取：["GB/T 14549"]
"""
import re
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

# 标准号匹配模式（支持 GB/T、GB、DL、NB 等）
# 匹配带年份和不带年份两种情况
STANDARD_NO_PATTERN = re.compile(
    r'(GB|DL|NB)(?:[/\s]*T)?\s*(\d+)(?:[-–—](\d+))?',
    re.IGNORECASE
)


class ReferenceExtractor:
    """跨标准引用提取器"""

    def extract_from_gaps(self, gaps: List[str]) -> List[str]:
        """
        从充分性判断的信息缺口中提取被引用标准号

        Args:
            gaps: 信息缺口列表，如 ["缺少 GB/T 14549 的具体限值", "未找到电压等级分类"]

        Returns:
            被引用标准号列表，如 ["GB/T 14549"]
        """
        standards = set()
        for gap in gaps:
            standards.update(self._extract_from_text(gap))
        return list(standards)

    def extract_from_chunks(self, chunks: List[dict]) -> List[str]:
        """
        从召回的文档块中提取被引用标准号

        Args:
            chunks: 召回的文档块列表，每项包含 content 字段

        Returns:
            被引用标准号列表
        """
        standards = set()
        for chunk in chunks:
            content = chunk.get('content', '')
            if not content:
                continue
            # 检测引用型文本（包含常见引导词）
            if self._contains_reference_indicators(content):
                standards.update(self._extract_from_text(content))
        return list(standards)

    def _extract_from_text(self, text: str) -> Set[str]:
        """
        从文本中提取所有标准号

        Returns:
            标准号集合，如 {"GB/T 14549", "GB 50054-2011"}
        """
        matches = STANDARD_NO_PATTERN.findall(text)
        standards = set()
        for match in matches:
            prefix, main, year = match
            # 规范化：统一为 "GB/T 14549-2023" 或 "GB/T 14549" 格式
            if '/' in prefix or 'T' in text[text.index(prefix):text.index(prefix) + 10]:
                if year:
                    normalized = f"{prefix}/T {main}-{year}"
                else:
                    normalized = f"{prefix}/T {main}"
            else:
                if year:
                    normalized = f"{prefix} {main}-{year}"
                else:
                    normalized = f"{prefix} {main}"
            standards.add(normalized)
        return standards

    def _contains_reference_indicators(self, text: str) -> bool:
        """
        判断文本是否包含引用型指示词

        常见引导词：
          - "应符合"、"须符合"、"需符合"
          - "应满足"、"须满足"、"需满足"
          - "应执行"
          - "参见"、"参考"、"见"
          - "依据"、"按照"、"根据"
        """
        indicators = [
            '应符合', '须符合', '需符合', '必须符合',
            '应满足', '须满足', '需满足',
            '应执行',
            '参见', '参考', '见',
            '依据', '按照', '根据',
            '引用', '遵循'
        ]
        return any(indicator in text for indicator in indicators)


# 全局单例
_extractor_instance = None


def get_reference_extractor() -> ReferenceExtractor:
    """获取引用提取器单例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = ReferenceExtractor()
    return _extractor_instance
