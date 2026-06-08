"""
通用响应模型
"""
from pydantic import BaseModel
from typing import Any, Optional


class APIResponse(BaseModel):
    """标准API响应格式"""
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None
