"""
订阅授权模型

记录用户对"每周一答题提醒"小程序订阅消息的一次性授权。
每次授权对应一条提醒（一次性订阅：同意一次可推一条），
调度器在 target_send_at（最近下一个周一 09:00）发送后将状态置为 sent。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SubscriptionAuth(Base, TimestampMixin):
    """
    订阅授权表

    存储用户订阅授权的快照与发送状态，供每周一 09:00 提醒调度器使用。
    """
    __tablename__ = "subscription_auths"

    # 主键：UUID
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    # 用户 UUID（对应 users 表 id）
    user_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    # 用户 openid 快照，发送订阅消息时直接使用，避免 join
    openid: Mapped[str] = mapped_column(String(64), nullable=False)

    # 发送状态：waiting(待发送)/sent(已发送)/failed(发送失败)
    status: Mapped[str] = mapped_column(
        String(20), default="waiting", nullable=False
    )

    # 目标发送时间：最近下一个周一 09:00（CST 无时区）
    target_send_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # 订阅模板 ID 快照（可在后台更换模板后保持历史记录）
    template_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 授权来源：home(首页引导条)/quiz(答题完成页)
    auth_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # 实际发送时间
    send_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 发送失败原因（截断）
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_subscription_auths_status_target", "status", "target_send_at"),
    )