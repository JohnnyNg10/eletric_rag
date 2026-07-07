"""
查询服务 - 服务层

职责：编排查询处理的完整流程
- 调用预处理层（术语标准化 + 笼统度评估）
- 调用路由层（快慢车道决策）
- 调用召回层（快车道/慢车道）
- 调用生成层（TODO）
- 记录日志和缓存

符合架构设计：
  预处理层 → 路由层 → 快车道/慢车道 → 生成层
"""
from typing import Dict, Any, Optional
import logging
import time

from app.core.preprocessing import (
    Preprocessor,
    PreprocessingInput,
    PreprocessingOutput
)
from app.core.retrieval import (
    Router,
    FastLane,
    SlowLane
)

logger = logging.getLogger(__name__)


class QueryService:
    """
    查询服务（业务编排层）

    编排完整的RAG查询流程
    """

    def __init__(self):
        self.preprocessor = Preprocessor()
        self.router = Router()
        self.fast_lane = FastLane()
        self.slow_lane = SlowLane()

    async def execute_query(
        self,
        query: str,
        user_id: int,
        conversation_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        执行完整的查询流程

        流程：
        1. 预处理：术语标准化 + 笼统度评估
        2. 路由决策：快车道 or 慢车道
        3. 检索：
           - 快车道：查询改写 + 元数据提取 + 三路召回 + 重排
           - 慢车道：工具调用循环
        4. 生成：LLM生成答案（TODO）
        """
        start_time = time.time()
        logger.info(f"[User {user_id}] Execute query: {query}")

        # 步骤1: 预处理（术语标准化 + 笼统度评估）
        preprocessing_input = PreprocessingInput(
            query=query,
            user_context={'user_id': user_id, 'conversation_id': conversation_id},
            enable_optimization=True
        )

        preprocessing_output: PreprocessingOutput = await self.preprocessor.preprocess(
            preprocessing_input
        )

        # 如果需要澄清，提前返回
        if preprocessing_output.status == 'need_clarification':
            logger.info(f"[User {user_id}] Query needs clarification")
            return {
                'status': 'need_clarification',
                'vagueness_score': preprocessing_output.vagueness_score,
                'clarification_options': preprocessing_output.clarification_options
            }

        # 步骤2: 路由决策
        route_decision = self.router.route(preprocessing_output.optimized_query)
        logger.info(f"[User {user_id}] Route decision: {route_decision.lane} - {route_decision.reason}")

        # 步骤3: 检索（根据路由结果选择车道）
        user_context = {'user_id': user_id, 'conversation_id': conversation_id}

        if route_decision.lane == "fast":
            # 快车道：查询改写 + 元数据提取 + 召回 + 重排
            retrieval_result = await self.fast_lane.execute(
                query=preprocessing_output.optimized_query,
                user_context=user_context,
                strategy_params=route_decision.strategy_params
            )

            lane_info = {
                'lane': 'fast',
                'expanded_queries': retrieval_result.expanded_queries,
                'filters': retrieval_result.filters,
                'metadata': retrieval_result.metadata,
                'retrieval_time': retrieval_result.retrieval_time,
                'retry_triggered': retrieval_result.retry_triggered,
                'recall_count': retrieval_result.recall_count
            }
        else:
            # 慢车道：工具调用循环
            retrieval_result = await self.slow_lane.execute(
                query=preprocessing_output.optimized_query,
                user_context=user_context,
                strategy_params=route_decision.strategy_params
            )

            lane_info = {
                'lane': 'slow',
                'reasoning_steps': retrieval_result.reasoning_steps,
                'retrieval_time': retrieval_result.retrieval_time,
                'steps_taken': retrieval_result.steps_taken,
                'recall_count': len(retrieval_result.retrieved_chunks)
            }

        # TODO: 步骤4: 生成答案
        # answer_result = await self.generator.generate(
        #     query=preprocessing_output.optimized_query,
        #     chunks=retrieval_result.retrieved_chunks
        # )

        # 当前返回模拟结果
        elapsed_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[User {user_id}] Query completed in {elapsed_ms}ms")

        return {
            'status': 'success',
            'answer': f"模拟答案：{preprocessing_output.optimized_query}",
            'citations': [],
            'lane': route_decision.lane,
            'route_reason': route_decision.reason,
            'retrieval_time': lane_info.get('retrieval_time', 0),
            'generation_time': 800,  # 模拟
            'total_time': elapsed_ms,
            'query_log_id': 0,  # TODO: 实际的日志ID
            **lane_info  # 合并车道特定信息
        }

