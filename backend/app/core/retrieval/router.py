"""
路由器 - 快慢车道决策

职责：根据查询复杂度选择快车道或慢车道
"""
import re
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RouteDecision:
    """路由决策结果"""
    lane: str  # "fast" or "slow"
    reason: str  # 路由理由
    strategy_params: Dict[str, Any]  # 检索策略参数


class Router:
    """
    路由器

    职责：根据查询复杂度选择快车道或慢车道

    路由规则：
    - 明确标准号/条款号 → 快车道
    - 对比/引用关键词 → 慢车道
    - 多跳推理关键词 → 慢车道
    - 默认 → 快车道
    """

    # 慢车道关键词（多跳推理、对比分析）
    SLOW_LANE_KEYWORDS = [
        '对比', '差异', '区别', '比较',
        '引用', '涉及哪些', '有哪些标准',
        '同时满足', '交叉', '关联'
    ]

    # 明确标准号/条款号的模式
    STANDARD_PATTERN = re.compile(r'GB[/\s]*[T]?\s*\d+|DL[/\s]*T\s*\d+|NB[/\s]*T\s*\d+')
    CLAUSE_PATTERN = re.compile(r'第?\s*\d+(\.\d+)*\s*[条款节章]')

    def route(self, query: str, metadata: Dict[str, Any] = None) -> RouteDecision:
        """
        路由决策

        Args:
            query: 预处理后的清晰查询（已标准化）
            metadata: 可选的元数据信息

        Returns:
            RouteDecision: 路由决策结果
        """
        metadata = metadata or {}

        # 规则1: 明确标准号/条款号 → 快车道
        if self._has_explicit_standard_clause(query):
            return RouteDecision(
                lane="fast",
                reason="包含明确标准号或条款号，可精确定位",
                strategy_params={"recall_top_k": 20, "enable_retry": True, "max_expansions": 3, "enable_hyde": True}
            )

        # 规则2: 对比/引用关键词 → 慢车道
        if self._has_comparison_keywords(query):
            return RouteDecision(
                lane="slow",
                reason="包含对比/引用关键词，需要多跳推理",
                strategy_params={"max_steps": 3, "step_timeout": 2000, "total_timeout": 7000}
            )

        # 规则3: 多跳推理关键词 → 慢车道
        if self._has_multihop_keywords(query):
            return RouteDecision(
                lane="slow",
                reason="需要多跳推理",
                strategy_params={"max_steps": 3, "step_timeout": 2000, "total_timeout": 7000}
            )

        # 默认: 快车道
        return RouteDecision(
            lane="fast",
            reason="常规单一维度查询",
            strategy_params={"recall_top_k": 20, "enable_retry": True, "max_expansions": 3, "enable_hyde": True}
        )

    def _has_explicit_standard_clause(self, query: str) -> bool:
        """检查是否包含明确的标准号或条款号"""
        return bool(self.STANDARD_PATTERN.search(query)) or bool(self.CLAUSE_PATTERN.search(query))

    def _has_comparison_keywords(self, query: str) -> bool:
        """检查是否包含对比关键词"""
        comparison_keywords = ['对比', '差异', '区别', '比较']
        return any(kw in query for kw in comparison_keywords)

    def _has_multihop_keywords(self, query: str) -> bool:
        """检查是否包含多跳推理关键词"""
        multihop_keywords = ['引用', '涉及哪些', '有哪些标准', '同时满足', '交叉', '关联']
        return any(kw in query for kw in multihop_keywords)
