"""Add batch fields to energy redemption records.

Revision ID: 20260429_01
Revises: 20260427_01
Create Date: 2026-04-29 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_01"
down_revision = "20260427_01"
branch_labels = None
depends_on = None

TABLE_NAME = "energy_redemption_records"


def _get_column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    additions = [
        ("batch_id", sa.String(length=80), ""),
        ("quantity", sa.Integer(), "1"),
        ("unit_cost", sa.Integer(), "0"),
        ("total_cost", sa.Integer(), "0"),
    ]

    for column_name, column_type, server_default in additions:
        if column_name in column_names:
            continue
        op.add_column(
            TABLE_NAME,
            sa.Column(
                column_name,
                column_type,
                nullable=False,
                server_default=server_default,
            ),
        )


def downgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    for column_name in [
        "total_cost",
        "unit_cost",
        "quantity",
        "batch_id",
    ]:
        if column_name in column_names:
            op.drop_column(TABLE_NAME, column_name)
