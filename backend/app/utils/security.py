"""
Security utilities: JWT token, password hashing
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from jose import JWTError, jwt
import bcrypt

from app.config import settings

logger = logging.getLogger(__name__)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码

    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码

    Returns:
        bool: 密码是否匹配
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    生成密码哈希

    Args:
        password: 明文密码

    Returns:
        str: 哈希后的密码
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问令牌 (Access Token)

    Args:
        data: 要编码的数据 (通常包含 sub: user_id)
        expires_delta: 过期时间增量，默认使用配置中的值

    Returns:
        str: JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "type": "access"
    })

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    创建刷新令牌 (Refresh Token)

    Args:
        data: 要编码的数据 (通常包含 sub: user_id)

    Returns:
        str: JWT refresh token
    """
    to_encode = data.copy()

    # Refresh token 有效期 7 天
    expire = datetime.utcnow() + timedelta(days=7)

    to_encode.update({
        "exp": expire,
        "type": "refresh"
    })

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码并验证 JWT token

    Args:
        token: JWT token 字符串

    Returns:
        Optional[Dict]: 解码后的 payload，失败返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"Token decode failed: {e}")
        return None


def verify_token_type(payload: Dict[str, Any], expected_type: str) -> bool:
    """
    验证 token 类型

    Args:
        payload: 解码后的 token payload
        expected_type: 期望的类型 (access/refresh)

    Returns:
        bool: 类型是否匹配
    """
    return payload.get("type") == expected_type
