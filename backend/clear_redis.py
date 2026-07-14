"""Clear Redis cache"""
import redis

# 连接 Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# 清空所有缓存
r.flushall()
print("Redis cache cleared successfully")

# 验证
keys = r.keys('*')
print(f"Remaining keys: {len(keys)}")
