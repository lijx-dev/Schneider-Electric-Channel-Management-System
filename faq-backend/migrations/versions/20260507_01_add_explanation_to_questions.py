"""Add explanation to questions.

Revision ID: 20260507_01
Revises: 20260430_01
Create Date: 2026-05-07 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260507_01"
down_revision = "20260430_01"
branch_labels = None
depends_on = None

TABLE_NAME = "questions"


def _get_column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    if "explanation" not in column_names:
        op.add_column(TABLE_NAME, sa.Column("explanation", sa.Text(), nullable=True))


def downgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if "explanation" in column_names:
        op.drop_column(TABLE_NAME, "explanation")
