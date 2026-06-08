"""Tests for automatic monthly reward settlement scheduler."""

from datetime import date, datetime, timezone

import pytest

from app.services import monthly_reward_scheduler as scheduler


def test_previous_month_key_returns_previous_calendar_month():
    assert scheduler.previous_month_key(scheduler.business_today(datetime(2026, 6, 1, tzinfo=timezone.utc))) == "2026-05"
    assert scheduler.previous_month_key(scheduler.business_today(datetime(2026, 1, 10, tzinfo=timezone.utc))) == "2025-12"


def test_business_today_uses_beijing_timezone():
    utc_time = datetime(2026, 5, 31, 20, 9, 54, tzinfo=timezone.utc)

    assert scheduler.business_today(utc_time).isoformat() == "2026-06-01"


def test_scheduler_should_run_only_when_enabled(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "ENABLE_MONTHLY_REWARD_SCHEDULER", False, raising=False)
    assert scheduler.should_start_scheduler() is False

    monkeypatch.setattr(scheduler.settings, "ENABLE_MONTHLY_REWARD_SCHEDULER", True, raising=False)
    assert scheduler.should_start_scheduler() is True


@pytest.mark.asyncio
async def test_run_monthly_settlement_once_invokes_settle_for_previous_month(monkeypatch):
    calls = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            calls.append(("commit", None))

    def fake_session_factory():
        return FakeSession()

    async def fake_settle(session, month_key):
        calls.append(("settle", month_key))
        return {"month": month_key, "already_settled": False}

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", fake_session_factory)
    monkeypatch.setattr(scheduler, "settle_monthly_rewards", fake_settle)

    result = await scheduler.run_monthly_settlement_once(today=date(2026, 6, 1))

    assert result == {"month": "2026-05", "already_settled": False}
    assert calls == [("settle", "2026-05"), ("commit", None)]


@pytest.mark.asyncio
async def test_run_monthly_tasks_runs_current_month_lottery_only_on_first_day(monkeypatch):
    calls = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def commit(self):
            calls.append(("commit", None))

    def fake_session_factory():
        return FakeSession()

    async def fake_settle(session, month_key):
        calls.append(("settle", month_key))
        return {"month": month_key, "already_settled": False}

    async def fake_lottery(session, month_key):
        calls.append(("lottery", month_key))
        return {"month": month_key, "already_drawn": False}

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", fake_session_factory)
    monkeypatch.setattr(scheduler, "settle_monthly_rewards", fake_settle)
    monkeypatch.setattr(scheduler, "run_monthly_lottery", fake_lottery)

    first_day = await scheduler.run_monthly_tasks_once(today=date(2026, 6, 1))
    middle_day = await scheduler.run_monthly_tasks_once(today=date(2026, 6, 2))

    assert first_day["settlement"] == {"month": "2026-05", "already_settled": False}
    assert first_day["lottery"] == {"month": "2026-06", "already_drawn": False}
    assert middle_day["lottery"] == {"skipped": True, "reason": "not_first_day"}
    assert calls == [
        ("settle", "2026-05"),
        ("commit", None),
        ("lottery", "2026-06"),
        ("commit", None),
        ("settle", "2026-05"),
        ("commit", None),
    ]
