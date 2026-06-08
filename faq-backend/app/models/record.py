"""Answer records and shared weekly quiz rounds."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AnswerRecord(Base, TimestampMixin):
    """Store each answer submission for quiz and practice flows."""

    __tablename__ = "answer_records"

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

    selected_answer: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    time_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="bank")
    quiz_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "question_id",
            "source",
            "quiz_date",
            name="uq_user_question_source_date",
        ),
        Index("ix_answer_records_quiz_date", "quiz_date"),
    )

    def __repr__(self) -> str:
        return f"<AnswerRecord user={self.user_id[:8]} q={self.question_id} correct={self.is_correct}>"


class DailyQuizRound(Base, TimestampMixin):
    """Store one shared question set for each weekly refresh cycle."""

    __tablename__ = "daily_quiz_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quiz_date: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    question_ids: Mapped[str] = mapped_column(Text, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=10)

    def __repr__(self) -> str:
        return f"<DailyQuizRound {self.quiz_date} ({self.question_count} questions)>"
