"""Background scheduler for monthly reward settlement."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.lottery import run_monthly_lottery
from app.services.monthly_leaderboard import settle_monthly_rewards

logger = get_logger(__name__)

_scheduler_task: Optional[asyncio.Task] = None
BUSINESS_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def business_today(now: datetime | None = None) -> date:
    current = now or datetime.now(BUSINESS_TIMEZONE)
    if current.tzinfo is None:
        current = current.replace(tzinfo=BUSINESS_TIMEZONE)
    return current.astimezone(BUSINESS_TIMEZONE).date()


def previous_month_key(today: date | None = None) -> str:
    current = today or business_today()
    first_day = current.replace(day=1)
    previous_month_day = first_day - timedelta(days=1)
    return previous_month_day.strftime("%Y-%m")


def should_start_scheduler() -> bool:
    return bool(settings.ENABLE_MONTHLY_REWARD_SCHEDULER)


async def run_monthly_settlement_once(today: date | None = None) -> dict:
    month_key = previous_month_key(today)
    async with AsyncSessionLocal() as session:
        result = await settle_monthly_rewards(session, month_key)
        await session.commit()
        logger.info("monthly_reward_settlement_checked", **result)
        return result


async def run_monthly_tasks_once(today: date | None = None) -> dict:
    current = today or business_today()
    settlement = await run_monthly_settlement_once(current)
    lottery = {
        "skipped": True,
        "reason": "not_first_day",
    }
    if current.day == 1:
        lottery_month = previous_month_key(today)
        async with AsyncSessionLocal() as session:
            lottery = await run_monthly_lottery(session, lottery_month)
            await session.commit()
            logger.info("monthly_lottery_checked", **lottery)

    return {
        "settlement": settlement,
        "lottery": lottery,
    }


async def _scheduler_loop() -> None:
    interval = max(3600, int(settings.MONTHLY_REWARD_CHECK_INTERVAL_SECONDS or 21600))
    logger.info("monthly_reward_scheduler_started", interval_seconds=interval)

    try:
        while True:
            try:
                await run_monthly_tasks_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("monthly_reward_scheduler_failed", error=str(exc))

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("monthly_reward_scheduler_stopped")
        raise


def start_monthly_reward_scheduler() -> Optional[asyncio.Task]:
    global _scheduler_task

    if not should_start_scheduler():
        logger.info("monthly_reward_scheduler_disabled")
        return None

    if _scheduler_task and not _scheduler_task.done():
        return _scheduler_task

    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="monthly-reward-scheduler")
    return _scheduler_task


async def stop_monthly_reward_scheduler() -> None:
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
