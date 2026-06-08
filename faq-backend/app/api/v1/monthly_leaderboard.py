from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.models.monthly import MonthlyRankSnapshot
from app.services.monthly_leaderboard import (
    fetch_live_month_entries,
    fetch_month_snapshots,
    validate_month_key,
)
from app.services.ranking import get_display_name
from app.services.ranking import is_ranking_excluded_user
from app.services.storage import StorageService
from app.models.user import User

router = APIRouter(tags=["月榜"])

REWARD_RULE_TEXT = "月末按排名发放施能量：前三30格，4-10名20格，11-20名10格，21-50名5格"


def _current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def _snapshot_to_row(snapshot: MonthlyRankSnapshot, base: str) -> dict:
    avatar = StorageService.build_avatar_access_url(snapshot.avatar_url, base)
    return {
        "user_id": snapshot.user_id,
        "nickname": snapshot.real_name or snapshot.nickname or "学员",
        "real_name": snapshot.real_name or "",
        "company": snapshot.company or "",
        "province": snapshot.province or "",
        "avatar": avatar,
        "rank": snapshot.rank,
        "monthly_correct_count": snapshot.monthly_correct_count,
        "monthly_time_spent": snapshot.monthly_time_spent,
        "monthly_total_count": snapshot.monthly_total_count,
        "reward_amount": snapshot.reward_amount,
        "weekly_correct_count": snapshot.monthly_correct_count,
        "weekly_time_spent": snapshot.monthly_time_spent,
        "weekly_total_count": snapshot.monthly_total_count,
    }


def _entry_to_row(entry, base: str) -> dict:
    user = entry.user
    avatar = StorageService.build_avatar_access_url(user.avatar_url, base)
    return {
        "user_id": user.id,
        "nickname": get_display_name(user),
        "real_name": user.real_name or "",
        "company": user.company or "",
        "province": user.province or "",
        "avatar": avatar,
        "rank": entry.rank,
        "monthly_correct_count": entry.monthly_correct_count,
        "monthly_time_spent": entry.monthly_time_spent,
        "monthly_total_count": entry.monthly_total_count,
        "reward_amount": entry.reward_amount,
        "weekly_correct_count": entry.monthly_correct_count,
        "weekly_time_spent": entry.monthly_time_spent,
        "weekly_total_count": entry.monthly_total_count,
    }


@router.get("/monthly-leaderboard")
async def get_monthly_leaderboard(
    request: Request,
    month: str | None = None,
    limit: int = Query(50, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    base = str(request.base_url).rstrip("/")
    try:
        month_key = validate_month_key(month or _current_month_key())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snapshots = await fetch_month_snapshots(db, month_key)
    if snapshots:
        rows = [_snapshot_to_row(snapshot, base) for snapshot in snapshots]
        status = "settled"
    else:
        entries = await fetch_live_month_entries(db, month_key)
        rows = [_entry_to_row(entry, base) for entry in entries]
        status = "active"

    my_rank = next((row for row in rows if row["user_id"] == current_user_id), None)
    if my_rank is None:
        user_result = await db.execute(select(User).where(User.id == current_user_id))
        current_user = user_result.scalar_one_or_none()
        if is_ranking_excluded_user(current_user):
            my_rank = {
                "user_id": current_user_id,
                "nickname": get_display_name(current_user),
                "real_name": current_user.real_name or "",
                "company": current_user.company or "",
                "province": current_user.province or "",
                "avatar": StorageService.build_avatar_access_url(current_user.avatar_url, base),
                "rank": "-",
                "monthly_correct_count": 0,
                "monthly_time_spent": 0,
                "monthly_total_count": 0,
                "weekly_correct_count": 0,
                "weekly_time_spent": 0,
                "weekly_total_count": 0,
                "reward_amount": 0,
                "ranking_excluded": True,
            }
    top_rows = rows[:limit]

    return {
        "code": 0,
        "data": {
            "month": month_key,
            "status": status,
            "reward_rule_text": REWARD_RULE_TEXT,
            "leaderboard": top_rows,
            "my_rank": my_rank,
        },
    }


@router.get("/monthly-leaderboard/months")
async def get_monthly_leaderboard_months(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    del current_user_id
    snapshot_result = await db.execute(
        select(MonthlyRankSnapshot.month_key).distinct().order_by(MonthlyRankSnapshot.month_key.desc())
    )
    months = list(snapshot_result.scalars().all())
    current = _current_month_key()
    if current not in months:
        months.insert(0, current)
    return {"code": 0, "data": months}
