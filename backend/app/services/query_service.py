"""
查询服务 - 服务层

职责：编排查询处理的完整流程
- 调用预处理层
- 调用路由层
- 调用召回层（快车道/慢车道）
- 调用重排层
- 调用生成层
- 记录日志和缓存

符合04-后端架构设计.md中的服务层定义
"""
from typing import Dict, Any, Optional
import logging
import time

from app.core.preprocessing import (
    Preprocessor,
    PreprocessingInput,
    PreprocessingOutput
)

logger = logging.getLogger(__name__)


class QueryService:
    """
    查询服务（业务编排层）

    编排完整的RAG查询流程
    """

    def __init__(self):
        self.preprocessor = Preprocessor()

    async def execute_query(
        self,
        query: str,
        user_id: int,
        conversation_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """执行完整的查询流程"""
        start_time = time.time()
        logger.info(f"[User {user_id}] Execute query: {query}")

        # 步骤1: 预处理
        preprocessing_input = PreprocessingInput(
            query=query,
            user_context={'user_id': user_id, 'conversation_id': conversation_id},
            enable_optimization=True,
            enable_expansion=True,
            max_expansions=3
        )

        preprocessing_output: PreprocessingOutput = await self.preprocessor.preprocess(
            preprocessing_input
        )

        # 如果需要澄清，提前返回
        if preprocessing_output.status == 'need_clarification':
            return {
                'status': 'need_clarification',
                'vagueness_score': preprocessing_output.vagueness_score,
                'clarification_options': preprocessing_output.clarification_options
            }

        # TODO: 步骤2-4（路由、检索、生成）

        # 当前返回模拟结果
        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            'status': 'success',
            'answer': f"模拟答案：{preprocessing_output.optimized_query}",
            'citations': [],
            'lane': 'fast',
            'retrieval_time': elapsed_ms,
            'generation_time': 800,
            'expanded_queries': preprocessing_output.expanded_queries,
            'metadata': preprocessing_output.metadata,
            'query_log_id': 0
        }
