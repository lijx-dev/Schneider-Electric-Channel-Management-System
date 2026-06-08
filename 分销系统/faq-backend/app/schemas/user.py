"""
用户相关数据模型
"""
from pydantic import BaseModel
from typing import Optional


class UserScore(BaseModel):
    """用户积分"""
    user_id: str
    nickname: str
    avatar: str
    total_score: int
    correct_count: int
    total_count: int
    rank: Optional[int] = None


class UserProfileUpdate(BaseModel):
    """用户信息更新"""
    user_id: str
    nickname: str
    avatar: str = ""
