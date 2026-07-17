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
        '对比', '差异', '区别', '比较', '不同', '相同', '平衡',
        '引用', '涉及哪些', '哪些标准涉及', '有哪些标准',
        '同时满足', '交叉', '关联'
    ]

    # 快车道可拆解关键词（同主题多方面查询）
    FAST_DECOMPOSE_KEYWORDS = [
        '和', '与', '以及', '及', '分别', '各自'
    ]

    # 明确标准号/条款号的模式
    STANDARD_PATTERN = re.compile(r'GB[/\s]*[T]?\s*\d+|DL[/\s]*T\s*\d+|NB[/\s]*T\s*\d+')
    CLAUSE_PATTERN = re.compile(r'第?\s*\d+(\.\d+)*\s*[条款节章]')

    # 增强的对比类模式（覆盖更多表达）
    COMPARISON_PATTERN = re.compile(r'(对比|差异|区别|比较|不同|相同|平衡|异同)')

    # 增强的标准引用模式
    STANDARD_INVOLVE_PATTERN = re.compile(
        r'(引用|涉及|包含|提到|参考|依据).{0,5}(哪些|什么).*标准|'
        r'(哪些|什么).*标准.{0,5}(引用|涉及|包含|提到|参考|依据)'
    )

    # 多标准对比模式（"A和B的区别/不同"）
    MULTI_STANDARD_COMPARISON_PATTERN = re.compile(
        r'(?:GB|DL|NB)[/\s]*[T]?\s*\d+.{0,10}(?:和|与|及).{0,10}(?:GB|DL|NB)[/\s]*[T]?\s*\d+.{0,10}(?:区别|不同|差异|对比|比较)'
    )

    # 同时满足/交叉要求模式
    MULTI_CONSTRAINT_PATTERN = re.compile(r'(同时|都|均).{0,5}(满足|符合|达到|要求)|既.{1,15}又')

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

        # 规则1: 多标准对比查询（"GB 50053 和 GB 50054 有什么不同"） → 慢车道
        if self.MULTI_STANDARD_COMPARISON_PATTERN.search(query):
            return RouteDecision(
                lane="slow",
                reason="查询涉及多个标准的对比分析",
                strategy_params={"max_steps": 3, "step_timeout": 120000, "total_timeout": 600000, "enable_decompose": True}
            )

        # 规则2: 多标准号查询（可能需要综合分析） → 慢车道
        standard_matches = self.STANDARD_PATTERN.findall(query)
        if len(standard_matches) >= 2:
            return RouteDecision(
                lane="slow",
                reason="查询涉及多个标准，需对比或综合分析",
                strategy_params={"max_steps": 3, "step_timeout": 120000, "total_timeout": 600000, "enable_decompose": True}
            )

        # 规则3: 对比/引用/多跳关键词（增强匹配） → 慢车道
        if self._has_comparison_keywords(query) or self._has_multihop_keywords(query) or self._has_multi_constraint(query):
            return RouteDecision(
                lane="slow",
                reason="包含对比/引用/多跳关键词，需要多跳推理",
                strategy_params={"max_steps": 3, "step_timeout": 120000, "total_timeout": 600000, "enable_decompose": True}
            )

        # 规则4: 明确单一标准号/条款号 → 快车道
        if self._has_explicit_standard_clause(query):
            return RouteDecision(
                lane="fast",
                reason="包含明确标准号或条款号，可精确定位",
                strategy_params={"recall_top_k": 20, "enable_retry": True, "max_expansions": 3, "enable_hyde": True, "enable_decompose": False}
            )

        # 默认: 快车道
        return RouteDecision(
            lane="fast",
            reason="常规单一维度查询",
            strategy_params={"recall_top_k": 20, "enable_retry": True, "max_expansions": 3, "enable_hyde": True, "enable_decompose": True}
        )

    def _has_explicit_standard_clause(self, query: str) -> bool:
        """检查是否包含明确的标准号或条款号"""
        return bool(self.STANDARD_PATTERN.search(query)) or bool(self.CLAUSE_PATTERN.search(query))

    def _has_comparison_keywords(self, query: str) -> bool:
        """检查是否包含对比关键词（增强匹配）"""
        return bool(self.COMPARISON_PATTERN.search(query))

    def _has_multihop_keywords(self, query: str) -> bool:
        """检查是否包含多跳推理关键词（增强匹配）"""
        return bool(self.STANDARD_INVOLVE_PATTERN.search(query))

    def _has_multi_constraint(self, query: str) -> bool:
        """检查是否包含多重约束条件"""
        return bool(self.MULTI_CONSTRAINT_PATTERN.search(query))
