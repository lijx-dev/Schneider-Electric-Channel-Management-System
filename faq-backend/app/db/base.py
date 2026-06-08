"""
SQLAlchemy 基础类定义

所有 ORM 模型继承自 Base
"""
from datetime import datetime
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    所有 ORM 模型的基类
    """
    pass


class TimestampMixin:
    """
    时间戳混入类
    
    为模型自动添加 created_at 和 updated_at 字段
    """
    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
        onupdate=func.now()
    )
