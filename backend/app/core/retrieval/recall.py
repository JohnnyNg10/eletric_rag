"""
召回层 (Recall Layer)

三路并行召回：
1. 向量召回 (Vector Recall) - Qdrant 混合检索
2. 关键词召回 (Keyword Recall) - Elasticsearch BM25
3. 结构化召回 (Structured Recall) - MySQL 精确查询
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import asyncio
import logging
import re
import time

from app.db.models import Document, Chunk
from app.schemas.retrieval import ChunkResult
from app.storage.vector_store import VectorStore
from app.storage.search_engine import SearchEngine
from app.core.embedding.embedder import Embedder

logger = logging.getLogger(__name__)


class VectorRecall:
    """向量召回（Qdrant 混合检索）"""

    def __init__(self):
        self.vector_store = VectorStore()
        self.embedder = Embedder()

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 20
    ) -> List[ChunkResult]:
        """
        向量召回

        Args:
            query: 查询文本
            filters: 元数据过滤条件
            top_k: 返回数量

        Returns:
            List[ChunkResult]: 召回的文档块
        """
        try:
            logger.info(f"[VectorRecall] query='{query}', top_k={top_k}")

            # 生成查询向量
            dense_vector = self.embedder.encode(query)  # 稠密向量
            sparse_vector = self.embedder.encode_sparse(query)  # 稀疏向量

            # 构建 Qdrant 过滤条件
            qdrant_filter = self._build_qdrant_filter(filters)

            # 构建 filter_conditions 字典（VectorStore 需要的格式）
            filter_conditions = None
            if qdrant_filter:
                # 将 Filter 对象转换为 dict 格式
                filter_conditions = self._filter_to_dict(qdrant_filter)

            # 混合检索（稠密 + 稀疏向量 RRF 融合）
            results = self.vector_store.hybrid_search(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                filter_conditions=filter_conditions,
                limit=top_k
            )

            # 转换为 ChunkResult
            chunk_results = []
            for result_dict in results:
                payload = result_dict['payload']
                chunk_result = ChunkResult(
                    chunk_id=int(payload.get('chunk_id', 0)),
                    document_id=int(payload.get('doc_id', 0)),
                    content=payload.get('text', ''),
                    score=result_dict['score'],
                    # 文档信息
                    document_title=payload.get('document_title'),
                    standard_no=payload.get('standard_no'),
                    doc_type=payload.get('doc_type'),
                    category=payload.get('category'),
                    voltage_level=payload.get('voltage_level'),
                    # 位置信息
                    clause=payload.get('clause'),
                    chapter=payload.get('chapter'),
                    section=payload.get('section'),
                    page_start=payload.get('page_start'),
                    page_end=payload.get('page_end'),
                    # 召回来源
                    recall_source="vector"
                )
                chunk_results.append(chunk_result)

            logger.info(f"[VectorRecall] Found {len(chunk_results)} results")
            return chunk_results

        except Exception as e:
            logger.error(f"[VectorRecall] Error: {e}", exc_info=True)
            return []

    def _build_qdrant_filter(self, filters: Dict[str, Any]):
        """
        构建 Qdrant 过滤条件（返回 Filter 对象）

        注意：VectorStore.hybrid_search 需要 dict 格式，
        所以这里返回的 Filter 会被 _filter_to_dict() 转换
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        if not filters:
            return None

        conditions = []

        # 文档类型过滤
        if 'doc_type' in filters:
            conditions.append(
                FieldCondition(key="doc_type", match=MatchValue(value=filters['doc_type']))
            )

        # 专业分类过滤
        if 'category' in filters:
            conditions.append(
                FieldCondition(key="category", match=MatchValue(value=filters['category']))
            )

        # 电压等级过滤
        if 'voltage_level' in filters:
            conditions.append(
                FieldCondition(key="voltage_level", match=MatchValue(value=filters['voltage_level']))
            )

        # 标准号过滤
        if 'standard_no' in filters:
            conditions.append(
                FieldCondition(key="standard_no", match=MatchValue(value=filters['standard_no']))
            )

        if conditions:
            return Filter(must=conditions)

        return None

    def _filter_to_dict(self, qdrant_filter) -> Dict[str, Any]:
        """
        将 Qdrant Filter 对象转换为 dict 格式

        VectorStore.hybrid_search 期望的格式:
        {
            "must": [
                {"key": "doc_type", "match": {"value": "standard"}},
                ...
            ]
        }
        """
        if not qdrant_filter or not qdrant_filter.must:
            return {}

        result = {"must": []}

        for condition in qdrant_filter.must:
            cond_dict = {
                "key": condition.key,
                "match": {}
            }

            # 提取 match 值
            if hasattr(condition.match, 'value'):
                cond_dict["match"]["value"] = condition.match.value
            elif hasattr(condition.match, 'any'):
                cond_dict["match"]["any"] = condition.match.any

            result["must"].append(cond_dict)

        return result


class KeywordRecall:
    """关键词召回（Elasticsearch BM25）"""

    def __init__(self):
        self.search_engine = SearchEngine()

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 20
    ) -> List[ChunkResult]:
        """
        关键词召回

        Args:
            query: 查询文本
            filters: 元数据过滤条件
            top_k: 返回数量

        Returns:
            List[ChunkResult]: 召回的文档块
        """
        try:
            logger.info(f"[KeywordRecall] query='{query}', top_k={top_k}")

            # 构建 ES 查询
            es_query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text^2", "clause^1.5"],
                                    "type": "best_fields",
                                    "operator": "or"
                                }
                            }
                        ],
                        "filter": self._build_es_filter(filters)
                    }
                },
                "size": top_k
            }

            # 执行搜索
            import json
            logger.info(f"[KeywordRecall] About to execute ES query")
            logger.info(f"[KeywordRecall] Query JSON: {json.dumps(es_query, ensure_ascii=False)}")
            results = self.search_engine.search(es_query)
            logger.info(f"[KeywordRecall] ES returned {len(results)} raw results")

            # 转换为 ChunkResult
            chunk_results = []
            for hit in results:
                source = hit.get('_source', {})
                chunk_id = source.get('chunk_id', 0)

                # 检查 chunk_id 类型
                if isinstance(chunk_id, str):
                    chunk_id = int(chunk_id) if chunk_id.isdigit() else 0

                doc_id = source.get('doc_id', 0)
                if isinstance(doc_id, str):
                    doc_id = int(doc_id) if doc_id.isdigit() else 0

                chunk_result = ChunkResult(
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    content=source.get('text', ''),
                    score=hit.get('_score', 0.0),
                    # 文档信息
                    standard_no=source.get('standard_no'),
                    category=source.get('category'),
                    voltage_level=source.get('voltage_level'),
                    # 位置信息
                    clause=source.get('clause'),
                    # 召回来源
                    recall_source="keyword"
                )
                chunk_results.append(chunk_result)

            logger.info(f"[KeywordRecall] Found {len(chunk_results)} results")
            return chunk_results

        except Exception as e:
            logger.error(f"[KeywordRecall] Error: {e}", exc_info=True)
            return []

    def _build_es_filter(self, filters: Dict[str, Any]) -> List[Dict]:
        """构建 ES 过滤条件"""
        es_filters = []

        # 文档类型过滤
        if 'doc_type' in filters:
            es_filters.append({"term": {"doc_type": filters['doc_type']}})

        # 专业分类过滤
        if 'category' in filters:
            es_filters.append({"term": {"category": filters['category']}})

        # 电压等级过滤
        if 'voltage_level' in filters:
            es_filters.append({"term": {"voltage_level": filters['voltage_level']}})

        # 标准号过滤
        if 'standard_no' in filters:
            es_filters.append({"term": {"standard_no": filters['standard_no']}})

        return es_filters


class StructuredRecall:
    """结构化召回（MySQL 精确查询）"""

    def __init__(self, db: Session):
        self.db = db

    async def search(
        self,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 10
    ) -> List[ChunkResult]:
        """
        结构化召回

        Args:
            query: 查询文本
            filters: 元数据过滤条件
            top_k: 返回数量

        Returns:
            List[ChunkResult]: 召回的文档块
        """
        logger.info(f"[StructuredRecall] query='{query}', filters={filters}, top_k={top_k}")

        # 提取查询中的结构化信息
        standard_no = self._extract_standard_no(query)
        clause_no = self._extract_clause_no(query)

        # 优先级1: 精确标准号 + 条款号
        if standard_no and clause_no:
            results = self._search_by_standard_and_clause(standard_no, clause_no, filters, top_k)
            if results:
                logger.info(f"[StructuredRecall] Found {len(results)} results by standard+clause")
                return results

        # 优先级2: 精确标准号
        if standard_no:
            results = self._search_by_standard(standard_no, filters, top_k)
            if results:
                logger.info(f"[StructuredRecall] Found {len(results)} results by standard")
                return results

        # 优先级3: 精确条款号
        if clause_no:
            results = self._search_by_clause(clause_no, filters, top_k)
            if results:
                logger.info(f"[StructuredRecall] Found {len(results)} results by clause")
                return results

        # 优先级4: 元数据组合查询
        results = self._search_by_metadata(filters, top_k)
        logger.info(f"[StructuredRecall] Found {len(results)} results by metadata")
        return results

    def _extract_standard_no(self, query: str) -> Optional[str]:
        """从查询中提取标准号"""
        patterns = [
            r'(GB(?:/T)?\s*\d+(?:-\d+)?)',
            r'(DL(?:/T)?\s*\d+(?:-\d+)?)',
            r'(NB(?:/T)?\s*\d+(?:-\d+)?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                standard_no = match.group(1)
                standard_no = re.sub(r'\s+', ' ', standard_no).strip()
                return standard_no

        return None

    def _extract_clause_no(self, query: str) -> Optional[str]:
        """从查询中提取条款号"""
        patterns = [
            r'第?(\d+(?:\.\d+)+)条?',
        ]

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1)

        return None

    def _search_by_standard_and_clause(
        self,
        standard_no: str,
        clause_no: str,
        filters: Dict[str, Any],
        top_k: int
    ) -> List[ChunkResult]:
        """精确标准号 + 条款号查询"""
        try:
            query = self.db.query(Chunk, Document).join(
                Document, Chunk.document_id == Document.id
            ).filter(
                Document.standard_no.like(f'{standard_no}%'),
                Chunk.clause == clause_no,
                Document.status == 'valid'
            )

            query = self._apply_filters(query, filters)
            query = query.order_by(Chunk.position_in_doc).limit(top_k)
            results = query.all()

            return [
                self._to_chunk_result(chunk, doc, 1.0)
                for chunk, doc in results
            ]

        except Exception as e:
            logger.error(f"[StructuredRecall] Error in standard+clause search: {e}")
            return []

    def _search_by_standard(
        self,
        standard_no: str,
        filters: Dict[str, Any],
        top_k: int
    ) -> List[ChunkResult]:
        """精确标准号查询"""
        try:
            query = self.db.query(Chunk, Document).join(
                Document, Chunk.document_id == Document.id
            ).filter(
                Document.standard_no.like(f'{standard_no}%'),
                Document.status == 'valid'
            )

            query = self._apply_filters(query, filters)
            query = query.order_by(Chunk.position_in_doc).limit(top_k)
            results = query.all()

            return [
                self._to_chunk_result(chunk, doc, 0.9)
                for chunk, doc in results
            ]

        except Exception as e:
            logger.error(f"[StructuredRecall] Error in standard search: {e}")
            return []

    def _search_by_clause(
        self,
        clause_no: str,
        filters: Dict[str, Any],
        top_k: int
    ) -> List[ChunkResult]:
        """精确条款号查询"""
        try:
            query = self.db.query(Chunk, Document).join(
                Document, Chunk.document_id == Document.id
            ).filter(
                Chunk.clause == clause_no,
                Document.status == 'valid'
            )

            query = self._apply_filters(query, filters)
            query = query.order_by(
                desc(Document.reference_count),
                Chunk.position_in_doc
            ).limit(top_k)
            results = query.all()

            return [
                self._to_chunk_result(chunk, doc, 0.85)
                for chunk, doc in results
            ]

        except Exception as e:
            logger.error(f"[StructuredRecall] Error in clause search: {e}")
            return []

    def _search_by_metadata(
        self,
        filters: Dict[str, Any],
        top_k: int
    ) -> List[ChunkResult]:
        """元数据组合查询"""
        try:
            query = self.db.query(Chunk, Document).join(
                Document, Chunk.document_id == Document.id
            ).filter(
                Document.status == 'valid'
            )

            query = self._apply_filters(query, filters)
            query = query.order_by(
                desc(Document.reference_count),
                Chunk.position_in_doc
            ).limit(top_k)
            results = query.all()

            return [
                self._to_chunk_result(chunk, doc, 0.7)
                for chunk, doc in results
            ]

        except Exception as e:
            logger.error(f"[StructuredRecall] Error in metadata search: {e}")
            return []

    def _apply_filters(self, query, filters: Dict[str, Any]):
        """应用元数据过滤条件"""
        if not filters:
            return query

        if 'doc_type' in filters:
            query = query.filter(Document.doc_type == filters['doc_type'])

        if 'category' in filters:
            query = query.filter(Document.category == filters['category'])

        if 'voltage_level' in filters:
            query = query.filter(Document.voltage_level == filters['voltage_level'])

        if 'standard_no' in filters:
            query = query.filter(Document.standard_no == filters['standard_no'])

        return query

    def _to_chunk_result(
        self,
        chunk: Chunk,
        document: Document,
        base_score: float
    ) -> ChunkResult:
        """将 Chunk + Document 转换为 ChunkResult"""
        return ChunkResult(
            chunk_id=chunk.id,
            document_id=document.id,
            content=chunk.content,
            score=base_score,
            document_title=document.title,
            standard_no=document.standard_no,
            doc_type=document.doc_type,
            category=document.category,
            voltage_level=document.voltage_level,
            clause=chunk.clause,
            chapter=chunk.chapter,
            section=chunk.section,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            recall_source="structured"
        )


class MultiPathRecall:
    """三路并行召回"""

    def __init__(self, db: Session):
        self.vector_recall = VectorRecall()
        self.keyword_recall = KeywordRecall()
        self.structured_recall = StructuredRecall(db)

    async def recall(
        self,
        query: str,
        filters: Dict[str, Any],
        expanded_queries: Optional[List[str]] = None
    ) -> List[ChunkResult]:
        """
        三路并行召回

        Args:
            query: 标准化后的查询
            filters: 元数据过滤条件
            expanded_queries: 扩展查询列表（快车道生成）

        Returns:
            List[ChunkResult]: 去重后的 Top50 文档块
        """
        start_time = time.time()
        logger.info(f"[MultiPathRecall] query='{query}', filters={filters}")

        # 步骤1: 三路并行召回
        vector_task = self.vector_recall.search(query, filters, top_k=20)
        keyword_task = self.keyword_recall.search(query, filters, top_k=20)
        structured_task = self.structured_recall.search(query, filters, top_k=10)

        # 等待所有任务完成
        vector_chunks, keyword_chunks, structured_chunks = await asyncio.gather(
            vector_task, keyword_task, structured_task
        )

        # 步骤2: 合并去重（按 chunk_id）
        all_chunks = self._merge_deduplicate([
            vector_chunks,
            keyword_chunks,
            structured_chunks
        ])

        # 步骤3: 保留召回来源信息（用于后续分析）
        chunk_id_to_sources = {}
        for chunk in vector_chunks:
            chunk_id_to_sources.setdefault(chunk.chunk_id, []).append("vector")
        for chunk in keyword_chunks:
            chunk_id_to_sources.setdefault(chunk.chunk_id, []).append("keyword")
        for chunk in structured_chunks:
            chunk_id_to_sources.setdefault(chunk.chunk_id, []).append("structured")

        for chunk in all_chunks:
            chunk.recall_sources = chunk_id_to_sources.get(chunk.chunk_id, [])

        # 步骤4: 返回 Top50
        final_chunks = all_chunks[:50]

        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"[MultiPathRecall] Completed in {elapsed_ms}ms | "
            f"vector={len(vector_chunks)}, keyword={len(keyword_chunks)}, "
            f"structured={len(structured_chunks)} → merged={len(all_chunks)} → top50={len(final_chunks)}"
        )

        return final_chunks

    def _merge_deduplicate(self, chunk_lists: List[List[ChunkResult]]) -> List[ChunkResult]:
        """
        合并去重

        策略：
        - 按 chunk_id 去重
        - 保留分数最高的副本
        - 按综合分数排序
        """
        chunk_map = {}

        for chunks in chunk_lists:
            for chunk in chunks:
                if chunk.chunk_id not in chunk_map:
                    chunk_map[chunk.chunk_id] = chunk
                else:
                    # 保留分数更高的副本
                    if chunk.score > chunk_map[chunk.chunk_id].score:
                        chunk_map[chunk.chunk_id] = chunk

        # 按分数排序
        merged_chunks = sorted(
            chunk_map.values(),
            key=lambda c: c.score,
            reverse=True
        )

        return merged_chunks
