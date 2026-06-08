"""Knowledge set APIs for saved explanation snapshots."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_same_user, get_current_user_id
from app.db.session import get_db
from app.models.knowledge import KnowledgeItem
from app.models.question import Question

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

ALLOWED_SOURCES = {"daily", "bank", "practice"}


class KnowledgeCreate(BaseModel):
    user_id: str
    question_id: int
    source: str = Field(default="bank", max_length=20)


def serialize_item(item: KnowledgeItem, already_saved: bool | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "id": item.id,
        "explanation": item.explanation,
        "source": item.source,
        "created_at": item.created_at.isoformat() if isinstance(item.created_at, datetime) else None,
    }
    if already_saved is not None:
        data["already_saved"] = already_saved
    return data


@router.get("")
async def list_knowledge_items(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    stmt = (
        select(KnowledgeItem)
        .where(KnowledgeItem.user_id == current_user_id)
        .order_by(KnowledgeItem.created_at.desc(), KnowledgeItem.id.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "items": [serialize_item(item) for item in items],
        },
    }


@router.post("")
async def create_knowledge_item(
    body: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, body.user_id)
    source = body.source if body.source in ALLOWED_SOURCES else "bank"

    existing_stmt = select(KnowledgeItem).where(
        KnowledgeItem.user_id == user_id,
        KnowledgeItem.question_id == body.question_id,
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {"code": 0, "data": serialize_item(existing, already_saved=True)}

    question_stmt = select(Question).where(Question.id == body.question_id)
    question_result = await db.execute(question_stmt)
    question = question_result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    explanation = (question.explanation or "").strip()
    if not explanation:
        raise HTTPException(status_code=400, detail="Question has no explanation")

    item = KnowledgeItem(
        user_id=user_id,
        question_id=question.id,
        explanation=explanation,
        source=source,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()
        if existing:
            return {"code": 0, "data": serialize_item(existing, already_saved=True)}
        raise

    await db.refresh(item)
    return {"code": 0, "data": serialize_item(item, already_saved=False)}


@router.delete("/{item_id}")
async def delete_knowledge_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.id == item_id,
        KnowledgeItem.user_id == current_user_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    await db.delete(item)
    await db.flush()
    return {"code": 0, "data": {"deleted": True}}
