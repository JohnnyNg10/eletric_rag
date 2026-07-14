"""
子块扩展层 (Child Chunk Expander)

功能：
1. 批量获取父块关联的子块（避免 N+1 查询）
2. 优先使用 Qdrant 已存储的向量，缺失时才重新计算
3. 用查询向量对子块做相似度计算
4. 过滤低相关子块
5. 返回"父块 + 高相关子块"的混合结果
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
import numpy as np
import logging

from app.db.models import Chunk
from app.schemas.retrieval import ChunkResult, ExpandedChunkResult
from app.core.embedding.embedder import get_embedder
from app.storage.cache import get_cache_manager
from app.storage.vector_store import VectorStore
from app.config import settings

logger = logging.getLogger(__name__)


class ChildChunkExpander:
    """子块扩展器"""

    def __init__(self, db: Session):
        self.db = db
        self.embedder = get_embedder()
        self.cache = get_cache_manager()
        self.vector_store = VectorStore()

    async def expand(
        self,
        parent_chunks: List[ChunkResult],
        query: str,
        similarity_threshold: Optional[float] = None,
        max_children_per_parent: Optional[int] = None
    ) -> List[ExpandedChunkResult]:
        """
        扩展父块的子块

        Args:
            parent_chunks: 重排后的父块列表
            query: 用户查询
            similarity_threshold: 子块相似度阈值（低于此值的子块不返回）
            max_children_per_parent: 每个父块最多保留的子块数

        Returns:
            List[ExpandedChunkResult]: 包含父块和高相关子块的结果
        """
        if not settings.CHILD_EXPANSION_ENABLED:
            logger.info("[ChildExpander] Child expansion disabled")
            return [ExpandedChunkResult(parent=p, relevant_children=[]) for p in parent_chunks]

        if not parent_chunks:
            return []

        # 使用配置中的默认值
        similarity_threshold = similarity_threshold or settings.CHILD_SIMILARITY_THRESHOLD
        max_children_per_parent = max_children_per_parent or settings.MAX_CHILDREN_PER_PARENT

        # 生成查询向量（用于计算子块相似度）
        query_vector = self.embedder.encode(query)

        # 批量获取所有父块的子块（一次查询，避免 N+1）
        parent_ids = [p.chunk_id for p in parent_chunks]
        children_map = self._get_children_batch(parent_ids)

        # 收集所有子块用于批量向量获取
        all_children = [child for children_list in children_map.values()
                        for child in children_list]

        if not all_children:
            logger.info("[ChildExpander] No children found for any parent")
            return [ExpandedChunkResult(parent=p, relevant_children=[])
                    for p in parent_chunks]

        # 优先从 Qdrant 获取已存储的向量，减少重复计算
        child_vectors = await self._get_child_vectors_batch(all_children)

        # 处理每个父块
        results = []
        total_children = 0
        filtered_children = 0
        cache_hits = 0

        for parent in parent_chunks:
            children = children_map.get(parent.chunk_id, [])
            if not children:
                results.append(ExpandedChunkResult(
                    parent=parent,
                    relevant_children=[]
                ))
                continue

            total_children += len(children)

            # 计算子块相似度
            child_scores = []
            for child in children:
                child_vector = child_vectors.get(child.id)
                if child_vector is None:
                    logger.warning(f"No vector for child {child.id}, skipping")
                    continue

                if child_vector.get('from_cache'):
                    cache_hits += 1

                # 余弦相似度
                similarity = float(np.dot(query_vector, child_vector['vector']))
                child_scores.append((child, similarity))

            # 过滤 + 排序
            relevant_children = [
                (child, score) for child, score in child_scores
                if score >= similarity_threshold
            ]
            relevant_children.sort(key=lambda x: x[1], reverse=True)

            # 限制数量
            relevant_children = relevant_children[:max_children_per_parent]
            filtered_children += len(relevant_children)

            # 转换为 ChunkResult
            child_results = [
                self._to_chunk_result(child, score, parent)
                for child, score in relevant_children
            ]

            results.append(ExpandedChunkResult(
                parent=parent,
                relevant_children=child_results,
                expansion_stats={
                    'total_children': len(children),
                    'filtered_children': len(child_results),
                    'avg_score': float(np.mean([s for _, s in relevant_children])) if relevant_children else 0.0
                }
            ))

        # 监控指标
        cache_hit_rate = cache_hits / total_children if total_children > 0 else 0
        logger.info(
            f"[ChildExpander] Stats: parents={len(parent_chunks)}, "
            f"total_children={total_children}, filtered_children={filtered_children}, "
            f"avg_children_per_parent={filtered_children / len(parent_chunks):.1f}, "
            f"cache_hit_rate={cache_hit_rate:.2%}"
        )

        return results

    def _get_children_batch(self, parent_ids: List[int]) -> Dict[int, List[Chunk]]:
        """
        批量获取多个父块的子块（避免 N+1 查询）

        Args:
            parent_ids: 父块 ID 列表

        Returns:
            Dict[parent_id, List[Chunk]]: 父块 ID → 子块列表的映射
        """
        if not parent_ids:
            return {}

        try:
            children = (self.db.query(Chunk)
                        .filter(Chunk.parent_chunk_id.in_(parent_ids),
                                Chunk.chunk_type == 'child')
                        .order_by(Chunk.parent_chunk_id, Chunk.position_in_doc)
                        .all())

            # 按父块 ID 分组
            result = {}
            for child in children:
                result.setdefault(child.parent_chunk_id, []).append(child)

            logger.info(f"[ChildExpander] Fetched {len(children)} children for {len(parent_ids)} parents")
            return result

        except Exception as e:
            logger.error(f"Failed to batch get children: {e}", exc_info=True)
            return {}

    async def _get_child_vectors_batch(
        self,
        children: List[Chunk]
    ) -> Dict[int, Dict[str, any]]:
        """
        批量获取子块向量（优先缓存 → Qdrant → 重新计算）

        Args:
            children: 子块列表

        Returns:
            Dict[chunk_id, {'vector': np.ndarray, 'from_cache': bool}]
        """
        result = {}

        # 第一步：从缓存获取
        children_need_fetch = []
        for child in children:
            # 使用 chunk_id 作为缓存键，避免内容冲突
            cached_vector = self.cache.get_dense_by_id(child.id)
            if cached_vector is not None:
                result[child.id] = {'vector': cached_vector, 'from_cache': True}
            else:
                children_need_fetch.append(child)

        if not children_need_fetch:
            return result

        # 第二步：从 Qdrant 获取已存储的向量
        children_with_vector_id = [c for c in children_need_fetch if c.vector_id]
        children_need_compute = [c for c in children_need_fetch if not c.vector_id]

        if children_with_vector_id:
            stored_vectors = await self._batch_get_vectors_from_qdrant(children_with_vector_id)
            for child_id, vector in stored_vectors.items():
                result[child_id] = {'vector': vector, 'from_cache': False}
                # 写入缓存供后续使用
                self.cache.set_dense_by_id(child_id, vector)

        # 第三步：批量计算缺失的向量
        if children_need_compute:
            contents = [c.content for c in children_need_compute]
            new_vectors = self.embedder.encode_batch(contents)
            for child, vector in zip(children_need_compute, new_vectors):
                result[child.id] = {'vector': vector, 'from_cache': False}
                # 写入缓存
                self.cache.set_dense_by_id(child.id, vector)

        return result

    async def _batch_get_vectors_from_qdrant(
        self,
        children: List[Chunk]
    ) -> Dict[int, np.ndarray]:
        """
        从 Qdrant 批量获取子块向量

        Args:
            children: 有 vector_id 的子块列表

        Returns:
            Dict[chunk_id, vector]
        """
        try:
            vector_ids = [c.vector_id for c in children]
            points = self.vector_store.client.retrieve(
                collection_name=settings.QDRANT_COLLECTION,
                ids=vector_ids,
                with_vectors=True
            )

            result = {}
            id_to_chunk = {c.vector_id: c for c in children}

            for point in points:
                chunk = id_to_chunk.get(point.id)
                if chunk and point.vector:
                    # Qdrant 返回的 vector 可能是 dict (稠密+稀疏)，取 dense
                    if isinstance(point.vector, dict):
                        vector = np.array(point.vector.get('dense', []), dtype=np.float32)
                    else:
                        vector = np.array(point.vector, dtype=np.float32)
                    result[chunk.id] = vector

            logger.info(f"[ChildExpander] Fetched {len(result)} vectors from Qdrant")
            return result

        except Exception as e:
            logger.error(f"Failed to batch get vectors from Qdrant: {e}", exc_info=True)
            return {}

    def _to_chunk_result(
        self,
        chunk: Chunk,
        score: float,
        parent: ChunkResult
    ) -> ChunkResult:
        """将 Chunk 转换为 ChunkResult"""
        return ChunkResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.content,
            score=score,
            # 继承父块的文档信息
            document_title=parent.document_title,
            standard_no=parent.standard_no,
            doc_type=parent.doc_type,
            category=parent.category,
            voltage_level=parent.voltage_level,
            clause=chunk.clause,
            chapter=chunk.chapter,
            section=chunk.section,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            recall_source="child_expanded"
        )
