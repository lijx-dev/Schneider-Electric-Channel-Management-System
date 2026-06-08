"""
题目相关 API 路由

包含：
- /questions      — 获取答题用的随机题目（隐藏答案）
- /questions/bank  — 浏览题库（按分类分组）
- /answer          — 提交答案
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, func, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_same_user, get_current_user_id
from app.db.session import get_db
from app.models.question import Question
from app.models.record import AnswerRecord
from app.models.user import User
from app.schemas.question import AnswerSubmit

router = APIRouter(tags=["题目"])


def random_order_clause(db: AsyncSession):
    dialect_name = db.bind.dialect.name if db.bind is not None else ""
    return func.rand() if dialect_name == "mysql" else func.random()


def normalize_category_name(value: Optional[str]) -> str:
    text = (value or "").strip()
    return text or "未分类"


def build_category_filter(category: str):
    normalized = normalize_category_name(category)
    if normalized == "未分类":
        return or_(Question.category.is_(None), Question.category == "")
    return Question.category == normalized


@router.get("/questions/bank")
async def get_question_bank(
    category: Optional[str] = None,
    question_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    浏览题库（题库页面用）

    - 不传 category / question_type：返回各分类统计数量
    - 传 category：返回该分类下的题目列表（分页，隐藏答案）
    - 兼容保留 question_type 参数，便于旧页面继续访问
    """
    if not category and not question_type:
        # 返回分类统计
        stmt = (
            select(
                Question.category,
                func.count(Question.id).label("count")
            )
            .where(Question.is_active == True)
            .group_by(Question.category)
            .order_by(func.count(Question.id).desc(), Question.category.asc())
        )
        result = await db.execute(stmt)
        categories = []
        total = 0
        for row in result.all():
            category_name = normalize_category_name(row.category)
            categories.append({
                "category": category_name,
                "count": row.count
            })
            total += row.count

        return {
            "code": 0,
            "data": {
                "total": total,
                "categories": categories
            }
        }

    # 返回指定分类/题型的题目列表（分页）
    offset = (page - 1) * page_size
    filters = [Question.is_active == True]

    if category:
        filters.append(build_category_filter(category))

    if question_type:
        filters.append(Question.question_type == question_type)

    # 查总数
    count_stmt = (
        select(func.count(Question.id))
        .where(*filters)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar()

    # 查列表
    list_stmt = (
        select(Question)
        .where(*filters)
        .order_by(Question.id)
        .offset(offset)
        .limit(page_size)
    )
    list_result = await db.execute(list_stmt)
    questions = list_result.scalars().all()

    return {
        "code": 0,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "questions": [
                q.to_dict(hide_answer=q.question_type != "short_answer")
                for q in questions
            ]
        }
    }


@router.get("/questions/detail/{question_id}")
async def get_question_detail(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """获取单道题目详情（含答案，用于查看解析）"""
    stmt = select(Question).where(Question.id == question_id)
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    return {"code": 0, "data": question.to_dict(hide_answer=False)}


@router.get("/questions")
async def get_questions(
    user_id: Optional[str] = None,
    count: int = 5,
    question_type: str = "single_choice",
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """获取随机题目（答题页用，隐藏答案）"""
    ensure_same_user(current_user_id, user_id)

    stmt = (
        select(Question)
        .where(Question.is_active == True, Question.question_type == question_type)
        .order_by(random_order_clause(db))
        .limit(count)
    )
    result = await db.execute(stmt)
    questions = result.scalars().all()

    return {
        "code": 0,
        "data": [q.to_dict(hide_answer=True) for q in questions]
    }


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


@router.post("/answer")
async def submit_answer(
    answer: AnswerSubmit,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    """提交答案"""
    ensure_same_user(current_user_id, answer.user_id)

    stmt = select(Question).where(Question.id == answer.question_id)
    result = await db.execute(stmt)
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=400, detail="题目不存在")

    # 判断答案是否正确
    if question.question_type == "true_false":
        is_correct = normalize_true_false_value(answer.selected_answer) == normalize_true_false_value(question.answer)
    else:
        is_correct = answer.selected_answer.strip().upper() == question.answer.strip().upper()

    # 计算得分（仅选择题和判断题计分）
    score = 0

    record = AnswerRecord(
        user_id=answer.user_id,
        question_id=answer.question_id,
        selected_answer=answer.selected_answer,
        is_correct=is_correct,
        score=score,
        time_spent=answer.time_spent,
        source="bank",
        quiz_date=None,
    )
    db.add(record)

    await db.execute(
        update(User)
        .where(User.id == answer.user_id)
        .values(
            total_count=User.total_count + 1,
            correct_count=User.correct_count + (1 if is_correct else 0),
            last_study_at=datetime.now(),
        )
    )

    return {
        "code": 0,
        "data": {
            "is_correct": is_correct,
            "correct_answer": question.answer,
            "explanation": question.explanation or "",
            "score": score
        }
    }
