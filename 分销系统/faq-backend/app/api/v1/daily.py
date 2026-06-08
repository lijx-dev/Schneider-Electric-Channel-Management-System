"""Weekly quiz and study record APIs."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_same_user, get_current_user_id
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.question import Question
from app.models.record import AnswerRecord, DailyQuizRound
from app.models.user import User

logger = get_logger(__name__)
router = APIRouter(tags=["每周答题"])

APP_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")
QUIZ_REFRESH_WEEKDAY = 0
QUIZ_REFRESH_HOUR = 9
QUIZ_QUESTION_COUNT = 10


def random_order_clause(db: AsyncSession):
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    return func.rand() if dialect_name == "mysql" else func.random()


def parse_question_ids(raw_value: str | None) -> list[int]:
    if not raw_value:
        return []

    question_ids: list[int] = []
    for item in str(raw_value).split(","):
        text = item.strip()
        if not text:
            continue
        if not text.isdigit():
            return []
        question_ids.append(int(text))
    return question_ids


def normalize_true_false_value(value: str) -> str:
    if value is None:
        return ""

    text = str(value).strip().upper()
    mapping = {
        "A": "TRUE",
        "B": "FALSE",
        "对": "TRUE",
        "正确": "TRUE",
        "TRUE": "TRUE",
        "是": "TRUE",
        "错": "FALSE",
        "错误": "FALSE",
        "FALSE": "FALSE",
        "否": "FALSE",
    }
    return mapping.get(text, text)


def get_local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def get_current_cycle_start(now: datetime | None = None) -> datetime:
    current = now or get_local_now()
    if current.tzinfo is not None:
        current = current.astimezone(APP_TIMEZONE)
    else:
        current = current.replace(tzinfo=APP_TIMEZONE)

    cycle_start = current.replace(hour=QUIZ_REFRESH_HOUR, minute=0, second=0, microsecond=0)
    cycle_start = cycle_start - timedelta(days=current.weekday() - QUIZ_REFRESH_WEEKDAY)

    if current < cycle_start:
        cycle_start -= timedelta(days=7)

    return cycle_start


def get_quiz_date(now: datetime | None = None) -> str:
    return get_current_cycle_start(now).strftime("%Y-%m-%d")


def get_quiz_time_window(quiz_date: str) -> tuple[datetime, datetime]:
    """Map the weekly quiz key to its real answer window."""

    cycle_start = datetime.strptime(quiz_date, "%Y-%m-%d").replace(
        hour=QUIZ_REFRESH_HOUR,
        tzinfo=APP_TIMEZONE,
    )
    cycle_end = cycle_start + timedelta(days=7)
    return cycle_start, cycle_end


async def pick_quiz_question_ids(db: AsyncSession) -> list[int]:
    q_stmt = (
        select(Question.id)
        .where(and_(Question.is_active == True, Question.question_type != "short_answer"))
        .order_by(random_order_clause(db))
        .limit(QUIZ_QUESTION_COUNT)
    )
    q_result = await db.execute(q_stmt)
    return [row[0] for row in q_result.all()]


async def get_quiz_target_count(db: AsyncSession) -> int:
    count_stmt = select(func.count(Question.id)).where(
        Question.is_active == True,
        Question.question_type != "short_answer",
    )
    count_result = await db.execute(count_stmt)
    available_count = count_result.scalar() or 0
    return min(available_count, QUIZ_QUESTION_COUNT)


async def is_valid_quiz_round(db: AsyncSession, question_ids: list[int]) -> bool:
    if len(question_ids) != len(set(question_ids)):
        return False

    expected_count = await get_quiz_target_count(db)
    if len(question_ids) != expected_count:
        return False

    if not question_ids:
        return expected_count == 0

    question_stmt = select(func.count(Question.id)).where(
        Question.id.in_(question_ids),
        Question.is_active == True,
        Question.question_type != "short_answer",
    )
    question_result = await db.execute(question_stmt)
    return (question_result.scalar() or 0) == len(question_ids)


async def ensure_quiz_round(
    db: AsyncSession,
    quiz_date: str,
) -> tuple[DailyQuizRound | None, list[int]]:
    round_stmt = (
        select(DailyQuizRound)
        .where(DailyQuizRound.quiz_date == quiz_date)
        .order_by(DailyQuizRound.id.desc())
    )
    round_result = await db.execute(round_stmt)
    quiz_rounds = round_result.scalars().all()
    quiz_round = quiz_rounds[0] if quiz_rounds else None

    if len(quiz_rounds) > 1:
        logger.warning("quiz_round_duplicate_rows", date=quiz_date, row_count=len(quiz_rounds))

    if not quiz_round:
        ids = await pick_quiz_question_ids(db)
        if not ids:
            return None, []

        quiz_round = DailyQuizRound(
            quiz_date=quiz_date,
            question_ids=",".join(str(i) for i in ids),
            question_count=len(ids),
        )
        db.add(quiz_round)
        try:
            await db.flush()
            logger.info("quiz_round_created", date=quiz_date, count=len(ids))
        except IntegrityError:
            await db.rollback()
            round_result = await db.execute(round_stmt)
            quiz_rounds = round_result.scalars().all()
            quiz_round = quiz_rounds[0] if quiz_rounds else None
            if not quiz_round:
                raise HTTPException(status_code=500, detail="题目生成失败，请重试")
            ids = parse_question_ids(quiz_round.question_ids)

        return quiz_round, ids

    ids = parse_question_ids(quiz_round.question_ids)
    if ids and await is_valid_quiz_round(db, ids):
        return quiz_round, ids

    logger.warning(
        "quiz_round_invalid_question_ids",
        date=quiz_date,
        raw_question_ids=quiz_round.question_ids,
        reason="invalid_count_or_contains_inactive_or_short_answer",
    )
    ids = await pick_quiz_question_ids(db)
    if not ids:
        return quiz_round, []

    quiz_round.question_ids = ",".join(str(i) for i in ids)
    quiz_round.question_count = len(ids)
    await db.flush()
    logger.info("quiz_round_rebuilt", date=quiz_date, count=len(ids), reason="invalid_question_ids")
    return quiz_round, ids


@router.get("/daily/quiz")
async def get_daily_quiz(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, user_id)
    quiz_date = get_quiz_date()

    quiz_round, question_ids = await ensure_quiz_round(db, quiz_date)
    if not question_ids:
        return {
            "code": 0,
            "data": {
                "quiz_date": quiz_date,
                "questions": [],
                "is_completed": False,
                "answered_count": 0,
                "total_count": 0,
                "score": 0,
                "correct_count": 0,
            },
        }

    rec_stmt = (
        select(AnswerRecord)
        .where(
            AnswerRecord.user_id == user_id,
            AnswerRecord.source == "daily",
            AnswerRecord.question_id.in_(question_ids),
            AnswerRecord.quiz_date == quiz_date,
        )
    )
    rec_result = await db.execute(rec_stmt)
    user_records = {record.question_id: record for record in rec_result.scalars().all()}

    q_stmt = select(Question).where(Question.id.in_(question_ids))
    q_result = await db.execute(q_stmt)
    questions_map = {question.id: question for question in q_result.scalars().all()}

    if len(questions_map) != len(set(question_ids)):
        logger.warning(
            "quiz_round_question_missing",
            date=quiz_date,
            question_ids=question_ids,
            loaded_ids=sorted(questions_map.keys()),
        )
        if quiz_round:
            quiz_round.question_ids = ""
            quiz_round.question_count = 0
            await db.flush()

        quiz_round, question_ids = await ensure_quiz_round(db, quiz_date)
        if not question_ids:
            return {
                "code": 0,
                "data": {
                    "quiz_date": quiz_date,
                    "questions": [],
                    "is_completed": False,
                    "answered_count": 0,
                    "total_count": 0,
                    "score": 0,
                    "correct_count": 0,
                },
            }

        q_stmt = select(Question).where(Question.id.in_(question_ids))
        q_result = await db.execute(q_stmt)
        questions_map = {question.id: question for question in q_result.scalars().all()}

    questions = []
    is_completed = len(user_records) >= len(question_ids)

    for qid in question_ids:
        question = questions_map.get(qid)
        if not question:
            continue

        question_data = question.to_dict(hide_answer=not is_completed and qid not in user_records)
        if qid in user_records:
            record = user_records[qid]
            question_data["user_answer"] = record.selected_answer
            question_data["is_correct"] = record.is_correct
            question_data["score"] = record.score
            question_data["answer"] = question.answer

        questions.append(question_data)

    total_score = sum(record.score for record in user_records.values())
    correct_count = sum(1 for record in user_records.values() if record.is_correct)

    return {
        "code": 0,
        "data": {
            "quiz_date": quiz_date,
            "questions": questions,
            "is_completed": is_completed,
            "answered_count": len(user_records),
            "total_count": len(question_ids),
            "score": total_score,
            "correct_count": correct_count,
        },
    }


class DailyAnswerSubmit(BaseModel):
    user_id: str
    question_id: int
    selected_answer: str
    time_spent: int = 0


@router.post("/daily/submit")
async def submit_daily_answer(
    body: DailyAnswerSubmit,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, body.user_id)
    quiz_date = get_quiz_date()
    quiz_round, question_ids = await ensure_quiz_round(db, quiz_date)
    if not quiz_round or not question_ids:
        raise HTTPException(status_code=400, detail="本周题目尚未生成")

    if body.question_id not in question_ids:
        raise HTTPException(status_code=400, detail="该题目不在本周答题范围内")

    dup_stmt = select(AnswerRecord).where(
        AnswerRecord.user_id == user_id,
        AnswerRecord.question_id == body.question_id,
        AnswerRecord.source == "daily",
        AnswerRecord.quiz_date == quiz_date,
    )
    dup_result = await db.execute(dup_stmt)
    if dup_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该题目已作答，不可重复提交")

    q_stmt = select(Question).where(Question.id == body.question_id)
    q_result = await db.execute(q_stmt)
    question = q_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=400, detail="题目不存在")

    if question.question_type == "true_false":
        is_correct = normalize_true_false_value(body.selected_answer) == normalize_true_false_value(question.answer)
    else:
        is_correct = body.selected_answer.strip().upper() == question.answer.strip().upper()

    score = 1 if is_correct else 0

    record = AnswerRecord(
        user_id=user_id,
        question_id=body.question_id,
        selected_answer=body.selected_answer,
        is_correct=is_correct,
        score=score,
        time_spent=body.time_spent,
        source="daily",
        quiz_date=quiz_date,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="该题目已作答，不可重复提交")

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            total_score=User.total_score + score,
            total_count=User.total_count + 1,
            correct_count=User.correct_count + (1 if is_correct else 0),
            last_study_at=get_local_now().replace(tzinfo=None),
        )
    )

    answered_stmt = select(func.count(AnswerRecord.id)).where(
        AnswerRecord.user_id == user_id,
        AnswerRecord.source == "daily",
        AnswerRecord.question_id.in_(question_ids),
        AnswerRecord.quiz_date == quiz_date,
    )
    answered_result = await db.execute(answered_stmt)
    answered_count = answered_result.scalar() or 0
    is_completed = answered_count >= len(question_ids)

    return {
        "code": 0,
        "data": {
            "is_correct": is_correct,
            "correct_answer": question.answer,
            "explanation": question.explanation or "",
            "score": score,
            "is_completed": is_completed,
        },
    }


@router.get("/study/records")
async def get_study_records(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, user_id)

    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    records_stmt = (
        select(AnswerRecord)
        .where(AnswerRecord.user_id == user_id)
        .order_by(AnswerRecord.created_at.desc())
    )
    records_result = await db.execute(records_stmt)
    records = records_result.scalars().all()

    question_ids = [record.question_id for record in records[:20]]
    questions_map = {}
    if question_ids:
        questions_stmt = select(Question).where(Question.id.in_(question_ids))
        questions_result = await db.execute(questions_stmt)
        questions_map = {question.id: question for question in questions_result.scalars().all()}

    total_answers = len(records)
    total_correct = sum(1 for record in records if record.is_correct)
    total_score = sum(record.score or 0 for record in records)
    accuracy = round((total_correct / total_answers) * 100, 1) if total_answers else 0
    daily_answers = sum(1 for record in records if record.source == "daily")
    practice_answers = sum(1 for record in records if record.source in {"bank", "practice"})
    practice_duration_seconds = sum(
        record.time_spent or 0 for record in records if record.source in {"bank", "practice"}
    )

    active_days = set()
    today_key = get_local_now().strftime("%Y-%m-%d")
    today_answers = 0
    week_counts: dict[str, int] = {}
    local_now = get_local_now()
    for offset in range(6, -1, -1):
        day = (local_now - timedelta(days=offset)).strftime("%Y-%m-%d")
        week_counts[day] = 0

    for record in records:
        if not record.created_at:
            continue
        day_key = record.created_at.strftime("%Y-%m-%d")
        active_days.add(day_key)
        if day_key in week_counts:
            week_counts[day_key] += 1
        if day_key == today_key:
            today_answers += 1

    recent_records = []
    for record in records[:12]:
        question = questions_map.get(record.question_id)
        question_content = ""
        question_type = ""
        if question:
            question_content = question.content or ""
            question_type = question.question_type
        recent_records.append(
            {
                "id": record.id,
                "question_id": record.question_id,
                "question_preview": question_content,
                "question_content": question_content,
                "question_type": question_type,
                "selected_answer": record.selected_answer,
                "is_correct": record.is_correct,
                "score": record.score,
                "source": record.source,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
        )

    week_activity = [
        {
            "date": day,
            "count": count,
            "label": day[5:],
        }
        for day, count in week_counts.items()
    ]

    return {
        "code": 0,
        "data": {
            "summary": {
                "total_answers": total_answers,
                "total_correct": total_correct,
                "accuracy": accuracy,
                "total_score": total_score,
                "daily_answers": daily_answers,
                "practice_answers": practice_answers,
                "practice_duration_seconds": practice_duration_seconds,
                "active_days": len(active_days),
                "today_answers": today_answers,
                "nickname": user.nickname if user else "",
                "real_name": user.real_name if user else "",
            },
            "week_activity": week_activity,
            "recent_records": recent_records,
        },
    }
