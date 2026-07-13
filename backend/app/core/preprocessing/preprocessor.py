"""
预处理层协调器

职责（按照 08-RAG功能层次与状态机.md）：
1. 术语标准化：行业黑话 → 标准术语
2. 笼统度评估：判断是否需要澄清

注意：查询改写和元数据提取已移至快车道（retrieval/fast_lane.py），
在路由决策后执行，符合架构设计。

重构说明：
- QueryRewriter 和 MetadataExtractor 保留在 preprocessing/ 目录（代码位置）
- 但逻辑上它们属于快车道，由 FastLane 调用
- Preprocessor 不再直接调用这两个组件
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass

from .term_normalizer import TermNormalizer
from .query_optimizer import QueryOptimizer, OptimizationResult


@dataclass
class PreprocessingInput:
    """预处理输入"""
    query: str
    user_context: Dict[str, Any]
    enable_optimization: bool = True


@dataclass
class PreprocessingOutput:
    """预处理输出"""
    status: str  # "ready" or "need_clarification"
    optimized_query: str
    clarification_options: Optional[list] = None
    vagueness_score: float = 0.0
    strategy: Optional[str] = None  # none/suggest/clarify_optional/clarify_required

    # [阶段B] 路由建议字段（从 QueryOptimizer 传递）
    lane_suggestion: str = "fast"
    lane_confidence: float = 0.7
    lane_reason: str = ""
    missing_dimension_keys: list = None  # type: ignore[assignment]  # __post_init__ 保证不为 None

    # [新增] 类别识别字段
    category: Optional[str] = None
    category_confidence: float = 0.0

    # [新增] 保留原始 OptimizationResult（用于传递给 FastLane）
    optimization_result: Optional['OptimizationResult'] = None

    def __post_init__(self):
        if self.missing_dimension_keys is None:
            self.missing_dimension_keys = []


class Preprocessor:
    """
    预处理协调器

    职责：协调预处理层的2个核心组件
    - TermNormalizer: 术语标准化
    - QueryOptimizer: 笼统度评估
    """

    def __init__(self):
        self.term_normalizer = TermNormalizer()
        self.query_optimizer = QueryOptimizer()

    async def preprocess(self, input_data: PreprocessingInput) -> PreprocessingOutput:
        """
        执行核心预处理流程

        流程：
        1. 术语标准化
        2. 笼统度评估（可选）

        注意：查询改写和元数据提取已移至快车道，在路由决策后执行。

        Args:
            input_data: 预处理输入

        Returns:
            PreprocessingOutput: 预处理输出
        """
        query = input_data.query.strip()

        # 输入验证：拒绝空查询
        if not query:
            raise ValueError("查询内容不能为空")

        # 步骤1: 术语标准化
        normalized_query = self.term_normalizer.normalize(query)

        # 步骤2: 笼统度评估（如果启用）
        if input_data.enable_optimization:
            optimization_result = await self.query_optimizer.optimize(normalized_query)

            # 如果需要澄清，直接返回
            if optimization_result.strategy in ['clarify_required', 'clarify_optional']:
                return PreprocessingOutput(
                    status='need_clarification',
                    optimized_query=normalized_query,
                    clarification_options=[
                        {
                            'id': opt.id,
                            'label': opt.label,
                            'refined_query': opt.refined_query,
                            'standard_preview': opt.standard_preview,
                            'doc_count': opt.doc_count,
                            'kb_verified': opt.kb_verified,
                        }
                        for opt in optimization_result.options
                    ],
                    vagueness_score=optimization_result.vagueness_score,
                    strategy=optimization_result.strategy,  # [阶段B]
                    lane_suggestion=optimization_result.lane_suggestion,  # [阶段B]
                    lane_confidence=optimization_result.lane_confidence,  # [阶段B]
                    lane_reason=optimization_result.lane_reason,  # [阶段B]
                    missing_dimension_keys=optimization_result.missing_dimension_keys,  # [阶段B]
                    category=optimization_result.category,  # [新增]
                    category_confidence=optimization_result.category_confidence,  # [新增]
                    optimization_result=optimization_result  # [新增] 保留原始对象
                )
        else:
            optimization_result = None

        # 返回准备就绪的查询（标准化后的清晰查询）
        return PreprocessingOutput(
            status='ready',
            optimized_query=normalized_query,
            clarification_options=None,
            vagueness_score=optimization_result.vagueness_score if optimization_result else 0.0,
            strategy=optimization_result.strategy if optimization_result else 'none',  # [阶段B]
            lane_suggestion=optimization_result.lane_suggestion if optimization_result else 'fast',  # [阶段B]
            lane_confidence=optimization_result.lane_confidence if optimization_result else 0.7,  # [阶段B]
            lane_reason=optimization_result.lane_reason if optimization_result else '',  # [阶段B]
            missing_dimension_keys=optimization_result.missing_dimension_keys if optimization_result else [],  # [阶段B]
            category=optimization_result.category if optimization_result else None,  # [新增]
            category_confidence=optimization_result.category_confidence if optimization_result else 0.0,  # [新增]
            optimization_result=optimization_result  # [新增] 保留原始对象
        )

