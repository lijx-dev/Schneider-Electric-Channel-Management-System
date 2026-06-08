"""Create certificate records table.

Revision ID: 20260422_01
Revises: 20260414_01
Create Date: 2026-04-22 10:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260422_01"
down_revision = "20260414_01"
branch_labels = None
depends_on = None

TABLE_NAME = "certificate_records"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_key", sa.String(length=64), nullable=False),
        sa.Column("company_name", sa.String(length=120), nullable=False),
        sa.Column("cert_type", sa.String(length=64), nullable=False),
        sa.Column("category_name", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_sheet", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_certificate_records_hierarchy",
        TABLE_NAME,
        ["company_key", "cert_type", "category_name", "model"],
        unique=False,
    )
    op.create_index(
        "ix_certificate_records_company_cert_sort",
        TABLE_NAME,
        ["company_key", "cert_type", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_index("ix_certificate_records_company_cert_sort", table_name=TABLE_NAME)
    op.drop_index("ix_certificate_records_hierarchy", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
