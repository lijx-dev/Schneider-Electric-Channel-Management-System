"""
安全模块 - JWT Token 处理

提供 Token 的签发和验证功能
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import jwt, JWTError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# JWT 算法
ALGORITHM = "HS256"


def create_access_token(
    subject: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建 JWT Access Token
    
    Args:
        subject: Token 主体（通常是 user_id）
        expires_delta: 过期时间增量，默认从配置读取
        
    Returns:
        JWT Token 字符串
    """
    now = datetime.now(timezone.utc)

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": now,
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """
    验证 JWT Token
    
    Args:
        token: JWT Token 字符串
        
    Returns:
        Token 中的 subject（user_id），验证失败返回 None
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        subject: str = payload.get("sub")
        if subject is None:
            logger.warning("token_invalid", reason="no_subject")
            return None
        return subject
    except JWTError as e:
        logger.warning("token_invalid", reason=str(e))
        return None


def decode_token(token: str) -> Optional[dict]:
    """
    解码 JWT Token（不验证过期）
    
    用于获取 Token 中的信息
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )
        return payload
    except JWTError:
        return None
