"""分销商大会「能量印章·集章」模块 API 路由（手机号自助签到版）.

所有接口以手机号为身份，不依赖主用户鉴权 / 白名单。
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.models.conference import ConferenceMedal, ConferenceZone, ConferenceZoneMark
from app.models.question import Question
from app.schemas.conference import JoinPayload, QuizSubmit
from app.services.conference import (
    check_zone_window,
    find_or_create_attendee,
    get_zone_progress,
    grant_zone_mark,
    today_str,
    try_grant_medal,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/conference", tags=["分销商大会"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _validate_phone(phone: str) -> str:
    phone = (phone or "").strip()
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    return phone


async def _zone_by_code(db: AsyncSession, code: str) -> ConferenceZone:
    zone = await db.scalar(
        select(ConferenceZone).where(
            ConferenceZone.code == code,
            ConferenceZone.is_active.is_(True),
        )
    )
    if not zone:
        raise HTTPException(status_code=404, detail="打卡点不存在")
    return zone


async def _claimed_zone_ids(db: AsyncSession, phone: str) -> set[int]:
    result = await db.execute(
        select(ConferenceZoneMark.zone_id).where(ConferenceZoneMark.phone == phone)
    )
    return set(result.scalars().all())


async def _get_medal(db: AsyncSession, phone: str) -> Optional[ConferenceMedal]:
    return await db.scalar(
        select(ConferenceMedal).where(ConferenceMedal.phone == phone)
    )


def _zone_to_dict(zone: ConferenceZone, claimed: bool) -> dict:
    return {
        "id": zone.id,
        "code": zone.code,
        "name": zone.name,
        "slogan": zone.slogan,
        "icon_url": zone.icon_url,
        "sort_order": zone.sort_order,
        "question_category": zone.question_category,
        "claimed": claimed,
    }


# ── 自助签到 ─────────────────────────────────────────────────────────────

@router.post("/join")
async def join(
    body: JoinPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """姓名＋手机号自助签到，按手机号幂等建档。"""
    phone = _validate_phone(body.phone)
    attendee = await find_or_create_attendee(db, phone, body.name.strip())
    await db.commit()
    return {
        "code": 0,
        "data": {
            "phone": attendee.phone,
            "name": attendee.name,
            "attendee_id": attendee.id,
        },
    }


# ── 总览 ─────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(
    phone: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回所有启用打卡点 + 该手机号各点印章状态 + 勋章状态。"""
    phone = _validate_phone(phone)
    zones_result = await db.execute(
        select(ConferenceZone)
        .where(ConferenceZone.is_active.is_(True))
        .order_by(ConferenceZone.sort_order)
    )
    zones = zones_result.scalars().all()

    claimed_zone_ids = await _claimed_zone_ids(db, phone)
    medal = await _get_medal(db, phone)

    return {
        "code": 0,
        "data": {
            "zones": [
                _zone_to_dict(zone, zone.id in claimed_zone_ids) for zone in zones
            ],
            "medal": {
                "granted": bool(medal),
                "medal_code": medal.medal_code if medal else None,
            },
        },
    }


# ── 单打卡点详情 ──────────────────────────────────────────────────────────

@router.get("/zones/{code}")
async def zone_detail(
    code: str,
    phone: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回单打卡点配置 + 答题进度 + 题组题目列表（隐藏答案）。"""
    phone = _validate_phone(phone)
    zone = await _zone_by_code(db, code)
    check_zone_window(zone)

    progress = await get_zone_progress(db, phone, zone)
    data = {
        "id": zone.id,
        "code": zone.code,
        "name": zone.name,
        "slogan": zone.slogan,
        "icon_url": zone.icon_url,
        "sort_order": zone.sort_order,
        "question_category": zone.question_category,
        "claimed": zone.id in await _claimed_zone_ids(db, phone),
        "progress": progress,
    }

    questions_result = await db.execute(
        select(Question)
        .where(
            Question.category == zone.question_category,
            Question.is_active.is_(True),
        )
        .order_by(Question.id)
    )
    data["questions"] = [
        question.to_dict(hide_answer=True)
        for question in questions_result.scalars().all()
    ]

    return {"code": 0, "data": data}


# ── 提交题组答案（答题打卡）───────────────────────────────────────────────

@router.post("/zones/{code}/submit-quiz")
async def submit_quiz(
    code: str,
    body: QuizSubmit,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """逐条写入 conference_answers（按手机号×题目×日期幂等覆盖），
    题组全部答完后发放该打卡点印章并尝试发放勋章。"""
    phone = _validate_phone(body.phone)
    zone = await _zone_by_code(db, code)
    check_zone_window(zone)

    # 自动尝试建档（已签到则复用并更新姓名）
    await find_or_create_attendee(db, phone, (body.name or "").strip())

    quiz_date = today_str()

    from app.models.conference import ConferenceAnswer

    for answer in body.answers:
        question = await db.scalar(
            select(Question).where(
                Question.id == answer.question_id,
                Question.category == zone.question_category,
            )
        )
        if not question:
            raise HTTPException(
                status_code=400,
                detail=f"题目 {answer.question_id} 不属于该打卡点题组",
            )

        # (phone, question_id, quiz_date) 唯一约束：幂等覆盖
        existing = await db.scalar(
            select(ConferenceAnswer).where(
                ConferenceAnswer.phone == phone,
                ConferenceAnswer.question_id == answer.question_id,
                ConferenceAnswer.quiz_date == quiz_date,
            )
        )
        if existing:
            existing.selected_answer = answer.selected_answer
        else:
            db.add(
                ConferenceAnswer(
                    phone=phone,
                    question_id=answer.question_id,
                    zone_id=zone.id,
                    selected_answer=answer.selected_answer,
                    quiz_date=quiz_date,
                )
            )

    await db.flush()

    # 结算：题组全部答完 → 发印章 → 尝试发勋章
    progress = await get_zone_progress(db, phone, zone)
    stamp_earned = False
    medal_earned = False
    medal_code: Optional[str] = None

    if progress.get("completed"):
        stamp_earned = await grant_zone_mark(db, phone, zone.id)
        if stamp_earned:
            medal = await try_grant_medal(db, phone, (body.name or "").strip())
            if medal:
                medal_earned = True
                medal_code = medal.medal_code

    await db.commit()

    return {
        "code": 0,
        "data": {
            "claimed": progress.get("completed", False),
            "stamp_earned": stamp_earned,
            "medal_earned": medal_earned,
            "medal_code": medal_code,
        },
    }


# ── 勋章状态 ─────────────────────────────────────────────────────────────

@router.get("/medal")
async def medal_status(
    phone: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回本手机号勋章状态。"""
    phone = _validate_phone(phone)
    medal = await _get_medal(db, phone)

    zones_result = await db.execute(
        select(ConferenceZone)
        .where(ConferenceZone.is_active.is_(True))
        .order_by(ConferenceZone.sort_order)
    )
    zones = zones_result.scalars().all()
    claimed_zone_ids = await _claimed_zone_ids(db, phone)

    return {
        "code": 0,
        "data": {
            "granted": bool(medal),
            "medal_code": medal.medal_code if medal else None,
            "zone_count": medal.zone_count if medal else 0,
            "earned_zones": [
                zone.code for zone in zones if zone.id in claimed_zone_ids
            ],
            "total_active_zones": len(zones),
        },
    }
