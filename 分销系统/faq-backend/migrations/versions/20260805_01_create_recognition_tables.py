"""Create recognition plan system tables and seed data.

Revision ID: 20260805_01
Revises: 20260531_01
Create Date: 2026-08-05 00:00:00
"""
from __future__ import annotations

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260805_01"
down_revision = "20260531_01"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    # ── 1. Add columns to users table ──────────────────────────────────
    if not _column_exists("users", "recognition_role"):
        op.add_column("users", sa.Column("recognition_role", sa.String(20), nullable=False, server_default="distributor"))

    if not _column_exists("users", "recognition_score"):
        op.add_column("users", sa.Column("recognition_score", sa.Integer, nullable=False, server_default="0"))

    # ── 2. Create recognition_submissions ──────────────────────────────
    if not _table_exists("recognition_submissions"):
        op.create_table(
            "recognition_submissions",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("applicant_id", sa.String(36), nullable=False),
            sa.Column("submission_type", sa.String(30), nullable=False),
            sa.Column("content_json", sa.Text, nullable=False),
            sa.Column("attachments", sa.Text, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("reviewed_by", sa.String(36), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("review_comment", sa.Text, nullable=True),
            sa.Column("review_score", sa.Integer, nullable=True),
            sa.Column("quarter", sa.Integer, nullable=True),
            sa.Column("year", sa.Integer, nullable=True),
            sa.Column("submission_month", sa.String(7), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_foreign_key("fk_submissions_applicant", "recognition_submissions", "users", ["applicant_id"], ["id"])
        op.create_foreign_key("fk_submissions_reviewed_by", "recognition_submissions", "users", ["reviewed_by"], ["id"])

    if not _index_exists("recognition_submissions", "ix_submissions_type_quarter"):
        op.create_index("ix_submissions_type_quarter", "recognition_submissions", ["submission_type", "year", "quarter"])
    if not _index_exists("recognition_submissions", "ix_submissions_applicant_quarter"):
        op.create_index("ix_submissions_applicant_quarter", "recognition_submissions", ["applicant_id", "year", "quarter"])
    if not _index_exists("recognition_submissions", "ix_submissions_type_month"):
        op.create_index("ix_submissions_type_month", "recognition_submissions", ["submission_type", "submission_month"])

    # ── 3. Create recognition_surveys ──────────────────────────────────
    if not _table_exists("recognition_surveys"):
        op.create_table(
            "recognition_surveys",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("rater_id", sa.String(36), nullable=False),
            sa.Column("target_id", sa.String(36), nullable=False),
            sa.Column("survey_month", sa.String(7), nullable=False),
            sa.Column("score_efficiency", sa.Integer, nullable=True),
            sa.Column("score_response", sa.Integer, nullable=True),
            sa.Column("score_training", sa.Integer, nullable=True),
            sa.Column("score_communication", sa.Integer, nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_foreign_key("fk_surveys_rater", "recognition_surveys", "users", ["rater_id"], ["id"])
        op.create_foreign_key("fk_surveys_target", "recognition_surveys", "users", ["target_id"], ["id"])
        op.create_unique_constraint("uq_survey_rater_target_month", "recognition_surveys", ["rater_id", "target_id", "survey_month"])

    if not _index_exists("recognition_surveys", "ix_surveys_month_target"):
        op.create_index("ix_surveys_month_target", "recognition_surveys", ["survey_month", "target_id"])

    # ── 4. Create recognition_points ───────────────────────────────────
    if not _table_exists("recognition_points"):
        op.create_table(
            "recognition_points",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("point_change", sa.Integer, nullable=False),
            sa.Column("reason", sa.String(50), nullable=False),
            sa.Column("award_type", sa.String(30), nullable=True),
            sa.Column("related_month", sa.String(7), nullable=True),
            sa.Column("related_quarter", sa.String(10), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_foreign_key("fk_points_user", "recognition_points", "users", ["user_id"], ["id"])

    if not _index_exists("recognition_points", "ix_points_user_created"):
        op.create_index("ix_points_user_created", "recognition_points", ["user_id", "created_at"])

    # ── 5. Create recognition_awards ───────────────────────────────────
    if not _table_exists("recognition_awards"):
        op.create_table(
            "recognition_awards",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("award_type", sa.String(30), nullable=False),
            sa.Column("award_name", sa.String(50), nullable=False),
            sa.Column("rank", sa.Integer, nullable=True),
            sa.Column("score", sa.DECIMAL(10, 2), nullable=True),
            sa.Column("points_awarded", sa.Integer, nullable=False),
            sa.Column("award_month", sa.String(7), nullable=True),
            sa.Column("award_quarter", sa.String(10), nullable=True),
            sa.Column("award_year", sa.Integer, nullable=False),
            sa.Column("certificate_url", sa.String(500), nullable=True),
            sa.Column("published", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_foreign_key("fk_awards_user", "recognition_awards", "users", ["user_id"], ["id"])

    if not _index_exists("recognition_awards", "ix_awards_user_year"):
        op.create_index("ix_awards_user_year", "recognition_awards", ["user_id", "award_year"])
    if not _index_exists("recognition_awards", "ix_awards_month_type"):
        op.create_index("ix_awards_month_type", "recognition_awards", ["award_month", "award_type"])

    # ── 6. Create recognition_rules_config ─────────────────────────────
    if not _table_exists("recognition_rules_config"):
        op.create_table(
            "recognition_rules_config",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("rule_key", sa.String(50), unique=True, nullable=False),
            sa.Column("rule_value", sa.Text, nullable=False),
            sa.Column("description", sa.String(200), nullable=True),
            sa.Column("updated_by", sa.String(36), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── 7. Create recognition_scoring_criteria ─────────────────────────
    if not _table_exists("recognition_scoring_criteria"):
        op.create_table(
            "recognition_scoring_criteria",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("award_type", sa.String(30), nullable=False),
            sa.Column("item_name", sa.String(100), nullable=False),
            sa.Column("item_key", sa.String(50), nullable=False),
            sa.Column("item_type", sa.String(20), nullable=False, server_default="text_list"),
            sa.Column("item_placeholder", sa.String(200), nullable=True),
            sa.Column("item_help_text", sa.String(300), nullable=True),
            sa.Column("allow_multiple", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("points_per_unit", sa.Integer, nullable=False),
            sa.Column("unit_description", sa.String(100), nullable=True),
            sa.Column("max_points", sa.Integer, nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _index_exists("recognition_scoring_criteria", "ix_criteria_award_active"):
        op.create_index("ix_criteria_award_active", "recognition_scoring_criteria", ["award_type", "is_active"])

    # ── 8. Create sales_specialist_mapping ─────────────────────────────
    if not _table_exists("sales_specialist_mapping"):
        op.create_table(
            "sales_specialist_mapping",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("sales_id", sa.String(36), nullable=False),
            sa.Column("specialist_id", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_foreign_key("fk_mapping_sales", "sales_specialist_mapping", "users", ["sales_id"], ["id"])
        op.create_foreign_key("fk_mapping_specialist", "sales_specialist_mapping", "users", ["specialist_id"], ["id"])
        op.create_unique_constraint("uq_mapping_sales_specialist", "sales_specialist_mapping", ["sales_id", "specialist_id"])

    if not _index_exists("sales_specialist_mapping", "ix_mapping_sales"):
        op.create_index("ix_mapping_sales", "sales_specialist_mapping", ["sales_id"])
    if not _index_exists("sales_specialist_mapping", "ix_mapping_specialist"):
        op.create_index("ix_mapping_specialist", "sales_specialist_mapping", ["specialist_id"])

    # ── 9. Create recognition_annual_snapshots ─────────────────────────
    if not _table_exists("recognition_annual_snapshots"):
        op.create_table(
            "recognition_annual_snapshots",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("year", sa.Integer, nullable=False),
            sa.Column("final_score", sa.Integer, nullable=False),
            sa.Column("final_rank", sa.String(10), nullable=False),
            sa.Column("total_awards", sa.Integer, nullable=False),
            sa.Column("snapshot_data", sa.Text, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_foreign_key("fk_snapshot_user", "recognition_annual_snapshots", "users", ["user_id"], ["id"])
        op.create_unique_constraint("uq_snapshot_user_year", "recognition_annual_snapshots", ["user_id", "year"])

    # ── 10. Seed initial rules config data ─────────────────────────────
    now = datetime.utcnow()
    _seed_rules_config(op, now)

    # ── 11. Seed initial scoring criteria data (14 items) ──────────────
    _seed_scoring_criteria(op, now)


def downgrade() -> None:
    # Drop tables in reverse dependency order

    if _table_exists("recognition_annual_snapshots"):
        op.drop_table("recognition_annual_snapshots")

    if _table_exists("sales_specialist_mapping"):
        op.drop_table("sales_specialist_mapping")

    if _table_exists("recognition_scoring_criteria"):
        op.drop_table("recognition_scoring_criteria")

    if _table_exists("recognition_rules_config"):
        op.drop_table("recognition_rules_config")

    if _table_exists("recognition_awards"):
        op.drop_table("recognition_awards")

    if _table_exists("recognition_points"):
        op.drop_table("recognition_points")

    if _table_exists("recognition_surveys"):
        op.drop_table("recognition_surveys")

    if _table_exists("recognition_submissions"):
        op.drop_table("recognition_submissions")

    if _column_exists("users", "recognition_score"):
        op.drop_column("users", "recognition_score")

    if _column_exists("users", "recognition_role"):
        op.drop_column("users", "recognition_role")


def _seed_rules_config(op, now: datetime) -> None:
    """Insert initial rules configuration data."""
    conn = op.get_bind()

    rules = [
        {
            "rule_key": "monthly_nomination_max_winners",
            "rule_value": "2",
            "description": "微光之星月度获奖人数上限",
            "updated_at": now,
        },
        {
            "rule_key": "monthly_nomination_points",
            "rule_value": "30",
            "description": "微光之星获奖积分",
            "updated_at": now,
        },
        {
            "rule_key": "monthly_mvp_max_winners",
            "rule_value": "2",
            "description": "销圈人气王月度获奖人数上限",
            "updated_at": now,
        },
        {
            "rule_key": "monthly_mvp_rank1_points",
            "rule_value": "50",
            "description": "销圈人气王第1名积分",
            "updated_at": now,
        },
        {
            "rule_key": "monthly_mvp_rank2_points",
            "rule_value": "20",
            "description": "销圈人气王第2名积分",
            "updated_at": now,
        },
        {
            "rule_key": "quarterly_max_winners",
            "rule_value": "2",
            "description": "季度奖项获奖人数上限",
            "updated_at": now,
        },
        {
            "rule_key": "quarterly_points",
            "rule_value": "50",
            "description": "季度奖项获奖积分",
            "updated_at": now,
        },
        {
            "rule_key": "annual_max_winners",
            "rule_value": "1",
            "description": "年度渠道之星获奖人数上限",
            "updated_at": now,
        },
        {
            "rule_key": "annual_points",
            "rule_value": "100",
            "description": "年度渠道之星获奖积分",
            "updated_at": now,
        },
        {
            "rule_key": "annual_weight_score",
            "rule_value": "0.4",
            "description": "年度评选：积分权重",
            "updated_at": now,
        },
        {
            "rule_key": "annual_weight_awards",
            "rule_value": "0.2",
            "description": "年度评选：获奖数量权重",
            "updated_at": now,
        },
        {
            "rule_key": "annual_weight_mvp",
            "rule_value": "0.15",
            "description": "年度评选：人气王权重",
            "updated_at": now,
        },
        {
            "rule_key": "annual_weight_nomination",
            "rule_value": "0.1",
            "description": "年度评选：微光之星权重",
            "updated_at": now,
        },
        {
            "rule_key": "annual_weight_manager",
            "rule_value": "0.15",
            "description": "年度评选：经理评定权重",
            "updated_at": now,
        },
        {
            "rule_key": "survey_open_days",
            "rule_value": "3",
            "description": "评分开放时间：每月最后N个工作日",
            "updated_at": now,
        },
        {
            "rule_key": "survey_score_min",
            "rule_value": "1",
            "description": "满意度评分：最低分",
            "updated_at": now,
        },
        {
            "rule_key": "survey_score_max",
            "rule_value": "5",
            "description": "满意度评分：最高分",
            "updated_at": now,
        },
    ]

    # Check if rules already seeded
    result = conn.execute(sa.text("SELECT COUNT(*) FROM recognition_rules_config"))
    if result.scalar() == 0:
        for rule in rules:
            conn.execute(
                sa.text(
                    "INSERT INTO recognition_rules_config (rule_key, rule_value, description, updated_at) "
                    "VALUES (:rule_key, :rule_value, :description, :updated_at)"
                ),
                rule,
            )


def _seed_scoring_criteria(op, now: datetime) -> None:
    """Insert initial scoring criteria data (14 items, aligned with PDF plan)."""
    conn = op.get_bind()

    result = conn.execute(sa.text("SELECT COUNT(*) FROM recognition_scoring_criteria"))
    if result.scalar() > 0:
        return

    criteria = [
        # ── 报备秩序卫士 (order_guardian) ──
        {
            "award_type": "order_guardian",
            "item_name": "冲突解决",
            "item_key": "conflict_cases",
            "item_type": "text_list",
            "item_placeholder": "请描述自行解决的冲突案例（涉及方、冲突描述、解决思路、最终结果）",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 15,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 1,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "order_guardian",
            "item_name": "案例积累",
            "item_key": "case_documents",
            "item_type": "text_list",
            "item_placeholder": "请填写案例标题和文档内容（含背景、冲突方、解决思路、结果、可借鉴方法）",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 2,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "order_guardian",
            "item_name": "工作质量",
            "item_key": "no_errors",
            "item_type": "checkbox",
            "item_placeholder": None,
            "item_help_text": "本季度报备管理工作无差错、无投诉",
            "allow_multiple": False,
            "points_per_unit": 10,
            "unit_description": "达标",
            "max_points": None,
            "sort_order": 3,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        # ── 分销商支持先锋 (distributor_pioneer) ──
        {
            "award_type": "distributor_pioneer",
            "item_name": "新问题处理",
            "item_key": "new_problem_cases",
            "item_type": "text_list",
            "item_placeholder": "请描述自行处理的新问题（个人此前未处理过的类型），无需经理介入",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 15,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 1,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "distributor_pioneer",
            "item_name": "痛点捕捉",
            "item_key": "pain_points",
            "item_type": "text_list",
            "item_placeholder": "请描述在与分销商日常拜访/沟通中捕捉到的痛点共性问题",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 20,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 2,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "distributor_pioneer",
            "item_name": "推动解决",
            "item_key": "solutions_pushed",
            "item_type": "text_list",
            "item_placeholder": "请描述成功推动解决的问题及分销商反馈确认情况",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 3,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        # ── 分销商成长伯乐 (distributor_mentor) ──
        {
            "award_type": "distributor_mentor",
            "item_name": "报备质量",
            "item_key": "compliant_months",
            "item_type": "text_list",
            "item_placeholder": "请选择达标月份并描述具体达标情况",
            "item_help_text": "所负责分销商中，某月份报备池都不超限，或图纸占比都不超限",
            "allow_multiple": True,
            "points_per_unit": 5,
            "unit_description": "每月达标",
            "max_points": None,
            "sort_order": 1,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "distributor_mentor",
            "item_name": "合规改善",
            "item_key": "improvement_cases",
            "item_type": "text_list",
            "item_placeholder": "请描述推动分销商做的有效改善措施",
            "item_help_text": "分销商报备池或图纸占比超限后，推动分销商做出了有效的改善措施",
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 2,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "distributor_mentor",
            "item_name": "业绩增长",
            "item_key": "revenue_growth",
            "item_type": "text_list",
            "item_placeholder": "请填写分销商名称、去年同期业绩、今年同期业绩、增长率",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 0,
            "unit_description": "特殊计算",
            "max_points": None,
            "sort_order": 3,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "distributor_mentor",
            "item_name": "能力提升",
            "item_key": "capability_cases",
            "item_type": "text_list",
            "item_placeholder": "请描述推动分销商参与培训/获得认证/提升专业能力的具体案例",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每例",
            "max_points": None,
            "sort_order": 4,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        # ── 效能提升创新 (efficiency_innovator) ──
        {
            "award_type": "efficiency_innovator",
            "item_name": "制度完善",
            "item_key": "policy_suggestions",
            "item_type": "text_list",
            "item_placeholder": "请描述提出的制度/流程/操作规范完善建议",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每条",
            "max_points": None,
            "sort_order": 1,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "efficiency_innovator",
            "item_name": "流程优化",
            "item_key": "process_improvements",
            "item_type": "text_list",
            "item_placeholder": "请描述流程优化方案及量化依据（效率提升≥10%）",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 30,
            "unit_description": "每条",
            "max_points": None,
            "sort_order": 2,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "efficiency_innovator",
            "item_name": "工具分享",
            "item_key": "tool_sharings",
            "item_type": "text_list",
            "item_placeholder": "请描述分享的工具或经验（Excel模板、自动化工具、沟通话术等）",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 10,
            "unit_description": "每次",
            "max_points": None,
            "sort_order": 3,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
        {
            "award_type": "efficiency_innovator",
            "item_name": "建议落地",
            "item_key": "suggestions_implemented",
            "item_type": "text_list",
            "item_placeholder": "请描述被采纳并实际落地实施的建议及效果",
            "item_help_text": None,
            "allow_multiple": True,
            "points_per_unit": 15,
            "unit_description": "每条",
            "max_points": None,
            "sort_order": 4,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    ]

    for item in criteria:
        conn.execute(
            sa.text(
                "INSERT INTO recognition_scoring_criteria "
                "(award_type, item_name, item_key, item_type, item_placeholder, item_help_text, "
                "allow_multiple, points_per_unit, unit_description, max_points, sort_order, is_active, "
                "created_at, updated_at) "
                "VALUES (:award_type, :item_name, :item_key, :item_type, :item_placeholder, :item_help_text, "
                ":allow_multiple, :points_per_unit, :unit_description, :max_points, :sort_order, :is_active, "
                ":created_at, :updated_at)"
            ),
            item,
        )