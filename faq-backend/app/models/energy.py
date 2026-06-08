"""Energy redemption and reward records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EnergyRedemptionRecord(Base, TimestampMixin):
    """Store energy redemption records as a backend source of truth."""

    __tablename__ = "energy_redemption_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_record_id: Mapped[str] = mapped_column(String(80), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    receiver_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    receiver_phone: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    receiver_region: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    receiver_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    receiver_note: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "client_record_id",
            name="uq_energy_redemptions_user_client_record",
        ),
        Index("ix_energy_redemptions_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EnergyRedemptionRecord user={self.user_id[:8]} client={self.client_record_id}>"


class EnergyTransaction(Base, TimestampMixin):
    """Store awarded or adjusted energy as auditable records."""

    __tablename__ = "energy_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    related_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    related_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    related_month: Mapped[str] = mapped_column(String(7), nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued")
    notice_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "type",
            "related_month",
            name="uq_energy_transactions_user_type_month",
        ),
        Index("ix_energy_transactions_user_created", "user_id", "created_at"),
        Index("ix_energy_transactions_user_notice", "user_id", "notice_read_at"),
    )

    def __repr__(self) -> str:
        return f"<EnergyTransaction user={self.user_id[:8]} type={self.type} amount={self.amount}>"
