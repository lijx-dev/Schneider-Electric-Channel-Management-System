"""Saved explanation knowledge points."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class KnowledgeItem(Base, TimestampMixin):
    """Store a user's saved explanation snapshot."""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="bank")

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_knowledge_user_question"),
        Index("ix_knowledge_items_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeItem user={self.user_id[:8]} q={self.question_id}>"
