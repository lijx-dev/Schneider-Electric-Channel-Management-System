"""
分销商大会「能量印记·集章」模块数据模型

包含4个表：展区配置、能量印记发放记录、能量勋章发放记录、通用活动计数
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ConferenceZone(Base, TimestampMixin):
    """展区配置"""

    __tablename__ = "conference_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    slogan: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 展区任务类型：'quiz'=答题展区 / 'channel'=渠道联动展区
    task_type: Mapped[str] = mapped_column(String(20), default="quiz", nullable=False)
    # 仅 quiz 展区使用，标识该展区题组（对应 questions.category）
    question_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # channel 展区步骤1要求周答题数
    required_daily_quiz_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # channel 展区步骤2要求提问数
    required_ai_chat_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # 展区开放窗口，可空=不限制
    active_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    active_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_conference_zones_active", "is_active", "sort_order"),
    )


class ConferenceZoneMark(Base):
    """能量印记发放记录"""

    __tablename__ = "conference_zone_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    zone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conference_zones.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "zone_id", name="uq_zone_mark_user_zone"),
    )


class ConferenceMedal(Base):
    """能量勋章发放记录（一用户一枚）"""

    __tablename__ = "conference_medals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    # 生成规则：DY- + 8 位大写字母数字随机串，如 DY-8K2M4Q9X
    medal_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    zone_count: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ConferenceActivity(Base):
    """通用活动计数（渠道展区步骤计数，按用户×动作×日期一行）"""

    __tablename__ = "conference_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # 取值 'ai_chat' / 'energy_view'
    action_key: Mapped[str] = mapped_column(String(30), nullable=False)
    # YYYY-MM-DD
    activity_date: Mapped[str] = mapped_column(String(10), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "action_key", "activity_date",
            name="uq_conf_activity_user_action_date",
        ),
    )
