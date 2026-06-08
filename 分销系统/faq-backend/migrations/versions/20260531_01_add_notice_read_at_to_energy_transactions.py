"""Add notice read state to energy reward transactions.

Revision ID: 20260531_01
Revises: 20260520_01
Create Date: 2026-05-31 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260531_01"
down_revision = "20260520_01"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _column_exists("energy_transactions", "notice_read_at"):
        op.add_column("energy_transactions", sa.Column("notice_read_at", sa.DateTime(timezone=True), nullable=True))

    if not _index_exists("energy_transactions", "ix_energy_transactions_user_notice"):
        op.create_index(
            "ix_energy_transactions_user_notice",
            "energy_transactions",
            ["user_id", "notice_read_at"],
            unique=False,
        )


def downgrade() -> None:
    if _index_exists("energy_transactions", "ix_energy_transactions_user_notice"):
        op.drop_index("ix_energy_transactions_user_notice", table_name="energy_transactions")

    if _column_exists("energy_transactions", "notice_read_at"):
        op.drop_column("energy_transactions", "notice_read_at")
