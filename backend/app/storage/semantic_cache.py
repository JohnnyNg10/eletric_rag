"""
语义缓存实现

基于向量相似度的查询结果缓存，相比传统 md5 精确匹配，能够命中语义相似的查询。
"""
import json
import time
from typing import Dict, List, Optional, Any, NamedTuple
from uuid import uuid4
import hashlib
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.config import settings


class SemanticCacheResult(NamedTuple):
    """语义缓存命中结果"""
    answer: str
    citations: List[Dict]
    recall_results: List[Dict]
    rerank_results: List[Dict]
    similarity_score: float
    cached_at: float


class SemanticCache:
    """语义缓存，使用向量相似度检索缓存结果"""

    COLLECTION = "semantic_query_cache"
    DEFAULT_TTL = 21600  # 6小时（秒）

    def __init__(self, qdrant_client: QdrantClient, embedding_dim: int = 1024, similarity_threshold: float = 0.95):
        """
        初始化语义缓存

        Args:
            qdrant_client: Qdrant 客户端实例
            embedding_dim: 向量维度（与 bge-large-zh-v1.5 一致）
            similarity_threshold: 余弦相似度阈值（0-1）
        """
        self.client = qdrant_client
        self.embedding_dim = embedding_dim
        self.similarity_threshold = similarity_threshold
        self._ensure_collection()

    def _ensure_collection(self):
        """确保语义缓存 collection 存在"""
        try:
            collections = self.client.get_collections().collections
            if not any(c.name == self.COLLECTION for c in collections):
                self.client.create_collection(
                    collection_name=self.COLLECTION,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
        except Exception as e:
            # 集合已存在或创建失败，不阻塞主流程
            print(f"[SemanticCache] Collection 初始化警告: {e}")

    def _build_filters_hash(self, filters: Dict[str, Any]) -> str:
        """构建过滤条件的哈希值"""
        # 排序后序列化，确保一致性
        filter_str = json.dumps(filters, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(filter_str.encode()).hexdigest()

    def lookup(
        self,
        query_embedding: np.ndarray,
        filters: Dict[str, Any],
        query_text: str,  # 用于日志
    ) -> Optional[SemanticCacheResult]:
        """
        查找语义相似的缓存结果

        Args:
            query_embedding: 查询的向量表示（已归一化）
            filters: 过滤条件（必须完全一致才能命中）
            query_text: 查询文本（用于日志）

        Returns:
            SemanticCacheResult 如果命中，否则 None
        """
        try:
            filters_hash = self._build_filters_hash(filters)

            # 在 Qdrant 中搜索相似查询，且过滤条件哈希必须匹配
            results = self.client.query_points(
                collection_name=self.COLLECTION,
                query=query_embedding.tolist(),
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="filters_hash",
                            match=MatchValue(value=filters_hash),
                        )
                    ]
                ),
                limit=1,
                score_threshold=self.similarity_threshold,
                with_payload=True,
            ).points

            if not results:
                return None

            hit = results[0]
            payload = hit.payload

            # 检查 TTL
            created_at = payload.get("created_at", 0)
            if time.time() - created_at > self.DEFAULT_TTL:
                # 缓存过期，不返回（后台清理由 Qdrant TTL 或定期任务处理）
                return None

            return SemanticCacheResult(
                answer=payload.get("answer", ""),
                citations=payload.get("citations", []),
                recall_results=payload.get("recall_results", []),
                rerank_results=payload.get("rerank_results", []),
                similarity_score=hit.score,
                cached_at=created_at,
            )

        except Exception as e:
            # 缓存查找失败不阻塞主流程
            print(f"[SemanticCache] lookup 失败: {e}")
            return None

    def store(
        self,
        query_text: str,
        query_embedding: np.ndarray,
        filters: Dict[str, Any],
        recall_results: List[Dict],
        rerank_results: List[Dict],
        answer: str,
        citations: List[Dict],
    ):
        """
        存储查询结果到语义缓存

        Args:
            query_text: 原始查询文本
            query_embedding: 查询的向量表示
            filters: 过滤条件
            recall_results: 召回结果列表（字典格式）
            rerank_results: 重排后结果列表（字典格式）
            answer: 生成的答案
            citations: 引用列表
        """
        try:
            filters_hash = self._build_filters_hash(filters)

            point = PointStruct(
                id=str(uuid4()),
                vector=query_embedding.tolist(),
                payload={
                    "query_text": query_text,  # 存储原始查询用于调试
                    "filters_hash": filters_hash,
                    "filters": filters,  # 存储原始过滤条件用于调试
                    "recall_results": recall_results,
                    "rerank_results": rerank_results,
                    "answer": answer,
                    "citations": citations,
                    "created_at": time.time(),
                }
            )

            self.client.upsert(
                collection_name=self.COLLECTION,
                points=[point],
            )

        except Exception as e:
            # 缓存存储失败不阻塞主流程
            print(f"[SemanticCache] store 失败: {e}")

    def clear(self):
        """清空所有缓存（用于测试或维护）"""
        try:
            self.client.delete_collection(collection_name=self.COLLECTION)
            self._ensure_collection()
        except Exception as e:
            print(f"[SemanticCache] clear 失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            collection_info = self.client.get_collection(collection_name=self.COLLECTION)
            return {
                "total_entries": collection_info.points_count,
                "vector_dim": self.embedding_dim,
                "similarity_threshold": self.similarity_threshold,
                "ttl_seconds": self.DEFAULT_TTL,
            }
        except Exception as e:
            return {"error": str(e)}


# ────────────────────────────────────────────────────────────────────
# 全局单例管理
# ────────────────────────────────────────────────────────────────────

_semantic_cache_instance: Optional[SemanticCache] = None


def get_semantic_cache_manager(similarity_threshold: float = 0.95) -> SemanticCache:
    """
    获取语义缓存管理器单例

    Args:
        similarity_threshold: 相似度阈值（0-1）

    Returns:
        SemanticCache 实例
    """
    global _semantic_cache_instance

    if _semantic_cache_instance is None:
        from qdrant_client import QdrantClient
        qdrant_client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=30,
        )
        _semantic_cache_instance = SemanticCache(
            qdrant_client=qdrant_client,
            embedding_dim=1024,  # bge-large-zh-v1.5 的维度
            similarity_threshold=similarity_threshold
        )

    return _semantic_cache_instance

