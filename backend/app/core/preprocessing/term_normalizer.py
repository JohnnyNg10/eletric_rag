"""
术语标准化器 - 预处理层第一步

职责：将行业黑话、口语化表达转换为标准术语
"""
import re
from typing import Dict


class TermNormalizer:
    """术语标准化器"""

    def __init__(self):
        # 术语映射词典（行业黑话 → 标准术语）
        self.term_dict = {
            # 设备类
            "PT": "电压互感器",
            "CT": "电流互感器",
            "刀闸": "隔离开关",
            "刀开关": "隔离开关",
            "断路器": "断路器",
            "开关柜": "开关柜",

            # 电压等级
            "10千伏": "10kV",
            "35千伏": "35kV",
            "110千伏": "110kV",
            "220千伏": "220kV",
            "十千伏": "10kV",

            # 专业术语
            "接地": "接地",
            "防雷": "防雷",
            "避雷针": "接闪杆",
            "避雷器": "避雷器",

            # 其他常用
            "配电房": "配电室",
            "变压器室": "变压器室",
        }

    def normalize(self, query: str) -> str:
        """
        标准化查询中的术语

        Args:
            query: 原始查询

        Returns:
            str: 标准化后的查询
        """
        normalized_query = query

        # 遍历术语词典进行替换
        for slang, standard in self.term_dict.items():
            # 使用正则替换，避免部分匹配
            pattern = re.escape(slang)
            normalized_query = re.sub(pattern, standard, normalized_query)

        return normalized_query

    def add_term(self, slang: str, standard: str):
        """
        动态添加术语映射

        Args:
            slang: 行业黑话
            standard: 标准术语
        """
        self.term_dict[slang] = standard

    def get_term_dict(self) -> Dict[str, str]:
        """获取当前术语词典"""
        return self.term_dict.copy()
