"""Create energy redemption records table.

Revision ID: 20260424_01
Revises: 20260422_01
Create Date: 2026-04-24 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_01"
down_revision = "20260422_01"
branch_labels = None
depends_on = None

TABLE_NAME = "energy_redemption_records"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("client_record_id", sa.String(length=80), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "client_record_id", name="uq_energy_redemptions_user_client_record"),
    )
    op.create_index("ix_energy_redemption_records_user_id", TABLE_NAME, ["user_id"], unique=False)
    op.create_index("ix_energy_redemptions_user_created", TABLE_NAME, ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_index("ix_energy_redemptions_user_created", table_name=TABLE_NAME)
    op.drop_index("ix_energy_redemption_records_user_id", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
