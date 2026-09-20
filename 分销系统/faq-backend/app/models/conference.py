"""
分销商大会「能量印章·集章」模块数据模型（手机号自助签到版）

包含4个表：打卡点配置、参会人、印章发放记录、能量勋章发放记录。

业务形态：扫码进对应打卡点 → 填姓名＋手机号自助签到（无白名单/无微信登录）→
答题提交发对应打卡点印章（按手机号幂等）→ 集齐全部印章生成能量勋章（唯一编码）。
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
    """打卡点/展区配置"""

    __tablename__ = "conference_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    slogan: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 题组分类（对应 questions.category）：
    # conference_new_v / conference_digital / conference_channel / conference_business
    question_category: Mapped[str] = mapped_column(String(50), nullable=False)
    # 打卡点开放窗口，可空=不限制
    active_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    active_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_conference_zones_active", "is_active", "sort_order"),
    )


class ConferenceAttendee(Base, TimestampMixin):
    """参会人（以手机号唯一，姓名自助填写）"""

    __tablename__ = "conference_attendees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    __table_args__ = (
        Index("ix_conference_attendees_phone", "phone"),
    )


class ConferenceZoneMark(Base):
    """印章发放记录（按手机号×打卡点唯一，幂等）"""

    __tablename__ = "conference_zone_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    zone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conference_zones.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("phone", "zone_id", name="uq_conf_mark_phone_zone"),
    )


class ConferenceAnswer(Base, TimestampMixin):
    """打卡点答题进度（手机号维度专用进度表）。

    主表 answer_records.user_id 外键绑定主用户体系，无法承载手机号身份，
    故本表作为 conference 专用进度记录（按手机号×题目×日期幂等覆盖）。
    """

    __tablename__ = "conference_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    zone_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conference_zones.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_answer: Mapped[str] = mapped_column(String(500), nullable=False)
    # YYYY-MM-DD（Asia/Shanghai 当日）
    quiz_date: Mapped[str] = mapped_column(String(10), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "phone", "question_id", "quiz_date",
            name="uq_conf_answer_phone_question_date",
        ),
        Index("ix_conf_answer_phone_zone", "phone", "zone_id"),
    )


class ConferenceMedal(Base):
    """能量勋章发放记录（一手机号一枚）"""

    __tablename__ = "conference_medals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 生成规则：DY- + 8 位大写字母数字随机串，如 DY-8K2M4Q9X
    medal_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    zone_count: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
