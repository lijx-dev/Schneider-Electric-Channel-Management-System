from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.models.lottery import LotteryWinner
from app.services.lottery import build_lottery_notice_text

router = APIRouter(tags=["幸运抽奖"])


def serialize_lottery_notice(winner: LotteryWinner | None) -> dict:
    if not winner:
        return {"has_notice": False}

    return {
        "has_notice": True,
        "notice_id": winner.id,
        "month_key": winner.month_key,
        "prize_level": winner.prize_level,
        "prize_name": winner.prize_name,
        "reward_amount": winner.reward_amount,
        "text": build_lottery_notice_text(winner),
    }


@router.get("/lottery/my-latest-notice")
async def get_my_latest_lottery_notice(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(LotteryWinner)
        .where(LotteryWinner.user_id == current_user_id)
        .where(LotteryWinner.notice_read_at.is_(None))
        .order_by(LotteryWinner.month_key.desc(), LotteryWinner.id.desc())
        .limit(1)
    )
    return {"code": 0, "data": serialize_lottery_notice(result.scalar_one_or_none())}


@router.post("/lottery/notices/{notice_id}/read")
async def mark_lottery_notice_read(
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    result = await db.execute(
        select(LotteryWinner)
        .where(LotteryWinner.id == notice_id)
        .where(LotteryWinner.user_id == current_user_id)
    )
    winner = result.scalar_one_or_none()
    if not winner:
        raise HTTPException(status_code=404, detail="notice not found")

    if winner.notice_read_at is None:
        winner.notice_read_at = datetime.now(timezone.utc)

    return {"code": 0, "data": serialize_lottery_notice(None)}
