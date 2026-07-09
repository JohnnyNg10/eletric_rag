"""
Elasticsearch 全文检索引擎客户端

支持：
- BM25 关键词检索
- 自定义分词器（ik_max_word）
- 多字段查询
- 短语匹配
"""
from typing import List, Dict, Optional, Any
from elasticsearch import Elasticsearch
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class SearchEngine:
    """Elasticsearch 搜索引擎封装"""

    def __init__(self):
        self.client = Elasticsearch(
            hosts=[f"http://{settings.ELASTICSEARCH_HOST}:{settings.ELASTICSEARCH_PORT}"],
            request_timeout=30
        )
        self.index_name = "documents"

    def create_index_if_not_exists(self):
        """创建索引（如果不存在）"""
        try:
            if self.client.indices.exists(index=self.index_name):
                logger.info(f"Index {self.index_name} already exists")
                return

            logger.info(f"Creating index: {self.index_name}")

            # 索引配置
            index_body = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1,
                    "analysis": {
                        "analyzer": {
                            "electric_analyzer": {
                                "type": "custom",
                                "tokenizer": "ik_max_word",
                                "filter": ["lowercase"]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "doc_id": {"type": "keyword"},
                        "chunk_id": {"type": "keyword"},
                        "chunk_type": {"type": "keyword"},
                        "text": {
                            "type": "text",
                            "analyzer": "electric_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "standard_no": {"type": "keyword"},
                        "clause": {"type": "keyword"},
                        "chapter": {"type": "keyword"},
                        "category": {"type": "keyword"},
                        "voltage_level": {"type": "keyword"},
                        "is_table": {"type": "boolean"},
                        "table_title": {"type": "keyword"},
                        "page_number": {"type": "integer"},
                        "importance_score": {"type": "float"},
                        "created_at": {"type": "date"}
                    }
                }
            }

            self.client.indices.create(index=self.index_name, body=index_body)
            logger.info(f"Index {self.index_name} created successfully")

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise

    def bulk_index(self, documents: List[Dict[str, Any]]) -> bool:
        """
        批量索引文档

        Args:
            documents: 文档列表，每个文档包含:
                - chunk_id: 块ID
                - doc_id: 文档ID
                - text: 文本内容
                - standard_no: 标准号
                - clause: 条款号
                - category: 分类
                - voltage_level: 电压等级
                - ...其他元数据

        Returns:
            bool: 是否成功
        """
        try:
            from elasticsearch.helpers import bulk

            # 构建批量操作
            actions = []
            for doc in documents:
                action = {
                    "_index": self.index_name,
                    "_id": doc["chunk_id"],
                    "_source": doc
                }
                actions.append(action)

            # 批量索引
            success, failed = bulk(self.client, actions, raise_on_error=False)
            logger.info(f"Bulk indexed: {success} succeeded, {len(failed)} failed")

            if failed:
                logger.error(f"Failed documents: {failed[:5]}")  # 只记录前5个失败

            return len(failed) == 0

        except Exception as e:
            logger.error(f"Bulk index failed: {e}")
            return False

    def bm25_search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        BM25 关键词检索

        Args:
            query: 查询字符串
            filters: 过滤条件 {"status": "valid", "voltage_level": "250V"}
            size: 返回结果数量

        Returns:
            检索结果列表
        """
        try:
            # 构建查询
            must_clauses = [
                {
                    "match": {
                        "text": {
                            "query": query,
                            "operator": "and"
                        }
                    }
                }
            ]

            # 构建过滤条件
            filter_clauses = []
            if filters:
                for key, value in filters.items():
                    filter_clauses.append({"term": {key: value}})

            search_body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses if filter_clauses else []
                    }
                },
                "size": size,
                "_source": ["doc_id", "chunk_id", "text", "clause", "standard_no"]
            }

            # 执行搜索
            response = self.client.search(index=self.index_name, body=search_body)

            # 转换结果
            results = []
            for hit in response["hits"]["hits"]:
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"]
                })

            return results

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def phrase_search(
        self,
        phrase: str,
        size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        短语精确匹配（用于标准号、条款号查询）

        Args:
            phrase: 短语（如 "GB 1002-2024"）
            size: 返回结果数量

        Returns:
            检索结果列表
        """
        try:
            search_body = {
                "query": {
                    "match_phrase": {
                        "text": phrase
                    }
                },
                "size": size
            }

            response = self.client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response["hits"]["hits"]:
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"]
                })

            return results

        except Exception as e:
            logger.error(f"Phrase search failed: {e}")
            return []

    def multi_field_search(
        self,
        query: str,
        fields: Optional[List[str]] = None,
        size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        多字段查询

        Args:
            query: 查询字符串
            fields: 查询字段列表（带权重），如 ["text^2", "clause_title^3"]
            size: 返回结果数量

        Returns:
            检索结果列表
        """
        try:
            if not fields:
                fields = ["text^2", "standard_no^3"]

            search_body = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": fields,
                        "type": "best_fields"
                    }
                },
                "size": size
            }

            response = self.client.search(index=self.index_name, body=search_body)

            results = []
            for hit in response["hits"]["hits"]:
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "source": hit["_source"]
                })

            return results

        except Exception as e:
            logger.error(f"Multi-field search failed: {e}")
            return []

    def delete_by_doc_id(self, doc_id: str) -> bool:
        """删除文档的所有子块"""
        try:
            query = {
                "query": {
                    "term": {
                        "doc_id": doc_id
                    }
                }
            }

            self.client.delete_by_query(index=self.index_name, body=query)
            logger.info(f"Deleted all chunks for doc_id: {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")
            return False

    def search(self, query_body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        通用搜索方法（接受完整的 ES 查询体）

        Args:
            query_body: Elasticsearch 查询体

        Returns:
            List[Dict]: 搜索结果（包含 _score 和 _source）
        """
        try:
            logger.info(f"[SearchEngine.search] Executing query on index '{self.index_name}'")
            logger.info(f"[SearchEngine.search] Query body: {query_body}")
            response = self.client.search(index=self.index_name, body=query_body)
            hits = response["hits"]["hits"]
            logger.info(f"[SearchEngine.search] Got {len(hits)} hits from ES")
            return hits

        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []

    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        try:
            stats = self.client.indices.stats(index=self.index_name)
            index_stats = stats["indices"][self.index_name]

            return {
                "index_name": self.index_name,
                "docs_count": index_stats["total"]["docs"]["count"],
                "docs_deleted": index_stats["total"]["docs"]["deleted"],
                "store_size": index_stats["total"]["store"]["size_in_bytes"]
            }

        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {}


# 全局实例
search_engine = SearchEngine()
