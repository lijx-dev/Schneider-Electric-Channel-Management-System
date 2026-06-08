"""
聊天相关数据模型
"""
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """聊天消息"""
    user_id: str
    message: str


class ChatResponse(BaseModel):
    """AI回复"""
    reply: str
    sources: List[str] = []


class ChatFeedback(BaseModel):
    """AI回答反馈"""
    message_id: str
    like_type: int | str = "dislike"
    feedback_info: Dict[str, Any] = Field(default_factory=dict)
