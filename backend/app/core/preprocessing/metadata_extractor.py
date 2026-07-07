"""
元数据提取器 - 预处理层第四步

职责：
1. 提取电压等级、标准号、专业分类
2. 生成Qdrant Payload过滤条件
"""
import re
from typing import Dict, Any, Optional


class MetadataExtractor:
    """元数据提取器"""

    def __init__(self):
        # 专业分类关键词映射
        self.category_keywords = {
            '配电': ['配电室', '配电柜', '配电系统', '配电装置', '配电网'],
            '变电': ['变电站', '变压器', '变电设备', '变电所'],
            '继保': ['继电保护', '保护装置', '保护系统'],
            '输电': ['输电线路', '架空线', '电缆'],
            '安全': ['安全距离', '安全措施', '防护', '接地', '防雷'],
        }

    def extract(self, query: str) -> Dict[str, Any]:
        """
        提取元数据并生成过滤条件

        Args:
            query: 查询文本

        Returns:
            Dict: Qdrant Payload过滤条件
        """
        filters = {}

        # 1. 提取电压等级
        voltage_level = self._extract_voltage_level(query)
        if voltage_level:
            filters['voltage_level'] = voltage_level

        # 2. 提取标准号
        standard_no = self._extract_standard_no(query)
        if standard_no:
            filters['standard_no'] = standard_no

        # 3. 提取专业分类
        category = self._extract_category(query)
        if category:
            filters['category'] = category

        return filters

    def _extract_voltage_level(self, query: str) -> Optional[str]:
        """
        提取电压等级

        支持格式：
        - 10kV, 35kV, 110kV, 220kV
        - 10千伏, 35千伏（应该已被术语标准化）

        Args:
            query: 查询文本

        Returns:
            Optional[str]: 电压等级（如"10kV"）
        """
        # 匹配模式：数字 + kV
        pattern = r'(\d+(?:\.\d+)?)kV'
        match = re.search(pattern, query, re.IGNORECASE)

        if match:
            voltage = match.group(1)
            return f"{voltage}kV"

        return None

    def _extract_standard_no(self, query: str) -> Optional[str]:
        """
        提取标准号

        支持格式：
        - GB 50057-2010
        - DL/T 621-1997
        - NB/T 42021-2015

        Args:
            query: 查询文本

        Returns:
            Optional[str]: 标准号
        """
        # 匹配模式：标准类型 + 编号
        patterns = [
            r'GB\s*/?\s*T?\s*\d+(?:\.\d+)?(?:-\d{4})?',  # GB, GB/T
            r'DL\s*/?\s*T\s*\d+(?:\.\d+)?(?:-\d{4})?',   # DL/T
            r'NB\s*/?\s*T\s*\d+(?:\.\d+)?(?:-\d{4})?',   # NB/T
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                # 标准化标准号格式（去除多余空格）
                standard_no = re.sub(r'\s+', ' ', match.group(0))
                return standard_no.strip()

        return None

    def _extract_category(self, query: str) -> Optional[str]:
        """
        提取专业分类

        基于关键词匹配

        Args:
            query: 查询文本

        Returns:
            Optional[str]: 专业分类
        """
        # 遍历分类关键词，返回第一个匹配的分类
        for category, keywords in self.category_keywords.items():
            if any(keyword in query for keyword in keywords):
                return category

        return None

    def extract_all_metadata(self, query: str) -> Dict[str, Any]:
        """
        提取所有元数据（不仅用于过滤）

        Args:
            query: 查询文本

        Returns:
            Dict: 完整元数据
        """
        metadata = {
            'voltage_level': self._extract_voltage_level(query),
            'standard_no': self._extract_standard_no(query),
            'category': self._extract_category(query),
        }

        # 移除None值
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return metadata
