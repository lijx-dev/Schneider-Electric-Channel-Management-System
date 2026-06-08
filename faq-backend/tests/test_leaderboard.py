"""Regression tests for cumulative quiz leaderboard ranking."""

import pytest

from app.api.v1 import daily as daily_api
from app.core.security import create_access_token
from app.models.record import AnswerRecord
from app.models.user import User


async def create_rank_user(session, suffix, *, company="Test Company", total_score=0):
    user = User(
        openid=f"leaderboard_openid_{suffix}",
        nickname=f"Rank User {suffix}",
        phone=f"1390000{int(suffix):04d}",
        real_name=f"Rank User {suffix}",
        province="Shanghai",
        company=company,
        total_score=total_score,
        correct_count=0,
        total_count=0,
    )
    session.add(user)
    await session.flush()
    return user


def add_weekly_record(session, user, question, *, is_correct, time_spent, quiz_date):
    session.add(
        AnswerRecord(
            user_id=user.id,
            question_id=question.id,
            selected_answer="A" if is_correct else "B",
            is_correct=is_correct,
            score=1 if is_correct else 0,
            time_spent=time_spent,
            source="daily",
            quiz_date=quiz_date,
        )
    )


@pytest.mark.asyncio
async def test_total_leaderboard_ranks_by_all_daily_correct_count_then_total_time(
    client,
    test_user,
    test_questions,
    test_db,
):
    """The total leaderboard should rank by all daily answers, not energy score."""

    viewer, token = test_user
    quiz_date = daily_api.get_quiz_date()

    async with test_db() as session:
        more_correct = await create_rank_user(session, "0001", total_score=1)
        faster_equal = await create_rank_user(session, "0002", total_score=2)
        slower_equal = await create_rank_user(session, "0003", total_score=100)
        high_energy_low_quiz = await create_rank_user(session, "0004", total_score=999)

        for question, spent in zip(test_questions[:3], [100, 60, 40]):
            add_weekly_record(session, more_correct, question, is_correct=True, time_spent=spent, quiz_date=quiz_date)

        add_weekly_record(session, faster_equal, test_questions[0], is_correct=True, time_spent=10, quiz_date=quiz_date)
        add_weekly_record(session, faster_equal, test_questions[1], is_correct=True, time_spent=10, quiz_date=quiz_date)
        add_weekly_record(session, faster_equal, test_questions[2], is_correct=False, time_spent=10, quiz_date=quiz_date)
        add_weekly_record(session, slower_equal, test_questions[0], is_correct=True, time_spent=20, quiz_date=quiz_date)
        add_weekly_record(session, slower_equal, test_questions[1], is_correct=True, time_spent=50, quiz_date=quiz_date)
        add_weekly_record(session, slower_equal, test_questions[2], is_correct=False, time_spent=20, quiz_date=quiz_date)
        add_weekly_record(session, high_energy_low_quiz, test_questions[0], is_correct=True, time_spent=1, quiz_date="2026-01-05")
        add_weekly_record(session, viewer, test_questions[0], is_correct=True, time_spent=15, quiz_date=quiz_date)

        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/leaderboard", params={"limit": 10, "scope": "total"}, headers=headers)

    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert [row["user_id"] for row in rows[:5]] == [
        more_correct.id,
        faster_equal.id,
        slower_equal.id,
        high_energy_low_quiz.id,
        viewer.id,
    ]
    assert rows[0]["weekly_correct_count"] == 3
    assert rows[0]["weekly_time_spent"] == 200
    assert rows[1]["weekly_correct_count"] == rows[2]["weekly_correct_count"] == 2
    assert rows[1]["weekly_time_spent"] < rows[2]["weekly_time_spent"]


@pytest.mark.asyncio
async def test_user_rank_uses_same_cumulative_quiz_leaderboard_rules(
    client,
    test_user,
    test_questions,
    test_db,
):
    """The personal rank endpoint should match cumulative quiz leaderboard order."""

    viewer, token = test_user
    quiz_date = daily_api.get_quiz_date()

    async with test_db() as session:
        first = await create_rank_user(session, "0011", total_score=1)
        second = await create_rank_user(session, "0012", total_score=999)

        add_weekly_record(session, first, test_questions[0], is_correct=True, time_spent=20, quiz_date=quiz_date)
        add_weekly_record(session, first, test_questions[1], is_correct=True, time_spent=20, quiz_date=quiz_date)
        add_weekly_record(session, second, test_questions[0], is_correct=True, time_spent=50, quiz_date=quiz_date)
        add_weekly_record(session, second, test_questions[1], is_correct=False, time_spent=50, quiz_date=quiz_date)
        add_weekly_record(session, viewer, test_questions[0], is_correct=True, time_spent=60, quiz_date=quiz_date)
        add_weekly_record(session, viewer, test_questions[1], is_correct=False, time_spent=60, quiz_date=quiz_date)

        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/user/rank", params={"user_id": viewer.id, "scope": "total"}, headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["rank"] == 3
    assert data["weekly_correct_count"] == 1
    assert data["weekly_time_spent"] == 120


@pytest.mark.asyncio
async def test_schneider_electric_employees_are_excluded_from_leaderboards(
    client,
    test_user,
    test_questions,
    test_db,
):
    """Schneider Electric employees can answer questions but do not enter rankings."""

    viewer, token = test_user
    quiz_date = daily_api.get_quiz_date()

    async with test_db() as session:
        external_user = await create_rank_user(session, "0021", company="Partner Company")
        internal_user = await create_rank_user(session, "0022", company="施耐德电气")

        add_weekly_record(session, internal_user, test_questions[0], is_correct=True, time_spent=1, quiz_date=quiz_date)
        add_weekly_record(session, internal_user, test_questions[1], is_correct=True, time_spent=1, quiz_date=quiz_date)
        add_weekly_record(session, external_user, test_questions[0], is_correct=True, time_spent=30, quiz_date=quiz_date)
        add_weekly_record(session, viewer, test_questions[0], is_correct=False, time_spent=40, quiz_date=quiz_date)

        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    leaderboard_resp = await client.get("/api/leaderboard", params={"limit": 10, "scope": "total"}, headers=headers)
    rows = leaderboard_resp.json()["data"]

    assert internal_user.id not in [row["user_id"] for row in rows]
    assert rows[0]["user_id"] == external_user.id

    internal_token = create_access_token(internal_user.id)
    rank_resp = await client.get(
        "/api/user/rank",
        params={"user_id": internal_user.id, "scope": "total"},
        headers={"Authorization": f"Bearer {internal_token}"},
    )

    assert rank_resp.status_code == 200
    data = rank_resp.json()["data"]
    assert data["rank"] == "-"
    assert data["weekly_correct_count"] == 2
