"""
用户模型

包含智能推题预留字段：weak_categories, last_study_at
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """
    用户表
    
    存储微信用户信息和学习统计数据
    """
    __tablename__ = "users"
    
    # 主键：UUID
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    # 微信 OpenID（唯一标识）
    openid: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True
    )
    
    # 用户信息
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True, index=True)
    login_username: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, unique=True, index=True)
    login_password: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    
    # 分销商注册信息
    real_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    job_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # 学习统计
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    profile_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # 标书功能白名单（仅白名单用户可使用招标文件分析功能）
    bidding_whitelisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 认可计划角色：distributor(默认)/sales(销售)/specialist(专员)/manager(经理)
    recognition_role: Mapped[str] = mapped_column(String(20), default='distributor', nullable=False)
    # 认可计划累计积分
    recognition_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 免责声明同意记录（授权合作伙伴接入声明，仅登录用户使用系统前需同意）
    disclaimer_agreed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disclaimer_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    disclaimer_agreed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    # ===== 智能推题预留字段 =====
    # 薄弱分类：{"产品知识": 0.6, "销售技巧": 0.8} 表示各分类正确率
    weak_categories: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=None
    )
    # 最后学习时间（用于遗忘曲线）
    last_study_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    
    def __repr__(self) -> str:
        return f"<User {self.nickname or self.openid[:8]}>"
