"""Reconcile user cumulative answer and energy totals from audit tables.

This script is intentionally conservative:
- total_count/correct_count are rebuilt from answer_records.
- total_score is rebuilt from answer_records.score plus issued energy_transactions.
- users without answer records or issued energy transactions are not modified.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from sqlalchemy import and_, case, func, select

from app.db.session import AsyncSessionLocal
from app.models.energy import EnergyTransaction
from app.models.record import AnswerRecord
from app.models.user import User


def _int(value: object) -> int:
    return int(value or 0)


async def collect_differences() -> list[dict[str, object]]:
    answer_stats = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(AnswerRecord.id).label("answer_total_count"),
            func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("answer_correct_count"),  # noqa: E712
            func.sum(
                case(
                    (
                        and_(AnswerRecord.source == "daily", AnswerRecord.is_correct == True),  # noqa: E712
                        1,
                    ),
                    else_=func.coalesce(AnswerRecord.score, 0),
                )
            ).label("answer_score"),
        )
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    transaction_stats = (
        select(
            EnergyTransaction.user_id.label("user_id"),
            func.count(EnergyTransaction.id).label("transaction_count"),
            func.sum(func.coalesce(EnergyTransaction.amount, 0)).label("transaction_score"),
        )
        .where(EnergyTransaction.status == "issued")
        .group_by(EnergyTransaction.user_id)
        .subquery()
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                User,
                answer_stats.c.answer_total_count,
                answer_stats.c.answer_correct_count,
                answer_stats.c.answer_score,
                transaction_stats.c.transaction_count,
                transaction_stats.c.transaction_score,
            )
            .outerjoin(answer_stats, answer_stats.c.user_id == User.id)
            .outerjoin(transaction_stats, transaction_stats.c.user_id == User.id)
            .order_by(User.company.asc(), User.real_name.asc(), User.nickname.asc(), User.id.asc())
        )

        rows: list[dict[str, object]] = []
        for user, answer_total_count, answer_correct_count, answer_score, transaction_count, transaction_score in result.all():
            answer_total = _int(answer_total_count)
            tx_total = _int(transaction_count)
            if answer_total <= 0 and tx_total <= 0:
                continue

            expected_total_count = answer_total
            expected_correct_count = _int(answer_correct_count)
            source_total_score = _int(answer_score) + _int(transaction_score)

            old_total_score = _int(user.total_score)
            old_correct_count = _int(user.correct_count)
            old_total_count = _int(user.total_count)

            expected_total_score = max(old_total_score, source_total_score)

            if (
                old_total_score == expected_total_score
                and old_correct_count == expected_correct_count
                and old_total_count == expected_total_count
            ):
                continue

            rows.append(
                {
                    "user_id": user.id,
                    "name": user.real_name or user.nickname or "",
                    "phone": user.phone or "",
                    "company": user.company or "",
                    "job_role": user.job_role or "",
                    "old_total_score": old_total_score,
                    "new_total_score": expected_total_score,
                    "delta_total_score": expected_total_score - old_total_score,
                    "old_correct_count": old_correct_count,
                    "new_correct_count": expected_correct_count,
                    "delta_correct_count": expected_correct_count - old_correct_count,
                    "old_total_count": old_total_count,
                    "new_total_count": expected_total_count,
                    "delta_total_count": expected_total_count - old_total_count,
                    "source_total_score": source_total_score,
                    "answer_score": _int(answer_score),
                    "transaction_score": _int(transaction_score),
                    "answer_record_count": answer_total,
                    "energy_transaction_count": tx_total,
                }
            )
        return rows


async def apply_differences(rows: list[dict[str, object]]) -> None:
    if not rows:
        return

    by_user_id = {str(row["user_id"]): row for row in rows}
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id.in_(by_user_id.keys())))
        for user in result.scalars().all():
            row = by_user_id[user.id]
            user.total_score = int(row["new_total_score"])
            user.correct_count = int(row["new_correct_count"])
            user.total_count = int(row["new_total_count"])
        await session.commit()


def write_csv(rows: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "user_id",
        "name",
        "phone",
        "company",
        "job_role",
        "old_total_score",
        "new_total_score",
        "delta_total_score",
        "old_correct_count",
        "new_correct_count",
        "delta_correct_count",
        "old_total_count",
        "new_total_count",
        "delta_total_count",
        "source_total_score",
        "answer_score",
        "transaction_score",
        "answer_record_count",
        "energy_transaction_count",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write reconciled totals back to users")
    parser.add_argument("--output", default="tmp/user_energy_reconcile.csv")
    args = parser.parse_args()

    rows = await collect_differences()
    write_csv(rows, Path(args.output))
    if args.apply:
        await apply_differences(rows)
    print(
        {
            "mode": "apply" if args.apply else "dry-run",
            "changed_users": len(rows),
            "output": args.output,
            "delta_total_score": sum(int(row["delta_total_score"]) for row in rows),
            "delta_correct_count": sum(int(row["delta_correct_count"]) for row in rows),
            "delta_total_count": sum(int(row["delta_total_count"]) for row in rows),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
