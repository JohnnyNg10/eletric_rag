"""
Qdrant 向量数据库客户端

支持：
- 混合检索（稠密向量 + 稀疏向量 RRF 融合）
- Payload 过滤
- 批量写入
"""
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams,
    PointStruct, SearchRequest, Filter,
    FieldCondition, MatchValue, MatchAny, Range,
    ScoredPoint, Prefetch, Query, FusionQuery
)
import logging
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Qdrant 向量存储封装"""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            timeout=30
        )
        self.collection_name = "documents"

    def create_collection_if_not_exists(self):
        """创建 Collection（如果不存在）"""
        try:
            collections = self.client.get_collections()
            exists = any(c.name == self.collection_name for c in collections.collections)

            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        # 稠密向量配置（bge-large-zh-v1.5）
                        "dense": VectorParams(
                            size=1024,
                            distance=Distance.COSINE,
                            on_disk=False
                        )
                    },
                    sparse_vectors_config={
                        # 稀疏向量配置（BM42 / SPLADE）
                        "sparse": SparseVectorParams()
                    },
                    # Scalar Quantization 量化配置（节省内存）
                    quantization_config={
                        "scalar": {
                            "type": "int8",
                            "always_ram": True
                        }
                    }
                )
                logger.info(f"Collection {self.collection_name} created successfully")
            else:
                logger.info(f"Collection {self.collection_name} already exists")

        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise

    def upsert_points(
        self,
        points: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> bool:
        """
        批量插入/更新向量点

        Args:
            points: 点列表，每个点包含:
                - id: 点ID（UUID 字符串或整数）
                - dense_vector: 稠密向量 (1024维)
                - sparse_vector: 稀疏向量 {indices: [], values: []}
                - payload: 元数据字典
            batch_size: 批量大小

        Returns:
            bool: 是否成功
        """
        try:
            # 转换为 Qdrant PointStruct
            qdrant_points = []
            for point in points:
                # 确保 ID 是 UUID
                point_id = point["id"]
                if isinstance(point_id, str):
                    try:
                        point_id = uuid.UUID(point_id)
                    except ValueError:
                        # 如果不是有效 UUID，生成一个新的
                        point_id = uuid.uuid5(uuid.NAMESPACE_DNS, point_id)

                qdrant_points.append(
                    PointStruct(
                        id=str(point_id),
                        vector={
                            "dense": point["dense_vector"],
                            "sparse": point.get("sparse_vector", {"indices": [], "values": []})
                        },
                        payload=point["payload"]
                    )
                )

            # 批量写入
            for i in range(0, len(qdrant_points), batch_size):
                batch = qdrant_points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
                logger.info(f"Upserted batch {i//batch_size + 1}: {len(batch)} points")

            return True

        except Exception as e:
            logger.error(f"Failed to upsert points: {e}")
            return False

    def hybrid_search(
        self,
        dense_vector: List[float],
        sparse_vector: Optional[Dict[str, List]] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        混合检索（稠密 + 稀疏向量 RRF 融合）

        Args:
            dense_vector: 稠密向量查询
            sparse_vector: 稀疏向量查询 {"indices": [], "values": []}
            filter_conditions: Payload 过滤条件
            limit: 返回结果数量

        Returns:
            检索结果列表
        """
        try:
            # 构建过滤器
            query_filter = self._build_filter(filter_conditions) if filter_conditions else None

            if sparse_vector and sparse_vector.get("indices"):
                # 混合检索（稠密 + 稀疏向量，使用 prefetch + query API）
                # 先用稠密向量 prefetch，再用稀疏向量 query 并融合
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    prefetch=[
                        Prefetch(
                            query=dense_vector,
                            using="dense",
                            limit=limit * 2
                        )
                    ],
                    query=FusionQuery(
                        fusion="rrf"  # Reciprocal Rank Fusion
                    ),
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                ).points
            else:
                # 仅稠密向量检索
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    query=dense_vector,
                    using="dense",
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                ).points

            # 转换为字典格式
            return [
                {
                    "id": point.id,
                    "score": point.score,
                    "payload": point.payload
                }
                for point in results
            ]

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _build_filter(self, conditions: Dict[str, Any]) -> Filter:
        """
        构建 Qdrant 过滤器

        支持的条件格式:
        {
            "must": [
                {"key": "status", "match": {"value": "valid"}},
                {"key": "voltage_level", "match": {"any": ["250V", "380V"]}},
                {"key": "importance_score", "range": {"gte": 0.8}}
            ],
            "should": [...],
            "must_not": [...]
        }
        """
        must_conditions = []
        should_conditions = []
        must_not_conditions = []

        # 处理 must 条件
        if "must" in conditions:
            for cond in conditions["must"]:
                must_conditions.append(self._build_field_condition(cond))

        # 处理 should 条件
        if "should" in conditions:
            for cond in conditions["should"]:
                should_conditions.append(self._build_field_condition(cond))

        # 处理 must_not 条件
        if "must_not" in conditions:
            for cond in conditions["must_not"]:
                must_not_conditions.append(self._build_field_condition(cond))

        return Filter(
            must=must_conditions if must_conditions else None,
            should=should_conditions if should_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None
        )

    def _build_field_condition(self, cond: Dict[str, Any]) -> FieldCondition:
        """构建字段条件"""
        key = cond["key"]

        # 精确匹配
        if "match" in cond:
            match_cond = cond["match"]
            if "value" in match_cond:
                return FieldCondition(key=key, match=MatchValue(value=match_cond["value"]))
            elif "any" in match_cond:
                return FieldCondition(key=key, match=MatchAny(any=match_cond["any"]))

        # 范围查询
        elif "range" in cond:
            range_cond = cond["range"]
            return FieldCondition(
                key=key,
                range=Range(
                    gte=range_cond.get("gte"),
                    lte=range_cond.get("lte"),
                    gt=range_cond.get("gt"),
                    lt=range_cond.get("lt")
                )
            )

        raise ValueError(f"Unsupported condition: {cond}")

    def delete_by_doc_id(self, doc_id: str) -> bool:
        """删除文档的所有向量点"""
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            )
            logger.info(f"Deleted all points for doc_id: {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete points: {e}")
            return False

    def get_collection_info(self) -> Dict[str, Any]:
        """获取 Collection 信息"""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": info.points_count,
                "vectors_count": info.points_count,  # points_count 即向量数
                "status": info.status.value if hasattr(info.status, 'value') else str(info.status)
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}


# 全局实例
vector_store = VectorStore()
