"""分销商大会「能量印记·集章」模块 API 路由."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, require_conference_whitelist
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.conference import ConferenceMedal, ConferenceZone, ConferenceZoneMark
from app.models.question import Question
from app.models.record import AnswerRecord
from app.schemas.conference import ActivityReport, QuizSubmit
from app.services.conference import (
    check_zone_window,
    get_zone_progress,
    grant_zone_mark,
    record_activity,
    today_str,
    try_grant_medal,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/conference", tags=["分销商大会"])


def _normalize_answer(question_type: str, selected: str, correct: str) -> bool:
    """答案比对：多选去除非字母字符比较，判断题归一化，其余忽略大小写。"""
    if not selected:
        return False

    if question_type == "true_false":
        from app.api.v1.daily import normalize_true_false_value

        return normalize_true_false_value(selected) == normalize_true_false_value(correct)

    if question_type == "multiple_choice":
        clean = lambda value: "".join(ch for ch in str(value).upper() if ch.isalpha())
        return clean(selected) == clean(correct)

    return str(selected).strip().upper() == str(correct).strip().upper()


async def _zone_by_code(db: AsyncSession, code: str) -> ConferenceZone:
    zone = await db.scalar(
        select(ConferenceZone).where(
            ConferenceZone.code == code,
            ConferenceZone.is_active.is_(True),
        )
    )
    if not zone:
        raise HTTPException(status_code=404, detail="展区不存在")
    return zone


async def _claimed_zone_ids(db: AsyncSession, user_id: str) -> set[int]:
    result = await db.execute(
        select(ConferenceZoneMark.zone_id).where(ConferenceZoneMark.user_id == user_id)
    )
    return set(result.scalars().all())


async def _get_medal(db: AsyncSession, user_id: str) -> Optional[ConferenceMedal]:
    return await db.scalar(
        select(ConferenceMedal).where(ConferenceMedal.user_id == user_id)
    )


def _zone_to_dict(zone: ConferenceZone, claimed: bool) -> dict:
    return {
        "id": zone.id,
        "code": zone.code,
        "name": zone.name,
        "slogan": zone.slogan,
        "icon_url": zone.icon_url,
        "sort_order": zone.sort_order,
        "task_type": zone.task_type,
        "question_category": zone.question_category,
        "claimed": claimed,
    }


# ── 总览 ─────────────────────────────────────────────────────────────────

@router.get("/overview")
async def overview(
    current_user_id: str = Depends(require_conference_whitelist),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回所有启用展区 + 各展区印记是否已领取 + 勋章状态。"""
    zones_result = await db.execute(
        select(ConferenceZone)
        .where(ConferenceZone.is_active.is_(True))
        .order_by(ConferenceZone.sort_order)
    )
    zones = zones_result.scalars().all()

    claimed_zone_ids = await _claimed_zone_ids(db, current_user_id)
    medal = await _get_medal(db, current_user_id)

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


# ── 单展区详情 ───────────────────────────────────────────────────────────

@router.get("/zones/{code}")
async def zone_detail(
    code: str,
    current_user_id: str = Depends(require_conference_whitelist),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回单展区配置 + 进度；quiz 展区额外返回题目列表（隐藏答案）。"""
    zone = await _zone_by_code(db, code)
    check_zone_window(zone)

    progress = await get_zone_progress(db, current_user_id, zone)

    # 结算：任务全部完成 → 自动发放印记 + 尝试发放勋章（幂等，grant_zone_mark 唯一约束兜底）。
    # 覆盖 channel 展区（三任务完成）与 quiz 展区（题目完成）进入页面时的补发场景。
    if progress.get("completed"):
        if await grant_zone_mark(db, current_user_id, zone.id):
            await try_grant_medal(db, current_user_id)
            await db.commit()

    claimed = zone.id in await _claimed_zone_ids(db, current_user_id)
    data = {
        "id": zone.id,
        "code": zone.code,
        "name": zone.name,
        "slogan": zone.slogan,
        "icon_url": zone.icon_url,
        "sort_order": zone.sort_order,
        "task_type": zone.task_type,
        "question_category": zone.question_category,
        "required_daily_quiz_count": zone.required_daily_quiz_count,
        "required_ai_chat_count": zone.required_ai_chat_count,
        "claimed": claimed,
        "progress": progress,
    }

    if zone.task_type == "quiz" and zone.question_category:
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


# ── 提交题组答案（quiz 展区）────────────────────────────────────────────

@router.post("/zones/{code}/submit-quiz")
async def submit_quiz(
    code: str,
    body: QuizSubmit,
    current_user_id: str = Depends(require_conference_whitelist),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """逐条写入 answer_records（source='conference'，幂等覆盖），
    题目全部完成后发放印记并尝试发放勋章。"""
    zone = await _zone_by_code(db, code)
    check_zone_window(zone)

    if zone.task_type != "quiz":
        raise HTTPException(status_code=400, detail="该展区不是答题展区")

    if not zone.question_category:
        raise HTTPException(status_code=400, detail="该展区未配置题组")

    quiz_date = today_str()

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
                detail=f"题目 {answer.question_id} 不属于该展区题组",
            )

        is_correct = _normalize_answer(
            question.question_type, answer.selected_answer, question.answer
        )

        # (user_id, question_id, source, quiz_date) 唯一约束：幂等覆盖
        existing = await db.scalar(
            select(AnswerRecord).where(
                AnswerRecord.user_id == current_user_id,
                AnswerRecord.question_id == answer.question_id,
                AnswerRecord.source == "conference",
                AnswerRecord.quiz_date == quiz_date,
            )
        )
        if existing:
            existing.selected_answer = answer.selected_answer
            existing.is_correct = is_correct
            existing.score = 1 if is_correct else 0
        else:
            db.add(
                AnswerRecord(
                    user_id=current_user_id,
                    question_id=answer.question_id,
                    selected_answer=answer.selected_answer,
                    is_correct=is_correct,
                    score=1 if is_correct else 0,
                    source="conference",
                    quiz_date=quiz_date,
                )
            )

    await db.flush()

    # 结算：题目全部完成 → 发印记 → 尝试发勋章
    progress = await get_zone_progress(db, current_user_id, zone)
    mark_earned = False
    medal_earned = False
    medal_code: Optional[str] = None

    if progress.get("completed"):
        mark_earned = await grant_zone_mark(db, current_user_id, zone.id)
        if mark_earned:
            medal = await try_grant_medal(db, current_user_id)
            if medal:
                medal_earned = True
                medal_code = medal.medal_code

    await db.commit()

    return {
        "code": 0,
        "data": {
            "claimed": progress.get("completed", False),
            "mark_earned": mark_earned,
            "medal_earned": medal_earned,
            "medal_code": medal_code,
        },
    }


# ── 活动计数上报（channel 展区步骤3 施能量页浏览）────────────────────────

@router.post("/activity")
async def report_activity(
    body: ActivityReport,
    current_user_id: str = Depends(require_conference_whitelist),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """上报 activity 计数（当前仅 energy_view）。"""
    action = (body.action or "").strip()
    if action != "energy_view":
        raise HTTPException(status_code=400, detail="不支持的 activity 动作")

    await record_activity(db, current_user_id, action)

    # 结算：施能量页是 channel 展区最后一步，三任务全部完成 → 自动发放印记 + 勋章（幂等）
    if action == "energy_view":
        channel_zone = await db.scalar(
            select(ConferenceZone).where(
                ConferenceZone.task_type == "channel",
                ConferenceZone.is_active.is_(True),
            )
        )
        if channel_zone:
            progress = await get_zone_progress(db, current_user_id, channel_zone)
            if progress.get("completed"):
                if await grant_zone_mark(db, current_user_id, channel_zone.id):
                    await try_grant_medal(db, current_user_id)

    await db.commit()

    from app.services.conference import get_activity_count

    count = await get_activity_count(db, current_user_id, action)
    return {"code": 0, "data": {"count": count}}


# ── 勋章状态 ─────────────────────────────────────────────────────────────

@router.get("/medal")
async def medal_status(
    current_user_id: str = Depends(require_conference_whitelist),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回本用户勋章状态。"""
    medal = await _get_medal(db, current_user_id)

    zones_result = await db.execute(
        select(ConferenceZone)
        .where(ConferenceZone.is_active.is_(True))
        .order_by(ConferenceZone.sort_order)
    )
    zones = zones_result.scalars().all()
    claimed_zone_ids = await _claimed_zone_ids(db, current_user_id)

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
