"""
查询接口 - 接入层

POST   /api/v1/query                       执行查询（主接口）
POST   /api/v1/query/optimize              提问优化（笼统度评估 + 澄清选项）
POST   /api/v1/query/{query_log_id}/feedback  提交用户反馈
GET    /api/v1/query/history               查询历史（分页）
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional
from sqlalchemy.orm import Session
import logging

from app.schemas.query import (
    QueryRequest,
    QueryResponse,
    Citation,
    OptimizeQueryRequest,
    OptimizeQueryResponse,
    OptimizationOption,
    FeedbackRequest,
    FeedbackResponse,
    QueryHistoryItem,
    QueryHistoryResponse,
)
from app.services.query_service import QueryService
from app.core.preprocessing.query_optimizer import QueryOptimizer
from app.api.deps import get_current_user
from app.db.models import User, QueryLog
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# 每个请求创建一个新实例（无状态），避免并发污染
def _get_optimizer() -> QueryOptimizer:
    return QueryOptimizer()


@router.post("/", response_model=QueryResponse, summary="执行查询")
async def execute_query(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    执行完整的 RAG 查询流程。

    正常返回 status="success" 并携带答案和引用。
    当查询过于笼统时返回 status="need_clarification" 并携带澄清选项，
    前端可展示选项让用户二次输入，然后以 refined_query 字段重新调用本接口。
    """
    try:
        logger.info(f"[User {current_user.id}] Query: {request.query!r}")

        query_service = QueryService(db=db)
        result = await query_service.execute_query(
            query=request.query,
            user_id=current_user.id,
            conversation_id=request.conversation_id,
            filters=request.filters,
            refined_query=request.refined_query,
            selected_option_id=request.selected_option_id,
            clarification_context=request.clarification_context
        )

        # 需要澄清：200 + status=need_clarification
        if result['status'] == 'need_clarification':
            raw_options = result.get('clarification_options') or []
            options = [
                OptimizationOption(
                    id=opt.id if hasattr(opt, 'id') else (opt.get('id', i + 1)),
                    label=opt.label if hasattr(opt, 'label') else opt.get('label', ''),
                    refined_query=opt.refined_query if hasattr(opt, 'refined_query') else opt.get('refined_query', ''),
                    standard_preview=opt.standard_preview if hasattr(opt, 'standard_preview') else opt.get('standard_preview'),
                    doc_count=opt.doc_count if hasattr(opt, 'doc_count') else opt.get('doc_count', 0),
                )
                for i, opt in enumerate(raw_options)
            ]
            return QueryResponse(
                status="need_clarification",
                vagueness_score=result.get('vagueness_score'),
                clarification_options=options,
            )

        # 正常返回：映射 citations 字段
        citations = [
            Citation(
                index=c.get('index', i + 1),
                chunk_id=c.get('chunk_id', 0),
                standard_no=c.get('standard_no'),
                clause=c.get('clause'),
                content_snippet=c.get('content_snippet', ''),
                document_title=c.get('document_title'),
            )
            for i, c in enumerate(result.get('citations') or [])
        ]

        return QueryResponse(
            status="success",
            answer=result.get('answer', ''),
            citations=citations,
            lane=result.get('lane', ''),
            retrieval_time=result.get('retrieval_time', 0),
            generation_time=result.get('generation_time', 0),
            expanded_queries=result.get('expanded_queries') or [],
            query_log_id=result.get('query_log_id', 0),
        )

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
    独立的提问优化接口。

    用于前端输入框实时提示：评估查询笼统度，返回策略和澄清选项。
    调用方无需触发完整检索，只评估 + 生成选项。
    """
    try:
        logger.info(f"[User {current_user.id}] Optimize query: {request.query!r}")

        optimizer = _get_optimizer()
        result = await optimizer.optimize(request.query)

        options = [
            OptimizationOption(
                id=opt.id,
                label=opt.label,
                refined_query=opt.refined_query,
                standard_preview=opt.standard_preview,
                doc_count=opt.doc_count,
            )
            for opt in result.options
        ]

        return OptimizeQueryResponse(
            strategy=result.strategy,
            vagueness_score=result.vagueness_score,
            options=options,
        )

    except Exception as e:
        logger.error(f"[User {current_user.id}] Optimize failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"优化失败: {str(e)}"
        )


@router.post("/{query_log_id}/feedback", response_model=FeedbackResponse, summary="提交查询反馈")
async def submit_feedback(
    query_log_id: int,
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    对某次查询结果提交评分和文字反馈（1-5分）。

    只允许提交自己查询的反馈。
    """
    query_log = db.query(QueryLog).filter(QueryLog.id == query_log_id).first()

    if query_log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="查询记录不存在")

    if query_log.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作此记录")

    query_log.feedback_score = request.feedback_score
    query_log.feedback_text = request.feedback_text
    db.commit()

    logger.info(
        f"[User {current_user.id}] Feedback submitted: query_log_id={query_log_id}, "
        f"score={request.feedback_score}"
    )

    return FeedbackResponse(
        query_log_id=query_log_id,
        feedback_score=request.feedback_score,
    )


@router.get("/history", response_model=QueryHistoryResponse, summary="查询历史")
async def get_query_history(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    conversation_id: Optional[str] = Query(default=None, description="会话ID过滤"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    分页获取当前用户的查询历史。

    按创建时间倒序排列。可按 conversation_id 过滤。
    """
    base_query = (
        db.query(QueryLog)
        .filter(QueryLog.user_id == current_user.id)
    )

    if conversation_id:
        base_query = base_query.filter(QueryLog.conversation_id == conversation_id)

    total = base_query.count()

    logs = (
        base_query
        .order_by(QueryLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        QueryHistoryItem(
            query_log_id=log.id,
            query=log.query,
            answer=log.answer,
            lane=log.lane,
            total_time=log.total_time,
            feedback_score=log.feedback_score,
            created_at=log.created_at.isoformat() if log.created_at else "",
        )
        for log in logs
    ]

    return QueryHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )
