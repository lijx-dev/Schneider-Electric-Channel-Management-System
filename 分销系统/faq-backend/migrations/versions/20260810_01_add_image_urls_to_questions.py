"""Add image_urls to questions.

Revision ID: 20260810_01
Revises: 20260805_01
Create Date: 2026-08-10 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_01"
down_revision = "20260805_01"
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

    if "image_urls" not in column_names:
        op.add_column(TABLE_NAME, sa.Column("image_urls", sa.JSON(), nullable=True))


def downgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if "image_urls" in column_names:
        op.drop_column(TABLE_NAME, "image_urls")
