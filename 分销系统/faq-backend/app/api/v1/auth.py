"""Authentication APIs for WeChat mini program login."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_rate_limit, get_client_ip
from app.core.logging import get_logger
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.storage import StorageService
from app.services.wechat import get_user_phone_number, get_wechat_session

logger = get_logger(__name__)
router = APIRouter(tags=["auth"])


def mask_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}****{digits[-4:]}"


def get_full_avatar_url(request: Request, avatar_url: str | None) -> str:
    return StorageService.build_avatar_access_url(avatar_url, str(request.base_url).rstrip("/"))


class LoginRequest(BaseModel):
    code: str


class LoginPhoneRequest(BaseModel):
    login_code: str
    phone_code: str


class LoginPasswordRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


def build_login_user_payload(request: Request, user: User) -> dict:
    return {
        "id": user.id,
        "phone": user.phone,
        "nickname": user.nickname,
        "avatar_url": get_full_avatar_url(request, user.avatar_url),
        "total_score": user.total_score,
        "correct_count": user.correct_count,
        "total_count": user.total_count,
        "real_name": user.real_name,
        "province": user.province,
        "company": user.company,
        "profile_verified": bool(user.profile_verified),
        "bidding_whitelisted": bool(user.bidding_whitelisted),
        "recognition_role": user.recognition_role,
        "recognition_score": user.recognition_score or 0,
    }


def password_matches(expected_password: str, submitted_password: str) -> bool:
    return secrets.compare_digest(
        str(expected_password or "").encode("utf-8"),
        str(submitted_password or "").encode("utf-8"),
    )


@router.post("/auth/login")
async def wechat_login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        enforce_rate_limit("auth_login", get_client_ip(request), limit=20, window_seconds=300)

        wechat_result = await get_wechat_session(login_data.code)
        openid = wechat_result.openid

        result = await db.execute(select(User).where(User.openid == openid))
        user = result.scalar_one_or_none()

        if not user:
            logger.info("openid_not_found", openid=openid[:8])
            return {
                "code": 1002,
                "message": "用户未注册",
                "detail": "请先点击手机号快捷登录进行身份验证",
            }

        logger.info("user_login", user_id=user.id, openid=openid[:8])
        token = create_access_token(subject=user.id)

        return {
            "code": 0,
            "data": {
                "token": token,
                "user": {
                    "id": user.id,
                    "nickname": user.nickname,
                    "avatar_url": get_full_avatar_url(request, user.avatar_url),
                    "total_score": user.total_score,
                    "correct_count": user.correct_count,
                    "total_count": user.total_count,
                    "real_name": user.real_name,
                    "province": user.province,
                    "company": user.company,
                    "profile_verified": bool(user.profile_verified),
                    "bidding_whitelisted": bool(user.bidding_whitelisted),
                    "recognition_role": user.recognition_role,
                    "recognition_score": user.recognition_score or 0,
                },
            },
        }
    except ValueError as e:
        logger.error("login_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("login_error", error=str(e))
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")


@router.post("/auth/login_phone")
async def wechat_login_phone(
    request: Request,
    login_data: LoginPhoneRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        enforce_rate_limit("auth_login_phone", get_client_ip(request), limit=12, window_seconds=300)

        wechat_result = await get_wechat_session(login_data.login_code)
        openid = wechat_result.openid
        phone = await get_user_phone_number(login_data.phone_code)

        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning("unauthorized_login_attempt", phone=mask_phone(phone), openid=openid[:8])
            return {
                "code": 1001,
                "message": "未授权用户",
                "detail": "您不在授权分销商名单内，无法使用本系统。请联系管理员添加您的手机号。",
            }

        # If this WeChat account is already bound to another record, prefer the bound record
        # instead of crashing on the unique openid constraint during rebind.
        openid_result = await db.execute(select(User).where(User.openid == openid))
        openid_user = openid_result.scalar_one_or_none()
        if openid_user and openid_user.id != user.id:
            logger.warning(
                "openid_phone_conflict",
                openid=openid[:8],
                phone=mask_phone(phone),
                whitelist_user_id=user.id,
                bound_user_id=openid_user.id,
            )
            user = openid_user

        if user.openid != openid:
            old_openid = user.openid or ""
            user.openid = openid
            logger.info(
                "openid_bound_to_imported_user",
                user_id=user.id,
                phone=mask_phone(phone),
                old_openid=old_openid[:8],
            )

        await db.flush()

        token = create_access_token(subject=user.id)
        return {
            "code": 0,
            "data": {
                "token": token,
                "user": {
                    "id": user.id,
                    "phone": user.phone,
                    "nickname": user.nickname,
                    "avatar_url": get_full_avatar_url(request, user.avatar_url),
                    "total_score": user.total_score,
                    "correct_count": user.correct_count,
                    "total_count": user.total_count,
                    "real_name": user.real_name,
                    "province": user.province,
                    "company": user.company,
                    "profile_verified": bool(user.profile_verified),
                    "bidding_whitelisted": bool(user.bidding_whitelisted),
                    "recognition_role": user.recognition_role,
                    "recognition_score": user.recognition_score or 0,
                },
            },
        }
    except ValueError as e:
        logger.error("login_phone_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("login_phone_error", error=str(e))
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")


@router.post("/auth/login_password")
async def password_login(
    request: Request,
    login_data: LoginPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        enforce_rate_limit("auth_login_password", get_client_ip(request), limit=20, window_seconds=300)

        username = login_data.username.strip()
        password = login_data.password
        if not username or not password:
            return {
                "code": 1005,
                "message": "账号或密码错误",
                "detail": "请确认账号和密码后重试",
            }

        result = await db.execute(select(User).where(User.login_username == username))
        user = result.scalar_one_or_none()

        expected_password = user.login_password if user else ""
        if not user or not expected_password or not password_matches(expected_password, password):
            logger.warning("password_login_failed", username=username)
            return {
                "code": 1005,
                "message": "账号或密码错误",
                "detail": "请确认账号和密码后重试",
            }

        token = create_access_token(subject=user.id)
        return {
            "code": 0,
            "data": {
                "token": token,
                "user": build_login_user_payload(request, user),
            },
        }
    except Exception as e:
        logger.exception("password_login_error", error=str(e))
        raise HTTPException(status_code=500, detail="登录失败，请稍后重试")
