"""
Authentication endpoints: login, refresh, logout
"""
from datetime import datetime
from typing import Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db.session import get_db
from app.db.models import User
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, RefreshResponse
from app.utils.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token_type
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    获取当前登录用户信息

    需要认证
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
        "query_count": current_user.query_count,
        "last_login_at": current_user.last_login_at
    }


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录

    - 验证用户名密码
    - 返回 access_token 和 refresh_token
    """
    # 查询用户
    user = db.query(User).filter(User.username == request.username).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证密码
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否激活
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    # 生成 token
    token_data = {"sub": str(user.id), "username": user.username, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # 更新最后登录时间
    from datetime import datetime
    user.last_login_at = datetime.utcnow()
    db.commit()

    logger.info(f"User {user.username} logged in successfully")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        }
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(request: RefreshRequest):
    """
    刷新访问令牌

    - 使用 refresh_token 获取新的 access_token
    """
    # 解码 refresh token
    payload = decode_token(request.refresh_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 验证 token 类型
    if not verify_token_type(payload, "refresh"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 类型错误，需要 refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 生成新的 access token
    user_id = payload.get("sub")
    username = payload.get("username")
    role = payload.get("role")

    token_data = {"sub": user_id, "username": username, "role": role}
    access_token = create_access_token(token_data)

    logger.info(f"Access token refreshed for user {username}")

    return RefreshResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """
    用户登出

    - 将 token 加入黑名单（需要 Redis）
    - 如果 Redis 不可用，降级为客户端丢弃 token
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "")

    # 尝试将 token 加入 Redis 黑名单
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)

        # 解码 token 获取过期时间
        payload = decode_token(token)
        if payload:
            exp = payload.get("exp")
            if exp:
                from datetime import datetime
                ttl = int(exp - datetime.utcnow().timestamp())
                if ttl > 0:
                    # 将 token 加入黑名单，TTL 为剩余过期时间
                    r.setex(f"blacklist:{token}", ttl, "1")
                    logger.info(f"Token added to blacklist")

        return {"code": 0, "message": "登出成功"}

    except Exception as e:
        # Redis 不可用时降级处理
        logger.warning(f"Redis unavailable for logout, fallback to client-side: {e}")
        return {
            "code": 0,
            "message": "登出成功（请在客户端清除 token）"
        }
