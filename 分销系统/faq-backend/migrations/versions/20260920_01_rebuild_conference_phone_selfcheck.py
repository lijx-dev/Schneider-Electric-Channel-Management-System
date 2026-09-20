"""Rebuild conference tables for phone-based self-check-in.

方案变更：上一版基于微信账号关联（user_id / task_type / activity 计数）被否决，
新版以「手机号自助签到」为身份，4 个打卡点全部答题制。
旧版表结构整体重建：旧数据为已否决方案的测试数据，无保留价值，直接 drop 后重建。

Revision ID: 20260920_01
Revises: 20260917_01
Create Date: 2026-09-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260920_01"
down_revision = "20260917_01"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # ── 0. Drop 旧版 conference 表（依赖顺序：先子表后父表）──────────────────
    for table in [
        "conference_activity",
        "conference_medals",
        "conference_zone_marks",
        "conference_zones",
    ]:
        if _table_exists(table):
            op.drop_table(table)

    # ── 1. conference_zones（打卡点配置，全答题制）──────────────────────────
    op.create_table(
        "conference_zones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(30), unique=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("slogan", sa.String(200), nullable=True),
        sa.Column("icon_url", sa.String(300), nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("question_category", sa.String(50), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conference_zones_active", "conference_zones", ["is_active", "sort_order"])

    # ── 2. conference_attendees（参会人，手机号唯一）────────────────────────
    op.create_table(
        "conference_attendees",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conference_attendees_phone", "conference_attendees", ["phone"])

    # ── 3. conference_zone_marks（印章，phone+zone_id 唯一幂等）──────────────
    op.create_table(
        "conference_zone_marks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("zone_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["zone_id"], ["conference_zones.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("phone", "zone_id", name="uq_conf_mark_phone_zone"),
    )
    op.create_index("ix_conference_zone_marks_phone", "conference_zone_marks", ["phone"])

    # ── 4. conference_medals（勋章，phone 唯一）──────────────────────────────
    op.create_table(
        "conference_medals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("medal_code", sa.String(30), unique=True, nullable=False),
        sa.Column("zone_count", sa.Integer, nullable=False, server_default="4"),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "conference_medals",
        "conference_zone_marks",
        "conference_attendees",
        "conference_zones",
    ]:
        if _table_exists(table):
            op.drop_table(table)
