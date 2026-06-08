"""Certificate query records with dynamic detail fields."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CertificateRecord(Base, TimestampMixin):
    """Store certificate records from vendor spreadsheets.

    The navigation hierarchy is stable, while the detail fields vary between
    certificate types, so row-specific fields live in detail_json.
    """

    __tablename__ = "certificate_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_key: Mapped[str] = mapped_column(String(64), nullable=False)
    company_name: Mapped[str] = mapped_column(String(120), nullable=False)
    cert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    category_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_sheet: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index(
            "ix_certificate_records_hierarchy",
            "company_key",
            "cert_type",
            "category_name",
            "model",
        ),
        Index("ix_certificate_records_company_cert_sort", "company_key", "cert_type", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<CertificateRecord {self.company_key}/{self.cert_type}/{self.category_name}/{self.model}>"
