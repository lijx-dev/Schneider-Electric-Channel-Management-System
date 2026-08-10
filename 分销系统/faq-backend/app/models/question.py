"""
题目模型 - 支持5种题型

题型：single_choice(单选), multiple_choice(多选), fill_blank(填空),
      short_answer(解答/问答), true_false(判断)

答案字段 answer 使用 JSON 存储，格式：
  单选题:   "A"
  多选题:   "ABD"
  判断题:   "对" 或 "错"
  填空题:   "填空答案文本"
  解答题:   "解答答案文本"
"""
from typing import Optional, List, Any
from sqlalchemy import String, Integer, Text, Boolean, JSON, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# 题型常量
QUESTION_TYPES = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "fill_blank": "填空题",
    "short_answer": "问答题",
    "true_false": "判断题",
}


class Question(Base, TimestampMixin):
    """
    题目表

    支持5种题型：单选、多选、判断、填空、解答
    """
    __tablename__ = "questions"

    # 主键：自增ID
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 题型：single_choice / multiple_choice / fill_blank / short_answer / true_false
    question_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, default="single_choice"
    )

    # 题目内容
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 题目配图URL列表（JSON数组），如 ["https://example.com/img1.jpg", ...]
    image_urls: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)

    # 选项：JSON 数组 ["选项A", "选项B", "选项C", "选项D"]
    # 单选/多选/判断有选项，填空/解答为 null
    options: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)

    # 正确答案（字符串格式）
    # 单选: "A"  多选: "ABD"  判断: "对"/"错"  填空/解答: 答案文本
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # 试题解析（答题后或详情页展示）
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 难度描述（如"技术基础"、"技术综合"），从 Excel C 列读取
    difficulty_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # 难度数值（1=简单, 2=中等, 3=困难），可根据 label 映射
    difficulty: Mapped[int] = mapped_column(Integer, default=1)

    # 分类（产品知识、销售技巧等），预留
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)

    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ===== 智能推题预留字段 =====
    success_rate: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    avg_time_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Question {self.id} [{self.question_type}]: {self.content[:20]}...>"

    def to_dict(self, hide_answer: bool = False) -> dict:
        """
        转换为字典（API 返回用）

        Args:
            hide_answer: 是否隐藏正确答案（答题时隐藏，查看解析时显示）
        """
        result = {
            "id": self.id,
            "question_type": self.question_type,
            "content": self.content,
            "image_urls": self.image_urls or [],
            "options": self.options,
            "difficulty": self.difficulty,
            "difficulty_label": self.difficulty_label,
            "category": self.category,
        }
        if not hide_answer:
            result["answer"] = self.answer
            result["explanation"] = self.explanation or ""
        return result
