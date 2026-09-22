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

import re
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


def _norm_multi(value: str) -> str:
    """多选答案归一化：大写 + 去重 + 排序（选项顺序不敏感）。"""
    return "".join(sorted(dict.fromkeys((value or "").upper())))


def _strip_text(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip())


def _label_to_text(options: list | None, label: str) -> str:
    """把选项 label（A/B/C…）转成对应选项文本；越界/无效时原样返回。"""
    if not options:
        return label
    idx = ord((label or "")[:1].upper()) - ord("A")
    if 0 <= idx < len(options):
        return str(options[idx])
    return label


def _is_question_correct(question: Question, selected: str) -> bool:
    """判定单题答案是否与标准答案一致。按题型区分匹配规则：

    - single_choice: 选项 label 直接比较（大写）
    - multiple_choice: 选项 label 归一化（大写+去重+排序）后比较
    - true_false: 选项文本化后与标准答案（对/错/正确/错误）比较
    - fill_blank: 去除空白后全文比较
    """
    qtype = question.question_type
    answer = _strip_text(question.answer or "")
    selected = selected or ""

    if qtype == "multiple_choice":
        return _norm_multi(question.answer or "") == _norm_multi(selected)

    if qtype == "true_false":
        selected_text = _strip_text(_label_to_text(question.options, selected))
        answer_text = _strip_text(question.answer or "")
        return selected_text == answer_text

    if qtype == "fill_blank":
        return _strip_text(question.answer or "") == _strip_text(selected)

    # single_choice 及默认：label 大写比较
    return (question.answer or "").strip().upper() == selected.strip().upper()


def _display_answer(question: Question) -> str:
    """返回适合用户阅读的标准答案展示文本。"""
    qtype = question.question_type
    if qtype == "multiple_choice":
        return "".join(sorted(dict.fromkeys((question.answer or "").upper())))
    if qtype == "true_false":
        return _strip_text(question.answer or "")
    return (question.answer or "").strip()


async def _load_zone_questions(db: AsyncSession, category: str) -> list[Question]:
    result = await db.execute(
        select(Question)
        .where(Question.category == category, Question.is_active.is_(True))
        .order_by(Question.id)
    )
    return list(result.scalars().all())


async def _load_answered_map(
    db: AsyncSession, phone: str, zone_id: int
) -> dict[int, str]:
    """手机号在该打卡点的最近作答（question_id -> selected_answer，去重取最新）。"""
    result = await db.execute(
        select(ConferenceAnswer.question_id, ConferenceAnswer.selected_answer)
        .where(
            ConferenceAnswer.phone == phone,
            ConferenceAnswer.zone_id == zone_id,
        )
        .order_by(ConferenceAnswer.id.asc())
    )
    answered: dict[int, str] = {}
    for qid, selected in result.all():
        answered[qid] = selected  # 后写覆盖先写 → 保留最新
    return answered


async def grade_zone(
    db: AsyncSession, phone: str, zone: ConferenceZone
) -> dict:
    """按标准答案对手机号在该打卡点的作答逐题判分。

    返回：
      total      题组总题数
      answered   已答题目数（去重）
      correct    答对题数
      completed  是否全部答对（=可发印章）
      results    逐题结果（用于提交后展示对错与正确答案）
    """
    questions = await _load_zone_questions(db, zone.question_category)
    total = len(questions)
    answered_map = await _load_answered_map(db, phone, zone.id)

    results = []
    correct_count = 0
    for q in questions:
        selected = answered_map.get(q.id, "")
        is_correct = bool(selected) and _is_question_correct(q, selected)
        if is_correct:
            correct_count += 1
        results.append(
            {
                "question_id": q.id,
                "question_type": q.question_type,
                "is_correct": is_correct,
                "user_answer": selected,
                "correct_answer": _display_answer(q),
            }
        )

    answered = len(answered_map)
    completed = bool(total) and correct_count == total
    return {
        "total": total,
        "answered": answered,
        "correct": correct_count,
        "completed": completed,
        "results": results,
    }


async def get_zone_progress(
    db: AsyncSession, phone: str, zone: ConferenceZone
) -> dict:
    """返回单打卡点进度：{"done","total","completed"}。通关=全部答对。"""
    grade = await grade_zone(db, phone, zone)
    return {
        "done": grade["answered"],
        "total": grade["total"],
        "completed": grade["completed"],
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
