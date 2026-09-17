"""
分销商大会「能量印记·集章」业务逻辑

负责：
- 渠道展区三步计数（conference_activity upsert）
- 展区进度计算（quiz 题组完成度 / channel 三步漏斗）
- 能量印记发放（幂等）
- 能量勋章发放（幂等）
- 展区开放窗口校验
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
    ConferenceActivity,
    ConferenceMedal,
    ConferenceZone,
    ConferenceZoneMark,
)
from app.models.record import AnswerRecord

logger = get_logger(__name__)

APP_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
# 与 app/api/v1/daily.py 保持一致的每周答题刷新周期（周一 09:00）
QUIZ_REFRESH_WEEKDAY = 0
QUIZ_REFRESH_HOUR = 9

# channel 展区步骤3（施能量页浏览）要求次数（模型未配置该计数，固定为 1 次）
ENERGY_VIEW_REQUIRED = 1

# 勋章编码前缀：DY- + 8 位大写字母数字
MEDAL_CODE_PREFIX = "DY-"
MEDAL_CODE_LENGTH = 8


def local_now() -> datetime:
    """Asia/Shanghai 当前时间（带时区）。"""
    return datetime.now(APP_TIMEZONE)


def today_str() -> str:
    """今日日期 YYYY-MM-DD（Asia/Shanghai）。"""
    return local_now().strftime("%Y-%m-%d")


def weekly_quiz_date() -> str:
    """当前每周答题周期键（周一 09:00 起算，与 daily.py 一致）。"""
    now = local_now()
    cycle_start = now.replace(hour=QUIZ_REFRESH_HOUR, minute=0, second=0, microsecond=0)
    cycle_start = cycle_start - timedelta(days=now.weekday() - QUIZ_REFRESH_WEEKDAY)
    if now < cycle_start:
        cycle_start -= timedelta(days=7)
    return cycle_start.strftime("%Y-%m-%d")


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
    """展区开放窗口校验：窗口已设置且当前时间不在窗口内时抛 403。"""
    now = local_now()
    active_from = _as_aware(zone.active_from)
    active_to = _as_aware(zone.active_to)
    if active_from is not None and now < active_from:
        raise HTTPException(status_code=403, detail="大会模块当前未开放")
    if active_to is not None and now > active_to:
        raise HTTPException(status_code=403, detail="大会模块当前未开放")


# ── 活动计数（渠道展区步骤计数）──────────────────────────────────────────

async def record_activity(db: AsyncSession, user_id: str, action_key: str) -> None:
    """按 user_id + action_key + 今日唯一行 upsert 计数 +1。

    并发安全：唯一约束 uq_conf_activity_user_action_date 兜底，
    冲突时回滚重查后自增，保证不丢计数、不产生重复行。
    """
    date = today_str()
    for _attempt in range(2):
        stmt = select(ConferenceActivity).where(
            ConferenceActivity.user_id == user_id,
            ConferenceActivity.action_key == action_key,
            ConferenceActivity.activity_date == date,
        )
        row = (await db.execute(stmt)).scalar_one_or_none()

        if row:
            row.count += 1
            row.updated_at = local_now()
            await db.flush()
            return

        db.add(
            ConferenceActivity(
                user_id=user_id,
                action_key=action_key,
                activity_date=date,
                count=1,
                updated_at=local_now(),
            )
        )
        try:
            await db.flush()
            return
        except IntegrityError:
            await db.rollback()
            continue

    logger.warning(
        "conference_activity_upsert_conflict",
        user_id=user_id,
        action_key=action_key,
    )


async def get_activity_count(
    db: AsyncSession,
    user_id: str,
    action_key: str,
    date: str | None = None,
) -> int:
    """读取指定日期（默认今日）的活动计数。"""
    date = date or today_str()
    result = await db.execute(
        select(func.coalesce(func.sum(ConferenceActivity.count), 0)).where(
            ConferenceActivity.user_id == user_id,
            ConferenceActivity.action_key == action_key,
            ConferenceActivity.activity_date == date,
        )
    )
    return int(result.scalar() or 0)


# ── 展区进度 ─────────────────────────────────────────────────────────────

async def _count_questions_in_category(db: AsyncSession, category: str) -> int:
    from app.models.question import Question

    result = await db.execute(
        select(func.count(Question.id)).where(
            Question.category == category,
            Question.is_active.is_(True),
        )
    )
    return int(result.scalar() or 0)


async def _count_conference_answered_today(
    db: AsyncSession, user_id: str, category: str
) -> int:
    """用户今日已提交的该题组题目数（source='conference'，按 question_id 去重）。"""
    from app.models.question import Question

    result = await db.execute(
        select(func.count(func.distinct(AnswerRecord.question_id)))
        .select_from(AnswerRecord)
        .join(Question, Question.id == AnswerRecord.question_id)
        .where(
            AnswerRecord.user_id == user_id,
            AnswerRecord.source == "conference",
            AnswerRecord.quiz_date == today_str(),
            Question.category == category,
        )
    )
    return int(result.scalar() or 0)


async def _count_daily_answered(db: AsyncSession, user_id: str) -> int:
    """用户当前每周答题周期已答题目数（source='daily'，按 question_id 去重）。"""
    result = await db.execute(
        select(func.count(func.distinct(AnswerRecord.question_id))).where(
            AnswerRecord.user_id == user_id,
            AnswerRecord.source == "daily",
            AnswerRecord.quiz_date == weekly_quiz_date(),
        )
    )
    return int(result.scalar() or 0)


async def get_zone_progress(
    db: AsyncSession, user_id: str, zone: ConferenceZone
) -> dict:
    """返回单展区进度。

    quiz 展区：{"type":"quiz","done","total","completed"}
    channel 展区：{"completed", "daily_quiz":{done,required}, "ai_chat":{...}, "energy_view":{...}}
    """
    if zone.task_type == "channel":
        daily_done = await _count_daily_answered(db, user_id)
        ai_chat_done = await get_activity_count(db, user_id, "ai_chat")
        energy_view_done = await get_activity_count(db, user_id, "energy_view")

        daily_quiz = {
            "done": daily_done,
            "required": zone.required_daily_quiz_count,
        }
        ai_chat = {
            "done": ai_chat_done,
            "required": zone.required_ai_chat_count,
        }
        energy_view = {
            "done": energy_view_done,
            "required": ENERGY_VIEW_REQUIRED,
        }
        completed = (
            daily_done >= zone.required_daily_quiz_count
            and ai_chat_done >= zone.required_ai_chat_count
            and energy_view_done >= ENERGY_VIEW_REQUIRED
        )
        return {
            "completed": completed,
            "daily_quiz": daily_quiz,
            "ai_chat": ai_chat,
            "energy_view": energy_view,
        }

    total = await _count_questions_in_category(db, zone.question_category or "")
    done = await _count_conference_answered_today(db, user_id, zone.question_category or "")
    return {
        "type": "quiz",
        "done": done,
        "total": total,
        "completed": bool(total) and done >= total,
    }


# ── 印记 / 勋章发放（均幂等）──────────────────────────────────────────────

async def grant_zone_mark(db: AsyncSession, user_id: str, zone_id: int) -> bool:
    """发放展区能量印记。已存在（唯一约束幂等）返回 False，新增返回 True。"""
    existing = await db.execute(
        select(ConferenceZoneMark.id).where(
            ConferenceZoneMark.user_id == user_id,
            ConferenceZoneMark.zone_id == zone_id,
        )
    )
    if existing.scalar_one_or_none():
        return False

    db.add(
        ConferenceZoneMark(
            user_id=user_id,
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


async def maybe_record_ai_chat(
    user_id: str, db: Optional[AsyncSession] = None
) -> None:
    """母线豆包成功提问后，若用户处于大会白名单则 ai_chat 计数 +1。

    仅白名单用户计数；不改变问答主流程；任何异常只记日志。
    未传 db 时自行打开会话（适配 WebSocket 无请求级会话的场景）。
    """
    try:
        if db is None:
            from app.db.session import AsyncSessionLocal

            async with AsyncSessionLocal() as own_db:
                await _record_ai_chat_inner(own_db, user_id)
        else:
            await _record_ai_chat_inner(db, user_id)
    except Exception as exc:
        logger.warning(
            "conference_ai_chat_count_failed",
            user_id=user_id,
            error=str(exc),
        )


async def _record_ai_chat_inner(db: AsyncSession, user_id: str) -> None:
    from app.models.user import User

    whitelisted = await db.scalar(
        select(User.conference_whitelisted).where(User.id == user_id)
    )
    if not whitelisted:
        return
    await record_activity(db, user_id, "ai_chat")
    await db.commit()


async def try_grant_medal(
    db: AsyncSession, user_id: str
) -> Optional[ConferenceMedal]:
    """集齐当前全部启用展区印记后自动发放勋章。

    - 查询所有 is_active=1 的展区
    - 若用户已集齐对应印记 → 创建 conference_medals（user_id 唯一幂等）
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
            ConferenceZoneMark.user_id == user_id,
            ConferenceZoneMark.zone_id.in_([z.id for z in zones]),
        )
    )
    marked_zone_ids = set(marks.scalars().all())
    active_zone_ids = {z.id for z in zones}

    if not active_zone_ids.issubset(marked_zone_ids):
        return None

    medal = ConferenceMedal(
        user_id=user_id,
        medal_code=_generate_medal_code(),
        zone_count=len(active_zone_ids),
        granted_at=local_now(),
    )
    db.add(medal)
    try:
        await db.flush()
        return medal
    except IntegrityError:
        # 用户已有一枚勋章（user_id 唯一约束），幂等返回 None
        await db.rollback()
        return None
