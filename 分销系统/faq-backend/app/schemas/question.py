"""
题目相关数据模型（Pydantic Schema）

支持5种题型：单选、多选、判断、填空、解答
"""
from pydantic import BaseModel
from typing import List, Optional


class Question(BaseModel):
    """题目完整模型（含答案）"""
    id: int
    question_type: str           # single_choice / multiple_choice / fill_blank / short_answer / true_false
    content: str
    options: Optional[List[str]] = None  # 选择题/判断题有选项，填空/解答为 null
    answer: str                  # 正确答案
    explanation: Optional[str] = None
    difficulty: int = 1
    difficulty_label: Optional[str] = None
    category: Optional[str] = None


class QuestionSafe(BaseModel):
    """题目模型（安全版本，不含答案，答题时用）"""
    id: int
    question_type: str
    content: str
    options: Optional[List[str]] = None
    difficulty: int = 1
    category: Optional[str] = None


class AnswerSubmit(BaseModel):
    """答题提交"""
    user_id: str
    question_id: int
    selected_answer: str         # 改为 str：单选 "A"，多选 "ABD"，填空/解答为文本
    time_spent: int = 0          # 用时(秒)


class AnswerResult(BaseModel):
    """答题结果"""
    is_correct: bool
    correct_answer: str          # 正确答案
    explanation: str = ""
    score: int
