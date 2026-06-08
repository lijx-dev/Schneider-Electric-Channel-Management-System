"""Rename one question category to another in the questions table.

Usage:
  cd faq-backend
  venv\\Scripts\\python scripts\\merge_question_category.py Track "I-Line Track"
  venv\\Scripts\\python scripts\\merge_question_category.py Track "I-Line Track" --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_category")
    parser.add_argument("target_category")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


async def rename_category(source_category: str, target_category: str, apply: bool) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal, engine, init_db
    from app.models.question import Question

    await init_db()

    source_count = 0
    target_count = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        source_result = await session.execute(
            select(Question).where(Question.category == source_category)
        )
        source_questions = source_result.scalars().all()
        source_count = len(source_questions)

        target_result = await session.execute(
            select(Question).where(Question.category == target_category)
        )
        target_questions = target_result.scalars().all()
        target_count = len(target_questions)

        for question in source_questions:
            updated += 1
            if apply:
                question.category = target_category

        if apply:
            await session.commit()
        else:
            await session.rollback()

    await engine.dispose()
    return {
        "source_count_before": source_count,
        "target_count_before": target_count,
        "updated": updated,
        "target_count_after": target_count + updated,
    }


async def main() -> None:
    args = parse_args()
    stats = await rename_category(args.source_category, args.target_category, args.apply)
    mode = "APPLY" if args.apply else "DRY_RUN"
    print(f"[{mode}] {args.source_category} -> {args.target_category}")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
