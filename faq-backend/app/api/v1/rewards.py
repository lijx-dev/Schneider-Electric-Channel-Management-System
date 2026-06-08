from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.models.energy import EnergyTransaction
from app.models.lottery import LotteryWinner
from app.models.monthly import MonthlyRankSnapshot
from app.services.lottery import previous_calendar_month_key
from app.services.monthly_leaderboard import validate_month_key

router = APIRouter(tags=["奖励记录"])


REWARD_NOTICE_TYPES = {"monthly_rank_reward", "lottery_reward"}


class RewardNoticeReadRequest(BaseModel):
    reward_transaction_ids: list[int] = Field(default_factory=list)
    lottery_notice_ids: list[int] = Field(default_factory=list)


def next_calendar_month_key(current_month: str) -> str:
    month = validate_month_key(current_month)
    year_text, month_text = month.split("-")
    year = int(year_text)
    month_number = int(month_text)
    if month_number == 12:
        return f"{year + 1}-01"
    return f"{year}-{month_number + 1:02d}"


def format_reward_notice_month(month_key: str) -> str:
    month = validate_month_key(month_key)
    year_text, month_text = month.split("-")
    return f"{int(year_text)}年{int(month_text)}月"


def serialize_monthly_notice(
    transaction: EnergyTransaction | None,
    snapshot: MonthlyRankSnapshot | None,
) -> dict | None:
    if not transaction:
        return None

    rank_text = f"第{snapshot.rank}名，" if snapshot and snapshot.rank else ""
    return {
        "transaction_id": transaction.id,
        "month_key": transaction.related_month,
        "amount": transaction.amount,
        "rank": snapshot.rank if snapshot else None,
        "title": transaction.title,
        "description": transaction.description,
        "summary": f"{rank_text}奖励{transaction.amount}格施能量",
    }


def serialize_lottery_reward_notice(
    transaction: EnergyTransaction | None,
    winner: LotteryWinner | None,
) -> dict | None:
    if not transaction or not winner:
        return None

    return {
        "transaction_id": transaction.id,
        "notice_id": winner.id,
        "month_key": winner.month_key,
        "prize_level": winner.prize_level,
        "prize_name": winner.prize_name,
        "amount": winner.reward_amount,
        "winner_order": winner.winner_order,
    }


def build_reward_notice_text(monthly: dict | None, lottery: dict | None) -> str:
    if monthly and lottery:
        return (
            f"🎉 恭喜您获得{format_reward_notice_month(lottery['month_key'])}幸运抽奖{lottery['prize_name']}，"
            f"同时获得{format_reward_notice_month(monthly['month_key'])}月榜奖励{monthly['amount']}格施能量，点击查看>"
        )
    if lottery:
        return f"🎉 恭喜您获得{format_reward_notice_month(lottery['month_key'])}幸运抽奖{lottery['prize_name']}，点击查看>"
    if monthly:
        return f"🎉 恭喜您获得{format_reward_notice_month(monthly['month_key'])}月榜奖励{monthly['amount']}格施能量，点击查看>"
    return ""


def serialize_reward_notice(monthly: dict | None, lottery: dict | None) -> dict:
    if not monthly and not lottery:
        return {"has_notice": False}

    reward_transaction_ids = []
    lottery_notice_ids = []
    if monthly:
        reward_transaction_ids.append(monthly["transaction_id"])
    if lottery:
        reward_transaction_ids.append(lottery["transaction_id"])
        lottery_notice_ids.append(lottery["notice_id"])

    return {
        "has_notice": True,
        "notice_id": ",".join(str(item) for item in reward_transaction_ids),
        "reward_transaction_ids": reward_transaction_ids,
        "lottery_notice_ids": lottery_notice_ids,
        "monthly": monthly,
        "lottery": lottery,
        "text": build_reward_notice_text(monthly, lottery),
    }


async def fetch_latest_unread_reward_transaction(
    db: AsyncSession,
    current_user_id: str,
) -> EnergyTransaction | None:
    result = await db.execute(
        select(EnergyTransaction)
        .where(EnergyTransaction.user_id == current_user_id)
        .where(EnergyTransaction.type.in_(sorted(REWARD_NOTICE_TYPES)))
        .where(EnergyTransaction.notice_read_at.is_(None))
        .order_by(EnergyTransaction.related_month.desc(), EnergyTransaction.created_at.desc(), EnergyTransaction.id.desc())
        .limit(20)
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return None

    lottery_transaction_ids = [item.id for item in candidates if item.type == "lottery_reward"]
    unread_lottery_transaction_ids: set[int] = set()
    if lottery_transaction_ids:
        lottery_result = await db.execute(
            select(LotteryWinner.energy_transaction_id)
            .where(LotteryWinner.user_id == current_user_id)
            .where(LotteryWinner.notice_read_at.is_(None))
            .where(LotteryWinner.energy_transaction_id.in_(lottery_transaction_ids))
        )
        unread_lottery_transaction_ids = {
            int(item)
            for item in lottery_result.scalars().all()
            if item is not None
        }

    for item in candidates:
        if item.type == "monthly_rank_reward":
            return item
        if item.type == "lottery_reward" and item.id in unread_lottery_transaction_ids:
            return item
    return None


async def fetch_monthly_notice(
    db: AsyncSession,
    current_user_id: str,
    month_key: str,
) -> tuple[EnergyTransaction | None, MonthlyRankSnapshot | None]:
    transaction_result = await db.execute(
        select(EnergyTransaction)
        .where(EnergyTransaction.user_id == current_user_id)
        .where(EnergyTransaction.type == "monthly_rank_reward")
        .where(EnergyTransaction.related_month == month_key)
        .where(EnergyTransaction.notice_read_at.is_(None))
        .order_by(EnergyTransaction.created_at.desc(), EnergyTransaction.id.desc())
        .limit(1)
    )
    transaction = transaction_result.scalar_one_or_none()
    if not transaction:
        return None, None

    snapshot_result = await db.execute(
        select(MonthlyRankSnapshot)
        .where(MonthlyRankSnapshot.user_id == current_user_id)
        .where(MonthlyRankSnapshot.month_key == month_key)
        .limit(1)
    )
    return transaction, snapshot_result.scalar_one_or_none()


async def fetch_lottery_notice(
    db: AsyncSession,
    current_user_id: str,
    month_key: str,
) -> tuple[EnergyTransaction | None, LotteryWinner | None]:
    result = await db.execute(
        select(EnergyTransaction, LotteryWinner)
        .join(LotteryWinner, LotteryWinner.energy_transaction_id == EnergyTransaction.id)
        .where(EnergyTransaction.user_id == current_user_id)
        .where(EnergyTransaction.type == "lottery_reward")
        .where(EnergyTransaction.related_month == month_key)
        .where(EnergyTransaction.notice_read_at.is_(None))
        .where(LotteryWinner.user_id == current_user_id)
        .where(LotteryWinner.notice_read_at.is_(None))
        .order_by(LotteryWinner.winner_order.asc(), EnergyTransaction.id.desc())
        .limit(1)
    )
    row = result.first()
    if not row:
        return None, None
    return row[0], row[1]


async def build_latest_reward_notice(
    db: AsyncSession,
    current_user_id: str,
) -> dict:
    latest = await fetch_latest_unread_reward_transaction(db, current_user_id)
    if not latest or not latest.related_month:
        return serialize_reward_notice(None, None)

    if latest.type == "lottery_reward":
        lottery_month = latest.related_month
        monthly_month = previous_calendar_month_key(lottery_month)
    else:
        monthly_month = latest.related_month
        lottery_month = next_calendar_month_key(monthly_month)

    monthly_transaction, monthly_snapshot = await fetch_monthly_notice(db, current_user_id, monthly_month)
    lottery_transaction, lottery_winner = await fetch_lottery_notice(db, current_user_id, lottery_month)
    return serialize_reward_notice(
        serialize_monthly_notice(monthly_transaction, monthly_snapshot),
        serialize_lottery_reward_notice(lottery_transaction, lottery_winner),
    )


@router.get("/rewards/records")
async def get_reward_records(
    limit: int = Query(50, ge=1, le=100),
    reward_type: str = Query("all"),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    stmt = (
        select(EnergyTransaction)
        .where(EnergyTransaction.user_id == current_user_id)
        .order_by(EnergyTransaction.created_at.desc(), EnergyTransaction.id.desc())
        .limit(limit)
    )
    if reward_type != "all":
        stmt = stmt.where(EnergyTransaction.type == reward_type)

    result = await db.execute(stmt)
    rows = [
        {
            "id": item.id,
            "amount": item.amount,
            "type": item.type,
            "title": item.title,
            "description": item.description,
            "related_type": item.related_type,
            "related_id": item.related_id,
            "related_month": item.related_month,
            "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else "",
        }
        for item in result.scalars().all()
    ]
    return {"code": 0, "data": rows}


@router.get("/rewards/latest-notice")
async def get_latest_reward_notice(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return {"code": 0, "data": await build_latest_reward_notice(db, current_user_id)}


@router.post("/rewards/notices/read")
async def mark_reward_notice_read(
    payload: RewardNoticeReadRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    now = datetime.now(timezone.utc)
    reward_transaction_ids = list(dict.fromkeys((payload.reward_transaction_ids if payload else []) or []))
    lottery_notice_ids = list(dict.fromkeys((payload.lottery_notice_ids if payload else []) or []))

    if not reward_transaction_ids and not lottery_notice_ids:
        notice = await build_latest_reward_notice(db, current_user_id)
        reward_transaction_ids = notice.get("reward_transaction_ids") or []
        lottery_notice_ids = notice.get("lottery_notice_ids") or []

    if reward_transaction_ids:
        tx_result = await db.execute(
            select(EnergyTransaction)
            .where(EnergyTransaction.user_id == current_user_id)
            .where(EnergyTransaction.id.in_(reward_transaction_ids))
        )
        for transaction in tx_result.scalars().all():
            if transaction.notice_read_at is None:
                transaction.notice_read_at = now

    if lottery_notice_ids:
        lottery_result = await db.execute(
            select(LotteryWinner)
            .where(LotteryWinner.user_id == current_user_id)
            .where(LotteryWinner.id.in_(lottery_notice_ids))
        )
        for winner in lottery_result.scalars().all():
            if winner.notice_read_at is None:
                winner.notice_read_at = now

    return {"code": 0, "data": serialize_reward_notice(None, None)}
