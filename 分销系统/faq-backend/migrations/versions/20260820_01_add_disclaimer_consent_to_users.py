"""Add disclaimer consent fields to users.

Revision ID: 20260820_01
Revises: 20260810_01
Create Date: 2026-08-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260820_01"
down_revision = "20260810_01"
branch_labels = None
depends_on = None

TABLE_NAME = "users"

# 新增字段清单：(列名, 列定义)
NEW_COLUMNS = [
    ("disclaimer_agreed", sa.Column("disclaimer_agreed", sa.Boolean(), nullable=False, server_default=sa.false())),
    ("disclaimer_version", sa.Column("disclaimer_version", sa.String(32), nullable=True)),
    ("disclaimer_agreed_at", sa.Column("disclaimer_agreed_at", sa.DateTime(), nullable=True)),
]


def _get_inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        for col_name, column in NEW_COLUMNS:
            if not _column_exists(TABLE_NAME, col_name):
                batch_op.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        for col_name, _ in NEW_COLUMNS:
            if _column_exists(TABLE_NAME, col_name):
                batch_op.drop_column(col_name)