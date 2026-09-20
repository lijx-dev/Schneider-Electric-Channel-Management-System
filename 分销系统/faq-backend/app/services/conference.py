"""
分销商大会「能量印章·集章」业务逻辑（手机号自助签到版）

负责：
- 参会人登记（按手机号幂等）
- 打卡点答题进度（conference_answers 专用进度表）
- 印章发放（按手机号×打卡点幂等）
- 能量勋章发放（按手机号幂等）
- 打卡点开放窗口校验
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conference import (
    ConferenceAnswer,
    ConferenceAttendee,
    ConferenceMedal,
    ConferenceZone,
    ConferenceZoneMark,
)
from app.models.question import Question

logger = get_logger(__name__)

APP_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")

# 勋章编码前缀：DY- + 8 位大写字母数字
MEDAL_CODE_PREFIX = "DY-"
MEDAL_CODE_LENGTH = 8


def local_now() -> datetime:
    """Asia/Shanghai 当前时间（带时区）。"""
    return datetime.now(APP_TIMEZONE)


def today_str() -> str:
    """今日日期 YYYY-MM-DD（Asia/Shanghai）。"""
    return local_now().strftime("%Y-%m-%d")


def _generate_medal_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return MEDAL_CODE_PREFIX + "".join(
        secrets.choice(alphabet) for _ in range(MEDAL_CODE_LENGTH)
    )


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """将可能为 naive 的数据库时间转为 Asia/Shanghai aware，便于与 now 比较。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=APP_TIMEZONE)
    return dt.astimezone(APP_TIMEZONE)


def check_zone_window(zone: ConferenceZone) -> None:
    """打卡点开放窗口校验：窗口已设置且当前时间不在窗口内时抛 403。"""
    now = local_now()
    active_from = _as_aware(zone.active_from)
    active_to = _as_aware(zone.active_to)
    if active_from is not None and now < active_from:
        raise HTTPException(status_code=403, detail="大会打卡当前未开放")
    if active_to is not None and now > active_to:
        raise HTTPException(status_code=403, detail="大会打卡当前未开放")


# ── 参会人登记 ────────────────────────────────────────────────────────────

async def find_or_create_attendee(
    db: AsyncSession, phone: str, name: str
) -> ConferenceAttendee:
    """按手机号查询参会人，存在则更新姓名（幂等），不存在则创建。"""
    attendee = await db.scalar(
        select(ConferenceAttendee).where(ConferenceAttendee.phone == phone)
    )
    if attendee:
        if name and attendee.name != name:
            attendee.name = name
            await db.flush()
        return attendee

    attendee = ConferenceAttendee(name=name or phone, phone=phone)
    db.add(attendee)
    try:
        await db.flush()
    except IntegrityError:
        # 并发首次登记冲突：回滚后重查既有参会人
        await db.rollback()
        attendee = await db.scalar(
            select(ConferenceAttendee).where(ConferenceAttendee.phone == phone)
        )
        if attendee is None:
            raise
    return attendee


# ── 打卡点答题进度 ────────────────────────────────────────────────────────

async def _count_questions_in_category(db: AsyncSession, category: str) -> int:
    result = await db.execute(
        select(func.count(Question.id)).where(
            Question.category == category,
            Question.is_active.is_(True),
        )
    )
    return int(result.scalar() or 0)


async def _count_answered(db: AsyncSession, phone: str, zone_id: int) -> int:
    """手机号在该打卡点已答题目数（去重 question_id，不限日期）。

    说明：通关标准为「答完该题组全部题目即发印章」（不校验对错），
    跨天答题同样累计，故不按 quiz_date 过滤；重复提交由唯一约束幂等。
    """
    result = await db.execute(
        select(func.count(func.distinct(ConferenceAnswer.question_id))).where(
            ConferenceAnswer.phone == phone,
            ConferenceAnswer.zone_id == zone_id,
        )
    )
    return int(result.scalar() or 0)


async def get_zone_progress(
    db: AsyncSession, phone: str, zone: ConferenceZone
) -> dict:
    """返回单打卡点进度：{"done","total","completed"}。"""
    total = await _count_questions_in_category(db, zone.question_category)
    done = await _count_answered(db, phone, zone.id)
    return {
        "done": done,
        "total": total,
        "completed": bool(total) and done >= total,
    }


# ── 印章 / 勋章发放（均幂等）──────────────────────────────────────────────

async def grant_zone_mark(
    db: AsyncSession, phone: str, zone_id: int
) -> bool:
    """发放打卡点印章。已存在（唯一约束幂等）返回 False，新增返回 True。"""
    existing = await db.scalar(
        select(ConferenceZoneMark.id).where(
            ConferenceZoneMark.phone == phone,
            ConferenceZoneMark.zone_id == zone_id,
        )
    )
    if existing:
        return False

    db.add(
        ConferenceZoneMark(
            phone=phone,
            zone_id=zone_id,
            created_at=local_now(),
        )
    )
    try:
        await db.flush()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def try_grant_medal(
    db: AsyncSession, phone: str, name: str
) -> Optional[ConferenceMedal]:
    """集齐当前全部启用打卡点印章后自动发放勋章。

    - 查询所有 is_active=1 的打卡点
    - 若手机号已集齐对应印章 → 创建 conference_medals（phone 唯一幂等）
    - 返回新勋章；未集齐或已发放返回 None
    """
    active_zones = await db.execute(
        select(ConferenceZone).where(ConferenceZone.is_active.is_(True))
    )
    zones = active_zones.scalars().all()
    if not zones:
        return None

    marks = await db.execute(
        select(ConferenceZoneMark.zone_id).where(
            ConferenceZoneMark.phone == phone,
            ConferenceZoneMark.zone_id.in_([z.id for z in zones]),
        )
    )
    marked_zone_ids = set(marks.scalars().all())
    active_zone_ids = {z.id for z in zones}

    if not active_zone_ids.issubset(marked_zone_ids):
        return None

    medal = ConferenceMedal(
        phone=phone,
        name=name or phone,
        medal_code=_generate_medal_code(),
        zone_count=len(active_zone_ids),
        granted_at=local_now(),
    )
    db.add(medal)
    try:
        await db.flush()
        return medal
    except IntegrityError:
        # 手机号已有一枚勋章（phone 唯一约束），幂等返回 None
        await db.rollback()
        return None
