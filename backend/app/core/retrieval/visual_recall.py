"""
视觉召回模块（ColPali Late Interaction）

基于 ColPali multi-vector 的视觉文档检索：
- 查询编码：文本 → multi-vector (Seq_Len, 128)
- 图片索引：PIL.Image → multi-vector (Seq_Len, 128)
- 相似度计算：Late Interaction MaxSim
- 无条件执行：所有查询都会尝试视觉召回
"""
from typing import List, Dict, Any, Optional
import logging
import asyncio

from app.core.embedding.colpali_embedder import ColPaliEmbedder
from app.storage.vector_store import vector_store
from app.schemas.retrieval import ChunkResult
from app.config import settings

logger = logging.getLogger(__name__)


class VisualRecall:
    """视觉召回（ColPali）"""

    def __init__(self):
        """初始化视觉召回器"""
        self.embedder: Optional[ColPaliEmbedder] = None
        self.enabled = settings.ENABLE_VISUAL_RECALL
        self.timeout_ms = settings.VISUAL_RECALL_TIMEOUT_MS
        self.top_k = settings.VISUAL_RECALL_TOP_K

        # 延迟加载模型（首次调用时才加载）
        if self.enabled:
            logger.info("[VisualRecall] Visual recall enabled, model will load on first query")
        else:
            logger.info("[VisualRecall] Visual recall disabled by config")

    def _ensure_embedder_loaded(self):
        """确保 ColPali 模型已加载（懒加载）"""
        if self.embedder is None:
            logger.info("[VisualRecall] Loading ColPali model...")
            self.embedder = ColPaliEmbedder(
                model_path=settings.COLPALI_MODEL_CACHE_DIR,
                device=settings.COLPALI_DEVICE
            )
            logger.info("[VisualRecall] ColPali model loaded successfully")

    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = None
    ) -> List[ChunkResult]:
        """
        视觉召回检索（无条件执行）

        Args:
            query: 查询文本
            filters: Qdrant payload 过滤条件
            top_k: 召回数量（默认使用配置值）

        Returns:
            ChunkResult 列表（按 MaxSim 相似度降序）

        说明：
            - 不判断查询意图，始终执行召回
            - 相关性由 RRF 和 Reranker 决定
            - 超时保护（500ms）自动降级
        """
        if not self.enabled:
            logger.debug("[VisualRecall] Visual recall disabled, returning empty results")
            return []

        if top_k is None:
            top_k = self.top_k

        try:
            # 确保模型已加载
            self._ensure_embedder_loaded()

            # 编码查询（同步操作，但在事件循环中执行）
            query_vectors = await asyncio.get_event_loop().run_in_executor(
                None,
                self.embedder.encode_query,
                query
            )

            logger.info(
                f"[VisualRecall] Query encoded: '{query}' → "
                f"multi-vector shape={query_vectors.shape}"
            )

            # 执行视觉检索（真正的异步）
            results = await asyncio.wait_for(
                vector_store.colpali_search(
                    query_vectors=query_vectors,
                    filter_conditions=filters,
                    limit=top_k
                ),
                timeout=self.timeout_ms / 1000.0
            )

            logger.info(f"[VisualRecall] Retrieved {len(results)} visual chunks")

            # 转换为 ChunkResult
            chunk_results = []
            for result in results:
                payload = result["payload"]
                chunk_results.append(
                    ChunkResult(
                        chunk_id=payload.get("chunk_id", 0),
                        document_id=payload.get("doc_id", 0),  # 修正字段名
                        content=payload.get("text", ""),
                        score=result["score"],
                        # 文档信息
                        document_title=payload.get("document_title"),
                        standard_no=payload.get("standard_no"),
                        doc_type=payload.get("doc_type"),
                        category=payload.get("category"),
                        voltage_level=payload.get("voltage_level"),
                        # 位置信息
                        page_start=payload.get("page_number"),
                        # 内容类型
                        content_type=payload.get("content_type", "image_description"),
                        # 召回来源
                        recall_source="visual",
                        # 图片信息
                        image_page=payload.get("page_number"),
                        image_figure_number=payload.get("figure_number")
                    )
                )

            return chunk_results

        except asyncio.TimeoutError:
            logger.warning(
                f"[VisualRecall] Search timeout after {self.timeout_ms}ms, "
                "returning empty results"
            )
            return []

        except Exception as e:
            logger.error(f"[VisualRecall] Search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def batch_search(
        self,
        queries: List[str],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = None
    ) -> List[List[ChunkResult]]:
        """
        批量视觉召回检索

        Args:
            queries: 查询文本列表
            filters: 共享的过滤条件
            top_k: 每个查询的召回数量

        Returns:
            每个查询的 ChunkResult 列表
        """
        tasks = [
            self.search(query=q, filters=filters, top_k=top_k)
            for q in queries
        ]
        return await asyncio.gather(*tasks)


# 全局实例（懒加载）
visual_recall = VisualRecall()
