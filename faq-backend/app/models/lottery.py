"""Monthly lucky lottery draws and winners."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LotteryDraw(Base, TimestampMixin):
    """Persist one lucky lottery draw per month."""

    __tablename__ = "lottery_draws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, unique=True, index=True)
    participant_month: Mapped[str] = mapped_column(String(7), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    eligible_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<LotteryDraw month={self.month_key} winners={self.winner_count}>"


class LotteryWinner(Base, TimestampMixin):
    """Persist a user's prize result and unread home notice state."""

    __tablename__ = "lottery_winners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draw_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lottery_draws.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prize_level: Mapped[str] = mapped_column(String(20), nullable=False)
    prize_name: Mapped[str] = mapped_column(String(20), nullable=False)
    reward_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    energy_transaction_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("energy_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    notice_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("month_key", "user_id", name="uq_lottery_winners_month_user"),
        Index("ix_lottery_winners_user_notice", "user_id", "notice_read_at"),
    )

    def __repr__(self) -> str:
        return f"<LotteryWinner user={self.user_id[:8]} month={self.month_key} prize={self.prize_name}>"
