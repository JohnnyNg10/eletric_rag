"""
查询接口 - 接入层

实现 POST /api/v1/query 接口
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
import time
import logging

from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    Citation,
    OptimizeQueryRequest,
    OptimizeQueryResponse,
    OptimizationOption
)
from app.services.query_service import QueryService
from app.api.deps import get_current_user
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化查询服务
query_service = QueryService()


@router.post("/", response_model=QueryResponse, summary="执行查询")
async def execute_query(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    执行查询（核心接口）

    流程：
    1. 接入层：参数验证、鉴权（API层）
    2. 服务层：业务编排（QueryService）
       - 调用预处理层
       - 调用路由层
       - 调用召回/重排层
       - 调用生成层
    3. 返回结果

    当前实现：API层 + 服务层 + 预处理层 + 模拟响应
    """
    try:
        logger.info(f"[User {current_user.id}] Query: {request.query}")

        # 调用服务层执行查询
        result = await query_service.execute_query(
            query=request.query,
            user_id=current_user.id,
            conversation_id=request.conversation_id,
            filters=request.filters
        )

        # 如果需要澄清，返回400错误
        if result['status'] == 'need_clarification':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "需要澄清查询",
                    "strategy": "clarify",
                    "vagueness_score": result['vagueness_score'],
                    "options": result['clarification_options']
                }
            )

        # 构建成功响应
        response = QueryResponse(
            answer=result['answer'],
            citations=[Citation(**c) for c in result.get('citations', [])],
            lane=result['lane'],
            retrieval_time=result['retrieval_time'],
            generation_time=result['generation_time'],
            expanded_queries=result['expanded_queries'],
            query_log_id=result['query_log_id']
        )

        logger.info(f"[User {current_user.id}] Query completed")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[User {current_user.id}] Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}"
        )


@router.post("/optimize", response_model=OptimizeQueryResponse, summary="提问优化")
async def optimize_query(
    request: OptimizeQueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    提问优化接口

    评估查询笼统度并生成澄清选项

    用途：
    - 在用户输入时提供实时反馈
    - 帮助用户优化提问
    """
    try:
        logger.info(f"[User {current_user.id}] Optimize query: {request.query}")

        # 调用预处理层的优化服务
        preprocessing_input = PreprocessingInput(
            query=request.query,
            user_context={'user_id': current_user.id},
            enable_optimization=True,
            enable_expansion=False  # 不需要扩展
        )

        preprocessing_output = await preprocessing_service.preprocess(preprocessing_input)

        # 构建响应
        response = OptimizeQueryResponse(
            strategy=preprocessing_output.status,
            vagueness_score=preprocessing_output.vagueness_score,
            options=[
                OptimizationOption(**opt)
                for opt in (preprocessing_output.clarification_options or [])
            ]
        )

        return response

    except Exception as e:
        logger.error(f"[User {current_user.id}] Optimize failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"优化失败: {str(e)}"
        )
