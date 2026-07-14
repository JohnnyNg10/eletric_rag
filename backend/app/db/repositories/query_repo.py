"""
查询日志 Repository
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.models import QueryLog


class QueryLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 5,
    ) -> List[Dict[str, str]]:
        """
        按 conversation_id 查最近 limit 轮已完成的对话。

        QueryLog 在请求结束时写入，因此加载历史时不存在读到当前请求自身的风险。

        Returns:
            [{"query": ..., "answer": ...}, ...]，按 created_at 升序（旧→新）
        """
        stmt = (
            select(QueryLog.query, QueryLog.answer)
            .where(
                QueryLog.conversation_id == conversation_id,
                QueryLog.answer.isnot(None),
            )
            .order_by(QueryLog.created_at.desc(), QueryLog.id.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [{"query": r.query, "answer": r.answer} for r in reversed(rows)]

    def get_conversations_list(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[Dict], int]:
        """
        获取用户的会话列表

        Args:
            user_id: 用户ID
            page: 页码（从1开始）
            page_size: 每页条数

        Returns:
            tuple[List[Dict], int]: (会话列表, 总数)
        """
        from sqlalchemy import func

        # 主查询：获取会话统计信息
        conversations_query = (
            self.db.query(
                QueryLog.conversation_id,
                func.count(QueryLog.id).label('message_count'),
                func.max(QueryLog.created_at).label('last_message_at'),
                func.min(QueryLog.created_at).label('created_at')
            )
            .filter(
                QueryLog.user_id == user_id,
                QueryLog.conversation_id.isnot(None)
            )
            .group_by(QueryLog.conversation_id)
            .order_by(func.max(QueryLog.created_at).desc())
        )

        # 总数
        total = conversations_query.count()

        # 分页
        offset = (page - 1) * page_size
        conversations = conversations_query.offset(offset).limit(page_size).all()

        # 获取每个会话的第一条query作为标题
        result = []
        for conv in conversations:
            first_log = (
                self.db.query(QueryLog)
                .filter(
                    QueryLog.conversation_id == conv.conversation_id,
                    QueryLog.user_id == user_id
                )
                .order_by(QueryLog.created_at.asc(), QueryLog.id.asc())
                .first()
            )

            title = first_log.query[:50] if first_log and first_log.query else "未命名会话"
            if first_log and first_log.query and len(first_log.query) > 50:
                title += "..."

            result.append({
                "conversation_id": conv.conversation_id,
                "title": title,
                "message_count": conv.message_count,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
            })

        return result, total
