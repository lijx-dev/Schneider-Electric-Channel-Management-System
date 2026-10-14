"""把分销商大会三个展区已入库的占位题原位替换为真实题目，并停用商务展区多余题。

背景：import_conference_seed.py 早期向生产库导入了「占位题，待替换为真实题目」，
该脚本按 (category, content) 只做新增，无法替换旧题。本脚本按题目 id 顺序
原位 UPDATE 占位题的 题型/题干/选项/答案，保留 question 主键与历史作答关联，
不删除任何数据。

同时把商务展区（conference_business）原 Q4/Q5 置为 is_active=False：
答题接口只加载启用题，效果等同「只保留前三道」，且随时可恢复、历史作答保留。

安全策略：
- 仅处理题干包含「占位题」的题目；某题组已无占位题时自动跳过（可重复执行）
- 每个展区占位题数量必须与真实题数量一致（均为 3），否则跳过该展区并报警
- 商务停用题按题干精确匹配，只改 is_active，绝不 DELETE
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

# 商务展区停用题（原 Q4/Q5），按 (category, content) 精确匹配
BUSINESS_CATEGORY = "conference_business"
BUSINESS_RETIRED_CONTENTS = [
    "合同（订货单）金额大于多少万，必须原件快递施耐德进行归档？",
    "铜母线产品合同：当铜现货市场含税均价≥多少万元/吨时，调整系数T值为80%？",
]


async def deactivate_business_extras(session) -> int:
    """把商务展区原 Q4/Q5 置为 is_active=False，返回变更行数。"""
    changed = 0
    result = await session.execute(
        select(Question).where(
            Question.category == BUSINESS_CATEGORY,
            Question.is_active.is_(True),
            Question.content.in_(BUSINESS_RETIRED_CONTENTS),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        print("  [商务展区] 未发现需停用的 Q4/Q5（可能已停用或本环境未导入），跳过")
        return 0

    print(f"  [商务展区] 停用 {len(rows)} 道题（is_active=False，保留数据，可恢复）：")
    for row in rows:
        print(f"    id={row.id} {row.content}")
        row.is_active = False
        changed += 1
    return changed


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
        total += await deactivate_business_extras(session)
        for category, real_questions, label in CATEGORY_TARGETS:
            total += await replace_category(session, category, real_questions, label)

        if apply and total:
            await session.commit()
            print(f"\n已提交：变更 {total} 道题（占位题原位更新 / 商务多余题停用）")
        elif total:
            await session.rollback()
            print(f"\n预演完成：计划变更 {total} 道题，未写库")
        else:
            print("\n没有需要更新的题目")

    # 显式释放连接池，避免 Windows 下 aiomysql 在事件循环关闭后 GC 连接报 RuntimeError
    from app.db.session import engine

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
