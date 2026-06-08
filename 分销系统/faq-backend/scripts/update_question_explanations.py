"""Update existing question explanations from an Excel question bank.

The workbook can place the explanation column differently per sheet. This
script finds the column whose header is exactly "解析", then updates matching
questions by question_type + content.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass

import xlrd
from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


DEFAULT_EXCEL_PATH = (
    r"C:\Users\86135\Documents\WeChat Files\wxid_stm8la2kv7jr22\FileStorage\File"
    r"\2026-05\技术综合题库20221210tosarah--勘正-1toveeko-分类入数据库添加解析.xls"
)

SHEET_TYPE_MAP = {
    "单选题": "single_choice",
    "多选题": "multiple_choice",
    "填空题": "fill_blank",
    "问答题": "short_answer",
    "判断题": "true_false",
}

DATA_START_ROW = 3


@dataclass(frozen=True)
class ExplanationRow:
    question_type: str
    content: str
    explanation: str


def clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        try:
            return str(int(float(text)))
        except ValueError:
            pass
    return text


def normalize_content(value: str) -> str:
    return " ".join(clean_text(value).split())


def resolve_excel_path() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip().strip('"')
    return os.getenv("EXCEL_PATH") or DEFAULT_EXCEL_PATH


def find_header_col(sheet, header_name: str, header_row: int = 2) -> int | None:
    if sheet.nrows <= header_row:
        return None

    for col_idx in range(sheet.ncols):
        if clean_text(sheet.cell_value(header_row, col_idx)) == header_name:
            return col_idx
    return None


def read_explanations_from_excel(file_path: str) -> list[ExplanationRow]:
    workbook = xlrd.open_workbook(file_path)
    rows: list[ExplanationRow] = []

    print(f"[FILE] {file_path}")
    for sheet_name in workbook.sheet_names():
        question_type = SHEET_TYPE_MAP.get(sheet_name)
        if not question_type:
            print(f"[SKIP] Unknown sheet: {sheet_name}")
            continue

        sheet = workbook.sheet_by_name(sheet_name)
        explanation_col = find_header_col(sheet, "解析")
        if explanation_col is None:
            print(f"[SKIP] {sheet_name}: missing 解析 header")
            continue

        sheet_count = 0
        for row_idx in range(DATA_START_ROW, sheet.nrows):
            content = normalize_content(sheet.cell_value(row_idx, 0))
            explanation = clean_text(sheet.cell_value(row_idx, explanation_col))
            if not content or not explanation:
                continue

            rows.append(
                ExplanationRow(
                    question_type=question_type,
                    content=content,
                    explanation=explanation,
                )
            )
            sheet_count += 1

        print(f"[OK] {sheet_name}: read {sheet_count} explanations")

    return rows


async def update_database(rows: list[ExplanationRow]) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal, engine, init_db
    from app.models.question import Question

    await init_db()

    rows_by_key: dict[tuple[str, str], ExplanationRow] = {}
    duplicate_excel_rows = 0
    for row in rows:
        key = (row.question_type, row.content)
        if key in rows_by_key:
            duplicate_excel_rows += 1
        rows_by_key[key] = row

    unique_rows = list(rows_by_key.values())

    matched = 0
    missing = 0
    missing_samples: list[str] = []
    duplicates = 0
    unchanged = 0
    total_questions = 0
    questions_with_explanation = 0

    async with AsyncSessionLocal() as session:
        question_result = await session.execute(select(Question))
        questions_by_key: dict[tuple[str, str], list[Question]] = {}
        for question in question_result.scalars().all():
            total_questions += 1
            if question.explanation:
                questions_with_explanation += 1
            key = (question.question_type, normalize_content(question.content))
            questions_by_key.setdefault(key, []).append(question)

        for row in unique_rows:
            questions = questions_by_key.get((row.question_type, row.content), [])

            if not questions:
                missing += 1
                if len(missing_samples) < 20:
                    missing_samples.append(f"{row.question_type}: {row.content}")
                continue

            if len(questions) > 1:
                duplicates += len(questions) - 1

            for question in questions:
                if (question.explanation or "") == row.explanation:
                    unchanged += 1
                    continue
                question.explanation = row.explanation
                matched += 1

        await session.commit()

    await engine.dispose()
    return {
        "read": len(rows),
        "unique_rows": len(unique_rows),
        "duplicate_excel_rows": duplicate_excel_rows,
        "total_questions": total_questions,
        "updated": matched,
        "unchanged": unchanged,
        "missing": missing,
        "duplicate_extra_rows": duplicates,
        "questions_with_explanation_before": questions_with_explanation,
        "missing_samples": missing_samples,
    }


async def main() -> None:
    excel_path = resolve_excel_path()
    if not os.path.exists(excel_path):
        raise FileNotFoundError(excel_path)

    rows = read_explanations_from_excel(excel_path)
    stats = await update_database(rows)

    print("[SUMMARY]")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
