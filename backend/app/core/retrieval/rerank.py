"""
重排层 (Reranking Layer)

两阶段重排：
1. 粗排：bge-reranker-base (Top50 → Top20)
2. 精排：bge-reranker-large (Top20 → Top5)
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np
import torch
import logging
import hashlib
import asyncio
from pathlib import Path

from app.schemas.retrieval import ChunkResult
from app.storage.cache import cache
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """重排结果"""
    chunk_id: int
    content: str
    document_id: int
    standard_no: Optional[str]
    clause: Optional[str]
    score: float  # sigmoid归一化分数 [0, 1]
    recall_source: str  # "vector" / "keyword" / "structured"

    # 额外文档信息（用于生成层）
    document_title: Optional[str] = None
    doc_type: Optional[str] = None
    category: Optional[str] = None
    voltage_level: Optional[str] = None
    chapter: Optional[str] = None
    section: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None


class TwoStageReranker:
    """
    两阶段重排器

    粗排：bge-reranker-base (快速剪枝)
    精排：bge-reranker-large (精准排序)
    """

    def __init__(
        self,
        coarse_model_path: Optional[str] = None,
        fine_model_path: Optional[str] = None,
        coarse_threshold: float = 0.1,
        fine_threshold: float = 0.2,
        coarse_top_k: int = 20,
        fine_top_k: int = 5,
        coarse_batch_size: int = 16,
        fine_batch_size: int = 8,
        enable_cache: bool = True,
        cache_ttl: int = 300,
    ):
        """
        初始化两阶段重排器

        Args:
            coarse_model_path: 粗排模型路径（bge-reranker-base）
            fine_model_path: 精排模型路径（bge-reranker-large）
            coarse_threshold: 粗排分数阈值
            fine_threshold: 精排分数阈值
            coarse_top_k: 粗排保留数量
            fine_top_k: 精排保留数量
            coarse_batch_size: 粗排批处理大小
            fine_batch_size: 精排批处理大小
            enable_cache: 是否启用Redis缓存
            cache_ttl: 缓存TTL（秒）
        """
        self.coarse_threshold = coarse_threshold
        self.fine_threshold = fine_threshold
        self.coarse_top_k = coarse_top_k
        self.fine_top_k = fine_top_k
        self.coarse_batch_size = coarse_batch_size
        self.fine_batch_size = fine_batch_size
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl

        # 模型路径
        self.coarse_model_path = coarse_model_path or self._get_model_path(settings.RERANKER_MODEL_BASE)
        self.fine_model_path = fine_model_path or self._get_model_path(settings.RERANKER_MODEL_LARGE)

        # 延迟加载模型
        self.coarse_model = None
        self.coarse_tokenizer = None
        self.fine_model = None
        self.fine_tokenizer = None

        self._load_models()

    def _get_model_path(self, model_name: str) -> str:
        """获取本地模型路径"""
        local_path = Path(settings.MODELS_DIR) / model_name.replace("/", "--")
        if local_path.exists():
            return str(local_path)
        logger.warning(f"Local model not found at {local_path}, using HF name: {model_name}")
        return model_name

    def _load_models(self):
        """加载重排模型"""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            # 加载粗排模型（bge-reranker-base）
            logger.info(f"Loading coarse reranker from: {self.coarse_model_path}")
            self.coarse_tokenizer = AutoTokenizer.from_pretrained(self.coarse_model_path)
            self.coarse_model = AutoModelForSequenceClassification.from_pretrained(self.coarse_model_path)
            self.coarse_model.eval()
            logger.info("Coarse reranker loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load coarse reranker: {e}")
            self.coarse_model = None
            self.coarse_tokenizer = None

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            # 加载精排模型（bge-reranker-large）
            logger.info(f"Loading fine reranker from: {self.fine_model_path}")
            self.fine_tokenizer = AutoTokenizer.from_pretrained(self.fine_model_path)
            self.fine_model = AutoModelForSequenceClassification.from_pretrained(self.fine_model_path)
            self.fine_model.eval()
            logger.info("Fine reranker loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load fine reranker: {e}")
            self.fine_model = None
            self.fine_tokenizer = None

    async def rerank(
        self,
        query: str,
        candidates: List[ChunkResult],
        top_k: Optional[int] = None,
    ) -> List[RerankResult]:
        """
        两阶段重排

        Args:
            query: 用户查询
            candidates: 召回的候选块（Top50）
            top_k: 最终返回数量（默认使用 fine_top_k）

        Returns:
            List[RerankResult]: 重排后的结果
        """
        if not candidates:
            logger.warning("[TwoStageReranker] Empty candidates")
            return []

        top_k = top_k or self.fine_top_k

        # 候选块少于top_k时直接返回
        if len(candidates) <= top_k:
            logger.info(f"[TwoStageReranker] Only {len(candidates)} candidates, skipping rerank")
            return [self._chunk_to_rerank_result(c, c.score) for c in candidates]

        # 阶段1: 粗排（Top50 → Top20）
        coarse_results = await self._coarse_rerank(query, candidates)

        if not coarse_results:
            logger.warning("[TwoStageReranker] Coarse rerank returned empty, using recall scores")
            return self._fallback_to_recall_scores(candidates, top_k)

        # 阶段2: 精排（Top20 → Top5）
        fine_results = await self._fine_rerank(query, coarse_results, top_k)

        if not fine_results:
            logger.warning("[TwoStageReranker] Fine rerank returned empty, using coarse results")
            return coarse_results[:top_k]

        logger.info(f"[TwoStageReranker] Completed: {len(candidates)} → {len(coarse_results)} → {len(fine_results)}")
        return fine_results

    async def _coarse_rerank(
        self,
        query: str,
        candidates: List[ChunkResult],
    ) -> List[RerankResult]:
        """
        粗排：bge-reranker-base (Top50 → Top20)

        Args:
            query: 查询文本
            candidates: 候选块列表

        Returns:
            粗排后的Top20结果
        """
        # 降级策略：粗排模型不可用
        if self.coarse_model is None or self.coarse_tokenizer is None:
            logger.warning("[CoarseRerank] Model not available, using recall scores")
            sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
            return [
                self._chunk_to_rerank_result(c, c.score)
                for c in sorted_candidates[:self.coarse_top_k]
            ]

        try:
            # 批量计算重排分数
            scores = await self._compute_scores(
                query,
                candidates,
                self.coarse_model,
                self.coarse_tokenizer,
                self.coarse_batch_size,
                stage="coarse"
            )

            # 构造结果并排序（不设硬阈值截断，避免整批候选被淘汰后回退到召回分数）
            results = [self._chunk_to_rerank_result(c, s) for c, s in zip(candidates, scores)]
            results.sort(key=lambda x: x.score, reverse=True)
            top_results = results[:self.coarse_top_k]

            best = top_results[0].score if top_results else 0.0
            logger.info(f"[CoarseRerank] {len(candidates)} → Top{len(top_results)} (best_score={best:.3f})")
            return top_results

        except Exception as e:
            logger.error(f"[CoarseRerank] Error: {e}", exc_info=True)
            # 降级：返回召回分数前20
            sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
            return [
                self._chunk_to_rerank_result(c, c.score)
                for c in sorted_candidates[:self.coarse_top_k]
            ]

    async def _fine_rerank(
        self,
        query: str,
        candidates: List[RerankResult],
        top_k: int,
    ) -> List[RerankResult]:
        """
        精排：bge-reranker-large (Top20 → Top5)

        Args:
            query: 查询文本
            candidates: 粗排后的候选块
            top_k: 最终保留数量

        Returns:
            精排后的TopK结果
        """
        # 降级策略：精排模型不可用，使用粗排模型
        if self.fine_model is None or self.fine_tokenizer is None:
            if self.coarse_model is not None:
                logger.warning("[FineRerank] Fine model not available, using coarse model")
                # 用粗排模型重新打分
                chunk_results = [self._rerank_to_chunk_result(r) for r in candidates]
                scores = await self._compute_scores(
                    query,
                    chunk_results,
                    self.coarse_model,
                    self.coarse_tokenizer,
                    self.fine_batch_size,
                    stage="fine_fallback"
                )
                for candidate, score in zip(candidates, scores):
                    candidate.score = score
            else:
                logger.warning("[FineRerank] No rerank model available, using coarse scores")

            # 排序并返回
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:top_k]

        try:
            # 批量计算精排分数
            chunk_results = [self._rerank_to_chunk_result(r) for r in candidates]
            scores = await self._compute_scores(
                query,
                chunk_results,
                self.fine_model,
                self.fine_tokenizer,
                self.fine_batch_size,
                stage="fine"
            )

            # 更新分数
            for candidate, score in zip(candidates, scores):
                candidate.score = score

            # 按分数排序
            candidates.sort(key=lambda x: x.score, reverse=True)

            # 应用阈值过滤并取Top K
            results = [c for c in candidates if c.score >= self.fine_threshold]

            # 如果过滤后少于top_k，放宽阈值
            if len(results) < top_k:
                logger.warning(f"[FineRerank] Only {len(results)} above threshold {self.fine_threshold}, returning top {top_k}")
                results = candidates[:top_k]

            logger.info(f"[FineRerank] {len(candidates)} → Top{len(results[:top_k])}")
            return results[:top_k]

        except Exception as e:
            logger.error(f"[FineRerank] Error: {e}", exc_info=True)
            # 降级：使用粗排分数
            candidates.sort(key=lambda x: x.score, reverse=True)
            return candidates[:top_k]

    async def _compute_scores(
        self,
        query: str,
        candidates: List[ChunkResult],
        model,
        tokenizer,
        batch_size: int,
        stage: str,
    ) -> List[float]:
        """
        批量计算重排分数（带缓存）

        Args:
            query: 查询文本
            candidates: 候选块
            model: 重排模型
            tokenizer: 分词器
            batch_size: 批处理大小
            stage: 阶段标识（coarse/fine）

        Returns:
            归一化分数列表
        """
        scores = []
        query_hash = self._hash_query(query)

        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            batch_scores = []

            for candidate in batch:
                # 尝试从缓存读取
                if self.enable_cache:
                    cache_key = f"rerank:score:{query_hash}:{candidate.chunk_id}"
                    cached_score = cache.get(cache_key)
                    if cached_score is not None:
                        batch_scores.append(float(cached_score))
                        continue

                # 缓存未命中，需要计算
                batch_scores.append(None)

            # 找出需要计算的索引
            compute_indices = [i for i, score in enumerate(batch_scores) if score is None]

            if compute_indices:
                # 批量推理
                compute_batch = [batch[i] for i in compute_indices]
                text_pairs = [[query, self._truncate_text(c.content)] for c in compute_batch]

                try:
                    # Tokenize
                    inputs = tokenizer(
                        text_pairs,
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt"
                    )

                    # 推理
                    with torch.no_grad():
                        outputs = model(**inputs)
                        logits = outputs.logits.squeeze(-1)  # (batch_size,)

                    # Sigmoid归一化到[0, 1]
                    normalized_scores = torch.sigmoid(logits).cpu().numpy().tolist()

                    # 填充计算结果
                    for idx, score in zip(compute_indices, normalized_scores):
                        batch_scores[idx] = float(score)

                        # 写入缓存
                        if self.enable_cache:
                            cache_key = f"rerank:score:{query_hash}:{batch[idx].chunk_id}"
                            cache.set(cache_key, score, ttl=self.cache_ttl)

                except Exception as e:
                    logger.error(f"[{stage}] Batch inference error: {e}")
                    # 降级：使用召回分数
                    for idx in compute_indices:
                        batch_scores[idx] = batch[idx].score

            scores.extend(batch_scores)

        return scores

    def _truncate_text(self, text: str, max_tokens: int = 256) -> str:
        """截断文本到最大token数"""
        # 简单按字符截断（中文平均1字≈1.5token）
        max_chars = int(max_tokens * 1.5)
        if len(text) > max_chars:
            return text[:max_chars]
        return text

    def _hash_query(self, query: str) -> str:
        """生成查询的MD5哈希"""
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def _chunk_to_rerank_result(self, chunk: ChunkResult, score: float) -> RerankResult:
        """ChunkResult 转换为 RerankResult"""
        return RerankResult(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            document_id=chunk.document_id,
            standard_no=chunk.standard_no,
            clause=chunk.clause,
            score=score,
            recall_source=chunk.recall_source or "unknown",
            document_title=chunk.document_title,
            doc_type=chunk.doc_type,
            category=chunk.category,
            voltage_level=chunk.voltage_level,
            chapter=chunk.chapter,
            section=chunk.section,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )

    def _rerank_to_chunk_result(self, rerank: RerankResult) -> ChunkResult:
        """RerankResult 转换为 ChunkResult"""
        return ChunkResult(
            chunk_id=rerank.chunk_id,
            content=rerank.content,
            document_id=rerank.document_id,
            score=rerank.score,
            standard_no=rerank.standard_no,
            doc_type=rerank.doc_type,
            category=rerank.category,
            voltage_level=rerank.voltage_level,
            clause=rerank.clause,
            chapter=rerank.chapter,
            section=rerank.section,
            page_start=rerank.page_start,
            page_end=rerank.page_end,
            recall_source=rerank.recall_source,
            document_title=rerank.document_title,
        )

    def _fallback_to_recall_scores(
        self,
        candidates: List[ChunkResult],
        top_k: int
    ) -> List[RerankResult]:
        """降级：直接使用召回分数"""
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        return [
            self._chunk_to_rerank_result(c, c.score)
            for c in sorted_candidates[:top_k]
        ]


# 全局单例
_reranker_instance: Optional[TwoStageReranker] = None


def get_reranker() -> TwoStageReranker:
    """获取重排器单例"""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = TwoStageReranker()
    return _reranker_instance
