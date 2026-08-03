"""Monthly lucky lottery selection, reward issuing, and notice helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy import EnergyTransaction
from app.models.lottery import LotteryDraw, LotteryWinner
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.monthly_leaderboard import validate_month_key
from app.services.ranking import build_name_sort_key, get_display_name, is_ranking_excluded_user


@dataclass(frozen=True)
class LotteryPrize:
    level: str
    name: str
    amount: int
    count: int


LOTTERY_PRIZES = (
    LotteryPrize(level="first", name="一等奖", amount=30, count=10),
    LotteryPrize(level="second", name="二等奖", amount=20, count=10),
    LotteryPrize(level="third", name="三等奖", amount=10, count=10),
)


def format_lottery_month(month_key: str) -> str:
    month = validate_month_key(month_key)
    year_text, month_text = month.split("-")
    return f"{int(year_text)}年{int(month_text)}月"


async def fetch_lottery_candidates(db: AsyncSession, participant_month: str) -> list[User]:
    month = validate_month_key(participant_month)
    participant_user_ids = (
        select(AnswerRecord.user_id)
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date.like(f"{month}-%"))
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    result = await db.execute(
        select(User).join(participant_user_ids, participant_user_ids.c.user_id == User.id)
    )
    candidates = [
        user
        for user in result.scalars().all()
        if not is_ranking_excluded_user(user)
    ]
    return sorted(
        candidates,
        key=lambda user: (
            build_name_sort_key(get_display_name(user)),
            str(user.id),
        ),
    )


def assign_lottery_prizes(users: list[User], month_key: str) -> list[tuple[User, LotteryPrize, int]]:
    shuffled = list(users)
    random.Random(month_key).shuffle(shuffled)

    winners: list[tuple[User, LotteryPrize, int]] = []
    cursor = 0
    winner_order = 1
    for prize in LOTTERY_PRIZES:
        for user in shuffled[cursor:cursor + prize.count]:
            winners.append((user, prize, winner_order))
            winner_order += 1
        cursor += prize.count
        if cursor >= len(shuffled):
            break
    return winners


async def fetch_lottery_draw(db: AsyncSession, month_key: str) -> LotteryDraw | None:
    month = validate_month_key(month_key)
    result = await db.execute(select(LotteryDraw).where(LotteryDraw.month_key == month))
    return result.scalar_one_or_none()


async def run_monthly_lottery(db: AsyncSession, month_key: str) -> dict:
    month = validate_month_key(month_key)
    existing = await fetch_lottery_draw(db, month)
    if existing:
        return {
            "month": existing.month_key,
            "participant_month": existing.participant_month,
            "eligible_count": existing.eligible_count,
            "winner_count": existing.winner_count,
            "already_drawn": True,
        }

    participant_month = month
    candidates = await fetch_lottery_candidates(db, participant_month)
    now = datetime.now(timezone.utc)
    draw = LotteryDraw(
        month_key=month,
        participant_month=participant_month,
        status="completed",
        eligible_count=len(candidates),
        winner_count=0,
        drawn_at=now,
    )
    db.add(draw)
    await db.flush()

    winners = assign_lottery_prizes(candidates, month)
    for user, prize, winner_order in winners:
        user.total_score = int(user.total_score or 0) + prize.amount
        transaction = EnergyTransaction(
            user_id=user.id,
            amount=prize.amount,
            type="lottery_reward",
            title=f"{format_lottery_month(month)}幸运抽奖",
            description=f"{format_lottery_month(month)}幸运抽奖{prize.name}，奖励{prize.amount}格施能量",
            related_type="lottery_winner",
            related_id=f"{month}:{user.id}",
            related_month=month,
            status="issued",
        )
        db.add(transaction)
        await db.flush()

        db.add(
            LotteryWinner(
                draw_id=draw.id,
                month_key=month,
                user_id=user.id,
                prize_level=prize.level,
                prize_name=prize.name,
                reward_amount=prize.amount,
                winner_order=winner_order,
                energy_transaction_id=transaction.id,
            )
        )

    draw.winner_count = len(winners)
    return {
        "month": month,
        "participant_month": participant_month,
        "eligible_count": len(candidates),
        "winner_count": len(winners),
        "already_drawn": False,
    }


def build_lottery_notice_text(winner: LotteryWinner) -> str:
    return f"🎉 您获得了{format_lottery_month(winner.month_key)}幸运抽奖{winner.prize_name}，点击查看>"
