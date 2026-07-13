"""
查询优化器 - 预处理层第二步

职责：
1. 评估查询笼统度（使用 LLM，规则作为降级方案）
2. 生成澄清选项（当前为模板，后续接入知识库动态生成）
3. 决策优化策略
4. [阶段B] 同时输出路由建议（lane_suggestion/lane_confidence/lane_reason）
"""
from typing import List, Dict, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

# 电力专业澄清维度枚举表（阶段B：将缺失维度从自由文本改为枚举键）
POWER_CLARIFICATION_DIMS: Dict[str, str] = {
    "voltage_level":      "电压等级",       # 6/10/35/110/220/500kV
    "equipment_type":     "设备类型",       # 变压器/开关柜/GIS/电缆/互感器
    "application_scene":  "应用场景",       # 新建/改造/运维/验收/检修
    "neutral_grounding":  "中性点接地方式", # 直接/消弧线圈/不接地/低电阻
    "capacity_range":     "容量范围",       # <1MVA / 1-10MVA / >10MVA
    "install_env":        "安装环境",       # 户内/户外/地下/高海拔
    "standard_series":    "标准系列",       # GB/DL/NB/企标
    "protection_type":    "保护类型",       # 差动/距离/过流/零序
}

# 维度键列表，供 LLM prompt 使用
_DIM_KEYS_STR = ", ".join(
    f"{k}({v})" for k, v in POWER_CLARIFICATION_DIMS.items()
)


@dataclass
class OptimizationOption:
    """优化选项"""
    id: int
    label: str
    refined_query: str
    standard_preview: Optional[str] = None
    doc_count: int = 0
    kb_verified: bool = False  # True 表示 standard_preview/doc_count 来自 ES 真实聚合


@dataclass
class OptimizationResult:
    """优化结果"""
    strategy: str  # none/suggest/clarify_optional/clarify_required
    vagueness_score: float  # 0-1
    options: List[OptimizationOption]

    # [阶段B] 路由建议字段（LLM 一体化输出，与 Router.route() 互补）
    lane_suggestion: str = "fast"          # fast/slow（LLM 建议）
    lane_confidence: float = 0.7           # 路由置信度 0-1
    lane_reason: str = ""                  # 路由理由（可读，展示给用户）
    missing_dimension_keys: List[str] = field(default_factory=list)  # 枚举键列表


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

    # 慢车道触发关键词：包含这些词时即使满足 specific 规则也不短路
    _SLOW_LANE_KEYWORDS = (
        "区别", "差异", "对比", "比较", "不同",
        "同时满足", "哪些标准", "哪些规范",
        "引用了", "涉及哪些", "分别对应",
        "关联", "交叉",
    )

    async def optimize(self, query: str) -> OptimizationResult:
        """
        优化查询（一体化实现：在一次 LLM 调用中完成评估和优化）

        Args:
            query: 标准化后的查询

        Returns:
            OptimizationResult: 优化结果
        """
        # 规则前置检查：含标准号等特征时跳过 LLM，但含慢车道关键词时不短路
        # （避免"10kV和35kV配电装置的区别"被误判为明确单路查询）
        has_slow_keywords = any(kw in query for kw in self._SLOW_LANE_KEYWORDS)
        if self._is_clearly_specific(query) and not has_slow_keywords:
            logger.info(f"Pre-check: specific query, no slow-lane keywords, skipping LLM. query='{query}'")
            return OptimizationResult(strategy='none', vagueness_score=0.2, options=[])

        try:
            # 尝试使用 LLM 一体化评估和优化
            result = await self._llm_optimize(query)
        except Exception as e:
            # LLM 失败时降级到规则方案
            logger.warning(f"LLM optimize failed, fallback to rule-based: {e}")
            return await self._rule_based_optimize(query)

        # KB 聚合填充：对 standard_series 维度，用 ES 真实数据替换 LLM 生成的选项
        if "standard_series" in result.missing_dimension_keys and result.options:
            result = await self._fill_standard_series_options(query, result)

        return result

    async def _fill_standard_series_options(
        self, query: str, result: OptimizationResult
    ) -> OptimizationResult:
        """
        用 ES 聚合结果填充 standard_series 维度的澄清选项。
        每个标准系列（GB/DL/NB）生成一个选项，doc_count 来自真实统计。
        填充成功则替换 LLM 生成的选项；ES 失败则保留 LLM 生成结果。
        """
        from app.storage.search_engine import search_engine
        try:
            buckets = search_engine.aggregate_by_standard(query_text=query, top_n=5)
            if not buckets:
                return result

            kb_options = []
            for i, bucket in enumerate(buckets, 1):
                sno = bucket["standard_no"]
                series = bucket["series"]
                count = bucket["doc_count"]
                label = f"{series}系列标准（{sno} 等）"
                refined = f"{query}（依据{sno}等{series}系列标准）"
                kb_options.append(OptimizationOption(
                    id=i,
                    label=label,
                    refined_query=refined,
                    standard_preview=sno,
                    doc_count=count,
                    kb_verified=True,
                ))
            result.options = kb_options
            logger.info(
                f"KB fill standard_series: replaced options with {len(kb_options)} ES buckets"
            )
        except Exception as e:
            logger.warning(f"KB fill standard_series failed, keeping LLM options: {e}")
        return result

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
        使用 LLM 一体化评估和优化（一次调用完成评估+澄清选项生成+路由建议）

        [阶段B] 扩展：同时输出 lane_suggestion、lane_confidence、lane_reason

        Args:
            query: 查询文本

        Returns:
            OptimizationResult: 优化结果（含路由建议）
        """
        from app.core.generation import llm_client
        import json

        prompt = f"""
你是电力标准知识库助手。分析以下查询的明确程度，生成澄清选项，并给出路由建议。

查询：{query}

任务：
1. 评估笼统度（0-1分）
   - 0.0-0.3：明确（含标准号/条款号/具体参数）
   - 0.3-0.6：轻度笼统（缺少1个关键维度）
   - 0.6-0.8：中度笼统（缺少多个关键维度）
   - 0.8-1.0：严重笼统（缺少所有关键信息）

2. 识别缺失维度（从以下枚举中选择）：{_DIM_KEYS_STR}
   返回英文键列表，如 ["voltage_level", "equipment_type"]

3. 生成3个澄清选项（仅当笼统度>0.5时）
   - 每个选项补充一个不同的缺失维度
   - label：展示给用户的简短标题，5-12个字，点明核心区分维度
   - refined_query：实际用于检索的完整句子，须包含原始查询的主题 + 补充的具体维度信息，15-30个字

4. 路由建议（fast或slow）：
   - fast：明确标准号/条款号，或单一维度查询
   - slow：对比/差异/多跳推理/涉及多个标准的关联查询
   返回 lane_suggestion（fast/slow）、lane_confidence（0-1）、lane_reason（一句话理由）

返回JSON格式：
{{
  "vagueness_score": 0.X,
  "missing_dimension_keys": ["voltage_level", "equipment_type"],
  "reason": "缺失维度说明",
  "options": [
    {{
      "label": "10kV户内隔离开关技术参数",
      "refined_query": "10kV户内隔离开关额定电流、额定电压及开断能力等技术参数要求"
    }},
    ...
  ],
  "lane_suggestion": "fast",
  "lane_confidence": 0.85,
  "lane_reason": "包含明确电压等级和设备类型，单一维度查询"
}}

注意：
- 如果笼统度<=0.5，options 返回空数组 []
- missing_dimension_keys 必须是枚举键列表，不是中文描述
- lane_suggestion 必须是 "fast" 或 "slow"
- lane_confidence 是路由置信度（0-1），lane_reason 是给用户看的理由
"""

        response = llm_client.chat([
            {"role": "system", "content": "你是电力标准知识库助手，专注查询优化和路由建议。回答必须是有效JSON。"},
            {"role": "user", "content": prompt}
        ], temperature=0.3, max_tokens=1000)

        # 解析 JSON
        result = json.loads(response.strip())
        vagueness_score = float(result.get("vagueness_score", 0.5))
        missing_dimension_keys = result.get("missing_dimension_keys", [])
        reason = result.get("reason", "")
        raw_options = result.get("options", [])

        # [阶段B] 提取路由建议
        lane_suggestion = result.get("lane_suggestion", "fast")
        lane_confidence = float(result.get("lane_confidence", 0.7))
        lane_reason = result.get("lane_reason", "常规查询")

        # 日志记录
        logger.info(
            f"LLM optimize: query='{query}', score={vagueness_score:.2f}, "
            f"missing_dims={missing_dimension_keys}, options_count={len(raw_options)}, "
            f"lane={lane_suggestion}, confidence={lane_confidence:.2f}"
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
            options=options,
            lane_suggestion=lane_suggestion,
            lane_confidence=lane_confidence,
            lane_reason=lane_reason,
            missing_dimension_keys=missing_dimension_keys
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

