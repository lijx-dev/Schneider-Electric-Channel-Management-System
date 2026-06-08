"""Add shipping fields to energy redemption records.

Revision ID: 20260427_01
Revises: 20260424_02
Create Date: 2026-04-27 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_01"
down_revision = "20260424_02"
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
        ("receiver_name", sa.String(length=100)),
        ("receiver_phone", sa.String(length=30)),
        ("receiver_region", sa.String(length=120)),
        ("receiver_address", sa.String(length=255)),
        ("receiver_note", sa.String(length=255)),
    ]

    for column_name, column_type in additions:
        if column_name in column_names:
            continue
        op.add_column(
            TABLE_NAME,
            sa.Column(
                column_name,
                column_type,
                nullable=False,
                server_default="",
            ),
        )


def downgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    for column_name in [
        "receiver_note",
        "receiver_address",
        "receiver_region",
        "receiver_phone",
        "receiver_name",
    ]:
        if column_name in column_names:
            op.drop_column(TABLE_NAME, column_name)
