"""
HiAgent 会话持久化模型

解决多实例部署时内存字典隔离导致的多轮对话上下文丢失问题。
将 AppConversationID 持久化到数据库，所有实例共享。
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HiAgentConversation(Base, TimestampMixin):
    """
    HiAgent 会话记录表

    以 user_id 为主键，记录用户在 HiAgent 平台的 AppConversationID，
    用于多轮对话上下文维护。服务重启或多实例路由时从数据库恢复。
    """
    __tablename__ = "hiagent_conversations"

    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="用户 UUID，对应 users 表 id"
    )
    app_conversation_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="HiAgent 平台返回的 AppConversationID"
    )

    def __repr__(self) -> str:
        return f"<HiAgentConversation user={self.user_id} conv={self.app_conversation_id[:16]}>"
