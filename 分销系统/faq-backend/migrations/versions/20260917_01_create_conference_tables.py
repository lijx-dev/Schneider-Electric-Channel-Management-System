"""Create conference tables and add conference_whitelisted to users.

Revision ID: 20260917_01
Revises: 20260903_02
Create Date: 2026-09-17 18:20:04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260917_01"
down_revision = "20260903_02"
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
    # ── 1. Add conference whitelist column to users ────────────────────
    if not _column_exists("users", "conference_whitelisted"):
        op.add_column(
            "users",
            sa.Column(
                "conference_whitelisted",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("0"),
                comment="是否允许访问分销商大会模块",
            ),
        )

    # ── 2. Create conference_zones ──────────────────────────────────────
    if not _table_exists("conference_zones"):
        op.create_table(
            "conference_zones",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("code", sa.String(30), unique=True, nullable=False),
            sa.Column("name", sa.String(50), nullable=False),
            sa.Column("slogan", sa.String(200), nullable=True),
            sa.Column("icon_url", sa.String(300), nullable=True),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("task_type", sa.String(20), nullable=False, server_default="quiz"),
            sa.Column("question_category", sa.String(50), nullable=True),
            sa.Column("required_daily_quiz_count", sa.Integer, nullable=False, server_default="2"),
            sa.Column("required_ai_chat_count", sa.Integer, nullable=False, server_default="2"),
            sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("active_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if not _index_exists("conference_zones", "ix_conference_zones_active"):
        op.create_index("ix_conference_zones_active", "conference_zones", ["is_active", "sort_order"])

    # ── 3. Create conference_zone_marks ────────────────────────────────
    if not _table_exists("conference_zone_marks"):
        op.create_table(
            "conference_zone_marks",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("zone_id", sa.Integer, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["zone_id"], ["conference_zones.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "zone_id", name="uq_zone_mark_user_zone"),
        )

    if not _index_exists("conference_zone_marks", "ix_conference_zone_marks_user_id"):
        op.create_index("ix_conference_zone_marks_user_id", "conference_zone_marks", ["user_id"])

    # ── 4. Create conference_medals ────────────────────────────────────
    if not _table_exists("conference_medals"):
        op.create_table(
            "conference_medals",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), unique=True, nullable=False),
            sa.Column("medal_code", sa.String(30), unique=True, nullable=False),
            sa.Column("zone_count", sa.Integer, nullable=False, server_default="4"),
            sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        )

    # ── 5. Create conference_activity ──────────────────────────────────
    if not _table_exists("conference_activity"):
        op.create_table(
            "conference_activity",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("action_key", sa.String(30), nullable=False),
            sa.Column("activity_date", sa.String(10), nullable=False),
            sa.Column("count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "user_id", "action_key", "activity_date",
                name="uq_conf_activity_user_action_date",
            ),
        )

    if not _index_exists("conference_activity", "ix_conference_activity_user_id"):
        op.create_index("ix_conference_activity_user_id", "conference_activity", ["user_id"])


def downgrade() -> None:
    # Drop tables in reverse dependency order

    if _table_exists("conference_activity"):
        op.drop_table("conference_activity")

    if _table_exists("conference_medals"):
        op.drop_table("conference_medals")

    if _table_exists("conference_zone_marks"):
        op.drop_table("conference_zone_marks")

    if _table_exists("conference_zones"):
        op.drop_table("conference_zones")

    if _column_exists("users", "conference_whitelisted"):
        op.drop_column("users", "conference_whitelisted")
