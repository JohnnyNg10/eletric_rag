"""
查询优化器 - 预处理层第二步

职责：
1. 评估查询笼统度（使用 LLM，规则作为降级方案）
2. 生成澄清选项（当前为模板，后续接入知识库动态生成）
3. 决策优化策略
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class OptimizationOption:
    """优化选项"""
    id: int
    label: str
    refined_query: str
    standard_preview: Optional[str] = None
    doc_count: int = 0


@dataclass
class OptimizationResult:
    """优化结果"""
    strategy: str  # none/suggest/clarify_optional/clarify_required
    vagueness_score: float  # 0-1
    options: List[OptimizationOption]


class QueryOptimizer:
    """查询优化器"""

    def __init__(self):
        # 笼统查询关键词（规则降级使用）
        self.vague_keywords = [
            "要求", "规定", "标准", "怎么", "如何", "什么",
            "哪些", "多少", "是否", "能不能"
        ]

        # 具体查询特征（规则降级使用）
        self.specific_indicators = [
            r'\d+kV',  # 电压等级
            r'GB\s*\d+',  # 标准号
            r'DL/T\s*\d+',  # 行业标准号
            r'\d+(?:米|m|毫米|mm)',  # 具体数值
        ]

    async def optimize(self, query: str) -> OptimizationResult:
        """
        优化查询

        Args:
            query: 标准化后的查询

        Returns:
            OptimizationResult: 优化结果
        """
        # 1. 评估笼统度（LLM优先，规则降级）
        vagueness_score = await self.assess_vagueness(query)

        # 2. 根据笼统度决策策略
        if vagueness_score > 0.7:
            # 非常笼统，必须澄清
            strategy = "clarify_required"
            options = await self.generate_clarification_options(query)
        elif vagueness_score > 0.5:
            # 较笼统，建议澄清
            strategy = "clarify_optional"
            options = await self.generate_clarification_options(query)
        elif vagueness_score > 0.3:
            # 轻微笼统，给出建议
            strategy = "suggest"
            options = await self.generate_suggestions(query)
        else:
            # 清晰查询，无需优化
            strategy = "none"
            options = []

        return OptimizationResult(
            strategy=strategy,
            vagueness_score=vagueness_score,
            options=options
        )

    async def assess_vagueness(self, query: str) -> float:
        """
        评估笼统度（使用 LLM，规则作为降级方案）

        Args:
            query: 查询文本

        Returns:
            float: 笼统度评分 0-1（0=非常具体，1=非常笼统）
        """
        try:
            # 尝试 LLM 评估
            from app.core.generation import llm_client
            import json

            prompt = f"""
评估以下电力专业查询的明确程度（0-1分）：

查询：{query}

评分标准：
- 0.0-0.3：明确（含标准号/条款号/具体参数/完整上下文）
  示例："GB 50057-2010第3.2.1条关于接地电阻的规定"
- 0.3-0.6：轻度笼统（缺少电压等级、应用场景或设备类型之一）
  示例："10kV配电装置与建筑物距离"（缺少室内/室外、架空/电缆）
- 0.6-0.8：中度笼统（只有大类概念，缺少多个关键维度）
  示例："隔离开关技术要求"（缺少电压等级、应用场景、具体参数类型）
- 0.8-1.0：严重笼统（仅有笼统描述，缺少所有关键信息）
  示例："配电规定"、"继电保护要求"

仅返回JSON格式：{{"score": 0.X, "reason": "缺失维度说明"}}
"""

            response = llm_client.chat([
                {"role": "system", "content": "你是电力标准知识库助手，专注评估查询明确性。回答必须是有效JSON。"},
                {"role": "user", "content": prompt}
            ], temperature=0.1, max_tokens=150)

            # 解析 JSON
            result = json.loads(response.strip())
            score = float(result.get("score", 0.5))

            # 日志记录（用于后续优化）
            logger.info(f"LLM vagueness assessment: query='{query}', score={score}, reason={result.get('reason')}")

            return max(0.0, min(1.0, score))

        except Exception as e:
            # LLM 失败时降级到规则评估
            logger.warning(f"LLM vagueness assessment failed, fallback to rule-based: {e}")
            return await self._rule_based_vagueness(query)

    async def _rule_based_vagueness(self, query: str) -> float:
        """
        规则评估（降级方案）

        评估规则：
        1. 查询长度（越短越笼统）
        2. 是否包含笼统关键词
        3. 是否包含具体信息（电压等级、标准号、数值）

        Args:
            query: 查询文本

        Returns:
            float: 笼统度评分 0-1
        """
        score = 0.0

        # 规则1: 查询长度
        if len(query) < 5:
            score += 0.4
        elif len(query) < 10:
            score += 0.2

        # 规则2: 笼统关键词
        vague_count = sum(1 for kw in self.vague_keywords if kw in query)
        if vague_count > 0:
            score += min(0.3, vague_count * 0.15)

        # 规则3: 缺少具体信息（减分）
        import re
        has_specific = any(re.search(pattern, query) for pattern in self.specific_indicators)
        if not has_specific:
            score += 0.2
        else:
            score -= 0.1

        # 限制在0-1范围
        score = max(0.0, min(1.0, score))

        return score

    async def generate_clarification_options(
        self,
        query: str
    ) -> List[OptimizationOption]:
        """
        生成澄清选项（当前为模板生成，TODO: 未来接入知识库动态生成）

        Args:
            query: 查询文本

        Returns:
            List[OptimizationOption]: 澄清选项列表
        """
        options = []

        # TODO: 阶段2 - 结合知识库动态生成
        # 当前返回通用澄清选项

        options.append(OptimizationOption(
            id=1,
            label=f"{query}的具体技术要求",
            refined_query=f"{query}具体技术要求",
            standard_preview="GB 50XXX",
            doc_count=10
        ))

        options.append(OptimizationOption(
            id=2,
            label=f"{query}的安全距离规定",
            refined_query=f"{query}安全距离",
            standard_preview="DL/T XXX",
            doc_count=8
        ))

        options.append(OptimizationOption(
            id=3,
            label=f"{query}的检测标准",
            refined_query=f"{query}检测标准",
            standard_preview="GB/T XXX",
            doc_count=6
        ))

        return options

    async def generate_suggestions(self, query: str) -> List[OptimizationOption]:
        """
        生成智能补全建议

        Args:
            query: 查询文本

        Returns:
            List[OptimizationOption]: 建议列表
        """
        # TODO: 未来基于历史查询或知识库生成
        return []

