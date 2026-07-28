"""
API v1 router - 聚合所有 endpoints
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, query, metrics, document, admin

api_router = APIRouter()

# 认证路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 查询路由
api_router.include_router(query.router, prefix="/query", tags=["查询"])

# 监控路由
api_router.include_router(metrics.router, prefix="/metrics", tags=["监控"])

# 文档管理路由
api_router.include_router(document.router, prefix="/documents", tags=["文档管理"])

# 管理员路由
api_router.include_router(admin.router, prefix="/admin", tags=["管理员"])
