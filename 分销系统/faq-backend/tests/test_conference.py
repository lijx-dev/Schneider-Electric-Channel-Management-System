"""
分销商大会「能量印章·集章」模块单元测试（手机号自助签到版）

覆盖：
a) join 同一手机号重复提交幂等，只产生一条参会人且返回成功
b) submit-quiz 同一题重复提交幂等，不产生重复印章
c) grant_zone_mark / try_grant_medal 重复调用不重复发勋章
d) 过期打卡点窗口：active_to 过期后 submit-quiz 返回 403
e) 集齐 4 个印章后 GET /api/conference/medal 返回 granted=true，且 medal_code 唯一
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models.conference import (
    ConferenceAttendee,
    ConferenceMedal,
    ConferenceZone,
    ConferenceZoneMark,
)
from app.models.question import Question
from app.services.conference import (
    get_zone_progress,
    grant_zone_mark,
    try_grant_medal,
)

TZ = timezone(timedelta(hours=8))


def _make_zone(session, code: str, category: str | None = None, **kw) -> ConferenceZone:
    zone = ConferenceZone(
        code=code,
        name=f"{code} 打卡点",
        sort_order=0,
        question_category=category or f"conf_test_{code}",
        **kw,
    )
    session.add(zone)
    return zone


async def _create_quiz_zone(session, code: str, question_count: int = 2, **zone_kw) -> ConferenceZone:
    zone = _make_zone(session, code, **zone_kw)
    session.add(zone)
    await session.flush()
    for i in range(question_count):
        session.add(
            Question(
                question_type="single_choice",
                content=f"{code} test question {i + 1}",
                options=["A", "B", "C"],
                answer="A",
                category=zone.question_category,
                is_active=True,
            )
        )
    await session.flush()
    return zone


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


# ── a) join 同一手机号重复提交幂等 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_join_idempotent_single_attendee(test_db, conf_client):
    resp = await conf_client.post(
        "/api/conference/join",
        json={"name": "张三", "phone": "13900001001"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["phone"] == "13900001001"
    attendee_id = data["attendee_id"]

    resp2 = await conf_client.post(
        "/api/conference/join",
        json={"name": "张三改", "phone": "13900001001"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["attendee_id"] == attendee_id

    async with test_db() as session:
        count = await session.scalar(
            select(func.count(ConferenceAttendee.id)).where(
                ConferenceAttendee.phone == "13900001001"
            )
        )
        assert count == 1

    # 手机号格式校验
    bad = await conf_client.post(
        "/api/conference/join",
        json={"name": "张三", "phone": "123"},
    )
    assert bad.status_code == 400


# ── b) submit-quiz 同一题重复提交幂等，不产生重复印章 ────────────────────

@pytest.mark.asyncio
async def test_submit_quiz_idempotent_no_duplicate_mark(test_db, conf_client):
    phone = "13900001002"
    async with test_db() as session:
        zone = await _create_quiz_zone(session, "idem", question_count=2)
        questions = await _zone_questions(session, zone)
        await session.commit()
        zone_code = zone.code
        question_ids = [q.id for q in questions]

    answers = [{"question_id": qid, "selected_answer": "A"} for qid in question_ids]
    first = await conf_client.post(
        f"/api/conference/zones/{zone_code}/submit-quiz",
        json={"phone": phone, "name": "李四", "answers": answers},
    )
    assert first.status_code == 200
    assert first.json()["data"]["stamp_earned"] is True

    second = await conf_client.post(
        f"/api/conference/zones/{zone_code}/submit-quiz",
        json={"phone": phone, "name": "李四", "answers": answers},
    )
    assert second.status_code == 200
    assert second.json()["data"]["stamp_earned"] is False

    async with test_db() as session:
        zone_id = await session.scalar(
            select(ConferenceZone.id).where(ConferenceZone.code == zone_code)
        )
        mark_count = await session.scalar(
            select(func.count(ConferenceZoneMark.id)).where(
                ConferenceZoneMark.phone == phone,
                ConferenceZoneMark.zone_id == zone_id,
            )
        )
        assert mark_count == 1


# ── c) grant_zone_mark / try_grant_medal 重复调用不重复发勋章 ─────────────

@pytest.mark.asyncio
async def test_medal_granted_once(test_db):
    phone = "13900001003"
    async with test_db() as session:
        zone = await _create_quiz_zone(session, "medal_a", question_count=1)
        zone2 = await _create_quiz_zone(session, "medal_b", question_count=1)
        await session.commit()

        assert await grant_zone_mark(session, phone, zone.id) is True
        assert await grant_zone_mark(session, phone, zone.id) is False

        # 未集齐全部启用打卡点时不发勋章
        assert await try_grant_medal(session, phone, "王五") is None

        # 集齐剩余打卡点后发放一枚
        assert await grant_zone_mark(session, phone, zone2.id) is True
        medal = await try_grant_medal(session, phone, "王五")
        assert medal is not None
        assert medal.medal_code.startswith("DY-")
        await session.commit()

        # 重复调用不发第二枚
        assert await try_grant_medal(session, phone, "王五") is None


# ── d) 过期打卡点窗口：active_to 过期后 submit-quiz 返回 403 ──────────────

@pytest.mark.asyncio
async def test_zone_window_expired_returns_403(test_db, conf_client):
    phone = "13900001004"
    async with test_db() as session:
        zone = await _create_quiz_zone(
            session,
            "window_exp",
            question_count=1,
            active_from=datetime.now(TZ) - timedelta(days=30),
            active_to=datetime.now(TZ) - timedelta(days=1),
        )
        questions = await _zone_questions(session, zone)
        await session.commit()
        zone_code = zone.code
        answers = [{"question_id": q.id, "selected_answer": "A"} for q in questions]

    resp = await conf_client.post(
        f"/api/conference/zones/{zone_code}/submit-quiz",
        json={"phone": phone, "name": "赵六", "answers": answers},
    )
    assert resp.status_code == 403
    assert "未开放" in resp.json()["detail"]


# ── e) 集齐 4 个印章后 medal 返回 granted=true，且 medal_code 唯一 ─────────

@pytest.mark.asyncio
async def test_medal_api_granted_after_all_marks(test_db, conf_client):
    phone = "13900001005"
    async with test_db() as session:
        zone_ids = []
        for code in ("full_a", "full_b", "full_c", "full_d"):
            zone = await _create_quiz_zone(session, code, question_count=1)
            zone_ids.append(zone.id)
        await session.commit()

        for zid in zone_ids:
            assert await grant_zone_mark(session, phone, zid) is True
        await session.commit()

        medal = await try_grant_medal(session, phone, "钱七")
        assert medal is not None
        assert medal.medal_code.startswith("DY-")
        medal_code = medal.medal_code
        await session.commit()

        # 重复调用不发第二枚
        assert await try_grant_medal(session, phone, "钱七") is None

    resp = await conf_client.get("/api/conference/medal", params={"phone": phone})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["granted"] is True
    assert data["medal_code"] == medal_code
    assert data["zone_count"] == 4
    assert len(data["earned_zones"]) == 4

    # medal_code 全局唯一
    async with test_db() as session:
        code_count = await session.scalar(
            select(func.count(ConferenceMedal.id)).where(
                ConferenceMedal.medal_code == medal_code
            )
        )
        assert code_count == 1
