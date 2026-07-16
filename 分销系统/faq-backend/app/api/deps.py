import time
from collections import deque
from threading import Lock
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
_rate_limit_lock = Lock()
_rate_limit_store: dict[str, deque[float]] = {}


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Resolve the current user from the Bearer token."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = verify_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    stmt = select(User.id).where(User.id == user_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=401, detail="User not found")

    return user_id


async def require_bidding_whitelist(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    校验当前用户是否在标书功能白名单中。
    非白名单用户返回 403。
    """
    stmt = select(User.bidding_whitelisted).where(User.id == user_id)
    result = await db.execute(stmt)
    whitelisted = result.scalar_one_or_none()

    if not whitelisted:
        raise HTTPException(
            status_code=403,
            detail="暂无使用权限，请联系管理员开通标书功能",
        )

    return user_id


def ensure_same_user(current_user_id: str, requested_user_id: Optional[str]) -> str:
    """Prevent horizontal privilege escalation when clients submit another user's ID."""
    if requested_user_id and requested_user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return current_user_id


def get_client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return "unknown"


def enforce_rate_limit(scope: str, key: str, limit: int, window_seconds: int) -> None:
    now = time.time()
    bucket_key = f"{scope}:{key}"

    with _rate_limit_lock:
        bucket = _rate_limit_store.setdefault(bucket_key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()

        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")

        bucket.append(now)
