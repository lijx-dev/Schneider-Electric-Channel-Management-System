"""Apply colour-marked question corrections from the Excel workbook.

Green, red, and yellow marked rows/cells are updated from Excel. Grey marked
rows are removed from the visible question bank by default (`is_active=False`).
Use `--hard-delete` only when answer history can also be removed by cascading
foreign keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pymysql
import xlrd
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


DEFAULT_EXCEL_PATH = (
    r"C:\Users\86135\Desktop\FAQ源数据集"
    r"\技术综合题库20221210tosarah--勘正-1toveeko-分类入数据库添加解析(1).xls"
)

HEADER_ROW = 2
DATA_START_ROW = 3

SHEET_TYPE_MAP = {
    "单选题": "single_choice",
    "多选题": "multiple_choice",
    "判断题": "true_false",
}

TYPE_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "true_false": "判断题",
}

UPDATE_RGBS = {
    (153, 204, 0),  # light green row marker
    (146, 208, 80),  # light green row marker in xlsx files
    (0, 128, 0),  # dark green cell marker
    (255, 0, 0),  # red cell marker
    (255, 255, 0),  # yellow cell marker
}
DELETE_RGBS = {
    (128, 128, 128),  # grey row marker
    ("theme", 0, -0.3499862666707358),  # dark grey in some xlsx files
}

DIFFICULTY_MAP = {
    "易": 1,
    "中": 2,
    "难": 3,
}

SKIP_CONTENTS = {
    "现阶段国内轮胎行业生产企业较多的省份是（）？",
}


@dataclass(frozen=True)
class ParsedCorrection:
    file_path: str
    sheet_name: str
    row_number: int
    action: str
    marker_rgbs: tuple[tuple[int, int, int], ...]
    question_type: str
    content: str
    category: str | None
    difficulty_label: str | None
    difficulty: int
    answer: str
    options: list[str] | None
    explanation: str | None


def clean_text(value: Any) -> str:
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


def normalize_category(value: str) -> str | None:
    text = clean_text(value)
    return text or None


def normalize_choice_answer(answer: str) -> str:
    letters: list[str] = []
    for char in clean_text(answer).upper():
        if char in "ABCDEFGHIJKL" and char not in letters:
            letters.append(char)
    return "".join(letters)


def normalize_answer(question_type: str, value: str) -> str:
    answer = clean_text(value)
    if question_type in {"single_choice", "multiple_choice"}:
        return normalize_choice_answer(answer) or answer.upper()
    return answer


def xls_cell_rgb(workbook, sheet, row_idx: int, col_idx: int):
    xf = workbook.xf_list[sheet.cell_xf_index(row_idx, col_idx)]
    pattern_colour = xf.background.pattern_colour_index
    background_colour = xf.background.background_colour_index
    colour_index = pattern_colour if pattern_colour not in (0, 64, 65) else background_colour
    return workbook.colour_map.get(colour_index)


def xls_marked_rgbs_for_row(workbook, sheet, row_idx: int) -> set[Any]:
    rgbs: set[Any] = set()
    for col_idx in range(sheet.ncols):
        rgb = xls_cell_rgb(workbook, sheet, row_idx, col_idx)
        if rgb in UPDATE_RGBS or rgb in DELETE_RGBS:
            rgbs.add(rgb)
    return rgbs


def xls_find_header_col(sheet, candidates: set[str]) -> int:
    for col_idx in range(sheet.ncols):
        header = clean_text(sheet.cell_value(HEADER_ROW, col_idx))
        if header in candidates:
            return col_idx
    raise RuntimeError(f"{sheet.name} missing header: {sorted(candidates)}")


def xlsx_cell_rgb(cell):
    fill = cell.fill
    if not fill or fill.fill_type is None:
        return None
    color = fill.fgColor
    if color.type == "rgb" and color.rgb:
        value = color.rgb[-6:].upper()
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    if color.type == "theme":
        return ("theme", color.theme, color.tint)
    if color.type == "indexed":
        return ("indexed", color.indexed)
    return None


def xlsx_marked_rgbs_for_row(sheet, row_idx: int) -> set[Any]:
    rgbs: set[Any] = set()
    for col_idx in range(1, sheet.max_column + 1):
        rgb = xlsx_cell_rgb(sheet.cell(row_idx, col_idx))
        if rgb in UPDATE_RGBS or rgb in DELETE_RGBS:
            rgbs.add(rgb)
    return rgbs


def xlsx_find_header_col(sheet, candidates: set[str]) -> int:
    for col_idx in range(1, sheet.max_column + 1):
        header = clean_text(sheet.cell(1, col_idx).value).lstrip("\ufeff")
        if header in candidates:
            return col_idx
    raise RuntimeError(f"{sheet.title} missing header: {sorted(candidates)}")


def question_type_from_row(content: str, answer: str, options: list[str]) -> str:
    normalized_answer = normalize_choice_answer(answer)
    if answer in {"正确", "错误", "对", "错"}:
        return "true_false"
    if options:
        return "multiple_choice" if len(normalized_answer) > 1 else "single_choice"
    return "short_answer"


def parse_xls_workbook(file_path: str) -> list[ParsedCorrection]:
    workbook = xlrd.open_workbook(file_path, formatting_info=True)
    corrections: list[ParsedCorrection] = []

    for sheet in workbook.sheets():
        question_type = SHEET_TYPE_MAP.get(sheet.name)
        if not question_type:
            continue

        content_col = xls_find_header_col(sheet, {"题目：", "题目"})
        category_col = xls_find_header_col(sheet, {"类别", "考核点：", "考核点"})
        difficulty_col = xls_find_header_col(sheet, {"难度：", "难度"})
        answer_col = xls_find_header_col(sheet, {"正确答案", "正确答案："})
        explanation_col = xls_find_header_col(sheet, {"解析"})

        for row_idx in range(DATA_START_ROW, sheet.nrows):
            content = normalize_content(sheet.cell_value(row_idx, content_col))
            if not content:
                continue
            if content in SKIP_CONTENTS:
                continue

            marker_rgbs = xls_marked_rgbs_for_row(workbook, sheet, row_idx)
            if not marker_rgbs:
                continue

            action = "deactivate" if marker_rgbs & DELETE_RGBS else "update"
            options: list[str] | None
            if question_type == "true_false":
                options = ["正确", "错误"]
            else:
                options = [
                    clean_text(sheet.cell_value(row_idx, col_idx))
                    for col_idx in range(answer_col + 1, explanation_col)
                    if clean_text(sheet.cell_value(row_idx, col_idx))
                ]

            difficulty_label = clean_text(sheet.cell_value(row_idx, difficulty_col)) or None
            corrections.append(
                ParsedCorrection(
                    file_path=file_path,
                    sheet_name=sheet.name,
                    row_number=row_idx + 1,
                    action=action,
                    marker_rgbs=tuple(sorted(marker_rgbs)),
                    question_type=question_type,
                    content=content,
                    category=normalize_category(sheet.cell_value(row_idx, category_col)),
                    difficulty_label=difficulty_label,
                    difficulty=DIFFICULTY_MAP.get(difficulty_label or "", 1),
                    answer=normalize_answer(question_type, sheet.cell_value(row_idx, answer_col)),
                    options=options,
                    explanation=clean_text(sheet.cell_value(row_idx, explanation_col)) or None,
                )
            )

    return corrections


def parse_xlsx_workbook(file_path: str) -> list[ParsedCorrection]:
    workbook = load_workbook(file_path, read_only=False, data_only=True)
    corrections: list[ParsedCorrection] = []

    for sheet in workbook.worksheets:
        if sheet.max_row < 2:
            continue

        content_col = xlsx_find_header_col(sheet, {"题目：", "题目"})
        answer_col = xlsx_find_header_col(sheet, {"正确答案", "正确答案："})
        explanation_col = xlsx_find_header_col(sheet, {"解析"})
        category_col = xlsx_find_header_col(sheet, {"题型分类", "类别", "考核点：", "考核点"})
        option_cols = [
            xlsx_find_header_col(sheet, {f"选项{letter}", f"答案{letter}"})
            for letter in "ABCDEF"
            if any(
                clean_text(sheet.cell(1, col_idx).value).lstrip("\ufeff")
                in {f"选项{letter}", f"答案{letter}"}
                for col_idx in range(1, sheet.max_column + 1)
            )
        ]

        for row_idx in range(2, sheet.max_row + 1):
            content = normalize_content(sheet.cell(row_idx, content_col).value)
            if not content or content in SKIP_CONTENTS:
                continue

            marker_rgbs = xlsx_marked_rgbs_for_row(sheet, row_idx)
            if not marker_rgbs:
                continue

            options = [
                clean_text(sheet.cell(row_idx, col_idx).value)
                for col_idx in option_cols
                if clean_text(sheet.cell(row_idx, col_idx).value)
            ]
            raw_answer = clean_text(sheet.cell(row_idx, answer_col).value)
            question_type = question_type_from_row(content, raw_answer, options)
            normalized_options = ["正确", "错误"] if question_type == "true_false" else options or None
            action = "delete" if marker_rgbs & DELETE_RGBS else "update"

            corrections.append(
                ParsedCorrection(
                    file_path=file_path,
                    sheet_name=sheet.title,
                    row_number=row_idx,
                    action=action,
                    marker_rgbs=tuple(sorted(marker_rgbs, key=str)),
                    question_type=question_type,
                    content=content,
                    category=normalize_category(sheet.cell(row_idx, category_col).value),
                    difficulty_label=None,
                    difficulty=1,
                    answer=normalize_answer(question_type, raw_answer),
                    options=normalized_options,
                    explanation=clean_text(sheet.cell(row_idx, explanation_col).value) or None,
                )
            )

    workbook.close()
    return corrections


def parse_workbook(file_path: str) -> list[ParsedCorrection]:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".xls":
        return parse_xls_workbook(file_path)
    if suffix == ".xlsx":
        return parse_xlsx_workbook(file_path)
    raise RuntimeError(f"Unsupported workbook type: {file_path}")


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_content(left), normalize_content(right)).ratio()


def choose_match(correction: ParsedCorrection, questions, used_ids: set[int]):
    candidates = [
        question
        for question in questions
        if question.question_type == correction.question_type and question.id not in used_ids
    ]

    exact = [
        question
        for question in candidates
        if normalize_content(question.content) == normalize_content(correction.content)
    ]
    if len(exact) == 1:
        return 1.0, exact[0], []

    ranked = sorted(
        ((similarity(correction.content, question.content), question) for question in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    close = [(score, question) for score, question in ranked[:3]]
    return (close[0][0], close[0][1], close[1:]) if close else (0.0, None, [])


def changed_fields(question, correction: ParsedCorrection) -> list[str]:
    desired_explanation = correction.explanation or None
    checks = {
        "content": question.content != correction.content,
        "category": question.category != correction.category,
        "difficulty_label": question.difficulty_label != correction.difficulty_label,
        "difficulty": question.difficulty != correction.difficulty,
        "answer": question.answer != correction.answer,
        "options": question.options != correction.options,
        "explanation": (question.explanation or None) != desired_explanation,
        "is_active": question.is_active is not True,
    }
    return [field for field, changed in checks.items() if changed]


def db_connect(database_url: str):
    parsed = urlparse(database_url)
    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=(parsed.path or "/").lstrip("/"),
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
        cursorclass=pymysql.cursors.DictCursor,
    )


def load_questions(cursor) -> list[SimpleNamespace]:
    cursor.execute(
        """
        SELECT
          id, question_type, content, options, answer, explanation, category,
          difficulty_label, difficulty, is_active
        FROM questions
        """
    )
    questions = []
    for row in cursor.fetchall():
        options = row["options"]
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except json.JSONDecodeError:
                pass
        row["options"] = options
        questions.append(SimpleNamespace(**row))
    return questions


def update_question(cursor, question_id: int, correction: ParsedCorrection) -> None:
    cursor.execute(
        """
        UPDATE questions
        SET
          content = %s,
          category = %s,
          difficulty_label = %s,
          difficulty = %s,
          answer = %s,
          options = %s,
          explanation = %s,
          is_active = 1,
          updated_at = NOW()
        WHERE id = %s
        """,
        (
            correction.content,
            correction.category,
            correction.difficulty_label,
            correction.difficulty,
            correction.answer,
            json.dumps(correction.options, ensure_ascii=False) if correction.options is not None else None,
            correction.explanation,
            question_id,
        ),
    )


def run(file_paths: list[str], apply: bool, hard_delete: bool, threshold: float) -> dict:
    from app.core.config import settings

    if settings.DB_TYPE != "mysql" or not settings.DATABASE_URL:
        raise RuntimeError("This correction script expects DB_TYPE=mysql and DATABASE_URL.")

    database_url = settings.DATABASE_URL.replace("+aiomysql", "")
    corrections: list[ParsedCorrection] = []
    for file_path in file_paths:
        corrections.extend(parse_workbook(file_path))
    report: list[dict] = []
    errors: list[str] = []

    connection = db_connect(database_url)
    try:
        cursor = connection.cursor()
        questions = load_questions(cursor)
        used_ids: set[int] = set()

        for correction in corrections:
            score, question, alternatives = choose_match(correction, questions, used_ids)
            if question is None or score < threshold:
                errors.append(
                    f"{correction.sheet_name}!row {correction.row_number} no safe match "
                    f"(best={score:.3f}): {correction.content}"
                )
                continue

            used_ids.add(question.id)
            fields = changed_fields(question, correction)
            item = {
                "action": correction.action,
                "file": correction.file_path,
                "row": f"{correction.sheet_name}!{correction.row_number}",
                "id": question.id,
                "question_type": question.question_type,
                "score": round(score, 3),
                "fields": fields,
                "content": correction.content,
                "before_content": question.content,
                "alt_scores": [
                    {
                        "id": alt.id,
                        "score": round(alt_score, 3),
                        "content": alt.content[:80],
                    }
                    for alt_score, alt in alternatives
                ],
            }

            if correction.action in {"deactivate", "delete"}:
                item["fields"] = ["delete"] if correction.action == "delete" else ["is_active"]
                if apply:
                    if correction.action == "delete" or hard_delete:
                        cursor.execute("DELETE FROM questions WHERE id = %s", (question.id,))
                        item["action"] = "hard-delete"
                    else:
                        cursor.execute(
                            "UPDATE questions SET is_active = 0, updated_at = NOW() WHERE id = %s",
                            (question.id,),
                        )
            else:
                if apply and fields:
                    update_question(cursor, question.id, correction)

            report.append(item)

        if errors:
            connection.rollback()
        elif apply:
            connection.commit()
        else:
            connection.rollback()
    finally:
        connection.close()

    action_counts = Counter(item["action"] for item in report)
    field_counts = Counter(field for item in report for field in item["fields"])
    return {
        "mode": "APPLY" if apply else "DRY-RUN",
        "excel_paths": file_paths,
        "marked_rows": len(corrections),
        "matched_rows": len(report),
        "action_counts": dict(action_counts),
        "field_counts": dict(field_counts),
        "errors": errors,
        "report": report,
    }


def print_report(result: dict) -> None:
    print(f"[{result['mode']}]")
    for file_path in result["excel_paths"]:
        print(f"  file={file_path}")
    print(f"marked_rows={result['marked_rows']} matched_rows={result['matched_rows']}")
    print(f"action_counts={result['action_counts']}")
    print(f"field_counts={result['field_counts']}")
    if result["errors"]:
        print("[ERRORS]")
        for error in result["errors"]:
            print(f"  - {error}")
        return

    for item in result["report"]:
        fields = ",".join(item["fields"]) if item["fields"] else "unchanged"
        type_label = TYPE_LABELS.get(item.get("question_type", ""), "")
        file_name = Path(item["file"]).name
        print(
            f"[{item['action']}] file={file_name} row={item['row']} id={item['id']} "
            f"score={item['score']} fields={fields} {type_label}"
        )
        if item["score"] < 1:
            print(f"  db   : {item['before_content']}")
            print(f"  excel: {item['content']}")
            for alt in item["alt_scores"]:
                print(f"  alt  : id={alt['id']} score={alt['score']} {alt['content']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--excel-path",
        action="append",
        dest="excel_paths",
        help="Workbook path. Can be passed more than once.",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to the database.")
    parser.add_argument(
        "--hard-delete",
        action="store_true",
        help="Physically delete grey-marked rows instead of setting is_active=False.",
    )
    parser.add_argument("--match-threshold", type=float, default=0.72)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_paths = args.excel_paths or [os.getenv("EXCEL_PATH") or DEFAULT_EXCEL_PATH]
    file_paths = [str(Path(file_path)) for file_path in raw_paths]
    for file_path in file_paths:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
    result = run(
        file_paths=file_paths,
        apply=args.apply,
        hard_delete=args.hard_delete,
        threshold=args.match_threshold,
    )
    print_report(result)
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
