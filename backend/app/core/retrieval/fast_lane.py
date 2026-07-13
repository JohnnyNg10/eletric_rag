"""
快车道 (Fast Lane)

职责：
- 查询改写与扩展（从 preprocessing 移入）
- 元数据提取（从 preprocessing 移入）
- 三路并行召回
- 两阶段重排
- 召回充分性判断
- 可选二次检索
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging
import re
import time

# 从 preprocessing 导入组件（这些组件逻辑上属于快车道）
from app.core.preprocessing.query_rewriter import QueryRewriter
from app.core.preprocessing.metadata_extractor import MetadataExtractor
from app.core.retrieval.rerank import TwoStageReranker, RerankResult, get_reranker
from app.core.retrieval.sufficiency import SufficiencyChecker, SufficiencyResult, get_sufficiency_checker
from app.core.retrieval.hyde import get_hyde_generator
from app.schemas.retrieval import ChunkResult

logger = logging.getLogger(__name__)


@dataclass
class FastLaneResult:
    """快车道检索结果"""
    status: str  # "success" or "insufficient"
    retrieved_chunks: List[Dict]  # 召回的文档块（转换为dict）
    rerank_results: List[RerankResult]  # 重排结果（保留完整对象）
    expanded_queries: List[str]  # 扩展查询列表
    filters: Dict[str, Any]  # 元数据过滤条件
    metadata: Dict[str, Any]  # 提取的元数据
    retrieval_time: int  # 检索耗时(ms)
    retry_triggered: bool  # 是否触发二次检索
    recall_count: int  # 召回块数量
    sufficiency_result: Optional[SufficiencyResult] = None  # 充分性判断结果
    hyde_query: Optional[str] = None  # HyDE 生成的假设文档（若启用）


class FastLane:
    """
    快车道 - 固定流水线检索

    适用场景：
    - 单一维度查询
    - 明确标准号/条款号
    - 常规问答

    处理流程：
    1. 查询改写 + 元数据提取
    2. 三路并行召回（TODO）
    3. 两阶段重排（TODO）
    4. 充分性判断（TODO）
    5. 可选二次检索（TODO）
    """

    def __init__(self, db=None):
        # 快车道专属组件
        self.query_rewriter = QueryRewriter()
        self.metadata_extractor = MetadataExtractor()

        # 重排和充分性判断组件
        self.reranker = get_reranker()
        self.sufficiency_checker = get_sufficiency_checker()

        # HyDE 生成器
        self.hyde_generator = get_hyde_generator()

        # 数据库会话（用于召回层）
        self.db = db

        # 召回引擎（懒加载）
        self._recall_engine = None

    async def execute(
        self,
        query: str,
        user_context: Dict[str, Any],
        strategy_params: Dict[str, Any],
        preprocessing_result=None
    ) -> FastLaneResult:
        """
        执行快车道流程

        Args:
            query: 预处理后的清晰查询（已标准化）
            user_context: 用户上下文
            strategy_params: 检索策略参数
            preprocessing_result: 预处理结果（OptimizationResult），包含 LLM 识别的类别

        Returns:
            FastLaneResult: 检索结果
        """
        start_time = time.time()

        logger.info(f"[FastLane] Start processing: {query}")

        # 步骤1: 查询增强（查询改写 + 元数据提取）
        expanded_queries = await self._enhance_query(query, strategy_params)
        filters = self._extract_metadata(query, preprocessing_result)  # 传递预处理结果
        metadata = self.metadata_extractor.extract_all_metadata(query, preprocessing_result)  # 传递预处理结果

        logger.info(f"[FastLane] Expanded queries: {expanded_queries}")
        logger.info(f"[FastLane] Filters: {filters}")
        logger.info(f"[FastLane] Metadata: {metadata}")

        # 步骤1.5: 可选的类别特定 HyDE 生成
        hyde_query = None
        enable_hyde = strategy_params.get("enable_hyde", False)
        if enable_hyde:
            category = metadata.get('category')
            hyde_query = await self.hyde_generator.generate(query, category)
            logger.info(f"[FastLane] HyDE enabled, category={category}, hyde_query={hyde_query[:50]}...")

        # 步骤2: 三路并行召回（向量召回使用 HyDE query）
        recalled_chunks = await self._multi_path_recall(
            expanded_queries,
            filters,
            hyde_query=hyde_query
        )
        logger.info(f"[FastLane] Recalled {len(recalled_chunks)} chunks")

        # 步骤2.5: 去重（精确内容去重，避免重复标题占据精排名额）
        deduped_chunks = self._deduplicate_candidates(recalled_chunks)
        logger.info(f"[FastLane] After dedup: {len(deduped_chunks)} chunks ({len(recalled_chunks) - len(deduped_chunks)} removed)")

        # 步骤3: 两阶段重排
        reranked_results = await self.reranker.rerank(
            query=query,
            candidates=deduped_chunks,
            top_k=8
        )
        logger.info(f"[FastLane] Reranked to Top{len(reranked_results)}")

        # 步骤4: 充分性判断
        sufficiency_result = await self.sufficiency_checker.check(
            query=query,
            top_results=reranked_results
        )
        logger.info(f"[FastLane] Sufficiency: {sufficiency_result.sufficient} (source={sufficiency_result.source})")

        retry_triggered = False
        retry_count = 0

        # 步骤5: 可选二次检索
        if not sufficiency_result.sufficient and strategy_params.get("enable_retry", True) and retry_count == 0:
            logger.info(f"[FastLane] Sufficiency check failed, triggering retry")

            # 基于gaps改写查询
            retry_query = await self._refine_query_for_gaps(query, sufficiency_result.gaps)
            logger.info(f"[FastLane] Retry query: {retry_query}")

            # 补充召回
            retry_chunks = await self._multi_path_recall([retry_query], filters)
            logger.info(f"[FastLane] Retry recalled {len(retry_chunks)} chunks")

            # 合并去重（保留原Top5 + 补充召回）
            merged_chunks = self._merge_deduplicate(recalled_chunks, retry_chunks)

            # 内容去重（同首次召回一样）
            merged_chunks = self._deduplicate_candidates(merged_chunks)

            # 重新精排（Top10，比正常多2个）
            reranked_results = await self.reranker.rerank(
                query=query,
                candidates=merged_chunks,
                top_k=10
            )
            logger.info(f"[FastLane] Retry reranked to Top{len(reranked_results)}")

            retry_triggered = True
            retry_count = 1

        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[FastLane] Completed in {elapsed_ms}ms")

        # 转换为dict格式（用于向后兼容）
        retrieved_chunks_dict = [self._rerank_result_to_dict(r) for r in reranked_results]

        # 返回结果
        return FastLaneResult(
            status="success",
            retrieved_chunks=retrieved_chunks_dict,
            rerank_results=reranked_results,
            expanded_queries=expanded_queries,
            filters=filters,
            metadata=metadata,
            retrieval_time=elapsed_ms,
            retry_triggered=retry_triggered,
            recall_count=len(reranked_results),
            sufficiency_result=sufficiency_result,
            hyde_query=hyde_query
        )

    async def _enhance_query(self, query: str, strategy_params: Dict) -> List[str]:
        """
        查询增强：生成2-3个扩展查询

        Args:
            query: 原始查询
            strategy_params: 策略参数

        Returns:
            List[str]: 扩展查询列表
        """
        max_expansions = strategy_params.get("max_expansions", 3)

        # 调用 QueryRewriter 生成扩展查询
        expanded_queries = await self.query_rewriter.rewrite(
            query,
            max_expansions=max_expansions
        )

        return expanded_queries

    def _extract_metadata(self, query: str, preprocessing_result=None) -> Dict[str, Any]:
        """
        元数据提取：提取电压等级、标准号等过滤条件

        Args:
            query: 查询
            preprocessing_result: 预处理结果（OptimizationResult），包含 LLM 识别的类别

        Returns:
            Dict: 元数据过滤条件
        """
        # 传递预处理结果给 MetadataExtractor
        return self.metadata_extractor.extract(query, preprocessing_result)

    async def _multi_path_recall(
        self,
        queries: List[str],
        filters: Dict[str, Any],
        hyde_query: Optional[str] = None
    ) -> List[ChunkResult]:
        """
        三路并行召回：向量 + 关键词 + 结构化

        Args:
            queries: 扩展查询列表
            filters: 元数据过滤条件
            hyde_query: HyDE 生成的假设文档（可选，仅用于向量召回）

        Returns:
            List[ChunkResult]: Top50候选块
        """
        if not self.db:
            logger.warning("[FastLane] No DB session, returning empty recall")
            return []

        # 懒加载召回引擎
        if self._recall_engine is None:
            from app.core.retrieval.recall import MultiPathRecall
            self._recall_engine = MultiPathRecall(self.db)

        # 使用第一个查询作为主查询
        main_query = queries[0] if queries else ""

        # 执行三路召回（向量召回使用 HyDE query，其他使用原查询）
        recalled_chunks = await self._recall_engine.recall(
            query=main_query,
            filters=filters,
            expanded_queries=queries,
            hyde_query=hyde_query  # 传递 HyDE query 给召回引擎
        )

        return recalled_chunks

    async def _refine_query_for_gaps(
        self,
        original_query: str,
        gaps: List[str]
    ) -> str:
        """
        基于信息缺口改写查询（用于二次检索）

        Args:
            original_query: 原始查询
            gaps: 信息缺口列表

        Returns:
            改写后的查询
        """
        if not gaps:
            return original_query

        # 调用QueryRewriter生成针对缺口的查询
        gaps_text = "、".join(gaps)
        refined_query = f"{original_query} {gaps_text}"

        # TODO: 可以用LLM更智能地改写
        # refined_query = await self.query_rewriter.rewrite_for_gaps(
        #     original_query, gaps
        # )

        return refined_query

    def _merge_deduplicate(
        self,
        original_chunks: List[ChunkResult],
        retry_chunks: List[ChunkResult]
    ) -> List[ChunkResult]:
        """
        合并去重（按chunk_id）

        Args:
            original_chunks: 原始召回块
            retry_chunks: 补充召回块

        Returns:
            合并去重后的候选块
        """
        chunk_map = {}

        # 先加入原始块
        for chunk in original_chunks:
            chunk_map[chunk.chunk_id] = chunk

        # 加入补充块（不覆盖已有）
        for chunk in retry_chunks:
            if chunk.chunk_id not in chunk_map:
                chunk_map[chunk.chunk_id] = chunk

        # 按分数排序
        merged = sorted(chunk_map.values(), key=lambda c: c.score, reverse=True)
        return merged

    # 目录页的典型特征：多行"标题文字 + 页码数字"
    _TOC_LINE_RE = re.compile(r'[一-鿿\w]{2,}\s+\d{1,3}\s*$', re.MULTILINE)

    def _deduplicate_candidates(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """
        精排前过滤 + 去重，防止纯标题/目录页占据精排名额。

        策略：
        1. 过滤纯标题块（正文内容 < 20字符，无参考价值）
        2. 过滤目录页（含 ≥3 行"文字+页码"结构）
        3. 精确内容去重（保留召回分最高的版本）
        4. 子集去重：若某块内容是另一块的真子串，丢弃较短的（冗余标题）
        """

        # 先按召回分排序，保证保留高分版本
        sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)

        seen_normalized: dict[str, bool] = {}
        kept: List[ChunkResult] = []

        for chunk in sorted_chunks:
            normalized = " ".join(chunk.content.strip().split())

            # 过滤纯标题块（太短，只有章节号+标题，没有实质内容）
            if len(normalized) < 20:
                logger.debug(f"[Dedup] Drop short chunk id={chunk.chunk_id}: {normalized!r}")
                continue

            # 过滤目录页（≥3 行以"文字+空格+页码"结尾）
            toc_matches = self._TOC_LINE_RE.findall(chunk.content)
            if len(toc_matches) >= 3:
                logger.debug(f"[Dedup] Drop TOC chunk id={chunk.chunk_id} ({len(toc_matches)} toc lines)")
                continue

            # 精确内容去重（只去掉完全相同的内容，保留高分版本）
            if normalized in seen_normalized:
                continue

            seen_normalized[normalized] = True
            kept.append(chunk)

        logger.info(f"[Dedup] {len(chunks)} → {len(kept)} (filtered {len(chunks)-len(kept)})")
        return kept

    def _rerank_result_to_dict(self, result: RerankResult) -> Dict[str, Any]:
        """将RerankResult转换为dict"""
        return {
            'chunk_id': result.chunk_id,
            'content': result.content,
            'document_id': result.document_id,
            'standard_no': result.standard_no,
            'clause': result.clause,
            'score': result.score,
            'recall_source': result.recall_source,
            'document_title': result.document_title,
            'doc_type': result.doc_type,
            'category': result.category,
            'voltage_level': result.voltage_level,
            'chapter': result.chapter,
            'section': result.section,
            'page_start': result.page_start,
            'page_end': result.page_end,
        }
