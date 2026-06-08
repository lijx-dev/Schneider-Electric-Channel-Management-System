"""
Test fixtures for daily quiz regression tests.

Uses SQLite in-memory DB to test the real FastAPI app with dependency overrides.
"""
import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.models.energy import EnergyRedemptionRecord, EnergyTransaction  # noqa: F401
from app.models.lottery import LotteryDraw, LotteryWinner  # noqa: F401
from app.main import app
from app.models.question import Question
from app.models.record import AnswerRecord, DailyQuizRound  # noqa: F401
from app.models.monthly import MonthlyRankSnapshot  # noqa: F401
from app.models.user import User

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db():
    """Create a fresh in-memory DB and override the app dependency."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    yield session_factory

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db):
    """Create a test user and return (user, token)."""
    async with test_db() as session:
        user = User(
            openid="test_openid_daily_001",
            nickname="DailyTestUser",
            phone="13800000099",
            real_name="Test Real Name",
            province="上海",
            company="Test Company",
            total_score=0,
            correct_count=0,
            total_count=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(user.id, expires_delta=timedelta(hours=1))
    return user, token


@pytest_asyncio.fixture
async def test_questions(test_db):
    """Create enough active questions for daily quiz and bank regression tests."""
    async with test_db() as session:
        questions = []
        for i in range(18):
            q = Question(
                question_type="single_choice",
                content=f"Test question {i + 1}?",
                options=["Option A", "Option B", "Option C", "Option D"],
                answer="A",
                difficulty=1,
                is_active=True,
            )
            session.add(q)
            questions.append(q)

        for i in range(2):
            q = Question(
                question_type="short_answer",
                content=f"Short answer question {i + 1}?",
                options=None,
                answer=f"Reference answer {i + 1}",
                difficulty=2,
                is_active=True,
            )
            session.add(q)
            questions.append(q)

        await session.commit()
        for q in questions:
            await session.refresh(q)
        return questions


@pytest_asyncio.fixture
async def client(test_db):
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
