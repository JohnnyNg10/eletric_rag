"""
查询改写器 - 预处理层第三步

职责：
1. 生成同义专业问法（2-3个）
2. HyDE假设答案生成（可选）
3. 查询拆解（复杂问题→多个子问题）
"""
import json
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

_COMPARISON_RE = re.compile(r'比较|对比|区别|差异|不同|平衡')
_MULTI_ASPECT_RE = re.compile(r'分别|各自|和|与|以及|及')
_QUERY_INTENT_RE = re.compile(r'哪些|什么|如何|要求|原则|配置|方式|规定')


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
        self._llm_client = None

    @property
    def llm_client(self):
        if self._llm_client is None:
            from app.core.generation.llm_client import get_llm_client
            self._llm_client = get_llm_client()
        return self._llm_client

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

    def is_comparison_query(self, query: str) -> bool:
        """判断是否为对比/差异/平衡类查询，应优先走慢车道"""
        return len(query) >= 12 and bool(_COMPARISON_RE.search(query))

    def is_multi_aspect_query(self, query: str) -> bool:
        """判断是否为同主题多方面查询，适合在快车道拆解召回"""
        return len(query) >= 12 and bool(_MULTI_ASPECT_RE.search(query) and _QUERY_INTENT_RE.search(query))

    def is_complex_query(self, query: str) -> bool:
        """
        判断是否为需要拆解的复杂查询

        包括对比/差异类查询，以及同主题多方面查询。
        """
        return self.is_comparison_query(query) or self.is_multi_aspect_query(query)

    async def decompose(self, query: str) -> List[str]:
        """
        查询拆解（复杂问题→多个子问题）

        简单查询直接返回原查询；复杂查询用LLM拆解为2-3个可独立回答的子问题。

        Args:
            query: 查询文本

        Returns:
            List[str]: 子问题列表（简单查询返回 [query]）
        """
        if not self.is_complex_query(query):
            return [query]

        prompt = f"""将以下复杂问题拆解为2-3个可独立回答的子问题。

问题：{query}

要求：
- 每个子问题应该独立、具体，可以单独检索回答
- 覆盖原问题的所有方面
- 只输出JSON数组，不要其他文字

示例：
问题：10kV配电系统的接地方式和保护配置有哪些要求？
输出：["10kV配电系统有哪些接地方式？", "10kV配电系统的保护装置如何配置？"]

输出："""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm_client.chat(
                messages=messages,
                temperature=0.2,
                max_tokens=200
            )

            # 提取JSON数组
            sub_queries = self._extract_json_array(response)
            if sub_queries and len(sub_queries) >= 2:
                logger.info(f"[QueryRewriter] Decomposed '{query[:40]}' -> {len(sub_queries)} sub-queries")
                return sub_queries[:3]

            logger.warning(f"[QueryRewriter] Decomposition returned invalid result, using original")
            return [query]

        except Exception as e:
            logger.error(f"[QueryRewriter] Decompose error: {e}")
            return [query]

    def _extract_json_array(self, text: str) -> List[str]:
        """从LLM响应中提取JSON数组"""
        text = text.strip()

        # 尝试直接解析
        try:
            result = json.loads(text)
            if isinstance(result, list) and all(isinstance(s, str) for s in result):
                return result
        except json.JSONDecodeError:
            pass

        # 提取 [ ... ]
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, list) and all(isinstance(s, str) for s in result):
                    return result
            except json.JSONDecodeError:
                pass

        return []
