"""Run monthly lucky lottery manually.

Usage:
    python scripts/run_monthly_lottery.py --month 2026-06
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.services.lottery import run_monthly_lottery


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run monthly lucky lottery.")
    parser.add_argument("--month", required=True, help="Lottery month in YYYY-MM format, e.g. 2026-06")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        result = await run_monthly_lottery(session, args.month)
        await session.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
