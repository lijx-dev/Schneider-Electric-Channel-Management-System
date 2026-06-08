"""Add profile_verified flag to users.

Revision ID: 20260401_01
Revises: 20260330_01
Create Date: 2026-04-01 10:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260401_01"
down_revision = "20260330_01"
branch_labels = None
depends_on = None

TABLE_NAME = "users"
COLUMN_NAME = "profile_verified"


def _get_inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = _get_inspector()
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _column_exists(TABLE_NAME, COLUMN_NAME):
        return

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.add_column(
            sa.Column(COLUMN_NAME, sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    if not _column_exists(TABLE_NAME, COLUMN_NAME):
        return

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_column(COLUMN_NAME)
