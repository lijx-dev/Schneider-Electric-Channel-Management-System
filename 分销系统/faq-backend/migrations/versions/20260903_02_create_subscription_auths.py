"""Create subscription_auths table.

Revision ID: 20260903_02
Revises: 20260903_01
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260903_02"
down_revision = "20260903_01"
branch_labels = None
depends_on = None

TABLE_NAME = "subscription_auths"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    # 幂等：生产库可能已手动建表，已存在则跳过，避免重复建表报错。
    if _table_exists(TABLE_NAME):
        return
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.String(36), primary_key=True, comment="主键 UUID"),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            comment="用户 UUID，对应 users 表 id",
        ),
        sa.Column("openid", sa.String(64), nullable=False, comment="用户 openid 快照，发送订阅消息用"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="waiting",
            comment="waiting(待发送)/sent(已发送)/failed(发送失败)",
        ),
        sa.Column(
            "target_send_at",
            sa.DateTime(),
            nullable=False,
            comment="最近下一个周一 09:00（CST 无时区）",
        ),
        sa.Column("template_id", sa.String(64), nullable=True, comment="订阅模板快照"),
        sa.Column("auth_source", sa.String(20), nullable=True, comment="授权来源 home/quiz"),
        sa.Column("send_at", sa.DateTime(), nullable=True, comment="实际发送时间"),
        sa.Column("error_message", sa.String(500), nullable=True, comment="发送失败原因截断"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        comment="每周一答题提醒的订阅授权（一次性订阅，每次授权对应一条提醒）",
    )
    op.create_index("ix_subscription_auths_user_id", TABLE_NAME, ["user_id"], unique=False)
    op.create_index(
        "ix_subscription_auths_status_target", TABLE_NAME, ["status", "target_send_at"], unique=False
    )


def downgrade() -> None:
    if _table_exists(TABLE_NAME):
        op.drop_table(TABLE_NAME)