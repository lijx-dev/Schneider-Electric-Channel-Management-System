"""订阅消息授权接口

记录用户对"每周一答题提醒"订阅消息的一次性授权。
- POST /subscription/auth   : 记录授权并计算目标发送时间（最近下一个周一 09:00）
- GET  /subscription/status : 查询当前用户是否有待发送的授权（前端判断是否展示引导）
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.models.subscription import SubscriptionAuth
from app.models.user import User
from app.services.subscription_reminder_scheduler import BUSINESS_TIMEZONE, compute_target_send_at

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscription"])


class SubscriptionAuthRequest(BaseModel):
    template_id: Optional[str] = None
    auth_source: Optional[str] = None  # home(首页引导条) / quiz(答题完成页)


async def _latest_subscription_auth(db: AsyncSession, user_id: str) -> Optional[SubscriptionAuth]:
    stmt = (
        select(SubscriptionAuth)
        .where(SubscriptionAuth.user_id == user_id)
        .order_by(SubscriptionAuth.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/subscription/auth")
async def create_subscription_auth(
    request: Request,
    body: SubscriptionAuthRequest,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """记录用户对每周一答题提醒订阅的一次性授权（幂等）。"""
    try:
        result = await db.execute(select(User.openid).where(User.id == current_user_id))
        openid = result.scalar_one_or_none()

        if not openid:
            return {
                "code": 1002,
                "message": "用户不存在",
                "detail": "用户不存在，请重新登录",
            }

        # 防重复：已有待发送（waiting）的授权则幂等返回，不新增行
        latest = await _latest_subscription_auth(db, current_user_id)
        if latest and latest.status == "waiting":
            return {
                "code": 0,
                "data": {
                    "status": latest.status,
                    "target_send_at": latest.target_send_at.isoformat(),
                    "template_id": latest.template_id,
                    "has_pending": True,
                },
                "message": "已开启提醒，下周一 9:00 将通知您答题",
            }

        now_cst = datetime.now(BUSINESS_TIMEZONE)
        target = compute_target_send_at(now_cst)

        auth = SubscriptionAuth(
            user_id=current_user_id,
            openid=openid,
            status="waiting",
            target_send_at=target,
            template_id=body.template_id,
            auth_source=body.auth_source,
        )
        db.add(auth)
        await db.commit()
        await db.refresh(auth)

        return {
            "code": 0,
            "data": {
                "status": auth.status,
                "target_send_at": auth.target_send_at.isoformat(),
                "template_id": auth.template_id,
                "has_pending": True,
            },
            "message": "已开启提醒，下周一 9:00 将通知您答题",
        }
    except Exception as e:
        logger.exception("subscription_auth_error", error=str(e))
        raise HTTPException(status_code=500, detail="开启提醒失败，请稍后重试")


@router.get("/subscription/status")
async def get_subscription_status(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """查询当前用户最近的订阅授权状态，前端据此决定是否展示开启提醒引导。"""
    try:
        latest = await _latest_subscription_auth(db, current_user_id)

        if not latest:
            return {
                "code": 0,
                "data": {
                    "has_pending": False,
                    "status": None,
                    "target_send_at": None,
                    "send_at": None,
                },
                "message": "ok",
            }

        return {
            "code": 0,
            "data": {
                "has_pending": latest.status == "waiting",
                "status": latest.status,
                "target_send_at": (
                    latest.target_send_at.isoformat() if latest.target_send_at else None
                ),
                "send_at": latest.send_at.isoformat() if latest.send_at else None,
            },
            "message": "ok",
        }
    except Exception as e:
        logger.exception("subscription_status_error", error=str(e))
        raise HTTPException(status_code=500, detail="查询提醒状态失败，请稍后重试")