"""Create energy products table.

Revision ID: 20260424_02
Revises: 20260424_01
Create Date: 2026-04-24 17:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_02"
down_revision = "20260424_01"
branch_labels = None
depends_on = None

TABLE_NAME = "energy_products"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("cost", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("badge", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("tag", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("art_label", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("art_class", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_energy_products_product_id"),
    )
    op.create_index("ix_energy_products_is_active", TABLE_NAME, ["is_active"], unique=False)
    op.create_index("ix_energy_products_product_id", TABLE_NAME, ["product_id"], unique=True)


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    op.drop_index("ix_energy_products_product_id", table_name=TABLE_NAME)
    op.drop_index("ix_energy_products_is_active", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
