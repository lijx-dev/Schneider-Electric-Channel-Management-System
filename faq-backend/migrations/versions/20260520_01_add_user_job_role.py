"""Add user job role for admin participation reports.

Revision ID: 20260520_01
Revises: 20260514_01
Create Date: 2026-05-20 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260520_01"
down_revision = "20260514_01"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("users", "job_role"):
        op.add_column("users", sa.Column("job_role", sa.String(length=20), nullable=True))
        op.create_index("ix_users_company_job_role", "users", ["company", "job_role"], unique=False)


def downgrade() -> None:
    if _column_exists("users", "job_role"):
        op.drop_index("ix_users_company_job_role", table_name="users")
        op.drop_column("users", "job_role")
