"""Tests for monthly leaderboard snapshots and rewards."""

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.energy import EnergyTransaction
from app.models.lottery import LotteryDraw, LotteryWinner
from app.models.monthly import MonthlyRankSnapshot
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.monthly_leaderboard import get_month_reward_amount, settle_monthly_rewards


async def create_month_user(session, index, *, total_score=0):
    user = User(
        openid=f"monthly_openid_{index:03d}",
        nickname=f"Month User {index:03d}",
        phone=f"1370000{index:04d}",
        real_name=f"Month User {index:03d}",
        province="Shanghai",
        company="Monthly Company",
        total_score=total_score,
        correct_count=0,
        total_count=0,
    )
    session.add(user)
    await session.flush()
    return user


def add_month_record(session, user, question, *, is_correct=True, time_spent=10, quiz_date="2026-05-01"):
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
async def test_monthly_leaderboard_limits_list_to_top_50_but_returns_my_rank(
    client,
    test_user,
    test_questions,
    test_db,
):
    viewer, token = test_user

    async with test_db() as session:
        for index in range(55):
            user = await create_month_user(session, index)
            add_month_record(
                session,
                user,
                test_questions[index % len(test_questions)],
                is_correct=True,
                time_spent=index + 1,
                quiz_date=f"2026-05-{(index % 28) + 1:02d}",
            )

        add_month_record(
            session,
            viewer,
            test_questions[-1],
            is_correct=False,
            time_spent=999,
            quiz_date="2026-05-20",
        )
        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(
        "/api/monthly-leaderboard",
        params={"month": "2026-05", "limit": 50},
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["leaderboard"]) == 50
    assert data["leaderboard"][0]["rank"] == 1
    assert data["leaderboard"][-1]["rank"] == 50
    assert data["my_rank"]["user_id"] == viewer.id
    assert data["my_rank"]["rank"] == 56
    assert data["my_rank"]["reward_amount"] == 0


@pytest.mark.asyncio
async def test_settle_monthly_rewards_snapshots_top_50_and_adds_energy_once(
    test_user,
    test_questions,
    test_db,
):
    viewer, _ = test_user

    async with test_db() as session:
        first = await create_month_user(session, 101, total_score=5)
        fourth = await create_month_user(session, 104, total_score=7)
        twenty_first = await create_month_user(session, 121, total_score=9)

        add_month_record(session, first, test_questions[0], is_correct=True, time_spent=10, quiz_date="2026-04-01")
        add_month_record(session, fourth, test_questions[1], is_correct=True, time_spent=40, quiz_date="2026-04-02")
        add_month_record(session, twenty_first, test_questions[2], is_correct=True, time_spent=210, quiz_date="2026-04-03")
        add_month_record(session, viewer, test_questions[3], is_correct=False, time_spent=300, quiz_date="2026-04-04")

        for index in range(2, 22):
            user = await create_month_user(session, 200 + index)
            add_month_record(
                session,
                user,
                test_questions[index % len(test_questions)],
                is_correct=True,
                time_spent=index * 10,
                quiz_date="2026-04-05",
            )

        result = await settle_monthly_rewards(session, "2026-04")
        await session.commit()

        assert result["snapshot_count"] == 24
        assert result["reward_count"] == 23
        assert get_month_reward_amount(1) == 30
        assert get_month_reward_amount(4) == 20
        assert get_month_reward_amount(11) == 10
        assert get_month_reward_amount(21) == 5
        assert get_month_reward_amount(51) == 0

        await session.refresh(first)
        await session.refresh(fourth)
        await session.refresh(twenty_first)
        viewer_result = await session.execute(select(User).where(User.id == viewer.id))
        db_viewer = viewer_result.scalar_one()

        assert first.total_score == 35
        assert fourth.total_score == 27
        assert twenty_first.total_score == 14
        assert db_viewer.total_score == 0

        second_result = await settle_monthly_rewards(session, "2026-04")
        await session.commit()

        await session.refresh(first)
        assert second_result["already_settled"] is True
        assert first.total_score == 35


@pytest.mark.asyncio
async def test_reward_records_returns_monthly_reward_history(
    client,
    test_user,
    test_questions,
    test_db,
):
    viewer, token = test_user

    async with test_db() as session:
        add_month_record(session, viewer, test_questions[0], is_correct=True, time_spent=10, quiz_date="2026-03-01")
        await settle_monthly_rewards(session, "2026-03")
        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get("/api/rewards/records", headers=headers)

    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert rows[0]["type"] == "monthly_rank_reward"
    assert rows[0]["amount"] == 30
    assert rows[0]["related_month"] == "2026-03"


@pytest.mark.asyncio
async def test_monthly_reward_notice_is_visible_until_marked_read(
    client,
    test_user,
    test_db,
):
    viewer, token = test_user

    async with test_db() as session:
        session.add(
            MonthlyRankSnapshot(
                month_key="2026-05",
                user_id=viewer.id,
                rank=2,
                nickname=viewer.nickname or "",
                real_name=viewer.real_name or "",
                company=viewer.company or "",
                province=viewer.province or "",
                monthly_correct_count=9,
                monthly_total_count=10,
                monthly_time_spent=88,
                reward_amount=30,
                reward_status="issued",
            )
        )
        session.add(
            EnergyTransaction(
                user_id=viewer.id,
                amount=30,
                type="monthly_rank_reward",
                title="2026-05月榜奖励",
                description="月榜第2名，奖励30格施能量",
                related_type="monthly_rank_snapshot",
                related_id=f"2026-05:{viewer.id}",
                related_month="2026-05",
                status="issued",
            )
        )
        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    notice_resp = await client.get("/api/rewards/latest-notice", headers=headers)
    assert notice_resp.status_code == 200
    notice_data = notice_resp.json()["data"]
    assert notice_data["has_notice"] is True
    assert notice_data["monthly"]["month_key"] == "2026-05"
    assert notice_data["monthly"]["amount"] == 30
    assert "2026年5月月榜奖励30格施能量" in notice_data["text"]

    read_resp = await client.post(
        "/api/rewards/notices/read",
        headers=headers,
        json={
            "reward_transaction_ids": notice_data["reward_transaction_ids"],
            "lottery_notice_ids": notice_data["lottery_notice_ids"],
        },
    )
    assert read_resp.status_code == 200

    hidden_resp = await client.get("/api/rewards/latest-notice", headers=headers)
    assert hidden_resp.status_code == 200
    assert hidden_resp.json()["data"]["has_notice"] is False


@pytest.mark.asyncio
async def test_reward_notice_combines_lottery_and_monthly_rewards(
    client,
    test_user,
    test_db,
):
    viewer, token = test_user

    async with test_db() as session:
        monthly_tx = EnergyTransaction(
            user_id=viewer.id,
            amount=20,
            type="monthly_rank_reward",
            title="2026-05月榜奖励",
            description="月榜第5名，奖励20格施能量",
            related_type="monthly_rank_snapshot",
            related_id=f"2026-05:{viewer.id}",
            related_month="2026-05",
            status="issued",
        )
        session.add(monthly_tx)
        session.add(
            MonthlyRankSnapshot(
                month_key="2026-05",
                user_id=viewer.id,
                rank=5,
                nickname=viewer.nickname or "",
                real_name=viewer.real_name or "",
                company=viewer.company or "",
                province=viewer.province or "",
                monthly_correct_count=8,
                monthly_total_count=10,
                monthly_time_spent=120,
                reward_amount=20,
                reward_status="issued",
            )
        )
        await session.flush()

        lottery_draw = LotteryDraw(
            month_key="2026-06",
            participant_month="2026-05",
            status="completed",
            eligible_count=1,
            winner_count=1,
        )
        session.add(lottery_draw)
        await session.flush()
        lottery_tx = EnergyTransaction(
            user_id=viewer.id,
            amount=30,
            type="lottery_reward",
            title="2026年6月幸运抽奖",
            description="2026年6月幸运抽奖一等奖，奖励30格施能量",
            related_type="lottery_winner",
            related_id=f"2026-06:{viewer.id}",
            related_month="2026-06",
            status="issued",
        )
        session.add(lottery_tx)
        await session.flush()
        session.add(
            LotteryWinner(
                draw_id=lottery_draw.id,
                month_key="2026-06",
                user_id=viewer.id,
                prize_level="first",
                prize_name="一等奖",
                reward_amount=30,
                winner_order=1,
                energy_transaction_id=lottery_tx.id,
            )
        )
        await session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    notice_resp = await client.get("/api/rewards/latest-notice", headers=headers)
    assert notice_resp.status_code == 200
    notice_data = notice_resp.json()["data"]
    assert notice_data["has_notice"] is True
    assert notice_data["monthly"]["transaction_id"] == monthly_tx.id
    assert notice_data["lottery"]["transaction_id"] == lottery_tx.id
    assert "幸运抽奖一等奖" in notice_data["text"]
    assert "同时获得2026年5月月榜奖励20格施能量" in notice_data["text"]

    read_resp = await client.post(
        "/api/rewards/notices/read",
        headers=headers,
        json={
            "reward_transaction_ids": notice_data["reward_transaction_ids"],
            "lottery_notice_ids": notice_data["lottery_notice_ids"],
        },
    )
    assert read_resp.status_code == 200

    hidden_resp = await client.get("/api/rewards/latest-notice", headers=headers)
    assert hidden_resp.status_code == 200
    assert hidden_resp.json()["data"]["has_notice"] is False


@pytest.mark.asyncio
async def test_schneider_electric_employees_are_excluded_from_monthly_ranking_and_rewards(
    client,
    test_user,
    test_questions,
    test_db,
):
    viewer, token = test_user

    async with test_db() as session:
        external_user = await create_month_user(session, 301, total_score=0)
        internal_user = await create_month_user(session, 302, total_score=0)
        internal_user.company = "施耐德电气"

        add_month_record(session, internal_user, test_questions[0], is_correct=True, time_spent=1, quiz_date="2026-02-01")
        add_month_record(session, internal_user, test_questions[1], is_correct=True, time_spent=1, quiz_date="2026-02-02")
        add_month_record(session, external_user, test_questions[0], is_correct=True, time_spent=30, quiz_date="2026-02-03")
        add_month_record(session, viewer, test_questions[1], is_correct=False, time_spent=40, quiz_date="2026-02-04")

        result = await settle_monthly_rewards(session, "2026-02")
        await session.commit()

        await session.refresh(internal_user)
        await session.refresh(external_user)

    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(
        "/api/monthly-leaderboard",
        params={"month": "2026-02", "limit": 50},
        headers=headers,
    )

    rows = resp.json()["data"]["leaderboard"]
    assert internal_user.id not in [row["user_id"] for row in rows]
    assert rows[0]["user_id"] == external_user.id
    assert result["reward_count"] == 1
    assert external_user.total_score == 30
    assert internal_user.total_score == 0

    internal_token = create_access_token(internal_user.id)
    internal_resp = await client.get(
        "/api/monthly-leaderboard",
        params={"month": "2026-02", "limit": 50},
        headers={"Authorization": f"Bearer {internal_token}"},
    )
    internal_my_rank = internal_resp.json()["data"]["my_rank"]
    assert internal_my_rank["ranking_excluded"] is True
    assert internal_my_rank["rank"] == "-"
    assert internal_my_rank["monthly_correct_count"] == 0
    assert internal_my_rank["monthly_time_spent"] == 0
