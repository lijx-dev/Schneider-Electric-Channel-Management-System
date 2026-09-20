"""Create conference_answers (phone-based quiz progress).

方案说明：主表 answer_records.user_id 外键绑定主用户体系（NOT NULL），
无法承载手机号身份。本表作为 conference 专用答题进度（按手机号×题目×日期幂等覆盖）。

Revision ID: 20260920_02
Revises: 20260920_01
Create Date: 2026-09-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260920_02"
down_revision = "20260920_01"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("conference_answers"):
        op.create_table(
            "conference_answers",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("phone", sa.String(20), nullable=False),
            sa.Column("question_id", sa.Integer, nullable=False),
            sa.Column("zone_id", sa.Integer, nullable=False),
            sa.Column("selected_answer", sa.String(500), nullable=False),
            sa.Column("quiz_date", sa.String(10), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["zone_id"], ["conference_zones.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "phone", "question_id", "quiz_date",
                name="uq_conf_answer_phone_question_date",
            ),
        )
        op.create_index("ix_conference_answers_phone", "conference_answers", ["phone"])
        op.create_index("ix_conf_answer_phone_zone", "conference_answers", ["phone", "zone_id"])


def downgrade() -> None:
    if _table_exists("conference_answers"):
        op.drop_table("conference_answers")
