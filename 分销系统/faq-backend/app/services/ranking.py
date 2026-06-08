from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import AnswerRecord
from app.models.user import User

RANKING_EXCLUDED_COMPANY_KEYWORDS = ("施耐德电气",)


def is_ranking_excluded_company(company: str | None) -> bool:
    text = str(company or "").strip()
    return any(keyword in text for keyword in RANKING_EXCLUDED_COMPANY_KEYWORDS)


def is_ranking_excluded_user(user: User | None) -> bool:
    return bool(user and is_ranking_excluded_company(user.company))


def get_display_name(user: User) -> str:
    return user.real_name or user.nickname or f"用户{str(user.id)[:6]}"


def build_name_sort_key(name: str) -> tuple[bytes, str]:
    text = (name or "").strip()
    if not text:
        return (b"", "")

    try:
        # GB18030 ordering is a practical approximation for Chinese pinyin order.
        return (text.encode("gb18030", errors="ignore"), text.casefold())
    except Exception:
        return (text.encode("utf-8", errors="ignore"), text.casefold())


def sort_users_for_leaderboard(users: Iterable[User]) -> list[User]:
    return sorted(
        users,
        key=lambda user: (
            -(user.total_score or 0),
            build_name_sort_key(get_display_name(user)),
            str(user.id),
        ),
    )


def build_competition_rank_map(users: Iterable[User]) -> dict[str, int]:
    rank_map: dict[str, int] = {}
    previous_score: int | None = None
    current_rank = 0

    for index, user in enumerate(sort_users_for_leaderboard(users), start=1):
        score = user.total_score or 0
        if previous_score is None or score != previous_score:
            current_rank = index
            previous_score = score
        rank_map[user.id] = current_rank

    return rank_map


@dataclass(frozen=True)
class WeeklyRankEntry:
    user: User
    weekly_correct_count: int
    weekly_time_spent: int
    weekly_total_count: int


async def fetch_weekly_rank_entries(
    db: AsyncSession,
    quiz_date: str | None = None,
    *,
    company: str | None = None,
) -> list[WeeklyRankEntry]:
    """Fetch weekly quiz stats used by leaderboard and personal rank."""

    correct_expr = func.sum(
        case((AnswerRecord.is_correct == True, 1), else_=0)  # noqa: E712
    ).label("weekly_correct_count")
    time_expr = func.sum(func.coalesce(AnswerRecord.time_spent, 0)).label("weekly_time_spent")
    total_expr = func.count(AnswerRecord.id).label("weekly_total_count")

    filters = [AnswerRecord.source == "daily"]
    if quiz_date:
        filters.append(AnswerRecord.quiz_date == quiz_date)

    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            correct_expr,
            time_expr,
            total_expr,
        )
        .where(*filters)
        .group_by(AnswerRecord.user_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            stats_subquery.c.weekly_correct_count,
            stats_subquery.c.weekly_time_spent,
            stats_subquery.c.weekly_total_count,
        )
        .join(stats_subquery, stats_subquery.c.user_id == User.id)
    )

    if company is not None:
        stmt = stmt.where(User.company == company)

    result = await db.execute(stmt)
    entries = [
        WeeklyRankEntry(
            user=user,
            weekly_correct_count=int(weekly_correct_count or 0),
            weekly_time_spent=int(weekly_time_spent or 0),
            weekly_total_count=int(weekly_total_count or 0),
        )
        for user, weekly_correct_count, weekly_time_spent, weekly_total_count in result.all()
        if not is_ranking_excluded_user(user)
    ]

    return sort_weekly_rank_entries(entries)


def sort_weekly_rank_entries(entries: Iterable[WeeklyRankEntry]) -> list[WeeklyRankEntry]:
    return sorted(
        entries,
        key=lambda entry: (
            -entry.weekly_correct_count,
            entry.weekly_time_spent,
            build_name_sort_key(get_display_name(entry.user)),
            str(entry.user.id),
        ),
    )


def build_weekly_competition_rank_map(entries: Iterable[WeeklyRankEntry]) -> dict[str, int]:
    rank_map: dict[str, int] = {}
    previous_key: tuple[int, int] | None = None
    current_rank = 0

    for index, entry in enumerate(sort_weekly_rank_entries(entries), start=1):
        rank_key = (entry.weekly_correct_count, entry.weekly_time_spent)
        if previous_key is None or rank_key != previous_key:
            current_rank = index
            previous_key = rank_key
        rank_map[entry.user.id] = current_rank

    return rank_map
