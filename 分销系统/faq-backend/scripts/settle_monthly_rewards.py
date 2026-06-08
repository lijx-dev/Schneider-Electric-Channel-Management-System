"""Settle monthly leaderboard rewards.

Usage:
    python scripts/settle_monthly_rewards.py --month 2026-05
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta

from app.db.session import AsyncSessionLocal, close_db
from app.services.monthly_leaderboard import settle_monthly_rewards


def previous_month_key(today: date | None = None) -> str:
    current = today or date.today()
    first_day = current.replace(day=1)
    previous_month_day = first_day - timedelta(days=1)
    return previous_month_day.strftime("%Y-%m")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=previous_month_key(), help="Month to settle, format YYYY-MM")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        result = await settle_monthly_rewards(session, args.month)
        await session.commit()

    print(result)
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
