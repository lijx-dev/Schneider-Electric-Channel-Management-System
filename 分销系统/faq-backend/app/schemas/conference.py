"""分销商大会「能量印记·集章」模块 Pydantic 请求 Schema."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ZoneAnswer(BaseModel):
    """单题作答"""
    question_id: int = Field(..., description="题目 ID")
    selected_answer: str = Field(..., description="选中的答案（单选 A/B/C；多选 ABD）")


class QuizSubmit(BaseModel):
    """提交题组答案"""
    answers: list[ZoneAnswer] = Field(..., description="答案列表")


class ActivityReport(BaseModel):
    """上报活动计数（channel 展区步骤）"""
    action: str = Field(..., description="动作类型：energy_view")
