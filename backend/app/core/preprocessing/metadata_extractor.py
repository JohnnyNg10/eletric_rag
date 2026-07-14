"""
元数据提取器 - 预处理层第四步

职责：
1. 提取电压等级、标准号、专业分类
2. 生成Qdrant Payload过滤条件
"""
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MetadataExtractor:
    """元数据提取器"""

    def __init__(self):
        # 专业分类关键词映射（扩充版，提升识别准确率）
        self.category_keywords = {
            '配电': [
                '配电室', '配电柜', '配电系统', '配电装置', '配电网', '配网',
                '低压开关柜', '开关柜', '母线', '进线柜', '出线柜'
            ],
            '变电': [
                '变电站', '变压器', '变电设备', '变电所',
                '主变', '副变', '变电容量', '变电运行', '变电检修',
                '油浸式', '干式变压器'
            ],
            '继保': [
                '继电保护', '保护装置', '保护系统',
                '整定', '整定计算', '保护配置', '保护定值',  # ← 扩充
                '差动保护', '距离保护', '过流保护', '零序保护',  # ← 扩充
                '保护原理', '选择性', '灵敏性', '速动性'  # ← 扩充
            ],
            '输电': [
                '输电线路', '架空线', '电缆',
                '输电走廊', '导线', '绝缘子', '杆塔', '输电容量'
            ],
            '安全': [
                '安全距离', '安全措施', '防护', '接地', '防雷',
                '安全净距', '防护等级', 'IP等级', '接地电阻', '接地装置'
            ],
        }

    def extract(self, query: str, preprocessing_result=None) -> Dict[str, Any]:
        """
        提取元数据并生成过滤条件

        Args:
            query: 查询文本
            preprocessing_result: 预处理结果（OptimizationResult），包含 LLM 识别的类别

        Returns:
            Dict: Qdrant Payload过滤条件
        """
        filters = {}

        logger.warning(f"[MetadataExtractor] extract called, query='{query[:50]}'")

        # 注意：voltage_level 过滤已禁用
        # 原因：当前所有入库文档的 voltage_level 字段均为 NULL，
        # 用该字段过滤会导致零召回。待入库流程补充该字段后再启用。

        # 2. 提取标准号
        standard_no = self._extract_standard_no(query)
        if standard_no:
            filters['standard_no'] = standard_no

        # 3. 提取专业分类
        # 优先使用 LLM 识别的类别（如果提供且置信度足够）
        if preprocessing_result and hasattr(preprocessing_result, 'category'):
            if preprocessing_result.category_confidence >= 0.6 and preprocessing_result.category != "通用":
                filters['category'] = preprocessing_result.category
                logger.info(f"[MetadataExtractor] Using LLM category: {preprocessing_result.category} (confidence={preprocessing_result.category_confidence:.2f})")
            else:
                # 置信度低或为"通用"，降级到关键词匹配
                category = self._extract_category(query)
                if category:
                    filters['category'] = category
                    logger.info(f"[MetadataExtractor] Using keyword category: {category} (LLM confidence too low or generic)")
        else:
            # 无预处理结果，使用关键词匹配
            category = self._extract_category(query)
            if category:
                filters['category'] = category
                logger.info(f"[MetadataExtractor] Using keyword category: {category} (no preprocessing result)")

        return filters

    def _is_compatibility_question(self, query: str) -> bool:
        """
        判断是否为兼容性/适用性问题

        这类问题通常是询问某个电压等级是否适用于某标准，
        不应该用电压等级作为过滤条件（会漏掉答案）

        Args:
            query: 查询文本

        Returns:
            bool: 是否为兼容性问题
        """
        compatibility_patterns = [
            r'能否.*参照',
            r'是否.*适用',
            r'可以.*参照',
            r'适用.*吗',
            r'适用.*哪些',
            r'包含.*哪些',
            r'.*适用范围',
        ]

        for pattern in compatibility_patterns:
            if re.search(pattern, query):
                return True

        return False

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
            Optional[str]: 专业分类，如果匹配多个则返回 None（避免过度过滤）
        """
        # 收集所有匹配的分类
        matched_categories = []
        for category, keywords in self.category_keywords.items():
            if any(keyword in query for keyword in keywords):
                matched_categories.append(category)

        # 如果匹配多个分类，说明是跨领域查询，不应该用单一分类过滤
        if len(matched_categories) > 1:
            logger.info(f"[MetadataExtractor] Query matches multiple categories: {matched_categories}, skip category filter")
            return None

        # 返回唯一匹配的分类
        return matched_categories[0] if matched_categories else None

    def extract_all_metadata(self, query: str, preprocessing_result=None) -> Dict[str, Any]:
        """
        提取所有元数据（不仅用于过滤）

        Args:
            query: 查询文本
            preprocessing_result: 预处理结果（OptimizationResult），包含 LLM 识别的类别

        Returns:
            Dict: 完整元数据
        """
        metadata = {
            'voltage_level': self._extract_voltage_level(query),
            'standard_no': self._extract_standard_no(query),
        }

        # 优先使用 LLM 识别的类别（如果提供且置信度足够）
        if preprocessing_result and hasattr(preprocessing_result, 'category'):
            if preprocessing_result.category_confidence >= 0.6:
                metadata['category'] = preprocessing_result.category
                metadata['category_source'] = 'llm'
                metadata['category_confidence'] = preprocessing_result.category_confidence
            else:
                # 置信度低，降级到关键词匹配
                metadata['category'] = self._extract_category(query)
                metadata['category_source'] = 'keyword'
        else:
            # 无预处理结果，使用关键词匹配
            metadata['category'] = self._extract_category(query)
            metadata['category_source'] = 'keyword'

        # 移除None值
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return metadata
