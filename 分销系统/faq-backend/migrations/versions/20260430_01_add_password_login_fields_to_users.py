"""Add password login fields to users.

Revision ID: 20260430_01
Revises: 20260429_01
Create Date: 2026-04-30 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_01"
down_revision = "20260429_01"
branch_labels = None
depends_on = None

TABLE_NAME = "users"
USERNAME_INDEX = "ix_users_login_username"


def _get_column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _get_index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    if "login_username" not in column_names:
        op.add_column(TABLE_NAME, sa.Column("login_username", sa.String(length=80), nullable=True))

    if "login_password" not in column_names:
        op.add_column(TABLE_NAME, sa.Column("login_password", sa.String(length=128), nullable=True))

    if USERNAME_INDEX not in _get_index_names(TABLE_NAME):
        op.create_index(USERNAME_INDEX, TABLE_NAME, ["login_username"], unique=True)


def downgrade() -> None:
    column_names = _get_column_names(TABLE_NAME)
    if not column_names:
        return

    if USERNAME_INDEX in _get_index_names(TABLE_NAME):
        op.drop_index(USERNAME_INDEX, table_name=TABLE_NAME)

    for column_name in ["login_password", "login_username"]:
        if column_name in column_names:
            op.drop_column(TABLE_NAME, column_name)
