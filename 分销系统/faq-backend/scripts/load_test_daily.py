"""Simple async load test for the daily quiz flow.

Runs against the FastAPI app in-process with a temporary SQLite database so
we can quickly smoke-test concurrency without external dependencies.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
import sys

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.question import Question
from app.models.record import DailyQuizRound
from app.models.user import User

LOAD_TEST_DB_PATH = ROOT_DIR / "tmp" / "load_test_daily.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{LOAD_TEST_DB_PATH.as_posix()}"
GET_CONCURRENCY = 30
GET_REQUESTS = 120
SUBMIT_CONCURRENCY = 10


@dataclass
class RequestStat:
    latency_ms: float
    status_code: int


async def setup_database(session_factory: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    async with session_factory() as session:
        user = User(
            openid="load_test_openid",
            nickname="LoadTestUser",
            phone="13900000001",
            total_score=0,
            correct_count=0,
            total_count=0,
        )
        session.add(user)

        for idx in range(20):
            session.add(
                Question(
                    question_type="single_choice",
                    content=f"Load test question {idx + 1}?",
                    options=["Option A", "Option B", "Option C", "Option D"],
                    answer="A",
                    difficulty=1,
                    is_active=True,
                )
            )

        await session.commit()
        await session.refresh(user)

    token = create_access_token(user.id)
    return user.id, token


async def run_get_benchmark(client: AsyncClient, user_id: str, token: str) -> list[RequestStat]:
    semaphore = asyncio.Semaphore(GET_CONCURRENCY)
    headers = {"Authorization": f"Bearer {token}"}

    async def one_request() -> RequestStat:
        async with semaphore:
            started = time.perf_counter()
            response = await client.get(
                "/api/daily/quiz",
                params={"user_id": user_id},
                headers=headers,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            return RequestStat(latency_ms=latency_ms, status_code=response.status_code)

    return await asyncio.gather(*(one_request() for _ in range(GET_REQUESTS)))


async def run_submit_benchmark(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: str,
    token: str,
) -> list[RequestStat]:
    headers = {"Authorization": f"Bearer {token}"}

    async with session_factory() as session:
        round_result = await session.execute(select(DailyQuizRound))
        daily_round = round_result.scalar_one()
        question_ids = [int(item) for item in daily_round.question_ids.split(",") if item]

    semaphore = asyncio.Semaphore(SUBMIT_CONCURRENCY)

    async def one_submit(question_id: int) -> RequestStat:
        async with semaphore:
            started = time.perf_counter()
            response = await client.post(
                "/api/daily/submit",
                json={
                    "user_id": user_id,
                    "question_id": question_id,
                    "selected_answer": "A",
                    "time_spent": 5,
                },
                headers=headers,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            return RequestStat(latency_ms=latency_ms, status_code=response.status_code)

    return await asyncio.gather(*(one_submit(question_id) for question_id in question_ids))


def summarize(label: str, stats: list[RequestStat]) -> None:
    latencies = sorted(item.latency_ms for item in stats)
    success_count = sum(1 for item in stats if item.status_code == 200)
    error_count = len(stats) - success_count

    def percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))
        return values[index]

    print(f"[{label}] total={len(stats)} success={success_count} error={error_count}")
    print(
        f"[{label}] avg={statistics.mean(latencies):.2f}ms "
        f"p50={percentile(latencies, 0.50):.2f}ms "
        f"p95={percentile(latencies, 0.95):.2f}ms "
        f"max={max(latencies):.2f}ms"
    )


async def main() -> None:
    LOAD_TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOAD_TEST_DB_PATH.exists():
        LOAD_TEST_DB_PATH.unlink()

    engine = create_async_engine(TEST_DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    try:
        user_id, token = await setup_database(session_factory)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            get_stats = await run_get_benchmark(client, user_id, token)
            summarize("daily_quiz_get", get_stats)

            submit_stats = await run_submit_benchmark(client, session_factory, user_id, token)
            summarize("daily_quiz_submit", submit_stats)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
