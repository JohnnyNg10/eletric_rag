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
