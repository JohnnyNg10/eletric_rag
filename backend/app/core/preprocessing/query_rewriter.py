"""
查询改写器 - 预处理层第三步

职责：
1. 生成同义专业问法（2-3个）
2. HyDE假设答案生成（可选）
3. 查询拆解（复杂问题→多个子问题）
"""
from typing import List


class QueryRewriter:
    """查询改写器"""

    def __init__(self):
        # 同义词映射
        self.synonym_map = {
            "要求": ["规定", "标准", "规范"],
            "距离": ["间距", "间隔", "间隙"],
            "安全": ["防护", "保护"],
            "设置": ["安装", "配置", "布置"],
            "检测": ["测试", "检验", "试验"],
        }

    async def rewrite(
        self,
        query: str,
        max_expansions: int = 3
    ) -> List[str]:
        """
        查询改写与扩展

        Args:
            query: 优化后的查询
            max_expansions: 最大扩展数量

        Returns:
            List[str]: 扩展查询列表（包含原查询）
        """
        expanded_queries = [query]  # 原查询

        # 生成同义改写
        synonym_queries = await self._generate_synonym_rewrites(query)
        expanded_queries.extend(synonym_queries[:max_expansions - 1])

        return expanded_queries[:max_expansions]

    async def _generate_synonym_rewrites(self, query: str) -> List[str]:
        """
        生成同义改写

        Args:
            query: 查询文本

        Returns:
            List[str]: 同义改写列表
        """
        rewrites = []

        # 简单实现：替换同义词
        for word, synonyms in self.synonym_map.items():
            if word in query:
                for synonym in synonyms[:2]:  # 每个词最多2个同义词
                    rewritten = query.replace(word, synonym)
                    if rewritten not in rewrites and rewritten != query:
                        rewrites.append(rewritten)

        return rewrites

    async def generate_hyde(self, query: str) -> str:
        """
        生成HyDE假设答案（用于向量检索）

        TODO: 使用LLM生成假设的专业答案（200字）

        Args:
            query: 查询文本

        Returns:
            str: 假设答案
        """
        # 当前返回空，未来集成LLM
        return ""

    async def decompose(self, query: str) -> List[str]:
        """
        查询拆解（复杂问题→多个子问题）

        TODO: 使用LLM识别并拆解复杂查询

        Args:
            query: 查询文本

        Returns:
            List[str]: 子问题列表
        """
        # 当前不拆解
        return [query]
