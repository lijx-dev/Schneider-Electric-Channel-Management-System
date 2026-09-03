"""Create hiagent_conversations table.

Revision ID: 20260903_01
Revises: 20260820_01
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260903_01"
down_revision = "20260820_01"
branch_labels = None
depends_on = None

TABLE_NAME = "hiagent_conversations"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # 幂等：生产库可能已手动建表（容器启动时 alembic upgrade head 先于手动 SQL），
    # 已存在则跳过，避免重复建表报错。
    if _table_exists(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("user_id", sa.String(36), primary_key=True, comment="用户 UUID，对应 users 表 id"),
        sa.Column("app_conversation_id", sa.String(128), nullable=False, comment="HiAgent 平台返回的 AppConversationID"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", name="pk_hiagent_conversations"),
        comment="HiAgent 会话持久化记录（多实例共享 AppConversationID）",
    )


def downgrade() -> None:
    if _table_exists(TABLE_NAME):
        op.drop_table(TABLE_NAME)