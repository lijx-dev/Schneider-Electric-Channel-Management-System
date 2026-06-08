"""
答题业务逻辑服务

注意：当前仍使用内存存储（MVP阶段），阶段二将迁移到 PostgreSQL
"""
from typing import Dict, List, Optional, Set
import random

from app.core.logging import get_logger

logger = get_logger(__name__)


# ==================== 题库数据 ====================
QUESTIONS = [
    {
        "id": 1,
        "content": "我们公司的核心产品X系列的最大特点是什么？",
        "options": ["价格低廉", "AI智能集成", "体积小巧", "颜色丰富"],
        "correct_answer": 1,
        "explanation": "X系列产品的核心卖点是其先进的AI智能集成技术，能够实现自动化操作和智能推荐。",
        "category": "产品知识",
        "difficulty": 1
    },
    {
        "id": 2,
        "content": "客户询问产品保修期时，正确的回答是？",
        "options": ["6个月", "1年", "2年", "3年"],
        "correct_answer": 2,
        "explanation": "我们所有产品均提供2年质保服务，这是我们对品质的承诺。",
        "category": "售后服务",
        "difficulty": 1
    },
    {
        "id": 3,
        "content": "面对客户的价格异议，最佳的应对策略是？",
        "options": ["直接降价", "强调产品价值", "忽略异议", "推荐更便宜的产品"],
        "correct_answer": 1,
        "explanation": "正确的做法是强调产品价值，通过对比竞品、展示ROI来让客户理解价格背后的价值。",
        "category": "销售技巧",
        "difficulty": 2
    },
    {
        "id": 4,
        "content": "新品Y系列预计什么时候上市？",
        "options": ["2024年Q1", "2024年Q2", "2024年Q3", "2024年Q4"],
        "correct_answer": 1,
        "explanation": "Y系列新品计划于2024年Q2正式上市，届时会有专门的培训。",
        "category": "产品知识",
        "difficulty": 1
    },
    {
        "id": 5,
        "content": "处理客户投诉时，第一步应该做什么？",
        "options": ["解释原因", "道歉并倾听", "转接上级", "提供补偿"],
        "correct_answer": 1,
        "explanation": "处理投诉的第一步是真诚道歉并耐心倾听客户诉求，让客户感受到被重视。",
        "category": "客户服务",
        "difficulty": 2
    },
    {
        "id": 6,
        "content": "分销商返点政策中，月销售额达到多少可享受最高返点？",
        "options": ["10万", "30万", "50万", "100万"],
        "correct_answer": 2,
        "explanation": "根据最新政策，月销售额达到50万即可享受最高档15%的返点优惠。",
        "category": "政策制度",
        "difficulty": 2
    },
    {
        "id": 7,
        "content": "产品演示时，最重要的是展示什么？",
        "options": ["所有功能", "客户关心的功能", "最新功能", "最复杂的功能"],
        "correct_answer": 1,
        "explanation": "演示应聚焦于客户关心的功能，而非面面俱到。了解客户需求后进行针对性展示更有效。",
        "category": "销售技巧",
        "difficulty": 2
    },
    {
        "id": 8,
        "content": "Z系列产品适合哪类客户群体？",
        "options": ["个人消费者", "中小企业", "大型企业", "政府机构"],
        "correct_answer": 1,
        "explanation": "Z系列定位于中小企业市场，性价比高，功能适中，是SMB客户的首选。",
        "category": "产品知识",
        "difficulty": 1
    },
    {
        "id": 9,
        "content": "跟进意向客户的最佳时间间隔是？",
        "options": ["每天", "每周", "每两周", "每月"],
        "correct_answer": 1,
        "explanation": "一般建议每周跟进一次意向客户，既保持联系又不会让客户感到压力。",
        "category": "销售技巧",
        "difficulty": 2
    },
    {
        "id": 10,
        "content": "遇到技术问题无法解答时，应该怎么做？",
        "options": ["随便回答", "承认不知道并记录后反馈", "转移话题", "让客户自己查资料"],
        "correct_answer": 1,
        "explanation": "诚实地告知客户会帮忙确认，记录问题后及时反馈给技术支持，这样既专业又负责。",
        "category": "客户服务",
        "difficulty": 1
    }
]


# ==================== 内存存储（阶段二迁移到数据库） ====================
# 用户积分
user_scores: Dict[str, dict] = {}
# 今日已答题目
daily_answered: Dict[str, Set[int]] = {}


class QuizService:
    """答题服务"""
    
    @staticmethod
    def get_questions(count: int = 5, user_id: Optional[str] = None) -> List[dict]:
        """获取今日题目"""
        # 如果用户已答过，返回相同题目
        if user_id and user_id in daily_answered:
            answered_ids = daily_answered[user_id]
            return [q for q in QUESTIONS if q["id"] in answered_ids]
        
        # 随机选择题目
        selected = random.sample(QUESTIONS, min(count, len(QUESTIONS)))
        
        # 记录用户今日题目
        if user_id:
            daily_answered[user_id] = {q["id"] for q in selected}
            logger.info("quiz_generated", user_id=user_id, question_count=len(selected))
        
        return selected
    
    @staticmethod
    def get_question_by_id(question_id: int) -> Optional[dict]:
        """根据ID获取题目"""
        for q in QUESTIONS:
            if q["id"] == question_id:
                return q
        return None
    
    @staticmethod
    def submit_answer(user_id: str, question_id: int, selected_answer: int, time_spent: int) -> dict:
        """提交答案并更新积分"""
        question = QuizService.get_question_by_id(question_id)
        if not question:
            logger.warning("question_not_found", question_id=question_id)
            return {"error": "题目不存在"}
        
        is_correct = selected_answer == question["correct_answer"]
        
        # 计算得分: 正确+10分，速度加成最高+5分
        score = 0
        if is_correct:
            score = 10
            if time_spent < 10:
                score += 5
            elif time_spent < 20:
                score += 3
            elif time_spent < 30:
                score += 1
        
        # 更新用户积分
        if user_id not in user_scores:
            user_scores[user_id] = {
                "nickname": f"用户{user_id[:6]}",
                "avatar": "",
                "total_score": 0,
                "correct_count": 0,
                "total_count": 0
            }
        
        user_scores[user_id]["total_score"] += score
        user_scores[user_id]["total_count"] += 1
        if is_correct:
            user_scores[user_id]["correct_count"] += 1
        
        logger.info(
            "answer_submitted",
            user_id=user_id,
            question_id=question_id,
            is_correct=is_correct,
            score=score
        )
        
        return {
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"],
            "score": score
        }
    
    @staticmethod
    def get_leaderboard(limit: int = 20) -> List[dict]:
        """获取排行榜"""
        sorted_users = sorted(
            user_scores.items(),
            key=lambda x: x[1]["total_score"],
            reverse=True
        )[:limit]
        
        result = []
        for rank, (user_id, data) in enumerate(sorted_users, 1):
            result.append({
                "user_id": user_id,
                "nickname": data["nickname"],
                "avatar": data["avatar"],
                "total_score": data["total_score"],
                "correct_count": data["correct_count"],
                "total_count": data["total_count"],
                "rank": rank
            })
        
        return result
    
    @staticmethod
    def get_user_rank(user_id: str) -> Optional[dict]:
        """获取用户排名"""
        if user_id not in user_scores:
            return None
        
        sorted_users = sorted(
            user_scores.items(),
            key=lambda x: x[1]["total_score"],
            reverse=True
        )
        
        for rank, (uid, data) in enumerate(sorted_users, 1):
            if uid == user_id:
                return {
                    "user_id": user_id,
                    "nickname": data["nickname"],
                    "avatar": data["avatar"],
                    "total_score": data["total_score"],
                    "correct_count": data["correct_count"],
                    "total_count": data["total_count"],
                    "rank": rank
                }
        
        return None
    
    @staticmethod
    def update_user_profile(user_id: str, nickname: str, avatar: str) -> None:
        """更新用户信息"""
        if user_id not in user_scores:
            user_scores[user_id] = {
                "nickname": nickname,
                "avatar": avatar,
                "total_score": 0,
                "correct_count": 0,
                "total_count": 0
            }
        else:
            user_scores[user_id]["nickname"] = nickname
            user_scores[user_id]["avatar"] = avatar
        
        logger.info("user_profile_updated", user_id=user_id, nickname=nickname)
