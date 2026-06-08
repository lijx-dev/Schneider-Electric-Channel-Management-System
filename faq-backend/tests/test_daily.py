"""Regression tests for weekly quiz and study record flows."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.api.v1 import daily as daily_api
from app.models.question import Question
from app.models.record import AnswerRecord, DailyQuizRound
from app.models.user import User as UserModel


@pytest.mark.asyncio
async def test_get_daily_quiz_creates_round_with_target_count_questions(client, test_user, test_questions):
    """GET /api/daily/quiz should create one weekly round with the configured target count."""

    user, token = test_user
    resp = await client.get(
        "/api/daily/quiz",
        params={"user_id": user.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["questions"]) == daily_api.QUIZ_QUESTION_COUNT
    assert data["total_count"] == daily_api.QUIZ_QUESTION_COUNT
    assert data["is_completed"] is False
    assert data["answered_count"] == 0
    assert all(question["question_type"] != "short_answer" for question in data["questions"])


def test_get_quiz_date_uses_asia_shanghai_timezone():
    """The logical quiz week should respect Asia/Shanghai time instead of UTC."""

    utc_now = datetime(2026, 3, 31, 4, 30, tzinfo=timezone.utc)
    assert daily_api.get_quiz_date(utc_now) == "2026-03-30"


def test_get_quiz_date_before_monday_refresh_uses_previous_week():
    """Before Monday 09:00 Asia/Shanghai, the previous week's round remains active."""

    utc_now = datetime(2026, 4, 6, 0, 30, tzinfo=timezone.utc)
    assert daily_api.get_quiz_date(utc_now) == "2026-03-30"


def test_get_quiz_date_after_monday_refresh_uses_current_week():
    """After Monday 09:00 Asia/Shanghai, a new weekly round starts."""

    utc_now = datetime(2026, 4, 6, 1, 30, tzinfo=timezone.utc)
    assert daily_api.get_quiz_date(utc_now) == "2026-04-06"


@pytest.mark.asyncio
async def test_get_daily_quiz_idempotent(client, test_user, test_questions):
    """Calling GET /api/daily/quiz twice should return the same weekly question set."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    first = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    second = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)

    first_ids = [question["id"] for question in first.json()["data"]["questions"]]
    second_ids = [question["id"] for question in second.json()["data"]["questions"]]
    assert first_ids == second_ids


@pytest.mark.asyncio
async def test_stale_quiz_round_is_rebuilt_to_target_count_non_short_questions(
    client,
    test_user,
    test_questions,
    test_db,
):
    """Invalid old rounds should be rebuilt to the configured active non-short-answer count."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    choice_ids = [question.id for question in test_questions if question.question_type != "short_answer"]
    short_answer_id = next(question.id for question in test_questions if question.question_type == "short_answer")
    stale_ids = choice_ids[:4] + [short_answer_id]

    async with test_db() as session:
        session.add(
            DailyQuizRound(
                quiz_date=daily_api.get_quiz_date(),
                question_ids=",".join(str(question_id) for question_id in stale_ids),
                question_count=len(stale_ids),
            )
        )
        await session.commit()

    resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert len(data["questions"]) == daily_api.QUIZ_QUESTION_COUNT
    assert all(question["question_type"] != "short_answer" for question in data["questions"])


@pytest.mark.asyncio
async def test_submit_correct_answer(client, test_user, test_questions):
    """Submitting a correct weekly answer should score one point."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    quiz_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    first_question = quiz_resp.json()["data"]["questions"][0]

    submit_resp = await client.post(
        "/api/daily/submit",
        json={
            "user_id": user.id,
            "question_id": first_question["id"],
            "selected_answer": "A",
            "time_spent": 5,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200
    result = submit_resp.json()["data"]
    assert result["is_correct"] is True
    assert result["score"] == 1


@pytest.mark.asyncio
async def test_daily_submit_returns_question_explanation(client, test_user, test_db):
    """Weekly answer feedback should include the question explanation."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    async with test_db() as session:
        question = Question(
            question_type="single_choice",
            content="Question with explanation?",
            options=["Option A", "Option B", "Option C", "Option D"],
            answer="A",
            explanation="Because option A matches the product rule.",
            difficulty=1,
            is_active=True,
        )
        session.add(question)
        await session.commit()
        await session.refresh(question)

        session.add(
            DailyQuizRound(
                quiz_date=daily_api.get_quiz_date(),
                question_ids=str(question.id),
                question_count=1,
            )
        )
        await session.commit()

    submit_resp = await client.post(
        "/api/daily/submit",
        json={
            "user_id": user.id,
            "question_id": question.id,
            "selected_answer": "A",
            "time_spent": 5,
        },
        headers=headers,
    )

    assert submit_resp.status_code == 200
    assert submit_resp.json()["data"]["explanation"] == "Because option A matches the product rule."


@pytest.mark.asyncio
async def test_practice_submit_and_detail_return_question_explanation(client, test_user, test_db):
    """Practice feedback and question detail should expose stored explanations."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    async with test_db() as session:
        question = Question(
            question_type="single_choice",
            content="Practice explanation question?",
            options=["Option A", "Option B", "Option C", "Option D"],
            answer="B",
            explanation="Option B is the documented answer.",
            difficulty=1,
            is_active=True,
        )
        session.add(question)
        await session.commit()
        await session.refresh(question)

    submit_resp = await client.post(
        "/api/answer",
        json={
            "user_id": user.id,
            "question_id": question.id,
            "selected_answer": "A",
            "time_spent": 8,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["data"]["explanation"] == "Option B is the documented answer."

    detail_resp = await client.get(f"/api/questions/detail/{question.id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["explanation"] == "Option B is the documented answer."


@pytest.mark.asyncio
async def test_submit_wrong_answer(client, test_user, test_questions):
    """Submitting a wrong weekly answer should score zero."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    quiz_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    second_question = quiz_resp.json()["data"]["questions"][1]

    submit_resp = await client.post(
        "/api/daily/submit",
        json={
            "user_id": user.id,
            "question_id": second_question["id"],
            "selected_answer": "B",
            "time_spent": 5,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200
    result = submit_resp.json()["data"]
    assert result["is_correct"] is False
    assert result["score"] == 0


@pytest.mark.asyncio
async def test_duplicate_submit_rejected(client, test_user, test_questions):
    """Submitting the same weekly question twice should be rejected."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    quiz_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    target_question = quiz_resp.json()["data"]["questions"][2]

    payload = {
        "user_id": user.id,
        "question_id": target_question["id"],
        "selected_answer": "A",
        "time_spent": 5,
    }

    first = await client.post("/api/daily/submit", json=payload, headers=headers)
    assert first.status_code == 200

    second = await client.post("/api/daily/submit", json=payload, headers=headers)
    assert second.status_code == 400
    assert "重复提交" in second.json()["detail"]


@pytest.mark.asyncio
async def test_score_accumulation(client, test_user, test_questions, test_db):
    """Weekly quiz submissions should still update user aggregate score counters."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    quiz_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    questions = quiz_resp.json()["data"]["questions"]

    total_expected = 0
    for question in questions[:2]:
        resp = await client.post(
            "/api/daily/submit",
            json={
                "user_id": user.id,
                "question_id": question["id"],
                "selected_answer": "A",
                "time_spent": 5,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        total_expected += resp.json()["data"]["score"]

    async with test_db() as session:
        result = await session.execute(select(UserModel).where(UserModel.id == user.id))
        db_user = result.scalar_one()
        assert db_user.total_score == total_expected == 2
        assert db_user.total_count == 2


@pytest.mark.asyncio
async def test_previous_week_record_does_not_leak_into_current_week(client, test_user, test_questions, test_db):
    """A previous week's submission for the same question should not count for the current week."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    quiz_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    question = quiz_resp.json()["data"]["questions"][0]

    async with test_db() as session:
        session.add(
            AnswerRecord(
                user_id=user.id,
                question_id=question["id"],
                selected_answer="A",
                is_correct=True,
                score=1,
                time_spent=5,
                source="daily",
                quiz_date="2026-01-05",
            )
        )
        await session.commit()

    fresh_resp = await client.get("/api/daily/quiz", params={"user_id": user.id}, headers=headers)
    fresh_data = fresh_resp.json()["data"]
    fresh_question = next(item for item in fresh_data["questions"] if item["id"] == question["id"])

    assert fresh_data["answered_count"] == 0
    assert "user_answer" not in fresh_question
    assert "is_correct" not in fresh_question


@pytest.mark.asyncio
async def test_bank_answer_updates_study_record_summary_without_mistake_count(
    client,
    test_user,
    test_questions,
):
    """Practice answers should update study records and no longer expose mistake summary fields."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    submit_resp = await client.post(
        "/api/answer",
        json={
            "user_id": user.id,
            "question_id": test_questions[0].id,
            "selected_answer": "A",
            "time_spent": 12,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["data"]["is_correct"] is True

    summary_resp = await client.get("/api/study/records", params={"user_id": user.id}, headers=headers)
    assert summary_resp.status_code == 200

    data = summary_resp.json()["data"]
    assert data["summary"]["practice_answers"] == 1
    assert data["summary"]["practice_duration_seconds"] == 12
    assert "mistake_count" not in data["summary"]
    assert data["recent_records"][0]["source"] == "bank"
    assert data["recent_records"][0]["question_preview"] == test_questions[0].content
    assert data["recent_records"][0]["question_content"] == test_questions[0].content


@pytest.mark.asyncio
async def test_bank_answer_does_not_add_energy(client, test_user, test_questions, test_db):
    """Practice mode should not increase leaderboard energy."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    submit_resp = await client.post(
        "/api/answer",
        json={
            "user_id": user.id,
            "question_id": test_questions[0].id,
            "selected_answer": "A",
            "time_spent": 8,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200
    assert submit_resp.json()["data"]["score"] == 0

    async with test_db() as session:
        result = await session.execute(select(UserModel).where(UserModel.id == user.id))
        db_user = result.scalar_one()
        assert db_user.total_score == 0


@pytest.mark.asyncio
async def test_short_answer_bank_returns_reference_answer(client, test_user, test_questions):
    """Short-answer bank items should expose their reference answer directly."""

    user, token = test_user
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        "/api/questions/bank",
        params={"question_type": "short_answer", "page": 1, "page_size": 20},
        headers=headers,
    )
    assert resp.status_code == 200

    questions = resp.json()["data"]["questions"]
    assert questions
    assert questions[0]["question_type"] == "short_answer"
    assert questions[0]["answer"].startswith("Reference answer")
