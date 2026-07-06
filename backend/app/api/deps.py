"""
Dependencies for API endpoints
"""
from typing import Optional
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.db.models import User
from app.utils.security import decode_token, verify_token_type

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    获取当前登录用户

    通过 JWT token 验证并返回用户对象
    用于需要登录的接口

    Usage:
        @router.get("/me")
        async def get_me(current_user: User = Depends(get_current_user)):
            return current_user
    """
    token = credentials.credentials

    # 检查 token 是否在黑名单（已登出）
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        if r.exists(f"blacklist:{token}"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已失效（已登出）",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception as e:
        # Redis 不可用时跳过黑名单检查
        logger.debug(f"Redis blacklist check skipped: {e}")

    # 解码 token
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证 token 类型
    if not verify_token_type(payload, "access"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 类型错误，需要 access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 获取用户 ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少用户信息",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查询用户
    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    要求管理员权限

    用于需要 admin 角色的接口

    Usage:
        @router.delete("/documents/{doc_id}")
        async def delete_doc(
            doc_id: int,
            current_user: User = Depends(require_admin)
        ):
            # 只有 admin 能访问
            pass
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )

    return current_user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    获取当前用户（可选）

    如果提供了 token 则验证，否则返回 None
    用于「登录后有更多功能」的接口

    Usage:
        @router.get("/documents")
        async def list_docs(
            current_user: Optional[User] = Depends(get_current_user_optional)
        ):
            # 未登录也能访问，但登录后可能有更多功能
            pass
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
