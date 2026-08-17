"""认可计划系统测试数据种子脚本.

运行方式（在 faq-backend 目录下）:
    python scripts/seed_recognition_test_data.py

功能:
    1. 创建4个角色的测试用户（经理、销售、专员、分销商）
    2. 创建销售-专员对接关系
    3. 创建测试申报数据
    4. 创建测试满意度评分
    5. 创建测试获奖记录
"""
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.user import User
from app.models.recognition import (
    RecognitionSubmission,
    RecognitionSurvey,
    RecognitionPoints,
    RecognitionAward,
    SalesSpecialistMapping,
)

# ── 测试账号配置 ──────────────────────────────────────────────────────────

TEST_USERS = [
    {
        "id": "test-manager-001",
        "openid": "test_openid_manager_001",
        "nickname": "张经理",
        "real_name": "张经理",
        "phone": "13900000001",
        "company": "施耐德电气",
        "province": "北京",
        "job_role": "渠道经理",
        "recognition_role": "manager",
        "recognition_score": 150,
    },
    {
        "id": "test-sales-001",
        "openid": "test_openid_sales_001",
        "nickname": "李销售",
        "real_name": "李销售",
        "phone": "13900000002",
        "company": "施耐德电气",
        "province": "上海",
        "job_role": "销售",
        "recognition_role": "sales",
        "recognition_score": 80,
    },
    {
        "id": "test-sales-002",
        "openid": "test_openid_sales_002",
        "nickname": "王销售",
        "real_name": "王销售",
        "phone": "13900000003",
        "company": "施耐德电气",
        "province": "广州",
        "job_role": "销售",
        "recognition_role": "sales",
        "recognition_score": 60,
    },
    {
        "id": "test-specialist-001",
        "openid": "test_openid_specialist_001",
        "nickname": "赵专员",
        "real_name": "赵专员",
        "phone": "13900000004",
        "company": "施耐德电气",
        "province": "上海",
        "job_role": "技术专员",
        "recognition_role": "specialist",
        "recognition_score": 200,
    },
    {
        "id": "test-specialist-002",
        "openid": "test_openid_specialist_002",
        "nickname": "钱专员",
        "real_name": "钱专员",
        "phone": "13900000005",
        "company": "施耐德电气",
        "province": "广州",
        "job_role": "商务专员",
        "recognition_role": "specialist",
        "recognition_score": 180,
    },
    {
        "id": "test-distributor-001",
        "openid": "test_openid_distributor_001",
        "nickname": "孙分销商",
        "real_name": "孙分销商",
        "phone": "13900000006",
        "company": "华东分销商A",
        "province": "上海",
        "job_role": "分销商",
        "recognition_role": "distributor",
        "recognition_score": 30,
    },
    {
        "id": "test-distributor-002",
        "openid": "test_openid_distributor_002",
        "nickname": "周分销商",
        "real_name": "周分销商",
        "phone": "13900000007",
        "company": "华南分销商B",
        "province": "广州",
        "job_role": "分销商",
        "recognition_role": "distributor",
        "recognition_score": 20,
    },
]

# 销售-专员对接关系（李销售 → 赵专员、钱专员；王销售 → 赵专员）
TEST_MAPPINGS = [
    {"sales_id": "test-sales-001", "specialist_id": "test-specialist-001"},
    {"sales_id": "test-sales-001", "specialist_id": "test-specialist-002"},
    {"sales_id": "test-sales-002", "specialist_id": "test-specialist-001"},
]

# 测试申报数据
TEST_SUBMISSIONS = [
    {
        "applicant_id": "test-specialist-001",
        "submission_type": "order_guardian",
        "content_json": json.dumps({
            "items": ["规范报备流程", "清理重复报备记录"],
            "custom_text": "本季度处理了15个报备冲突问题",
        }, ensure_ascii=False),
        "status": "approved",
        "review_score": 85,
        "quarter": 3,
        "year": 2026,
        "submission_month": "2026-08",
    },
    {
        "applicant_id": "test-specialist-001",
        "submission_type": "distributor_pioneer",
        "content_json": json.dumps({
            "items": ["新问题处理"],
            "custom_text": "帮助华东分销商A解决了母线槽选型问题",
        }, ensure_ascii=False),
        "status": "approved",
        "review_score": 90,
        "quarter": 3,
        "year": 2026,
        "submission_month": "2026-08",
    },
    {
        "applicant_id": "test-specialist-002",
        "submission_type": "distributor_mentor",
        "content_json": json.dumps({
            "items": ["合规改善"],
            "custom_text": "协助华南分销商B完成合规整改",
        }, ensure_ascii=False),
        "status": "approved",
        "review_score": 88,
        "quarter": 3,
        "year": 2026,
        "submission_month": "2026-08",
    },
    {
        "applicant_id": "test-specialist-002",
        "submission_type": "efficiency_innovator",
        "content_json": json.dumps({
            "items": ["流程优化"],
            "custom_text": "优化了报备审批流程，平均缩短2天",
        }, ensure_ascii=False),
        "status": "pending",
        "quarter": 3,
        "year": 2026,
        "submission_month": "2026-08",
    },
    # 微光提名：分销商提名专员
    {
        "applicant_id": "test-distributor-001",
        "submission_type": "nomination",
        "content_json": json.dumps({
            "nominee_id": "test-specialist-001",
            "nominee_name": "赵专员",
            "reason": "赵专员在母线槽选型问题上给予了非常专业和及时的帮助",
        }, ensure_ascii=False),
        "status": "approved",
        "submission_month": "2026-08",
    },
    {
        "applicant_id": "test-distributor-002",
        "submission_type": "nomination",
        "content_json": json.dumps({
            "nominee_id": "test-specialist-002",
            "nominee_name": "钱专员",
            "reason": "钱专员在合规整改方面提供了细致指导",
        }, ensure_ascii=False),
        "status": "approved",
        "submission_month": "2026-08",
    },
]

# 测试满意度评分（销售对专员评分）
TEST_SURVEYS = [
    {
        "rater_id": "test-sales-001",
        "target_id": "test-specialist-001",
        "survey_quarter": "2026-Q3",
        "score_efficiency": 5,
        "score_response": 4,
        "score_training": 5,
        "score_communication": 4,
    },
    {
        "rater_id": "test-sales-001",
        "target_id": "test-specialist-002",
        "survey_quarter": "2026-Q3",
        "score_efficiency": 4,
        "score_response": 5,
        "score_training": 4,
        "score_communication": 5,
    },
    {
        "rater_id": "test-sales-002",
        "target_id": "test-specialist-001",
        "survey_quarter": "2026-Q3",
        "score_efficiency": 3,
        "score_response": 4,
        "score_training": 3,
        "score_communication": 4,
    },
]

# 测试获奖记录
TEST_AWARDS = [
    {
        "user_id": "test-specialist-001",
        "award_type": "monthly_star",
        "award_name": "月度微光之星",
        "rank": 1,
        "score": 95.0,
        "points_awarded": 30,
        "award_month": "2026-08",
        "award_year": 2026,
        "published": True,
    },
    {
        "user_id": "test-specialist-002",
        "award_type": "monthly_star",
        "award_name": "月度微光之星",
        "rank": 2,
        "score": 88.0,
        "points_awarded": 30,
        "award_month": "2026-08",
        "award_year": 2026,
        "published": True,
    },
]


async def seed_test_data():
    """写入测试数据到 SQLite 数据库."""
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "faq_dev.db")

    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        print("   请先启动一次后端: cd faq-backend && python -m app.main")
        return

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        try:
            # ── 1. 创建测试用户 ──
            print("=" * 60)
            print("1. 创建测试用户...")
            created_users = 0
            for user_data in TEST_USERS:
                # 检查是否已存在
                existing = await session.execute(
                    select(User).where(User.id == user_data["id"])
                )
                if existing.scalar_one_or_none():
                    print(f"   ⏭ 跳过已存在: {user_data['nickname']} ({user_data['recognition_role']})")
                    continue
                user = User(**user_data)
                session.add(user)
                created_users += 1
                print(f"   ✅ 创建: {user_data['nickname']} - 角色: {user_data['recognition_role']}")

            await session.flush()
            print(f"   共创建 {created_users} 个测试用户\n")

            # ── 2. 创建对接关系 ──
            print("2. 创建销售-专员对接关系...")
            created_mappings = 0
            for mapping_data in TEST_MAPPINGS:
                existing = await session.execute(
                    select(SalesSpecialistMapping).where(
                        SalesSpecialistMapping.sales_id == mapping_data["sales_id"],
                        SalesSpecialistMapping.specialist_id == mapping_data["specialist_id"],
                    )
                )
                if existing.scalar_one_or_none():
                    print(f"   ⏭ 跳过已存在: {mapping_data['sales_id']} → {mapping_data['specialist_id']}")
                    continue
                mapping = SalesSpecialistMapping(
                    **mapping_data,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(mapping)
                created_mappings += 1
                print(f"   ✅ 创建: {mapping_data['sales_id']} → {mapping_data['specialist_id']}")

            await session.flush()
            print(f"   共创建 {created_mappings} 条对接关系\n")

            # ── 3. 创建申报数据 ──
            print("3. 创建测试申报数据...")
            created_submissions = 0
            for sub_data in TEST_SUBMISSIONS:
                sub = RecognitionSubmission(
                    **sub_data,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(sub)
                created_submissions += 1
                print(f"   ✅ 创建申报: [{sub_data['submission_type']}] {sub_data['status']}")

            await session.flush()
            print(f"   共创建 {created_submissions} 条申报数据\n")

            # ── 4. 创建满意度评分 ──
            print("4. 创建测试满意度评分...")
            created_surveys = 0
            for survey_data in TEST_SURVEYS:
                existing = await session.execute(
                    select(RecognitionSurvey).where(
                        RecognitionSurvey.rater_id == survey_data["rater_id"],
                        RecognitionSurvey.target_id == survey_data["target_id"],
                        RecognitionSurvey.survey_quarter == survey_data["survey_quarter"],
                    )
                )
                if existing.scalar_one_or_none():
                    print(f"   ⏭ 跳过已存在评分: {survey_data['rater_id']} → {survey_data['target_id']}")
                    continue
                survey = RecognitionSurvey(
                    **survey_data,
                    submitted_at=datetime.now(timezone.utc),
                )
                session.add(survey)
                created_surveys += 1
                print(f"   ✅ 创建评分: 销售 → 专员 ({survey_data['survey_quarter']})")

            await session.flush()
            print(f"   共创建 {created_surveys} 条满意度评分\n")

            # ── 5. 创建获奖记录 ──
            print("5. 创建测试获奖记录...")
            created_awards = 0
            for award_data in TEST_AWARDS:
                existing = await session.execute(
                    select(RecognitionAward).where(
                        RecognitionAward.user_id == award_data["user_id"],
                        RecognitionAward.award_type == award_data["award_type"],
                        RecognitionAward.award_month == award_data["award_month"],
                    )
                )
                if existing.scalar_one_or_none():
                    print(f"   ⏭ 跳过已存在获奖: {award_data['award_name']}")
                    continue
                award = RecognitionAward(
                    **award_data,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(award)
                created_awards += 1
                print(f"   ✅ 创建获奖: {award_data['award_name']} (rank={award_data['rank']})")

            await session.flush()
            print(f"   共创建 {created_awards} 条获奖记录\n")

            await session.commit()
            print("=" * 60)
            print("🎉 测试数据写入完成！")
            print("=" * 60)
            print()
            print("📋 测试账号一览:")
            print("┌─────────────────┬──────────┬──────────────┬──────────────────────┐")
            print("│ 角色            │ 姓名     │ 手机号       │ 用途                 │")
            print("├─────────────────┼──────────┼──────────────┼──────────────────────┤")
            print("│ 经理 (manager)  │ 张经理   │ 13900000001  │ 管理后台、审批、评选 │")
            print("│ 销售 (sales)    │ 李销售   │ 13900000002  │ 满意度评分、查看排名 │")
            print("│ 销售 (sales)    │ 王销售   │ 13900000003  │ 满意度评分            │")
            print("│ 专员 (specialist)│ 赵专员  │ 13900000004  │ 申报、查看积分       │")
            print("│ 专员 (specialist)│ 钱专员  │ 13900000005  │ 申报、查看积分       │")
            print("│ 分销商(distributor)│孙分销商│ 13900000006  │ 首页、微光提名       │")
            print("│ 分销商(distributor)│周分销商│ 13900000007  │ 首页、微光提名       │")
            print("└─────────────────┴──────────┴──────────────┴──────────────────────┘")
            print()
            print("💡 提示: 这些测试用户通过 openid 识别，在微信小程序中需要配置对应的 openid。")
            print("   如果需要在本地通过 API 测试，可以使用 admin 账号登录后台管理。")
            print("   admin 账号: admin / admin123456")

        except Exception as e:
            await session.rollback()
            print(f"❌ 错误: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_test_data())