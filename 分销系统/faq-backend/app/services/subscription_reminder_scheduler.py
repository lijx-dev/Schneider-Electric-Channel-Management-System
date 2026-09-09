"""Background scheduler for weekly quiz reminder (subscription message)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.subscription import SubscriptionAuth
from app.services.wechat import send_subscribe_message

logger = get_logger(__name__)

_scheduler_task: Optional[asyncio.Task] = None
BUSINESS_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def compute_target_send_at(now: datetime) -> datetime:
    """计算授权之后最近的下一个周一 09:00（返回 CST 无时区 datetime）。

    规则：
    - 取授权时刻之后最近的周一 09:00；
    - 若目标已过（授权时刻在目标之后）→ 顺延一周；
    - 若距目标不足 2 小时（如周一 08:30 授权）→ 顺延一周，
      避免"刚授权立刻扣一条"且提醒无意义。
    """
    cst = now.astimezone(BUSINESS_TIMEZONE)
    days_until_monday = (0 - cst.weekday()) % 7  # Monday = 0
    target = (cst + timedelta(days=days_until_monday)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    if target <= cst:
        target += timedelta(days=7)
    if target - cst < timedelta(hours=2):
        target += timedelta(days=7)
    return target.replace(tzinfo=None)


def should_start_scheduler() -> bool:
    return bool(settings.ENABLE_SUBSCRIPTION_SCHEDULER)


def _build_template_data(send_time: datetime) -> dict:
    """构造订阅消息 data。字段对应后台模板 77696「分销商培训答题提醒」：
    thing1=答题事项、thing2=温馨提示，均为 thing 类型，value 不超过 20 字符。
    """
    return {
        "thing1": {"value": f"{send_time.month}月{send_time.day}日答题已开启"},
        "thing2": {"value": "完成答题可赢取能量奖励"},
    }


async def run_subscription_send_once() -> dict:
    """扫描到期（waiting 且 target_send_at<=now）的授权并发送，一次最多 batch 条。"""
    now_cst = datetime.now(BUSINESS_TIMEZONE)
    now_naive = now_cst.replace(tzinfo=None)

    stats = {"scanned": 0, "sent": 0, "failed": 0}

    async with AsyncSessionLocal() as session:
        stmt = (
            select(SubscriptionAuth)
            .where(
                SubscriptionAuth.status == "waiting",
                SubscriptionAuth.target_send_at <= now_naive,
            )
            .order_by(SubscriptionAuth.target_send_at.asc())
            .limit(settings.SUBSCRIPTION_SEND_BATCH_SIZE)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        stats["scanned"] = len(rows)

        for auth in rows:
            template_id = settings.SUBSCRIPTION_TEMPLATE_ID or auth.template_id
            try:
                await send_subscribe_message(
                    openid=auth.openid,
                    template_id=template_id,
                    page="pages/quiz/quiz",
                    data=_build_template_data(auth.target_send_at),
                    miniprogram_state=settings.SUBSCRIPTION_MINIPROGRAM_STATE,
                )
                auth.status = "sent"
                auth.send_at = now_naive
                auth.error_message = None
                stats["sent"] += 1
            except Exception as exc:
                logger.warning(
                    "subscription_send_failed",
                    user_id=auth.user_id[:8],
                    error=str(exc),
                )
                auth.status = "failed"
                auth.error_message = str(exc)[:500]
                stats["failed"] += 1

            await session.commit()

            if rows.index(auth) < len(rows) - 1:
                await asyncio.sleep(settings.SUBSCRIPTION_SEND_BETWEEN_SECONDS)

    logger.info("subscription_send_once", **stats)
    return stats


async def _scheduler_loop() -> None:
    interval = max(60, int(settings.SUBSCRIPTION_SEND_INTERVAL_SECONDS or 60))
    logger.info("subscription_scheduler_started", interval_seconds=interval)

    try:
        while True:
            try:
                await run_subscription_send_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("subscription_scheduler_failed", error=str(exc))

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("subscription_scheduler_stopped")
        raise


def start_subscription_scheduler() -> Optional[asyncio.Task]:
    global _scheduler_task

    if not should_start_scheduler():
        logger.info("subscription_scheduler_disabled")
        return None

    if _scheduler_task and not _scheduler_task.done():
        return _scheduler_task

    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="subscription-reminder-scheduler")
    return _scheduler_task


async def stop_subscription_scheduler() -> None:
    global _scheduler_task

    task = _scheduler_task
    _scheduler_task = None
    if not task or task.done():
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass