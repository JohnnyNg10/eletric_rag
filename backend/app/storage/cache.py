"""
多级 Redis 缓存管理器

四级缓存架构：
  L1 Embedding 缓存 (24h) — 向量化结果
  L2 召回缓存    (6h)  — 三路召回结果
  L3 重排缓存    (4h)  — 重排后结果
  L4 生成缓存    (2h)  — LLM 生成答案
"""
import base64
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import redis

from app.config import settings

logger = logging.getLogger(__name__)


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class CacheManager:
    """四级缓存管理器"""

    def __init__(self):
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD or None,
                decode_responses=False,  # 二进制模式，便于存储 bytes
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        return self._client

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_raw(self, key: str) -> Optional[bytes]:
        try:
            return self.client.get(key)
        except Exception as e:
            logger.warning(f"[Cache] GET failed key={key}: {e}")
            return None

    def _set_raw(self, key: str, value: bytes, ttl: int) -> bool:
        try:
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"[Cache] SET failed key={key}: {e}")
            return False

    def _get_json(self, key: str) -> Optional[Any]:
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.warning(f"[Cache] JSON decode failed key={key}: {e}")
            return None

    def _set_json(self, key: str, value: Any, ttl: int) -> bool:
        try:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            return self._set_raw(key, data, ttl)
        except Exception as e:
            logger.warning(f"[Cache] JSON encode failed key={key}: {e}")
            return False

    # ------------------------------------------------------------------
    # L1：Embedding 缓存
    # ------------------------------------------------------------------

    def get_dense(self, text: str) -> Optional[np.ndarray]:
        """获取稠密向量缓存"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return None
        key = f"embedding:dense:{_md5(text)}"
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            decoded = base64.b64decode(raw)
            return np.frombuffer(decoded, dtype=np.float32).copy()
        except Exception as e:
            logger.warning(f"[Cache] Dense decode failed: {e}")
            return None

    def set_dense(self, text: str, vector: np.ndarray) -> bool:
        """写入稠密向量缓存"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return False
        key = f"embedding:dense:{_md5(text)}"
        encoded = base64.b64encode(vector.astype(np.float32).tobytes())
        return self._set_raw(key, encoded, settings.CACHE_EMBEDDING_TTL)

    def get_sparse(self, text: str) -> Optional[Dict]:
        """获取稀疏向量缓存"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return None
        key = f"embedding:sparse:{_md5(text)}"
        return self._get_json(key)

    def set_sparse(self, text: str, sparse_vec: Dict) -> bool:
        """写入稀疏向量缓存"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return False
        key = f"embedding:sparse:{_md5(text)}"
        return self._set_json(key, sparse_vec, settings.CACHE_EMBEDDING_TTL)

    def get_dense_by_id(self, chunk_id: int) -> Optional[np.ndarray]:
        """通过 chunk_id 获取稠密向量缓存（避免内容冲突）"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return None
        key = f"embedding:dense:id:{chunk_id}"
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            decoded = base64.b64decode(raw)
            return np.frombuffer(decoded, dtype=np.float32).copy()
        except Exception as e:
            logger.warning(f"[Cache] Dense decode failed for chunk_id={chunk_id}: {e}")
            return None

    def set_dense_by_id(self, chunk_id: int, vector: np.ndarray) -> bool:
        """通过 chunk_id 写入稠密向量缓存"""
        if not settings.CACHE_EMBEDDING_ENABLED:
            return False
        key = f"embedding:dense:id:{chunk_id}"
        encoded = base64.b64encode(vector.astype(np.float32).tobytes())
        return self._set_raw(key, encoded, settings.CACHE_EMBEDDING_TTL)

    # ------------------------------------------------------------------
    # L2：召回缓存
    # ------------------------------------------------------------------

    def get_recall(self, query: str, filters: Dict, hyde_enabled: bool = False) -> Optional[List[Dict]]:
        """获取召回缓存"""
        if not settings.CACHE_RECALL_ENABLED:
            return None
        key = self._recall_key(query, filters, hyde_enabled)
        return self._get_json(key)

    def set_recall(self, query: str, filters: Dict, chunks: List[Dict], hyde_enabled: bool = False) -> bool:
        """写入召回缓存"""
        if not settings.CACHE_RECALL_ENABLED:
            return False
        key = self._recall_key(query, filters, hyde_enabled)
        return self._set_json(key, chunks, settings.CACHE_RECALL_TTL)

    def _recall_key(self, query: str, filters: Dict, hyde_enabled: bool = False) -> str:
        raw = query + "|" + json.dumps(filters, sort_keys=True, ensure_ascii=False) + f"|hyde={hyde_enabled}"
        return f"recall:{_md5(raw)}"

    # ------------------------------------------------------------------
    # L3：重排缓存
    # ------------------------------------------------------------------

    def get_rerank(
        self,
        query: str,
        chunk_ids: List[int],
        stage: str = "two_stage",
        top_k: int = 5,
        model_version: str = "default",
    ) -> Optional[List[Dict]]:
        """获取重排缓存"""
        if not settings.CACHE_RERANK_ENABLED:
            return None
        key = self._rerank_key(query, chunk_ids, stage, top_k, model_version)
        return self._get_json(key)

    def set_rerank(
        self,
        query: str,
        chunk_ids: List[int],
        results: List[Dict],
        stage: str = "two_stage",
        top_k: int = 5,
        model_version: str = "default",
    ) -> bool:
        """写入重排缓存"""
        if not settings.CACHE_RERANK_ENABLED:
            return False
        key = self._rerank_key(query, chunk_ids, stage, top_k, model_version)
        return self._set_json(key, results, settings.CACHE_RERANK_TTL)

    def _rerank_key(
        self,
        query: str,
        chunk_ids: List[int],
        stage: str,
        top_k: int,
        model_version: str,
    ) -> str:
        raw = query + "|" + stage + "|" + str(top_k) + "|" + model_version + "|" + str(sorted(chunk_ids))
        return f"rerank:{_md5(raw)}"

    # ------------------------------------------------------------------
    # L4：生成缓存
    # ------------------------------------------------------------------

    def get_generation(self, query: str, chunk_contents: List[str], conversation_id: Optional[str] = None) -> Optional[Dict]:
        """获取生成缓存（多轮对话时跳过缓存）"""
        if not settings.CACHE_GENERATION_ENABLED:
            return None
        if conversation_id:
            return None
        key = self._generation_key(query, chunk_contents)
        return self._get_json(key)

    def set_generation(self, query: str, chunk_contents: List[str], result: Dict, conversation_id: Optional[str] = None) -> bool:
        """写入生成缓存（多轮对话时跳过缓存）"""
        if not settings.CACHE_GENERATION_ENABLED:
            return False
        if conversation_id:
            return False
        key = self._generation_key(query, chunk_contents)
        return self._set_json(key, result, settings.CACHE_GENERATION_TTL)

    def _generation_key(self, query: str, chunk_contents: List[str]) -> str:
        raw = query + "|" + "".join(chunk_contents)
        return f"generation:{_md5(raw)}"

    # ------------------------------------------------------------------
    # 主动失效
    # ------------------------------------------------------------------

    def invalidate_recall_and_generation(self) -> int:
        """文档更新后批量清除 L2/L3/L4 缓存（L1 Embedding 不需清除）"""
        count = 0
        try:
            for pattern in ("recall:*", "rerank:*", "generation:*"):
                cursor = 0
                while True:
                    cursor, keys = self.client.scan(cursor, match=pattern, count=200)
                    if keys:
                        self.client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
        except Exception as e:
            logger.error(f"[Cache] Invalidate failed: {e}")
        logger.info(f"[Cache] Invalidated {count} recall/rerank/generation entries")
        return count

    def invalidate_all(self) -> int:
        """清除所有四级缓存（含 Embedding）"""
        count = 0
        try:
            for pattern in ("embedding:*", "recall:*", "rerank:*", "generation:*"):
                cursor = 0
                while True:
                    cursor, keys = self.client.scan(cursor, match=pattern, count=200)
                    if keys:
                        self.client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
        except Exception as e:
            logger.error(f"[Cache] Invalidate all failed: {e}")
        return count

    # ------------------------------------------------------------------
    # 兼容旧接口（供其他模块继续使用）
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        return self._get_json(key)

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        return self._set_json(key, value, ttl)

    def delete(self, key: str) -> bool:
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"[Cache] DELETE failed key={key}: {e}")
            return False

    def exists(self, key: str) -> bool:
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.warning(f"[Cache] EXISTS failed key={key}: {e}")
            return False


# 全局单例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# 向后兼容
cache = get_cache_manager()
