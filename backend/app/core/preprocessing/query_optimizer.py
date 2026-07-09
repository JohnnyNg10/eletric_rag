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
        优化查询（一体化实现：在一次 LLM 调用中完成评估和优化）

        Args:
            query: 标准化后的查询

        Returns:
            OptimizationResult: 优化结果
        """
        # 规则前置检查：含标准号或已知领域专业术语时直接判为明确查询，跳过 LLM
        if self._is_clearly_specific(query):
            logger.info(f"Pre-check: query contains specific indicators, skipping LLM. query='{query}'")
            return OptimizationResult(strategy='none', vagueness_score=0.2, options=[])

        try:
            # 尝试使用 LLM 一体化评估和优化
            return await self._llm_optimize(query)
        except Exception as e:
            # LLM 失败时降级到规则方案
            logger.warning(f"LLM optimize failed, fallback to rule-based: {e}")
            return await self._rule_based_optimize(query)

    def _is_clearly_specific(self, query: str) -> bool:
        """
        规则判断查询是否明确（含标准号/条款号/已知专业术语）。
        满足任意一条即可跳过 LLM 笼统度评估。
        """
        import re
        patterns = [
            r'GB[/T]*[/\s]*\d+',    # GB/T 45418, GB 50XXX
            r'DL[/T]*[/\s]*\d+',    # DL/T XXX
            r'NB[/T]*[/\s]*\d+',    # NB/T XXX
            r'N-\d+准则',           # N-1准则, N-2准则
            r'\d+kV',               # 电压等级：10kV, 110kV
            r'\d+\.\d+(?:\.\d+)*',  # 条款号：5.1.2
        ]
        return any(re.search(p, query) for p in patterns)

    async def _llm_optimize(self, query: str) -> OptimizationResult:
        """
        使用 LLM 一体化评估和优化（一次调用完成评估+澄清选项生成）

        Args:
            query: 查询文本

        Returns:
            OptimizationResult: 优化结果
        """
        from app.core.generation import llm_client
        import json

        prompt = f"""
你是电力标准知识库助手。分析以下查询的明确程度并生成澄清选项。

查询：{query}

任务：
1. 评估笼统度（0-1分）
   - 0.0-0.3：明确（含标准号/条款号/具体参数）
   - 0.3-0.6：轻度笼统（缺少1个关键维度）
   - 0.6-0.8：中度笼统（缺少多个关键维度）
   - 0.8-1.0：严重笼统（缺少所有关键信息）

2. 识别缺失维度（电压等级、应用场景、设备类型、参数类别等）

3. 生成3个澄清选项（仅当笼统度>0.5时）
   - 每个选项补充一个不同的缺失维度
   - label：展示给用户的简短标题，5-12个字，点明核心区分维度
   - refined_query：实际用于检索的完整句子，须包含原始查询的主题 + 补充的具体维度信息，15-30个字

返回JSON格式：
{{
  "vagueness_score": 0.X,
  "missing_dimensions": ["维度1", "维度2"],
  "reason": "缺失维度说明",
  "options": [
    {{
      "label": "10kV户内隔离开关技术参数",
      "refined_query": "10kV户内隔离开关额定电流、额定电压及开断能力等技术参数要求"
    }},
    ...
  ]
}}

注意：
- 如果笼统度<=0.5，options 返回空数组 []
- label 是给用户看的选项标题，要简洁
- refined_query 是送入检索引擎的查询，要完整，和 label 内容不同
"""

        response = llm_client.chat([
            {"role": "system", "content": "你是电力标准知识库助手，专注查询优化。回答必须是有效JSON。"},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=800)

        # 解析 JSON
        result = json.loads(response.strip())
        vagueness_score = float(result.get("vagueness_score", 0.5))
        missing_dimensions = result.get("missing_dimensions", [])
        reason = result.get("reason", "")
        raw_options = result.get("options", [])

        # 日志记录
        logger.info(
            f"LLM optimize: query='{query}', score={vagueness_score:.2f}, "
            f"missing={missing_dimensions}, options_count={len(raw_options)}"
        )

        # 决策策略
        if vagueness_score > 0.7:
            strategy = "clarify_required"
        elif vagueness_score > 0.5:
            strategy = "clarify_optional"
        elif vagueness_score > 0.3:
            strategy = "suggest"
        else:
            strategy = "none"

        # 构建选项列表
        options = []
        if raw_options:
            for i, opt in enumerate(raw_options[:3], 1):  # 最多3个
                options.append(OptimizationOption(
                    id=i,
                    label=opt.get("label", f"{query}优化选项{i}"),
                    refined_query=opt.get("refined_query", query),
                    standard_preview=None,  # TODO: 阶段2从知识库获取
                    doc_count=0  # TODO: 阶段2从知识库统计
                ))

        return OptimizationResult(
            strategy=strategy,
            vagueness_score=vagueness_score,
            options=options
        )

    async def _rule_based_optimize(self, query: str) -> OptimizationResult:
        """
        规则方案（降级）：评估 + 优化

        Args:
            query: 查询文本

        Returns:
            OptimizationResult: 优化结果
        """
        # 1. 评估笼统度
        vagueness_score = await self._rule_based_vagueness(query)

        # 2. 根据笼统度决策策略
        if vagueness_score > 0.7:
            strategy = "clarify_required"
            options = await self._rule_based_clarification_options(query)
        elif vagueness_score > 0.5:
            strategy = "clarify_optional"
            options = await self._rule_based_clarification_options(query)
        elif vagueness_score > 0.3:
            strategy = "suggest"
            options = []  # 规则方案不生成建议
        else:
            strategy = "none"
            options = []

        return OptimizationResult(
            strategy=strategy,
            vagueness_score=vagueness_score,
            options=options
        )

    async def _rule_based_clarification_options(
        self,
        query: str
    ) -> List[OptimizationOption]:
        """
        规则生成澄清选项（降级方案）

        Args:
            query: 查询文本

        Returns:
            List[OptimizationOption]: 澄清选项列表
        """
        options = []

        # 通用澄清选项模板
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

    # ==================== 以下为兼容性方法（保留旧接口） ====================

    async def assess_vagueness(self, query: str) -> float:
        """
        评估笼统度（兼容性方法，建议使用 optimize() 一体化接口）

        Args:
            query: 查询文本

        Returns:
            float: 笼统度评分 0-1
        """
        try:
            result = await self._llm_optimize(query)
            return result.vagueness_score
        except Exception as e:
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
        生成澄清选项（兼容性方法，建议使用 optimize() 一体化接口）

        Args:
            query: 查询文本

        Returns:
            List[OptimizationOption]: 澄清选项列表
        """
        try:
            result = await self._llm_optimize(query)
            return result.options
        except Exception as e:
            logger.warning(f"LLM clarification generation failed, fallback to rule-based: {e}")
            return await self._rule_based_clarification_options(query)

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

