"""
Excel 题库导入脚本

从 Excel 文件中读取5种题型，写入 SQLite/MySQL 数据库。

Excel 格式要求（数据从第4行开始）：
- A列: 题目内容
- B列: 分类/考核点
- C列: 难度描述（如"易"、"中"、"难"）
- D列: 分值（当前忽略）
- E列: 试题解析/考核点
- F列: 正确答案
- G-R列: 选项A-L（选择题）
- 解析列: 表头为“解析”的列（不同 Sheet 位置可能不同）
- 支持 5 个 Sheet：单选题、多选题、填空题、问答题、判断题

常用环境变量：
- EXCEL_PATH: Excel 文件路径
- RESET_QUESTION_BANK: 是否先清空旧题库相关数据（true/false）
- AUTO_CONFIRM: 是否跳过导入确认（true/false）

用法:
  cd faq-backend
  venv\\Scripts\\python scripts/import_questions.py
"""
import sys
import os
from collections import Counter

# 把项目根目录加入 sys.path，以便 import app 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import xlrd
from sqlalchemy import text, delete

# ── 配置 ──────────────────────────────────────────────────────
DEFAULT_EXCEL_PATH = r"C:\Users\86135\Desktop\FAQ源数据集\技术综合题库20221210tosarah--勘正-1.xls"

# Sheet 名称 → 题型映射
SHEET_TYPE_MAP = {
    "单选题": "single_choice",
    "多选题": "multiple_choice",
    "填空题": "fill_blank",
    "问答题": "short_answer",
    "判断题": "true_false",
}

# 难度标签 → 数值映射
DIFFICULTY_MAP = {
    "易": 1,
    "中": 2,
    "难": 3,
    "技术基础": 1,
    "技术综合": 2,
    "技": 1,   # 防止表格里有缩写
}
DEFAULT_DIFFICULTY = 1

# 数据起始行（0-indexed，第4行 = index 3）
DATA_START_ROW = 3

# 手工分类修正：用于覆盖源表中的个别异常数据
CATEGORY_OVERRIDES = {
    "IEC认证和3C认证有什么不同（）？": "规范&认证&测试",
}

# 明确不导入的题目
SKIP_QUESTION_CONTENTS = {
    "现阶段国内轮胎行业生产企业较多的省份是（）？",
}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_excel_path() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip().strip('"')

    return os.getenv("EXCEL_PATH") or DEFAULT_EXCEL_PATH


def clean_text(value) -> str:
    """清理单元格值，转为干净的字符串"""
    if value is None:
        return ""
    s = str(value).strip()
    # xlrd 读取的浮点数（如 1.0）转为整数字符串
    if s.endswith(".0"):
        try:
            return str(int(float(s)))
        except ValueError:
            pass
    return s


def parse_difficulty(label: str) -> int:
    """将难度标签转为数值"""
    label = label.strip()
    if not label:
        return DEFAULT_DIFFICULTY

    for key, val in DIFFICULTY_MAP.items():
        if key in label:
            return val
    return DEFAULT_DIFFICULTY


def read_category(sheet, row_idx: int) -> str:
    return clean_text(sheet.cell_value(row_idx, 1))


def resolve_category(content: str, raw_category: str) -> str | None:
    normalized_content = clean_text(content)
    if normalized_content in SKIP_QUESTION_CONTENTS:
        print(f"[SKIP] 题目已按规则移除: {normalized_content}")
        return None

    if normalized_content in CATEGORY_OVERRIDES:
        return CATEGORY_OVERRIDES[normalized_content]

    normalized_category = clean_text(raw_category)
    if normalized_category:
        return normalized_category

    print(f"[SKIP] 题目缺少分类，已跳过: {normalized_content}")
    return None


def find_header_col(sheet, header_name: str, header_row: int = 2) -> int | None:
    if sheet.nrows <= header_row:
        return None

    for col_idx in range(sheet.ncols):
        if clean_text(sheet.cell_value(header_row, col_idx)) == header_name:
            return col_idx
    return None


def read_explanation(sheet, row_idx: int) -> str:
    col_idx = find_header_col(sheet, "解析")
    if col_idx is None:
        return ""
    return clean_text(sheet.cell_value(row_idx, col_idx))


def read_options(sheet, row_idx: int, start_col: int = 6) -> list:
    options = []
    explanation_col = find_header_col(sheet, "解析")
    end_col = explanation_col if explanation_col is not None else sheet.ncols
    for col_idx in range(start_col, end_col):
        opt = clean_text(sheet.cell_value(row_idx, col_idx))
        if opt:
            options.append(opt)
    return options


def read_single_choice(sheet) -> list:
    """读取单选题 Sheet"""
    questions = []
    for row_idx in range(DATA_START_ROW, sheet.nrows):
        content = clean_text(sheet.cell_value(row_idx, 0))    # A列：题目
        if not content:
            continue

        raw_category = read_category(sheet, row_idx)               # B列：分类
        category = resolve_category(content, raw_category)
        difficulty_label = clean_text(sheet.cell_value(row_idx, 2))  # C列：难度
        answer = clean_text(sheet.cell_value(row_idx, 5))            # F列：正确答案
        explanation = read_explanation(sheet, row_idx)

        # G-R列：选项 A-L
        options = read_options(sheet, row_idx)

        if not category or not answer or not options:
            continue

        questions.append({
            "question_type": "single_choice",
            "content": content,
            "category": category,
            "options": options,
            "answer": answer.upper(),
            "explanation": explanation,
            "difficulty_label": difficulty_label,
            "difficulty": parse_difficulty(difficulty_label),
        })
    return questions


def read_multiple_choice(sheet) -> list:
    """读取多选题 Sheet"""
    questions = []
    for row_idx in range(DATA_START_ROW, sheet.nrows):
        content = clean_text(sheet.cell_value(row_idx, 0))
        if not content:
            continue

        raw_category = read_category(sheet, row_idx)
        category = resolve_category(content, raw_category)
        difficulty_label = clean_text(sheet.cell_value(row_idx, 2))
        answer = clean_text(sheet.cell_value(row_idx, 5))
        explanation = read_explanation(sheet, row_idx)

        # G-R列：选项 A-L
        options = read_options(sheet, row_idx)

        if not category or not answer or not options:
            continue

        questions.append({
            "question_type": "multiple_choice",
            "content": content,
            "category": category,
            "options": options,
            "answer": answer.upper(),
            "explanation": explanation,
            "difficulty_label": difficulty_label,
            "difficulty": parse_difficulty(difficulty_label),
        })
    return questions


def read_fill_blank(sheet) -> list:
    """读取填空题 Sheet

    填空题的多个答案分布在 F、G、H... 多列，每个空对应一列。
    用 ';' 拼接多个答案，如 "型式试验;耐火"
    """
    questions = []
    for row_idx in range(DATA_START_ROW, sheet.nrows):
        content = clean_text(sheet.cell_value(row_idx, 0))
        if not content:
            continue

        raw_category = read_category(sheet, row_idx)
        category = resolve_category(content, raw_category)
        difficulty_label = clean_text(sheet.cell_value(row_idx, 2))
        explanation = read_explanation(sheet, row_idx)

        # 从 F 列开始，读取所有非空的答案列
        answers = []
        for col_idx in range(5, sheet.ncols):  # F=5 开始向后扫描
            val = clean_text(sheet.cell_value(row_idx, col_idx))
            if val:
                answers.append(val)
            else:
                break  # 遇到空列就停止

        if not category or not answers:
            continue

        # 多个答案用 ; 分隔
        answer_str = ";".join(answers)

        # 统计题目中有几个空（以（）计数）
        blank_count = content.count("（）") + content.count("()")

        questions.append({
            "question_type": "fill_blank",
            "content": content,
            "category": category,
            "options": None,
            "answer": answer_str,
            "explanation": explanation,
            "blank_count": max(blank_count, len(answers)),
            "difficulty_label": difficulty_label,
            "difficulty": parse_difficulty(difficulty_label),
        })
    return questions


def read_short_answer(sheet) -> list:
    """读取问答题/解答题 Sheet"""
    questions = []
    for row_idx in range(DATA_START_ROW, sheet.nrows):
        content = clean_text(sheet.cell_value(row_idx, 0))
        if not content:
            continue

        raw_category = read_category(sheet, row_idx)
        category = resolve_category(content, raw_category)
        difficulty_label = clean_text(sheet.cell_value(row_idx, 2))
        answer = clean_text(sheet.cell_value(row_idx, 5))
        explanation = read_explanation(sheet, row_idx)

        if not category or not answer:
            continue

        questions.append({
            "question_type": "short_answer",
            "content": content,
            "category": category,
            "options": None,
            "answer": answer,
            "explanation": explanation,
            "difficulty_label": difficulty_label,
            "difficulty": parse_difficulty(difficulty_label),
        })
    return questions


def read_true_false(sheet) -> list:
    """读取判断题 Sheet"""
    questions = []
    for row_idx in range(DATA_START_ROW, sheet.nrows):
        content = clean_text(sheet.cell_value(row_idx, 0))
        if not content:
            continue

        raw_category = read_category(sheet, row_idx)
        category = resolve_category(content, raw_category)
        difficulty_label = clean_text(sheet.cell_value(row_idx, 2))
        answer = clean_text(sheet.cell_value(row_idx, 5))
        explanation = read_explanation(sheet, row_idx)

        if not category or not answer:
            continue

        questions.append({
            "question_type": "true_false",
            "content": content,
            "category": category,
            "options": ["对", "错"],
            "answer": answer,
            "explanation": explanation,
            "difficulty_label": difficulty_label,
            "difficulty": parse_difficulty(difficulty_label),
        })
    return questions


# Sheet 名称 → 解析函数
SHEET_PARSER_MAP = {
    "单选题": read_single_choice,
    "多选题": read_multiple_choice,
    "填空题": read_fill_blank,
    "问答题": read_short_answer,
    "判断题": read_true_false,
}


def read_all_from_excel(file_path: str) -> list:
    """读取 Excel 中所有 Sheet 的题目"""
    workbook = xlrd.open_workbook(file_path)
    all_questions = []

    print(f"[FILE] 打开文件: {file_path}")
    print(f"[SHEETS] 发现 {workbook.nsheets} 个 Sheet: {workbook.sheet_names()}")

    for sheet_name in workbook.sheet_names():
        if sheet_name not in SHEET_PARSER_MAP:
            print(f"  ⏭ 跳过未知 Sheet: {sheet_name}")
            continue

        sheet = workbook.sheet_by_name(sheet_name)
        parser = SHEET_PARSER_MAP[sheet_name]
        questions = parser(sheet)
        all_questions.extend(questions)
        print(f"  [OK] {sheet_name}: 读取 {len(questions)} 道题")

    print(f"\n[SUMMARY] 总计读取 {len(all_questions)} 道题")
    return all_questions


def print_question_summary(questions: list) -> None:
    if not questions:
        return

    type_counter = Counter(q["question_type"] for q in questions)
    category_counter = Counter((q.get("category") or "未分类") for q in questions)

    print("\n[TYPE] 题型分布：")
    for question_type, count in sorted(type_counter.items()):
        print(f"  - {question_type}: {count} 道")

    print("\n[CATEGORY] 分类分布（前 15 项）：")
    for category, count in category_counter.most_common(15):
        print(f"  - {category}: {count} 道")


async def reset_question_bank_data(session):
    from app.models.question import Question
    from app.models.record import AnswerRecord, DailyQuizRound

    print("\n[RESET] 清空旧题库数据...")

    await session.execute(delete(DailyQuizRound))
    await session.execute(delete(AnswerRecord))
    await session.execute(delete(Question))

    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "mysql":
        for table_name in ("daily_quiz_rounds", "answer_records", "questions"):
            await session.execute(text(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = 1"))
    elif dialect_name == "sqlite":
        await session.execute(
            text(
                "DELETE FROM sqlite_sequence "
                "WHERE name IN ('daily_quiz_rounds', 'answer_records', 'questions')"
            )
        )

    await session.commit()
    print("[OK] 旧题库数据已清空")


async def import_to_db(questions: list, reset_before_import: bool = False):
    """将题目写入数据库"""
    from app.db.session import engine, AsyncSessionLocal, init_db
    from app.models.question import Question

    # 初始化数据库表
    await init_db()

    async with AsyncSessionLocal() as session:
        if reset_before_import:
            await reset_question_bank_data(session)

        # 统计
        count = 0
        for q in questions:
            question = Question(
                question_type=q["question_type"],
                content=q["content"],
                category=q.get("category"),
                options=q["options"],
                answer=q["answer"],
                explanation=q.get("explanation") or None,
                difficulty_label=q["difficulty_label"],
                difficulty=q["difficulty"],
                is_active=True,
            )
            session.add(question)
            count += 1

        await session.commit()
        print(f"\n[OK] 成功导入 {count} 道题到数据库！")

    # 关闭引擎
    await engine.dispose()


async def main():
    excel_path = resolve_excel_path()
    reset_before_import = env_flag("RESET_QUESTION_BANK", default=False)
    auto_confirm = env_flag("AUTO_CONFIRM", default=False)

    # 检查文件
    if not os.path.exists(excel_path):
        print(f"[ERROR] 文件不存在: {excel_path}")
        return

    # 读取 Excel
    questions = read_all_from_excel(excel_path)

    if not questions:
        print("[ERROR] 没有读取到任何题目")
        return

    print_question_summary(questions)

    # 预览前3题
    print("\n[PREVIEW] 预览前3道题：")
    for i, q in enumerate(questions[:3]):
        print(f"  [{i+1}] [{q['question_type']}] [{q['category']}] {q['content'][:50]}...")
        if q["options"]:
            print(f"      选项: {q['options'][:4]}...")
        print(f"      答案: {q['answer'][:30]}")
        print(f"      难度: {q['difficulty_label']} → {q['difficulty']}")

    # 确认导入
    print(f"\n即将导入 {len(questions)} 道题到数据库...")
    if reset_before_import:
        print("[WARN] 本次导入会先清空 questions / answer_records / daily_quiz_rounds")

    if auto_confirm:
        print("AUTO_CONFIRM=true，跳过手动确认")
    else:
        confirm = input("确认导入？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    # 导入
    await import_to_db(questions, reset_before_import=reset_before_import)


if __name__ == "__main__":
    asyncio.run(main())
