"""Create monthly lucky lottery draw tables.

Revision ID: 20260514_01
Revises: 20260513_01
Create Date: 2026-05-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260514_01"
down_revision = "20260513_01"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("lottery_draws"):
        op.create_table(
            "lottery_draws",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("month_key", sa.String(length=7), nullable=False),
            sa.Column("participant_month", sa.String(length=7), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
            sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("winner_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("drawn_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("month_key", name="uq_lottery_draws_month_key"),
        )
        op.create_index("ix_lottery_draws_month_key", "lottery_draws", ["month_key"], unique=True)
        op.create_index("ix_lottery_draws_participant_month", "lottery_draws", ["participant_month"], unique=False)

    if not _table_exists("lottery_winners"):
        op.create_table(
            "lottery_winners",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("draw_id", sa.Integer(), sa.ForeignKey("lottery_draws.id", ondelete="CASCADE"), nullable=False),
            sa.Column("month_key", sa.String(length=7), nullable=False),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("prize_level", sa.String(length=20), nullable=False),
            sa.Column("prize_name", sa.String(length=20), nullable=False),
            sa.Column("reward_amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("winner_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("energy_transaction_id", sa.Integer(), sa.ForeignKey("energy_transactions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notice_read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("month_key", "user_id", name="uq_lottery_winners_month_user"),
        )
        op.create_index("ix_lottery_winners_draw_id", "lottery_winners", ["draw_id"], unique=False)
        op.create_index("ix_lottery_winners_month_key", "lottery_winners", ["month_key"], unique=False)
        op.create_index("ix_lottery_winners_user_id", "lottery_winners", ["user_id"], unique=False)
        op.create_index("ix_lottery_winners_user_notice", "lottery_winners", ["user_id", "notice_read_at"], unique=False)


def downgrade() -> None:
    if _table_exists("lottery_winners"):
        op.drop_index("ix_lottery_winners_user_notice", table_name="lottery_winners")
        op.drop_index("ix_lottery_winners_user_id", table_name="lottery_winners")
        op.drop_index("ix_lottery_winners_month_key", table_name="lottery_winners")
        op.drop_index("ix_lottery_winners_draw_id", table_name="lottery_winners")
        op.drop_table("lottery_winners")

    if _table_exists("lottery_draws"):
        op.drop_index("ix_lottery_draws_participant_month", table_name="lottery_draws")
        op.drop_index("ix_lottery_draws_month_key", table_name="lottery_draws")
        op.drop_table("lottery_draws")
