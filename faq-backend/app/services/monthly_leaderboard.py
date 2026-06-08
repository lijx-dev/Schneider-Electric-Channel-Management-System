"""Monthly leaderboard aggregation, snapshots, and rewards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy import EnergyTransaction
from app.models.monthly import MonthlyRankSnapshot
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.ranking import build_name_sort_key, get_display_name, is_ranking_excluded_user

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class MonthlyRankEntry:
    user: User
    rank: int
    monthly_correct_count: int
    monthly_time_spent: int
    monthly_total_count: int
    reward_amount: int


def validate_month_key(month_key: str) -> str:
    month = str(month_key or "").strip()
    if not MONTH_RE.match(month):
        raise ValueError("month must use YYYY-MM format")
    return month


def get_month_reward_amount(rank: int | None) -> int:
    value = int(rank or 0)
    if 1 <= value <= 3:
        return 30
    if 4 <= value <= 10:
        return 20
    if 11 <= value <= 20:
        return 10
    if 21 <= value <= 50:
        return 5
    return 0


def sort_monthly_entries(entries: Iterable[MonthlyRankEntry]) -> list[MonthlyRankEntry]:
    return sorted(
        entries,
        key=lambda entry: (
            -entry.monthly_correct_count,
            entry.monthly_time_spent,
            build_name_sort_key(get_display_name(entry.user)),
            str(entry.user.id),
        ),
    )


async def fetch_live_month_entries(db: AsyncSession, month_key: str) -> list[MonthlyRankEntry]:
    month = validate_month_key(month_key)
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label(  # noqa: E712
        "monthly_correct_count"
    )
    time_expr = func.sum(func.coalesce(AnswerRecord.time_spent, 0)).label("monthly_time_spent")
    total_expr = func.count(AnswerRecord.id).label("monthly_total_count")

    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            correct_expr,
            time_expr,
            total_expr,
        )
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date.like(f"{month}-%"))
        .group_by(AnswerRecord.user_id)
        .subquery()
    )

    result = await db.execute(
        select(
            User,
            stats_subquery.c.monthly_correct_count,
            stats_subquery.c.monthly_time_spent,
            stats_subquery.c.monthly_total_count,
        ).join(stats_subquery, stats_subquery.c.user_id == User.id)
    )

    unranked = [
        MonthlyRankEntry(
            user=user,
            rank=0,
            monthly_correct_count=int(correct_count or 0),
            monthly_time_spent=int(time_spent or 0),
            monthly_total_count=int(total_count or 0),
            reward_amount=0,
        )
        for user, correct_count, time_spent, total_count in result.all()
        if not is_ranking_excluded_user(user)
    ]
    sorted_entries = sort_monthly_entries(unranked)

    ranked: list[MonthlyRankEntry] = []
    previous_key: tuple[int, int] | None = None
    current_rank = 0
    for index, entry in enumerate(sorted_entries, start=1):
        rank_key = (entry.monthly_correct_count, entry.monthly_time_spent)
        if previous_key is None or rank_key != previous_key:
            current_rank = index
            previous_key = rank_key
        reward_amount = (
            get_month_reward_amount(current_rank)
            if entry.monthly_correct_count > 0
            else 0
        )
        ranked.append(
            MonthlyRankEntry(
                user=entry.user,
                rank=current_rank,
                monthly_correct_count=entry.monthly_correct_count,
                monthly_time_spent=entry.monthly_time_spent,
                monthly_total_count=entry.monthly_total_count,
                reward_amount=reward_amount,
            )
        )
    return ranked


async def fetch_month_snapshots(db: AsyncSession, month_key: str) -> list[MonthlyRankSnapshot]:
    month = validate_month_key(month_key)
    result = await db.execute(
        select(MonthlyRankSnapshot)
        .where(MonthlyRankSnapshot.month_key == month)
        .order_by(MonthlyRankSnapshot.rank.asc(), MonthlyRankSnapshot.id.asc())
    )
    return list(result.scalars().all())


async def settle_monthly_rewards(db: AsyncSession, month_key: str) -> dict:
    month = validate_month_key(month_key)
    existing = await fetch_month_snapshots(db, month)
    if existing:
        return {
            "month": month,
            "snapshot_count": len(existing),
            "reward_count": sum(1 for item in existing if item.reward_amount > 0),
            "already_settled": True,
        }

    entries = await fetch_live_month_entries(db, month)
    settled_at = datetime.now(timezone.utc)
    reward_count = 0

    for entry in entries:
        user = entry.user
        reward_amount = entry.reward_amount
        snapshot = MonthlyRankSnapshot(
            month_key=month,
            user_id=user.id,
            rank=entry.rank,
            nickname=user.nickname or "",
            real_name=user.real_name or "",
            company=user.company or "",
            province=user.province or "",
            avatar_url=user.avatar_url or "",
            monthly_correct_count=entry.monthly_correct_count,
            monthly_total_count=entry.monthly_total_count,
            monthly_time_spent=entry.monthly_time_spent,
            reward_amount=reward_amount,
            reward_status="issued" if reward_amount > 0 else "none",
            settled_at=settled_at,
        )
        db.add(snapshot)

        if reward_amount > 0:
            user.total_score = int(user.total_score or 0) + reward_amount
            reward_count += 1
            db.add(
                EnergyTransaction(
                    user_id=user.id,
                    amount=reward_amount,
                    type="monthly_rank_reward",
                    title=f"{month}月榜奖励",
                    description=f"月榜第{entry.rank}名，奖励{reward_amount}格施能量",
                    related_type="monthly_rank_snapshot",
                    related_id=f"{month}:{user.id}",
                    related_month=month,
                    status="issued",
                )
            )

    return {
        "month": month,
        "snapshot_count": len(entries),
        "reward_count": reward_count,
        "already_settled": False,
    }
