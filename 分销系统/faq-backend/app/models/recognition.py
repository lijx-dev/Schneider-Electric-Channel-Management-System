"""
认可计划系统数据模型

包含8个表：申报表、满意度评分、积分记录、获奖记录、规则配置、评分标准、对接关系、年度快照
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    DECIMAL,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RecognitionSubmission(Base, TimestampMixin):
    """统一申报表"""

    __tablename__ = "recognition_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    submission_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    submission_month: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    __table_args__ = (
        Index("ix_submissions_type_quarter", "submission_type", "year", "quarter"),
        Index("ix_submissions_applicant_quarter", "applicant_id", "year", "quarter"),
        Index("ix_submissions_type_month", "submission_type", "submission_month"),
    )


class RecognitionSurvey(Base):
    """销售满意度评分"""

    __tablename__ = "recognition_surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rater_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    survey_quarter: Mapped[str] = mapped_column(String(7), nullable=False)
    score_efficiency: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_response: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_training: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_communication: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("rater_id", "target_id", "survey_quarter", name="uq_survey_rater_target_quarter"),
        Index("ix_surveys_quarter_target", "survey_quarter", "target_id"),
    )


class RecognitionPoints(Base):
    """积分记录"""

    __tablename__ = "recognition_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    point_change: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    award_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    related_month: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    related_quarter: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_points_user_created", "user_id", "created_at"),
    )


class RecognitionAward(Base):
    """获奖记录"""

    __tablename__ = "recognition_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    award_type: Mapped[str] = mapped_column(String(30), nullable=False)
    award_name: Mapped[str] = mapped_column(String(50), nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(DECIMAL(10, 2), nullable=True)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False)
    award_month: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    award_quarter: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    award_year: Mapped[int] = mapped_column(Integer, nullable=False)
    certificate_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_awards_user_year", "user_id", "award_year"),
        Index("ix_awards_month_type", "award_month", "award_type"),
    )


class RecognitionRulesConfig(Base):
    """规则配置"""

    __tablename__ = "recognition_rules_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    rule_value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RecognitionScoringCriteria(Base, TimestampMixin):
    """评分标准（表单预定义选项的数据源）"""

    __tablename__ = "recognition_scoring_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    award_type: Mapped[str] = mapped_column(String(30), nullable=False)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    item_key: Mapped[str] = mapped_column(String(50), nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), default="text_list", nullable=False)
    item_placeholder: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    item_help_text: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    allow_multiple: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    points_per_unit: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_description: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_criteria_award_active", "award_type", "is_active"),
    )


class SalesSpecialistMapping(Base):
    """销售-专员对接关系"""

    __tablename__ = "sales_specialist_mapping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sales_id: Mapped[str] = mapped_column(String(36), nullable=False)
    specialist_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("sales_id", "specialist_id", name="uq_mapping_sales_specialist"),
        Index("ix_mapping_sales", "sales_id"),
        Index("ix_mapping_specialist", "specialist_id"),
    )


class RecognitionAnnualSnapshot(Base):
    """年度快照"""

    __tablename__ = "recognition_annual_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    final_rank: Mapped[str] = mapped_column(String(10), nullable=False)
    total_awards: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "year", name="uq_snapshot_user_year"),
    )