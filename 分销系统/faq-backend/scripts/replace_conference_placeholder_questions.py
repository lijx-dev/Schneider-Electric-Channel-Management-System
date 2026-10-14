"""把分销商大会三个展区已入库的占位题原位替换为真实题目。

背景：import_conference_seed.py 早期向生产库导入了「占位题，待替换为真实题目」，
该脚本按 (category, content) 只做新增，无法替换旧题。本脚本按题目 id 顺序
原位 UPDATE 占位题的 题型/题干/选项/答案，保留 question 主键与历史作答关联，
不删除任何数据。

安全策略：
- 仅处理题干包含「占位题」的题目；某题组已无占位题时自动跳过（可重复执行）
- 每个展区占位题数量必须与真实题数量一致（均为 3），否则跳过该展区并报警
- 默认 dry-run 只打印变更计划，加 --apply 才写库

用法:
  cd faq-backend
  python scripts/replace_conference_placeholder_questions.py            # 预演
  python scripts/replace_conference_placeholder_questions.py --apply    # 写库
"""
from __future__ import annotations

import asyncio
import os
import sys

# 把项目根目录与 scripts 目录加入 sys.path
_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, _HERE)

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.question import Question
from import_conference_seed import (
    CHANNEL_QUESTIONS,
    DIGITAL_QUESTIONS,
    NEW_V_QUESTIONS,
)

# category -> (真实题列表, 展示名)
CATEGORY_TARGETS = [
    ("conference_new_v", NEW_V_QUESTIONS, "I-Line V Pro 展区"),
    ("conference_digital", DIGITAL_QUESTIONS, "数字母线展区"),
    ("conference_channel", CHANNEL_QUESTIONS, "渠道智能赋能展区"),
]

# 旧种子脚本占位题题干均含该标记
PLACEHOLDER_MARK = "占位题"

# 原位更新的字段（不动 id/category/is_active/difficulty 及历史作答关联）
UPDATE_FIELDS = ("question_type", "content", "options", "answer")


async def replace_category(session, category: str, real_questions: list[dict], label: str) -> int:
    """原位替换一个展区的占位题，返回实际更新行数。"""
    result = await session.execute(
        select(Question)
        .where(
            Question.category == category,
            Question.is_active.is_(True),
            Question.content.like(f"%{PLACEHOLDER_MARK}%"),
        )
        .order_by(Question.id)
    )
    placeholders = list(result.scalars().all())

    if not placeholders:
        print(f"  [{label}] 未发现占位题（可能已替换），跳过")
        return 0

    if len(placeholders) != len(real_questions):
        print(
            f"  [{label}] 安全拦截：占位题 {len(placeholders)} 道 != 真实题 {len(real_questions)} 道，"
            f"跳过本展区，请人工核对 category={category}"
        )
        return 0

    print(f"  [{label}] 命中 {len(placeholders)} 道占位题，按 id 顺序原位替换：")
    for index, (row, real) in enumerate(zip(placeholders, real_questions), start=1):
        print(f"    {index}. id={row.id} {row.question_type} {row.content}")
        print(f"       -> {real['question_type']} {real['content']}  答案={real['answer']}")
        for field in UPDATE_FIELDS:
            setattr(row, field, real[field])
    return len(placeholders)


async def main(apply: bool) -> None:
    mode = "写库 (--apply)" if apply else "dry-run 预演（加 --apply 才会写库）"
    print(f"分销商大会占位题替换：{mode}\n")

    total = 0
    async with AsyncSessionLocal() as session:
        for category, real_questions, label in CATEGORY_TARGETS:
            total += await replace_category(session, category, real_questions, label)

        if apply and total:
            await session.commit()
            print(f"\n已提交：原位更新 {total} 道题")
        elif total:
            await session.rollback()
            print(f"\n预演完成：计划更新 {total} 道题，未写库")
        else:
            print("\n没有需要更新的题目")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
