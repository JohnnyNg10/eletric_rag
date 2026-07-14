"""
指代消解器

检测查询中的指代词/省略主语，借助 LLM 将其替换为明确实体，
使每轮查询可以独立于上下文被正确检索。
"""
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 触发指代消解的词汇信号
_COREFERENCE_SIGNALS = re.compile(
    r'(它|该|此|这个|上述|上面|前面|之前提到|刚才说的|其中|其(?![他]))'
)
# 省略主语的追问模式（行首匹配）
_ELLIPSIS_SIGNALS = re.compile(
    r'^(还有|另外|此外|同时|以及|那么|那)(哪些|什么|怎么|如何|是否|有没有)'
)


class CoreferenceResolver:
    """
    指代消解：将含指代词的查询改写为可独立理解的完整问题。

    触发条件（满足任一）：
      - 包含指代词：它/该/此/上述/上面/前面/之前提到 等
      - 省略主语的追问：还有哪些/有什么要求/怎么规定 等

    不触发条件：
      - 历史为空（首轮对话）
      - 查询已包含明确标准号（如 GB 50054）
      - COREFERENCE_RESOLUTION_ENABLED = False
    """

    def resolve(
        self,
        query: str,
        history: List[Dict[str, str]],
    ) -> str:
        """
        返回消解后的 query；若无需消解或发生异常则原样返回。

        Args:
            query: 当前轮次的原始查询
            history: 历史轮次列表，每项格式 {"query": ..., "answer": ...}，按升序排列
        """
        from app.config import settings
        if not settings.COREFERENCE_RESOLUTION_ENABLED:
            return query
        if not history:
            return query
        if not self._needs_resolution(query):
            return query

        recent = history[-2:]
        try:
            return self._llm_resolve(query, recent)
        except Exception as e:
            logger.warning(f"[CoreferenceResolver] LLM 指代消解失败，降级使用原始 query: {e}")
            return query

    def _needs_resolution(self, query: str) -> bool:
        return bool(
            _COREFERENCE_SIGNALS.search(query)
            or _ELLIPSIS_SIGNALS.match(query)
        )

    def _llm_resolve(self, query: str, recent: List[Dict]) -> str:
        from app.core.generation.llm_client import get_llm_client

        history_text = "\n".join(
            f"用户：{h['query']}\n助手：{h['answer'][:300]}"
            for h in recent
        )
        user_prompt = (
            f"以下是对话历史（最近几轮）：\n{history_text}\n\n"
            f"当前用户问题：{query}\n\n"
            "请将当前问题中的指代词替换为明确的实体名称，使问题可以独立理解。"
            "只输出改写后的问题，不要任何解释。"
            "如果问题已经足够明确，原样输出。"
        )
        llm = get_llm_client()
        resolved = llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        return resolved.strip() or query
