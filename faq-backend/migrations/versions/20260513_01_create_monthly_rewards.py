"""Create monthly leaderboard snapshots and energy transactions.

Revision ID: 20260513_01
Revises: 20260509_01
Create Date: 2026-05-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_01"
down_revision = "20260509_01"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("monthly_rank_snapshots"):
        op.create_table(
            "monthly_rank_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("month_key", sa.String(length=7), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("nickname", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("real_name", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("company", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("province", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("avatar_url", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("monthly_correct_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("monthly_total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("monthly_time_spent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reward_status", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("month_key", "user_id", name="uq_monthly_rank_snapshots_month_user"),
        )
        op.create_index("ix_monthly_rank_snapshots_month_key", "monthly_rank_snapshots", ["month_key"], unique=False)
        op.create_index("ix_monthly_rank_snapshots_user_id", "monthly_rank_snapshots", ["user_id"], unique=False)
        op.create_index(
            "ix_monthly_rank_snapshots_month_rank",
            "monthly_rank_snapshots",
            ["month_key", "rank"],
            unique=False,
        )

    if not _table_exists("energy_transactions"):
        op.create_table(
            "energy_transactions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=40), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("related_type", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("related_id", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("related_month", sa.String(length=7), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="issued"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "type", "related_month", name="uq_energy_transactions_user_type_month"),
        )
        op.create_index("ix_energy_transactions_user_id", "energy_transactions", ["user_id"], unique=False)
        op.create_index("ix_energy_transactions_type", "energy_transactions", ["type"], unique=False)
        op.create_index("ix_energy_transactions_related_month", "energy_transactions", ["related_month"], unique=False)
        op.create_index(
            "ix_energy_transactions_user_created",
            "energy_transactions",
            ["user_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("energy_transactions"):
        op.drop_index("ix_energy_transactions_user_created", table_name="energy_transactions")
        op.drop_index("ix_energy_transactions_related_month", table_name="energy_transactions")
        op.drop_index("ix_energy_transactions_type", table_name="energy_transactions")
        op.drop_index("ix_energy_transactions_user_id", table_name="energy_transactions")
        op.drop_table("energy_transactions")

    if _table_exists("monthly_rank_snapshots"):
        op.drop_index("ix_monthly_rank_snapshots_month_rank", table_name="monthly_rank_snapshots")
        op.drop_index("ix_monthly_rank_snapshots_user_id", table_name="monthly_rank_snapshots")
        op.drop_index("ix_monthly_rank_snapshots_month_key", table_name="monthly_rank_snapshots")
        op.drop_table("monthly_rank_snapshots")
