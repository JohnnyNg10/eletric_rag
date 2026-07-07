"""
API v1 router - 聚合所有 endpoints
"""
from fastapi import APIRouter

from app.api.v1.endpoints import auth, query

api_router = APIRouter()

# 认证路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 查询路由
api_router.include_router(query.router, prefix="/query", tags=["查询"])

# 其他路由稍后添加
# api_router.include_router(documents.router, prefix="/documents", tags=["文档管理"])
