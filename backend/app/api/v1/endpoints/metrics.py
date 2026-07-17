"""
指标监控接口
"""
from fastapi import APIRouter
from typing import Dict, Any

from app.storage.cache import get_cache_manager

router = APIRouter()


@router.get("/cache_stats", response_model=Dict[str, Any], summary="缓存统计")
async def get_cache_stats():
    """
    获取五级缓存的命中率统计

    返回格式：
    {
        "L1": {"hits": 100, "misses": 20, "total": 120, "hit_rate": 0.833},
        "L2": {"hits": 50, "misses": 10, "total": 60, "hit_rate": 0.833},
        ...
    }
    """
    cache = get_cache_manager()
    return cache.get_stats()
