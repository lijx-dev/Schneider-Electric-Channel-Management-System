"""Create product guide tree tables.

Revision ID: 20260414_01
Revises: 20260413_01
Create Date: 2026-04-14 17:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260414_01"
down_revision = "20260413_01"
branch_labels = None
depends_on = None

NODE_TABLE = "product_guide_nodes"
ASSET_TABLE = "product_guide_assets"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists(NODE_TABLE):
        op.create_table(
            NODE_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "parent_id",
                sa.Integer(),
                sa.ForeignKey(f"{NODE_TABLE}.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("product_key", sa.String(length=64), nullable=False),
            sa.Column("node_key", sa.String(length=128), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("node_type", sa.String(length=20), nullable=False, server_default=sa.text("'branch'")),
            sa.Column("layout", sa.String(length=20), nullable=True),
            sa.Column(
                "response_mode",
                sa.String(length=20),
                nullable=False,
                server_default=sa.text("'text'"),
            ),
            sa.Column("answer_text", sa.Text(), nullable=True),
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
            sa.UniqueConstraint("product_key", "node_key", name="uq_product_guide_nodes_product_node_key"),
            sa.CheckConstraint("node_type in ('branch', 'leaf')", name="ck_product_guide_nodes_node_type"),
            sa.CheckConstraint(
                "response_mode in ('text', 'image', 'mixed')",
                name="ck_product_guide_nodes_response_mode",
            ),
        )
        op.create_index(
            "ix_product_guide_nodes_product_parent_sort",
            NODE_TABLE,
            ["product_key", "parent_id", "sort_order"],
            unique=False,
        )

    if not _table_exists(ASSET_TABLE):
        op.create_table(
            ASSET_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "node_id",
                sa.Integer(),
                sa.ForeignKey(f"{NODE_TABLE}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("asset_type", sa.String(length=20), nullable=False, server_default=sa.text("'image'")),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("cos_url", sa.String(length=1024), nullable=False),
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
            sa.CheckConstraint(
                "asset_type in ('image', 'pdf', 'link')",
                name="ck_product_guide_assets_asset_type",
            ),
        )
        op.create_index(
            "ix_product_guide_assets_node_sort",
            ASSET_TABLE,
            ["node_id", "sort_order"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists(ASSET_TABLE):
        op.drop_index("ix_product_guide_assets_node_sort", table_name=ASSET_TABLE)
        op.drop_table(ASSET_TABLE)

    if _table_exists(NODE_TABLE):
        op.drop_index("ix_product_guide_nodes_product_parent_sort", table_name=NODE_TABLE)
        op.drop_table(NODE_TABLE)
