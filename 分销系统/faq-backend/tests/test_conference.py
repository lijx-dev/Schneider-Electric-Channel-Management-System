"""
分销商大会「能量印记·集章」模块单元测试

覆盖：
- submit-quiz 重复提交幂等（不产生重复印记）
- grant_zone_mark / try_grant_medal 重复调用不重复发勋章
- 渠道展区三步计数（record_activity upsert / get_zone_progress.completed）
- 白名单依赖（非白名单用户访问 overview 返回 403）
- 展区窗口校验（active_to 过期后 submit-quiz 返回 403）
- 集齐 4 印记后 GET /api/conference/medal 返回 granted=true
"""
import asyncio
from datetime import datetime, timedelta, timezone
from datetime import time as dtime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.conference import (
    ConferenceActivity,
    ConferenceMedal,
    ConferenceZone,
    ConferenceZoneMark,
)
from app.models.question import Question
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.conference import (
    ENERGY_VIEW_REQUIRED,
    get_zone_progress,
    grant_zone_mark,
    record_activity,
    try_grant_medal,
)

TZ = timezone(timedelta(hours=8))


def _make_token(user: User) -> str:
    return create_access_token(user.id, expires_delta=timedelta(hours=1))


def _make_zone(session, code: str, task_type: str = "quiz", category: str | None = None, **kw) -> ConferenceZone:
    zone = ConferenceZone(
        code=code,
        name=f"{code} 展区",
        sort_order=0,
        task_type=task_type,
        question_category=category,
        **kw,
    )
    session.add(zone)
    return zone


async def _create_quiz_zone(session, code: str, question_count: int = 2, **zone_kw) -> ConferenceZone:
    category = f"conf_test_{code}"
    zone = _make_zone(session, code, task_type="quiz", category=category, **zone_kw)
    session.add(zone)
    await session.flush()
    for i in range(question_count):
        session.add(
            Question(
                question_type="single_choice",
                content=f"{code} test question {i + 1}",
                options=["A", "B", "C"],
                answer="A",
                category=category,
                is_active=True,
            )
        )
    await session.flush()
    return zone


async def _create_user(session, openid: str, whitelisted: bool) -> User:
    user = User(
        openid=openid,
        nickname=f"user-{openid}",
        phone=f"13966{openid[-6:]}",
        conference_whitelisted=whitelisted,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _zone_questions(session, zone: ConferenceZone):
    result = await session.execute(
        select(Question).where(Question.category == zone.question_category)
    )
    return result.scalars().all()


@pytest_asyncio.fixture
async def conf_client(test_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── a) submit-quiz 重复提交幂等，不产生重复印记 ────────────────────────────

@pytest.mark.asyncio
async def test_submit_quiz_idempotent_no_duplicate_mark(test_db, conf_client):
    async with test_db() as session:
        user = await _create_user(session, "conf_idem_001", whitelisted=True)
        zone = await _create_quiz_zone(session, "idem")
        questions = await _zone_questions(session, zone)
        await session.commit()
    token = _make_token(user)
    headers = {"Authorization": f"Bearer {token}"}
    answers = [{"question_id": q.id, "selected_answer": "A"} for q in questions]

    first = await conf_client.post(
        f"/api/conference/zones/{zone.code}/submit-quiz", json={"answers": answers}, headers=headers
    )
    assert first.json()["code"] == 0
    assert first.json()["data"]["mark_earned"] is True

    # 重复提交同一题（覆盖式幂等）
    second = await conf_client.post(
        f"/api/conference/zones/{zone.code}/submit-quiz", json={"answers": answers}, headers=headers
    )
    assert second.json()["code"] == 0
    assert second.json()["data"]["mark_earned"] is False

    async with test_db() as session:
        mark_count = await session.scalar(
            select(func.count(ConferenceZoneMark.id)).where(
                ConferenceZoneMark.user_id == user.id,
                ConferenceZoneMark.zone_id == zone.id,
            )
        )
        assert mark_count == 1


# ── b) grant_zone_mark / try_grant_medal 重复调用不重复发勋章 ──────────────

@pytest.mark.asyncio
async def test_medal_granted_once(test_db):
    async with test_db() as session:
        user = await _create_user(session, "conf_medal_001", whitelisted=True)
        zone = await _create_quiz_zone(session, "medal_a")
        zone2 = await _create_quiz_zone(session, "medal_b")
        await session.commit()

        # 重复调用 grant_zone_mark 幂等
        assert await grant_zone_mark(session, user.id, zone.id) is True
        assert await grant_zone_mark(session, user.id, zone.id) is False

        # 未集齐全部启用展区时不发勋章
        assert await try_grant_medal(session, user.id) is None

        # 集齐剩余展区后发放一枚
        assert await grant_zone_mark(session, user.id, zone2.id) is True
        medal = await try_grant_medal(session, user.id)
        assert medal is not None
        assert medal.medal_code.startswith("DY-")
        await session.commit()

        # 重复调用不发第二枚
        assert await try_grant_medal(session, user.id) is None


# ── c) 渠道展区三步计数：record_activity upsert + completed ───────────────

@pytest.mark.asyncio
async def test_channel_three_step_completed(test_db):
    async with test_db() as session:
        user = await _create_user(session, "conf_channel_001", whitelisted=True)
        zone = _make_zone(
            session,
            "channel_test",
            task_type="channel",
            required_daily_quiz_count=2,
            required_ai_chat_count=2,
        )
        await session.commit()

        # 初始未完成
        progress = await get_zone_progress(session, user.id, zone)
        assert progress["completed"] is False
        assert progress["daily_quiz"]["done"] == 0

        # record_activity upsert 幂等累计
        await record_activity(session, user.id, "ai_chat")
        await record_activity(session, user.id, "ai_chat")
        await record_activity(session, user.id, "energy_view")
        await session.commit()

        async with test_db() as session2:
            from app.services.conference import get_activity_count

            assert await get_activity_count(session2, user.id, "ai_chat") == 2
            assert await get_activity_count(session2, user.id, "energy_view") == 1

            # 插入 2 条今日周答题记录（用真实题目 id）
            quiz_date = None
            from app.services.conference import weekly_quiz_date

            quiz_date = weekly_quiz_date()
            daily_question_ids = []
            for i in range(2):
                q = Question(
                    question_type="single_choice",
                    content=f"daily helper q {i + 1}",
                    options=["A", "B"],
                    answer="A",
                    category="daily_helper",
                    is_active=True,
                )
                session2.add(q)
                await session2.flush()
                daily_question_ids.append(q.id)
                session2.add(
                    AnswerRecord(
                        user_id=user.id,
                        question_id=q.id,
                        selected_answer="A",
                        is_correct=True,
                        score=1,
                        source="daily",
                        quiz_date=quiz_date,
                    )
                )
            await session2.commit()

            # 三步全部满足 → completed
            progress2 = await get_zone_progress(session2, user.id, zone)
            assert progress2["daily_quiz"]["done"] == 2
            assert progress2["ai_chat"]["done"] == 2
            assert progress2["energy_view"]["done"] == ENERGY_VIEW_REQUIRED
            assert progress2["completed"] is True

            # 印记发放
            assert await grant_zone_mark(session2, user.id, zone.id) is True


# ── d) 白名单依赖：非白名单用户访问 overview 返回 403 ─────────────────────

@pytest.mark.asyncio
async def test_overview_requires_whitelist(test_db, conf_client):
    async with test_db() as session:
        normal_user = await _create_user(session, "conf_no_whitelist", whitelisted=False)
    headers = {"Authorization": f"Bearer {_make_token(normal_user)}"}
    resp = await conf_client.get("/api/conference/overview", headers=headers)
    assert resp.status_code == 403
    assert "分销商大会" in resp.json()["detail"]


# ── e) 展区窗口校验：active_to 过期后 submit-quiz 返回 403 ────────────────

@pytest.mark.asyncio
async def test_zone_window_expired_returns_403(test_db, conf_client):
    async with test_db() as session:
        user = await _create_user(session, "conf_window_001", whitelisted=True)
        user_id = user.id
        zone = await _create_quiz_zone(
            session,
            "window_exp",
            active_from=datetime.now(TZ) - timedelta(days=30),
            active_to=datetime.now(TZ) - timedelta(days=1),
        )
        zone_code = zone.code
        questions = await _zone_questions(session, zone)
        question_ids = [q.id for q in questions]
        await session.commit()
    token = create_access_token(user_id, expires_delta=timedelta(hours=1))
    headers = {"Authorization": f"Bearer {token}"}
    answers = [{"question_id": qid, "selected_answer": "A"} for qid in question_ids]
    resp = await conf_client.post(
        f"/api/conference/zones/{zone_code}/submit-quiz", json={"answers": answers}, headers=headers
    )
    assert resp.status_code == 403
    assert "未开放" in resp.json()["detail"]


# ── f) 集齐全部印记后 GET /api/conference/medal 返回 granted=true ─────────

@pytest.mark.asyncio
async def test_medal_api_granted_after_all_marks(test_db, conf_client):
    async with test_db() as session:
        user = await _create_user(session, "conf_full_001", whitelisted=True)
        user_id = user.id
        # 创建 4 个启用 quiz 展区
        zone_ids = []
        for code in ("full_a", "full_b", "full_c", "full_d"):
            zone = await _create_quiz_zone(session, code, question_count=1)
            zone_ids.append(zone.id)
        await session.commit()

        # 逐区发印记
        for zid in zone_ids:
            assert await grant_zone_mark(session, user_id, zid) is True
        await session.commit()

        medal = await try_grant_medal(session, user_id)
        assert medal is not None
        assert medal.medal_code.startswith("DY-")
        medal_code = medal.medal_code
        await session.commit()

        # 重复调用不发第二枚
        assert await try_grant_medal(session, user_id) is None

    headers = {"Authorization": f"Bearer {create_access_token(user_id, expires_delta=timedelta(hours=1))}"}
    resp = await conf_client.get("/api/conference/medal", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["granted"] is True
    assert data["medal_code"] == medal_code
    assert data["zone_count"] == 4
    assert len(data["earned_zones"]) == 4
