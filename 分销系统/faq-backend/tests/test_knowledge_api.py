from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.knowledge import KnowledgeItem
from app.models.question import Question
from app.models.user import User


async def create_user(
    test_db: async_sessionmaker[AsyncSession],
    user_id: str = "knowledge-user",
) -> tuple[User, str]:
    async with test_db() as session:
        user = User(id=user_id, openid=f"openid-{user_id}", nickname="Knowledge User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        token = create_access_token(user.id)
        return user, token


async def create_question(
    test_db: async_sessionmaker[AsyncSession],
    explanation: str = "A saved explanation knowledge point.",
) -> Question:
    async with test_db() as session:
        question = Question(
            question_type="single_choice",
            content="Question content must not appear in knowledge responses",
            options=["A", "B"],
            answer="A",
            explanation=explanation,
            difficulty=1,
            category="Test",
            is_active=True,
        )
        session.add(question)
        await session.commit()
        await session.refresh(question)
        return question


@pytest.mark.asyncio
async def test_create_knowledge_item_saves_explanation_only(
    client: AsyncClient,
    test_db: async_sessionmaker[AsyncSession],
):
    user, token = await create_user(test_db)
    question = await create_question(test_db)

    response = await client.post(
        "/api/knowledge",
        json={"user_id": user.id, "question_id": question.id, "source": "bank"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["explanation"] == "A saved explanation knowledge point."
    assert body["source"] == "bank"
    assert body["already_saved"] is False
    assert "content" not in body
    assert "answer" not in body
    assert "options" not in body


@pytest.mark.asyncio
async def test_create_knowledge_item_is_idempotent(
    client: AsyncClient,
    test_db: async_sessionmaker[AsyncSession],
):
    user, token = await create_user(test_db, "knowledge-user-2")
    question = await create_question(test_db, "Duplicate saves create one item.")

    payload = {"user_id": user.id, "question_id": question.id, "source": "daily"}
    headers = {"Authorization": f"Bearer {token}"}
    first = await client.post("/api/knowledge", json=payload, headers=headers)
    second = await client.post("/api/knowledge", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["already_saved"] is False
    assert second.json()["data"]["already_saved"] is True

    async with test_db() as session:
        result = await session.execute(select(KnowledgeItem))
        assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_list_knowledge_items_returns_explanations_only(
    client: AsyncClient,
    test_db: async_sessionmaker[AsyncSession],
):
    user, token = await create_user(test_db, "knowledge-user-3")
    question = await create_question(test_db, "The list contains only the explanation.")
    async with test_db() as session:
        session.add(
            KnowledgeItem(
                user_id=user.id,
                question_id=question.id,
                explanation=question.explanation or "",
                source="bank",
            )
        )
        await session.commit()

    response = await client.get(
        "/api/knowledge",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["explanation"] == "The list contains only the explanation."
    assert "question_id" not in items[0]
    assert "content" not in items[0]
    assert "answer" not in items[0]
    assert "options" not in items[0]


@pytest.mark.asyncio
async def test_delete_knowledge_item_enforces_ownership(
    client: AsyncClient,
    test_db: async_sessionmaker[AsyncSession],
):
    owner, owner_token = await create_user(test_db, "knowledge-owner")
    other, other_token = await create_user(test_db, "knowledge-other")
    question = await create_question(test_db, "Only the owner can delete this explanation.")
    async with test_db() as session:
        item = KnowledgeItem(
            user_id=owner.id,
            question_id=question.id,
            explanation=question.explanation or "",
            source="bank",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    forbidden = await client.delete(
        f"/api/knowledge/{item_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    allowed = await client.delete(
        f"/api/knowledge/{item_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert other.id != owner.id
    assert forbidden.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["data"]["deleted"] is True
