"""Create knowledge items table.

Revision ID: 20260509_01
Revises: 20260507_01
Create Date: 2026-05-09 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260509_01"
down_revision = "20260507_01"
branch_labels = None
depends_on = None

TABLE_NAME = "knowledge_items"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="bank"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "question_id", name="uq_knowledge_user_question"),
    )
    op.create_index("ix_knowledge_items_user_id", TABLE_NAME, ["user_id"], unique=False)
    op.create_index("ix_knowledge_items_question_id", TABLE_NAME, ["question_id"], unique=False)
    op.create_index("ix_knowledge_items_user_created", TABLE_NAME, ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_index("ix_knowledge_items_user_created", table_name=TABLE_NAME)
    op.drop_index("ix_knowledge_items_question_id", table_name=TABLE_NAME)
    op.drop_index("ix_knowledge_items_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
