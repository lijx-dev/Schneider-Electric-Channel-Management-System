"""Drop obsolete mistakes table.

Revision ID: 20260413_01
Revises: 20260401_01
Create Date: 2026-04-13 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_01"
down_revision = "20260401_01"
branch_labels = None
depends_on = None

TABLE_NAME = "mistakes"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_table(TABLE_NAME)


def downgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_answer", sa.String(length=500), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_review_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "question_id", name="uq_user_question"),
    )
    op.create_index("ix_mistakes_user_id", TABLE_NAME, ["user_id"], unique=False)
