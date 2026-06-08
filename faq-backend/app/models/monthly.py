"""Monthly leaderboard snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MonthlyRankSnapshot(Base, TimestampMixin):
    """Persist a user's rank and reward result for a settled month."""

    __tablename__ = "monthly_rank_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    real_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    province: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    monthly_correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_time_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("month_key", "user_id", name="uq_monthly_rank_snapshots_month_user"),
        Index("ix_monthly_rank_snapshots_month_rank", "month_key", "rank"),
    )

    def __repr__(self) -> str:
        return f"<MonthlyRankSnapshot {self.month_key} user={self.user_id[:8]} rank={self.rank}>"
