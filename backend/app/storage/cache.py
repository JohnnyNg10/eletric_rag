"""
Redis 缓存客户端
"""
from typing import Optional, Any
import redis
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class Cache:
    """Redis 缓存封装"""

    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """设置缓存"""
        try:
            self.client.setex(
                name=key,
                time=ttl,
                value=json.dumps(value, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.error(f"Cache set failed: {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete failed: {e}")
            return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists check failed: {e}")
            return False


# 全局实例
cache = Cache()
