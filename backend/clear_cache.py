"""清除 Redis 缓存"""
import redis
from app.config import settings

def clear_cache():
    """清除所有 Redis 缓存"""
    try:
        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )

        # 清除所有缓存
        r.flushdb()
        print("Redis cache cleared")

        # 显示统计
        info = r.info('stats')
        print(f"Current key count: {r.dbsize()}")

    except Exception as e:
        print(f"Failed to clear cache: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    clear_cache()
