"""
预处理层协调器 - 整合所有预处理组件

按照 08-RAG功能层次与状态机.md 定义的流程：
原始查询 → 术语标准化 → 笼统度评估 → 查询改写 → 元数据提取 → 输出
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from .term_normalizer import TermNormalizer
from .query_optimizer import QueryOptimizer, OptimizationResult
from .query_rewriter import QueryRewriter
from .metadata_extractor import MetadataExtractor


@dataclass
class PreprocessingInput:
    """预处理输入"""
    query: str
    user_context: Dict[str, Any]
    enable_optimization: bool = True
    enable_expansion: bool = True
    max_expansions: int = 3


@dataclass
class PreprocessingOutput:
    """预处理输出"""
    status: str  # "ready" or "need_clarification"
    optimized_query: str
    expanded_queries: List[str]
    filters: Dict[str, Any]
    clarification_options: Optional[List[Dict]] = None
    vagueness_score: float = 0.0
    metadata: Dict[str, Any] = None


class Preprocessor:
    """
    预处理协调器

    职责：协调预处理层的4个组件，执行完整的预处理流程
    """

    def __init__(self):
        self.term_normalizer = TermNormalizer()
        self.query_optimizer = QueryOptimizer()
        self.query_rewriter = QueryRewriter()
        self.metadata_extractor = MetadataExtractor()

    async def preprocess(self, input_data: PreprocessingInput) -> PreprocessingOutput:
        """
        执行完整的预处理流程

        流程：
        1. 术语标准化
        2. 笼统度评估（可选）
        3. 查询改写（如果不需要澄清）
        4. 元数据提取

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
                    expanded_queries=[normalized_query],
                    filters={},
                    clarification_options=[
                        {
                            'id': opt.id,
                            'label': opt.label,
                            'refined_query': opt.refined_query,
                            'standard_preview': opt.standard_preview,
                            'doc_count': opt.doc_count
                        }
                        for opt in optimization_result.options
                    ],
                    vagueness_score=optimization_result.vagueness_score
                )
        else:
            optimization_result = None

        # 步骤3: 查询改写（生成扩展查询）
        if input_data.enable_expansion:
            expanded_queries = await self.query_rewriter.rewrite(
                normalized_query,
                max_expansions=input_data.max_expansions
            )
        else:
            expanded_queries = [normalized_query]

        # 步骤4: 元数据提取
        filters = self.metadata_extractor.extract(normalized_query)
        metadata = self.metadata_extractor.extract_all_metadata(normalized_query)

        # 返回准备就绪的结果
        return PreprocessingOutput(
            status='ready',
            optimized_query=normalized_query,
            expanded_queries=expanded_queries,
            filters=filters,
            clarification_options=None,
            vagueness_score=optimization_result.vagueness_score if optimization_result else 0.0,
            metadata=metadata
        )
