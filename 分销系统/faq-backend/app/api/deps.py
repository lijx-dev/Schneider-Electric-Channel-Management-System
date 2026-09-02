import logging
import time
from collections import deque
from threading import Lock
from typing import List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.db.session import get_db
from app.models.user import User
from app.services.admin_auth import verify_admin_token

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)
_rate_limit_lock = Lock()
_rate_limit_store: dict[str, deque[float]] = {}


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Resolve the current user from the Bearer token.

    支持两种 token：
    1. 小程序用户 token（sub = user UUID，SECRET_KEY 签发）
    2. 后台管理员 token（sub = login_username，ADMIN_SECRET_KEY 签发）
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")

    # 先尝试小程序用户 token
    user_id = verify_token(credentials.credentials)
    if user_id:
        stmt = select(User.id).where(User.id == user_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            return user_id

    # 再尝试后台管理员 token
    admin_username = verify_admin_token(credentials.credentials)
    if admin_username:
        logger.info("auth_admin_token_decoded username=%s", admin_username)
        stmt = select(User.id).where(User.login_username == admin_username)
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            logger.info("auth_admin_token_success user_id=%s", row[:16])
            return row
        logger.warning("auth_admin_user_not_found username=%s", admin_username)
    else:
        logger.warning("auth_admin_token_verify_failed")

    raise HTTPException(status_code=401, detail="Could not validate credentials")


async def get_authenticated_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """轻量鉴权（不访问数据库）：仅校验 token 签名。

    与 get_current_user_id 安全强度等价 —— 小程序用户 token 用 SECRET_KEY
    签名、管理员 token 用 ADMIN_SECRET_KEY 签名，无法伪造；但不依赖 DB
    可用性，适合下载等纯读接口，避免被偶发数据库抖动拖垮。
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = verify_token(credentials.credentials)
    if user_id:
        return user_id

    admin_username = verify_admin_token(credentials.credentials)
    if admin_username:
        # 下载类接口无需真实 UUID，仅用于日志/标识
        return f"admin:{admin_username}"

    raise HTTPException(status_code=401, detail="Could not validate credentials")


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


# ── 认可计划角色校验依赖 ─────────────────────────────────────────────────────


async def require_recognition_access(
    allowed_roles: List[str],
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """校验用户角色是否在允许范围内."""
    result = await db.execute(select(User.recognition_role).where(User.id == user_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=401, detail="User not found")
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="无权访问此功能")
    return user_id


async def require_manager_role(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """校验经理角色."""
    return await require_recognition_access(["manager"], user_id, db)


async def require_sales_role(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """校验销售角色."""
    return await require_recognition_access(["sales"], user_id, db)


async def require_specialist_role(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """校验专员角色."""
    return await require_recognition_access(["specialist"], user_id, db)


async def require_specialist_or_manager(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> str:
    """校验专员或经理角色."""
    return await require_recognition_access(["specialist", "manager"], user_id, db)
