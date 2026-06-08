"""Tests for monthly lucky lottery rewards and notices."""

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.energy import EnergyTransaction
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.lottery import run_monthly_lottery


async def create_lottery_user(session, index, *, company="Lottery Company", total_score=0):
    user = User(
        openid=f"lottery_openid_{index:03d}",
        nickname=f"Lottery User {index:03d}",
        phone=f"1360000{index:04d}",
        real_name=f"Lottery User {index:03d}",
        province="Shanghai",
        company=company,
        total_score=total_score,
        correct_count=0,
        total_count=0,
    )
    session.add(user)
    await session.flush()
    return user


def add_lottery_record(session, user, question, *, quiz_date="2026-05-01", is_correct=False):
    session.add(
        AnswerRecord(
            user_id=user.id,
            question_id=question.id,
            selected_answer="A",
            is_correct=is_correct,
            score=1 if is_correct else 0,
            time_spent=10,
            source="daily",
            quiz_date=quiz_date,
        )
    )


@pytest.mark.asyncio
async def test_monthly_lottery_uses_previous_month_participants_and_is_idempotent(
    test_questions,
    test_db,
):
    async with test_db() as session:
        eligible_users = []
        for index in range(35):
            user = await create_lottery_user(session, index, total_score=1)
            add_lottery_record(
                session,
                user,
                test_questions[index % len(test_questions)],
                quiz_date=f"2026-05-{(index % 28) + 1:02d}",
                is_correct=index % 2 == 0,
            )
            eligible_users.append(user)

        internal_user = await create_lottery_user(
            session,
            900,
            company="\u65bd\u8010\u5fb7\u7535\u6c14",
            total_score=1,
        )
        add_lottery_record(session, internal_user, test_questions[0], quiz_date="2026-05-10")

        other_month_user = await create_lottery_user(session, 901, total_score=1)
        add_lottery_record(session, other_month_user, test_questions[1], quiz_date="2026-04-10")

        result = await run_monthly_lottery(session, "2026-06")
        await session.commit()

        assert result["month"] == "2026-06"
        assert result["participant_month"] == "2026-05"
        assert result["eligible_count"] == 35
        assert result["winner_count"] == 30
        assert result["already_drawn"] is False

        tx_result = await session.execute(
            select(EnergyTransaction).where(EnergyTransaction.type == "lottery_reward")
        )
        transactions = tx_result.scalars().all()
        assert len(transactions) == 30
        assert sum(1 for item in transactions if item.amount == 30) == 10
        assert sum(1 for item in transactions if item.amount == 20) == 10
        assert sum(1 for item in transactions if item.amount == 10) == 10
        assert internal_user.id not in {item.user_id for item in transactions}
        assert other_month_user.id not in {item.user_id for item in transactions}

        second = await run_monthly_lottery(session, "2026-06")
        await session.commit()

        assert second["already_drawn"] is True
        again_result = await session.execute(
            select(EnergyTransaction).where(EnergyTransaction.type == "lottery_reward")
        )
        assert len(again_result.scalars().all()) == 30


@pytest.mark.asyncio
async def test_lottery_notice_is_visible_until_marked_read(
    client,
    test_questions,
    test_db,
):
    async with test_db() as session:
        user = await create_lottery_user(session, 501, total_score=0)
        add_lottery_record(session, user, test_questions[0], quiz_date="2026-05-01")
        await run_monthly_lottery(session, "2026-06")
        await session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    notice_resp = await client.get("/api/lottery/my-latest-notice", headers=headers)
    assert notice_resp.status_code == 200
    notice_data = notice_resp.json()["data"]
    assert notice_data["has_notice"] is True
    assert notice_data["month_key"] == "2026-06"
    assert notice_data["prize_name"] == "\u4e00\u7b49\u5956"
    assert notice_data["reward_amount"] == 30
    assert "\u60a8\u83b7\u5f97\u4e862026\u5e746\u6708\u5e78\u8fd0\u62bd\u5956\u4e00\u7b49\u5956" in notice_data["text"]

    read_resp = await client.post(
        f"/api/lottery/notices/{notice_data['notice_id']}/read",
        headers=headers,
    )
    assert read_resp.status_code == 200

    hidden_resp = await client.get("/api/lottery/my-latest-notice", headers=headers)
    assert hidden_resp.status_code == 200
    assert hidden_resp.json()["data"]["has_notice"] is False
