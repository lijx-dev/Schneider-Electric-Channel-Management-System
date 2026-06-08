"""Set Schneider Electric users to the internal job role.

Usage:
    python scripts/normalize_schneider_internal_roles.py --dry-run
    python scripts/normalize_schneider_internal_roles.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import close_db, engine  # noqa: E402


SCHNEIDER_COMPANY = "施耐德电气"
SCHNEIDER_INTERNAL_ROLE = "施耐德内部"


async def preview_or_apply(apply: bool) -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, phone, real_name, company, job_role
                FROM users
                WHERE company LIKE :company OR province LIKE :company
                ORDER BY company, real_name, id
                """
            ),
            {"company": f"%{SCHNEIDER_COMPANY}%"},
        )
        rows = [dict(row._mapping) for row in result]
        changes = [row for row in rows if (row.get("job_role") or "") != SCHNEIDER_INTERNAL_ROLE]

        print("Schneider internal role preview")
        print(f"Matched users: {len(rows)}")
        print(f"Will update: {len(changes)}")
        print(
            "Update sample:",
            [
                {
                    "phone": row.get("phone") or "",
                    "name": row.get("real_name") or "",
                    "company": row.get("company") or "",
                    "old_role": row.get("job_role") or "",
                    "new_role": SCHNEIDER_INTERNAL_ROLE,
                }
                for row in changes[:10]
            ],
        )

        if not apply:
            print("\nDry run only. Re-run with --apply to write users.job_role.")
            return

        update_result = await conn.execute(
            text(
                """
                UPDATE users
                SET job_role = :job_role, updated_at = NOW()
                WHERE (company LIKE :company OR province LIKE :company)
                  AND (job_role IS NULL OR job_role != :job_role)
                """
            ),
            {"company": f"%{SCHNEIDER_COMPANY}%", "job_role": SCHNEIDER_INTERNAL_ROLE},
        )
        print(f"\nApplied updates: {update_result.rowcount}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("Choose either --apply or --dry-run, not both.")

    try:
        await preview_or_apply(apply=args.apply)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
