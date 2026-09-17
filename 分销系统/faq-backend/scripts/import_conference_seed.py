"""
分销商大会种子数据导入脚本

幂等执行（可重复运行）：
a) 向 questions 表导入 3 个题组题目：
   - conference_business（商务展区，docx 原文 Q1-Q5）
   - conference_new_v   （New V 展区，3 道占位题）
   - conference_digital （数字化展区，3 道占位题）
b) 向 conference_zones 插入 4 条展区配置（code 唯一冲突时跳过）
c) 打印导入结果统计

用法:
  cd faq-backend
  python scripts/import_conference_seed.py
"""
from __future__ import annotations

import asyncio
import sys
import os
from typing import Optional

# 把项目根目录加入 sys.path，以便 import app 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.conference import ConferenceZone
from app.models.question import Question

# ── 商务展区题组（category='conference_business'，来源 docx 原文）──────────
BUSINESS_QUESTIONS = [
    {
        "question_type": "single_choice",
        "content": "锁铜截止时间是交易日当天几点（需在此时间之前提供盖章合同以及预付款）？",
        "options": ["12:30", "13:00", "13:30"],
        "answer": "B",
        "difficulty": 1,
        "is_active": True,
        "category": "conference_business",
    },
    {
        "question_type": "multiple_choice",
        "content": "正常情况下（不考虑特殊产品定制），影响产品报价的五要素是什么？（多选题）",
        "options": [
            "项目所在地（影响运费）",
            "非标质保期（延保费）",
            "非标付款（可能产生资金成本）",
            "包装方式",
            "是否需要现场服务",
        ],
        "answer": "ABCDE",
        "difficulty": 1,
        "is_active": True,
        "category": "conference_business",
    },
    {
        "question_type": "single_choice",
        "content": "关于延保收费标准：若一个项目需要质保期为出厂后5年，则应在标准报价基础上加几个点作为合同价？",
        "options": ["4%", "5%", "6%"],
        "answer": "C",
        "difficulty": 1,
        "is_active": True,
        "category": "conference_business",
    },
    {
        "question_type": "single_choice",
        "content": "合同（订货单）金额大于多少万，必须原件快递施耐德进行归档？",
        "options": ["50万", "60万", "70万"],
        "answer": "A",
        "difficulty": 1,
        "is_active": True,
        "category": "conference_business",
    },
    {
        "question_type": "single_choice",
        "content": "铜母线产品合同：当铜现货市场含税均价≥多少万元/吨时，调整系数T值为80%？",
        "options": ["6万", "7万", "8万"],
        "answer": "B",
        "difficulty": 1,
        "is_active": True,
        "category": "conference_business",
    },
]

# ── 占位题组（conference_new_v / conference_digital）──────────────────────
def _placeholder_questions(category: str, zone_name: str, count: int) -> list[dict]:
    """生成占位单选题，题干注明占位，后补真实题。"""
    questions = []
    for index in range(1, count + 1):
        questions.append(
            {
                "question_type": "single_choice",
                "content": f"{zone_name}占位题 {index}/{count}（占位题，待替换为真实题目）",
                "options": ["选项A", "选项B", "选项C", "选项D"],
                "answer": "A",
                "difficulty": 1,
                "is_active": True,
                "category": category,
            }
        )
    return questions


PLACEHOLDER_QUESTIONS = (
    _placeholder_questions("conference_new_v", "New V 展区", 3)
    + _placeholder_questions("conference_digital", "数字化展区", 3)
)

# ── 展区配置（code 唯一冲突时跳过）─────────────────────────────────────────
ZONES = [
    {
        "code": "new_v",
        "name": "New V 展区",
        "slogan": None,
        "icon_url": None,
        "sort_order": 1,
        "task_type": "quiz",
        "question_category": "conference_new_v",
        "required_daily_quiz_count": 2,
        "required_ai_chat_count": 2,
        "is_active": True,
    },
    {
        "code": "digital",
        "name": "数字化展区",
        "slogan": None,
        "icon_url": None,
        "sort_order": 2,
        "task_type": "quiz",
        "question_category": "conference_digital",
        "required_daily_quiz_count": 2,
        "required_ai_chat_count": 2,
        "is_active": True,
    },
    {
        "code": "channel",
        "name": "渠道智能赋能展区",
        "slogan": None,
        "icon_url": None,
        "sort_order": 3,
        "task_type": "channel",
        "question_category": None,
        "required_daily_quiz_count": 2,
        "required_ai_chat_count": 2,
        "is_active": True,
    },
    {
        "code": "business",
        "name": "商务展区",
        "slogan": None,
        "icon_url": None,
        "sort_order": 4,
        "task_type": "quiz",
        "question_category": "conference_business",
        "required_daily_quiz_count": 2,
        "required_ai_chat_count": 2,
        "is_active": True,
    },
]


async def _import_question(session, question_data: dict) -> bool:
    """按 (category, content) 幂等导入题目，已存在返回 False。"""
    existing = await session.scalar(
        select(Question.id).where(
            Question.category == question_data["category"],
            Question.content == question_data["content"],
        )
    )
    if existing:
        return False
    session.add(Question(**question_data))
    return True


async def _import_zone(session, zone_data: dict) -> bool:
    """按 code 幂等导入展区，已存在返回 False。"""
    existing = await session.scalar(
        select(ConferenceZone.id).where(ConferenceZone.code == zone_data["code"])
    )
    if existing:
        return False
    session.add(ConferenceZone(**zone_data))
    return True


async def main() -> None:
    all_questions = BUSINESS_QUESTIONS + PLACEHOLDER_QUESTIONS

    async with AsyncSessionLocal() as session:
        inserted_questions = 0
        for question_data in all_questions:
            if await _import_question(session, question_data):
                inserted_questions += 1
        await session.flush()

        inserted_zones = 0
        for zone_data in ZONES:
            if await _import_zone(session, zone_data):
                inserted_zones += 1
        await session.commit()

    # 统计
    async with AsyncSessionLocal() as session:
        for category, label in [
            ("conference_business", "商务展区题组"),
            ("conference_new_v", "New V 展区题组"),
            ("conference_digital", "数字化展区题组"),
        ]:
            count = await session.scalar(
                select(func.count(Question.id)).where(Question.category == category)
            )
            print(f"  {label} ({category}): {count} 题")
        zone_count = await session.scalar(select(func.count(ConferenceZone.id)))
        print(f"  展区配置: {zone_count} 条")

    print(f"导入完成：新增题目 {inserted_questions}/{len(all_questions)}，新增展区 {inserted_zones}/{len(ZONES)}")


if __name__ == "__main__":
    asyncio.run(main())
