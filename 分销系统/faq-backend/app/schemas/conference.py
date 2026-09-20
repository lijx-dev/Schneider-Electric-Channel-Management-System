"""分销商大会「能量印章·集章」模块 Pydantic 请求 Schema."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class JoinPayload(BaseModel):
    """姓名＋手机号自助签到"""
    name: str = Field(..., min_length=1, max_length=50, description="参会人姓名")
    phone: str = Field(..., description="手机号（11 位，不校验短信）")


class ZoneAnswer(BaseModel):
    """单题作答"""
    question_id: int = Field(..., description="题目 ID")
    selected_answer: str = Field(..., description="选中的答案（单选 A/B/C；多选 ABD）")


class QuizSubmit(BaseModel):
    """提交题组答案"""
    phone: str = Field(..., description="手机号")
    answers: list[ZoneAnswer] = Field(..., description="答案列表")
    name: Optional[str] = Field(None, max_length=50, description="参会人姓名（可选，用于自动建档）")
