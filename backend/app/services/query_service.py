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
from sqlalchemy.orm import Session

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
from app.core.generation import (
    AnswerGenerator,
    get_generator
)
from app.db.models import QueryLog, ClarificationLog

logger = logging.getLogger(__name__)


class QueryService:
    """
    查询服务（业务编排层）

    编排完整的RAG查询流程
    """

    def __init__(self, db: Optional[Session] = None):
        self.preprocessor = Preprocessor()
        self.router = Router()
        self.fast_lane = FastLane(db=db)  # 传入DB会话用于召回
        self.slow_lane = SlowLane(db=db)  # 慢车道也需要DB会话
        self.generator = get_generator(enable_validation=False)  # 生成器（默认不开启验证以节省成本）
        self.db = db  # 数据库会话，用于日志记录

    async def execute_query(
        self,
        query: str,
        user_id: int,
        conversation_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        refined_query: Optional[str] = None,
        selected_option_id: Optional[int] = None,
        clarification_context: Optional[Dict[str, Any]] = None,
        user_lane: Optional[str] = None  # [阶段B] 用户选择的车道（覆盖系统建议）
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

        澄清流程：
        - 如果提供了 refined_query，说明用户选择了澄清选项
        - 跳过笼统度评估，只做术语标准化后直接进入路由层
        """
        start_time = time.time()
        logger.info(f"[User {user_id}] Execute query: {query}")

        # 判断是否为澄清后的查询
        is_clarified_query = refined_query is not None
        actual_query = refined_query if is_clarified_query else query

        # 步骤1: 预处理
        if is_clarified_query:
            # 澄清后的查询：仅做术语标准化，跳过笼统度评估
            logger.info(f"[User {user_id}] Processing clarified query: {refined_query}")
            preprocessing_input = PreprocessingInput(
                query=refined_query,
                user_context={'user_id': user_id, 'conversation_id': conversation_id},
                enable_optimization=False  # 跳过笼统度评估
            )
            preprocessing_output: PreprocessingOutput = await self.preprocessor.preprocess(
                preprocessing_input
            )
        else:
            # 首次查询：术语标准化 + 笼统度评估
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
        # [阶段B] 如果用户提供了 user_lane，则覆盖系统路由
        if user_lane:
            logger.info(f"[User {user_id}] User overriding route: {user_lane}")
            from app.core.retrieval import RouteDecision
            route_decision = RouteDecision(
                lane=user_lane,
                reason=f"用户选择：{user_lane}车道",
                strategy_params={"recall_top_k": 20, "enable_retry": True, "max_expansions": 3} if user_lane == "fast" else {"max_steps": 3, "step_timeout": 2000, "total_timeout": 7000}
            )
            predicted_lane = preprocessing_output.lane_suggestion if hasattr(preprocessing_output, 'lane_suggestion') else "fast"
            lane_confidence = preprocessing_output.lane_confidence if hasattr(preprocessing_output, 'lane_confidence') else 0.7
        else:
            # 使用 Router 路由（当前为关键词规则，未来可能替换为微调模型）
            route_decision = self.router.route(preprocessing_output.optimized_query)
            # [阶段B] 记录预测车道（来自 LLM 建议或 Router）
            predicted_lane = preprocessing_output.lane_suggestion if hasattr(preprocessing_output, 'lane_suggestion') else route_decision.lane
            lane_confidence = preprocessing_output.lane_confidence if hasattr(preprocessing_output, 'lane_confidence') else 0.7

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
                'recall_count': retrieval_result.recall_count,
                'rerank_results': retrieval_result.rerank_results,
                'sufficiency_result': retrieval_result.sufficiency_result
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

        # 步骤4: 生成答案
        try:
            # 从retrieval_result提取rerank结果
            if route_decision.lane == "fast" and hasattr(retrieval_result, 'rerank_results'):
                chunks_for_generation = retrieval_result.rerank_results
            else:
                # 慢车道：retrieved_chunks 是 List[ChunkResult]，需转换为 RerankResult
                from app.core.retrieval.rerank import RerankResult
                from app.schemas.retrieval import ChunkResult
                chunks_for_generation = []
                for chunk in retrieval_result.retrieved_chunks:
                    if isinstance(chunk, ChunkResult):
                        # ChunkResult → RerankResult
                        chunks_for_generation.append(RerankResult(
                            chunk_id=chunk.chunk_id,
                            content=chunk.content,
                            document_id=chunk.document_id,
                            standard_no=chunk.standard_no,
                            clause=chunk.clause,
                            score=chunk.score,
                            recall_source='slow_lane',
                            document_title=chunk.document_title
                        ))
                    elif isinstance(chunk, dict):
                        # 兼容旧的 dict 格式
                        chunks_for_generation.append(RerankResult(
                            chunk_id=chunk.get('chunk_id', 0),
                            content=chunk.get('content', ''),
                            document_id=chunk.get('document_id', 0),
                            standard_no=chunk.get('standard_no'),
                            clause=chunk.get('clause'),
                            score=chunk.get('score', 0.0),
                            recall_source=chunk.get('recall_source', 'unknown'),
                            document_title=chunk.get('document_title')
                        ))

            logger.info(f"[User {user_id}] Generating answer with {len(chunks_for_generation)} chunks")

            generation_result = await self.generator.generate(
                query=preprocessing_output.optimized_query,
                chunks=chunks_for_generation
            )

            logger.info(f"[User {user_id}] Answer generated in {generation_result.generation_time}ms, tokens={generation_result.token_count}")

            # 格式化citations为dict
            citations_list = [
                {
                    'index': c.index,
                    'chunk_id': c.chunk_id,
                    'standard_no': c.standard_no,
                    'clause': c.clause,
                    'content_snippet': c.content_snippet,
                    'document_title': c.document_title
                }
                for c in generation_result.citations
            ]

            answer = generation_result.answer
            generation_time = generation_result.generation_time
            citations = citations_list

        except Exception as e:
            logger.error(f"[User {user_id}] Generation error: {e}", exc_info=True)
            answer = f"抱歉，生成答案时出现错误。"
            generation_time = 0
            citations = []
            generation_result = None

        # 当前返回模拟结果
        elapsed_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[User {user_id}] Query completed in {elapsed_ms}ms")

        # 步骤5: 记录查询日志（如果提供了数据库会话）
        query_log_id = 0
        if self.db:
            try:
                query_log_id = self._record_query_log(
                    user_id=user_id,
                    query=query,
                    normalized_query=preprocessing_output.optimized_query,
                    lane=route_decision.lane,
                    predicted_lane=predicted_lane,  # [阶段B]
                    lane_confidence=lane_confidence,  # [阶段B]
                    user_lane=user_lane,  # [阶段B]
                    vagueness_score=preprocessing_output.vagueness_score if not is_clarified_query else None,
                    clarified=is_clarified_query,
                    retrieval_time=lane_info.get('retrieval_time', 0),
                    total_time=elapsed_ms,
                    lane_info=lane_info,
                    answer=answer,
                    citations=citations if citations else None,
                    conversation_id=conversation_id
                )

                # 如果是澄清后的查询，记录澄清日志
                if is_clarified_query and clarification_context:
                    self._record_clarification_log(
                        query_log_id=query_log_id,
                        original_query=query,
                        refined_query=refined_query,
                        selected_option_id=selected_option_id,
                        clarification_context=clarification_context
                    )
            except Exception as e:
                logger.error(f"[User {user_id}] Failed to record query log: {e}", exc_info=True)

        result = {
            'status': 'success',
            'answer': answer,
            'citations': citations,
            'lane': route_decision.lane,
            'route_reason': route_decision.reason,
            'retrieval_time': lane_info.get('retrieval_time', 0),
            'generation_time': generation_time,
            'total_time': elapsed_ms,
            'query_log_id': query_log_id,
            **lane_info  # 合并车道特定信息
        }

        # 如果是澄清后的查询，附加澄清上下文
        if is_clarified_query:
            result['clarification_applied'] = True
            result['original_query'] = query
            result['refined_query'] = refined_query
            result['selected_option_id'] = selected_option_id
            result['clarification_context'] = clarification_context

        return result

    def _record_query_log(
        self,
        user_id: int,
        query: str,
        normalized_query: str,
        lane: str,
        vagueness_score: Optional[float],
        clarified: bool,
        retrieval_time: int,
        total_time: int,
        lane_info: Dict[str, Any],
        answer: Optional[str] = None,
        citations: Optional[list] = None,
        conversation_id: Optional[str] = None,
        predicted_lane: Optional[str] = None,  # [阶段B] LLM预测车道
        lane_confidence: Optional[float] = None,  # [阶段B] 路由置信度
        user_lane: Optional[str] = None  # [阶段B] 用户选择的车道
    ) -> int:
        """
        记录查询日志

        Returns:
            int: 查询日志ID
        """
        # 提取重排结果和充分性结果（仅快车道有）
        rerank_scores = None
        sufficiency_result_data = None
        retrieved_chunk_ids = None
        reasoning_steps_data = None

        if lane == 'fast':
            rerank_results = lane_info.get('rerank_results', [])
            if rerank_results:
                # 构造 rerank_scores JSON
                rerank_scores = [
                    {'chunk_id': r.chunk_id, 'score': r.score}
                    for r in rerank_results
                ]
                # 构造 retrieved_chunk_ids
                retrieved_chunk_ids = [r.chunk_id for r in rerank_results]

            # 构造 sufficiency_result JSON
            suf = lane_info.get('sufficiency_result')
            if suf:
                sufficiency_result_data = {
                    'sufficient': suf.sufficient,
                    'source': suf.source,
                    'confidence': suf.confidence,
                    'gaps': suf.gaps
                }
        elif lane == 'slow':
            # 慢车道：提取 reasoning_steps
            reasoning_steps = lane_info.get('reasoning_steps', [])
            if reasoning_steps:
                # 转换 ToolCallRecord 为 dict
                reasoning_steps_data = [
                    {
                        'step': record.step,
                        'tool': record.tool,
                        'params': record.params,
                        'elapsed_ms': record.elapsed_ms,
                        'result_count': record.result_count,
                        'timeout': record.timeout
                    }
                    for record in reasoning_steps
                ]

            # 慢车道的 retrieved_chunk_ids（从 recall_count 推断，暂无具体 chunk_ids）
            # TODO: 如果需要具体 chunk_ids，需要从 retrieval_result.retrieved_chunks 提取
            retrieved_chunk_ids = []  # 慢车道暂不记录具体 chunk_ids

        query_log = QueryLog(
            user_id=user_id,
            conversation_id=conversation_id,
            query=query,
            normalized_query=normalized_query,
            lane=lane,
            predicted_lane=predicted_lane or lane,  # [阶段B] 默认等于最终车道
            lane_confidence=lane_confidence,  # [阶段B]
            user_lane=user_lane,  # [阶段B]
            vagueness_score=vagueness_score,
            clarified=clarified,
            retrieval_time=retrieval_time,
            total_time=total_time,
            recall_count=lane_info.get('recall_count', 0),
            retry_count=1 if lane_info.get('retry_triggered', False) else 0,
            retrieved_chunk_ids=retrieved_chunk_ids,
            rerank_scores=rerank_scores,
            sufficiency_result=sufficiency_result_data,
            reasoning_steps=reasoning_steps_data,  # 新增：慢车道推理步骤
            expanded_queries=lane_info.get('expanded_queries', []),
            answer=answer,
            citations=citations,
            has_citations=bool(citations)
        )

        self.db.add(query_log)
        self.db.commit()
        self.db.refresh(query_log)

        logger.info(f"[QueryLog] Recorded query_log_id={query_log.id}")

        # 如果充分性判断为不充分且触发了二次检索，考虑记录badcase
        if lane == 'fast' and sufficiency_result_data:
            if not sufficiency_result_data['sufficient'] and lane_info.get('retry_triggered', False):
                # 二次检索后仍可能不充分，记录badcase
                self._record_badcase_if_needed(query_log.id, sufficiency_result_data, query)

        return query_log.id

    def _record_clarification_log(
        self,
        query_log_id: int,
        original_query: str,
        refined_query: str,
        selected_option_id: Optional[int],
        clarification_context: Dict[str, Any]
    ) -> int:
        """
        记录澄清日志

        Returns:
            int: 澄清日志ID
        """
        # 从上下文中提取信息
        vagueness_score = clarification_context.get('vagueness_score', 0.0)
        strategy = clarification_context.get('strategy', 'clarify')
        options_generated = clarification_context.get('options', [])
        missing_dimensions = clarification_context.get('missing_dimensions')

        # 确定用户选择类型
        if selected_option_id:
            user_choice = f"option_{selected_option_id}"
        else:
            user_choice = "skip"

        clarification_log = ClarificationLog(
            query_log_id=query_log_id,
            original_query=original_query,
            strategy=strategy,
            vagueness_score=vagueness_score,
            options_generated=options_generated,
            user_choice=user_choice,
            refined_query=refined_query,
            missing_dimensions=missing_dimensions
        )

        self.db.add(clarification_log)
        self.db.commit()
        self.db.refresh(clarification_log)

        logger.info(f"[ClarificationLog] Recorded clarification_log_id={clarification_log.id} for query_log_id={query_log_id}")
        return clarification_log.id

    def _record_badcase_if_needed(
        self,
        query_log_id: int,
        sufficiency_result: Dict[str, Any],
        query: str = ""
    ):
        """
        记录坏案例（当充分性不足时）

        Args:
            query_log_id: 查询日志ID
            sufficiency_result: 充分性判断结果
        """
        try:
            from app.db.models import BadcaseTracking

            # 仅在LLM判断不充分时记录badcase
            if sufficiency_result.get('source') == 'llm' and not sufficiency_result.get('sufficient'):
                gaps = sufficiency_result.get('gaps', [])
                root_cause_detail = '; '.join(gaps) if gaps else '充分性判断失败'

                badcase = BadcaseTracking(
                    query_log_id=query_log_id,
                    query=query,
                    root_cause='reranking',  # 重排层问题
                    root_cause_detail=root_cause_detail,
                    status='pending'
                )

                self.db.add(badcase)
                self.db.commit()
                logger.info(f"[BadcaseTracking] Recorded badcase for query_log_id={query_log_id}")

        except Exception as e:
            logger.error(f"[BadcaseTracking] Failed to record badcase: {e}", exc_info=True)

