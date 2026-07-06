"""
Authentication schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str = Field(..., min_length=1)


class UserInfo(BaseModel):
    """用户基本信息"""
    id: int
    username: str
    email: str
    role: str
    full_name: Optional[str] = None


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


class RefreshResponse(BaseModel):
    """刷新 Token 响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
