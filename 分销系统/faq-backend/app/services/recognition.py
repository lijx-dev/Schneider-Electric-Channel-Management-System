"""认可计划计算引擎：积分、评选、加权排名."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recognition import (
    RecognitionAward,
    RecognitionPoints,
    RecognitionRulesConfig,
    RecognitionScoringCriteria,
    RecognitionSubmission,
    RecognitionSurvey,
)
from app.models.user import User

# ── 等级常量 ──────────────────────────────────────────────────────────────

LEVELS = [
    ("启明星", "☆", 0, 100),
    ("灿星", "★", 101, 300),
    ("耀星", "✦", 301, 600),
    ("极星", "✧", 601, None),
]

SUBMISSION_TYPE_MAP = {
    "nomination": "微光提名",
    "order_guardian": "报备秩序",
    "distributor_pioneer": "分销商支持",
    "distributor_mentor": "分销商成长",
    "efficiency_innovator": "效能提升",
}

AWARD_TYPE_MAP = {
    "monthly_star": "微光之星",
    "monthly_mvp": "销圈人气王",
    "order_guardian": "报备秩序卫士",
    "distributor_pioneer": "分销商支持先锋",
    "distributor_mentor": "分销商成长伯乐",
    "efficiency_innovator": "效率提升创新",
    "annual_star": "年度渠道之星",
}

QUARTERLY_AWARD_TYPES = ["order_guardian", "distributor_pioneer", "distributor_mentor", "efficiency_innovator"]


def get_level_info(total_score: int) -> dict:
    """根据积分返回等级信息."""
    for name, icon, low, high in LEVELS:
        if high is None or total_score <= high:
            return {
                "level": name,
                "level_icon": icon,
                "min": low,
                "max": high,
            }
    return {"level": "极星", "level_icon": "✧", "min": 601, "max": None}


async def get_rule_value(db: AsyncSession, rule_key: str, default: str = "0") -> str:
    """从 rules_config 读取规则值."""
    result = await db.execute(
        select(RecognitionRulesConfig.rule_value).where(
            RecognitionRulesConfig.rule_key == rule_key
        )
    )
    value = result.scalar_one_or_none()
    return value if value is not None else default


async def _get_user_name(db: AsyncSession, user_id: str) -> str:
    result = await db.execute(select(User.real_name).where(User.id == user_id))
    name = result.scalar_one_or_none()
    return name or user_id


async def _get_user_names(db: AsyncSession, user_ids: list[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    result = await db.execute(
        select(User.id, User.real_name).where(User.id.in_(user_ids))
    )
    return {row.id: row.real_name or row.id for row in result}


async def resolve_nominee_user_ids(
    db: AsyncSession, raw_values: list[str]
) -> tuple[dict[str, str], list[str]]:
    """把提名里的「被提名人」标识解析为真实用户ID。

    历史上该字段既可能存用户ID，也可能存姓名（前端为自由输入）。
    返回 (原始值 -> user_id 映射, 无法唯一匹配的原始值列表)。
    姓名重名无法唯一确定时视为无法匹配。
    """
    cleaned = {str(v).strip() for v in raw_values if v and str(v).strip()}
    if not cleaned:
        return {}, []

    result = await db.execute(
        select(User.id, User.real_name).where(
            or_(User.id.in_(cleaned), User.real_name.in_(cleaned))
        )
    )
    rows = result.all()

    by_id = {row.id for row in rows if row.id in cleaned}
    name_to_ids: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row.real_name and row.real_name in cleaned:
            name_to_ids[row.real_name].append(row.id)

    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for value in cleaned:
        if value in by_id:
            resolved[value] = value
        elif len(name_to_ids.get(value, [])) == 1:
            resolved[value] = name_to_ids[value][0]
        else:
            unresolved.append(value)
    return resolved, unresolved


# ── 月度微光之星评选 ─────────────────────────────────────────────────────

async def calculate_monthly_star(db: AsyncSession, month: str) -> list[dict]:
    """按当月提名次数统计，取前 max_winners 名."""
    max_winners = int(await get_rule_value(db, "monthly_nomination_max_winners", "2"))
    points = int(await get_rule_value(db, "monthly_nomination_points", "30"))

    # 微光提名中 content_json 的 nominee_id 才是被提名人
    # 需按 nominee_id 而非 applicant_id 统计
    nominations = await db.execute(
        select(RecognitionSubmission).where(
            RecognitionSubmission.submission_type == "nomination",
            RecognitionSubmission.submission_month == month,
            RecognitionSubmission.status == "approved",
        )
    )
    submissions = nominations.scalars().all()

    raw_counts: dict[str, int] = defaultdict(int)
    for sub in submissions:
        try:
            content = json.loads(sub.content_json) if isinstance(sub.content_json, str) else sub.content_json
            nominee_id = content.get("nominee_id", "")
            nominee_id = str(nominee_id).strip() if nominee_id is not None else ""
            if nominee_id:
                raw_counts[nominee_id] += 1
        except (json.JSONDecodeError, AttributeError):
            pass

    if not raw_counts:
        return []

    # 被提名人可能存的是用户ID或姓名，统一解析为真实 user_id
    resolved, _unresolved = await resolve_nominee_user_ids(db, list(raw_counts.keys()))

    nominee_counts: dict[str, int] = defaultdict(int)
    for raw_value, count in raw_counts.items():
        user_id = resolved.get(raw_value)
        if user_id:
            nominee_counts[user_id] += count

    if not nominee_counts:
        return []

    sorted_nominees = sorted(nominee_counts.items(), key=lambda x: x[1], reverse=True)[:max_winners]
    user_ids = [uid for uid, _ in sorted_nominees]
    names = await _get_user_names(db, user_ids)

    results = []
    for rank, (uid, count) in enumerate(sorted_nominees, 1):
        results.append({
            "user_id": uid,
            "user_name": names.get(uid, uid),
            "rank": rank,
            "nomination_count": count,
            "points": points,
        })
    return results


# ── 月度销圈人气王评选 ───────────────────────────────────────────────────

async def calculate_sales_mvp(db: AsyncSession, month: str) -> list[dict]:
    """每个专员取所有销售总分的「中位数」."""
    max_winners = int(await get_rule_value(db, "monthly_mvp_max_winners", "2"))
    rank1_points = int(await get_rule_value(db, "monthly_mvp_rank1_points", "50"))
    rank2_points = int(await get_rule_value(db, "monthly_mvp_rank2_points", "20"))

    # 获取当月所有评分
    result = await db.execute(
        select(RecognitionSurvey).where(RecognitionSurvey.survey_month == month)
    )
    surveys = result.scalars().all()

    if not surveys:
        return []

    # 按专员(target_id)分组
    specialist_scores: dict[str, list[float]] = defaultdict(list)
    for s in surveys:
        dims = [s.score_efficiency, s.score_response, s.score_training, s.score_communication]
        valid = [d for d in dims if d is not None]
        if valid:
            total = sum(valid)
            specialist_scores[s.target_id].append(float(total))

    if not specialist_scores:
        return []

    # 计算每个专员的中位数，排序
    medians = []
    for specialist_id, scores in specialist_scores.items():
        med = statistics.median(scores) if scores else 0
        medians.append((specialist_id, med, len(scores)))

    medians.sort(key=lambda x: x[1], reverse=True)
    winners = medians[:max_winners]

    user_ids = [uid for uid, _, _ in winners]
    names = await _get_user_names(db, user_ids)

    results = []
    for rank, (uid, median_val, rater_count) in enumerate(winners, 1):
        pts = rank1_points if rank == 1 else rank2_points
        results.append({
            "user_id": uid,
            "user_name": names.get(uid, uid),
            "rank": rank,
            "median_score": round(median_val, 2),
            "rater_count": rater_count,
            "points": pts,
        })
    return results


# ── 季度奖项评选（动态评分标准）──────────────────────────────────────────

async def calculate_quarterly_award(
    db: AsyncSession, award_type: str, quarter: int, year: int
) -> list[dict]:
    """从 scoring_criteria 动态读取评分标准，计算得分，取前 max_winners 名."""
    max_winners = int(await get_rule_value(db, "quarterly_max_winners", "2"))
    points = int(await get_rule_value(db, "quarterly_points", "50"))

    # 1. 读取评分标准
    criteria_result = await db.execute(
        select(RecognitionScoringCriteria).where(
            RecognitionScoringCriteria.award_type == award_type,
            RecognitionScoringCriteria.is_active == True,
        ).order_by(RecognitionScoringCriteria.sort_order)
    )
    criteria = criteria_result.scalars().all()

    if not criteria:
        return []

    # 2. 获取该季度已审核通过的申报
    submissions_result = await db.execute(
        select(RecognitionSubmission).where(
            RecognitionSubmission.submission_type == award_type,
            RecognitionSubmission.quarter == quarter,
            RecognitionSubmission.year == year,
            RecognitionSubmission.status == "approved",
        )
    )
    submissions = submissions_result.scalars().all()

    if not submissions:
        return []

    # 3. 按动态标准计算得分
    scored = []
    for sub in submissions:
        score = 0
        try:
            content = json.loads(sub.content_json) if isinstance(sub.content_json, str) else sub.content_json
        except (json.JSONDecodeError, AttributeError):
            content = {}
        predefined = content.get("predefined", {})

        for criterion in criteria:
            if criterion.item_key not in predefined:
                continue
            item_data = predefined[criterion.item_key]

            if criterion.item_type == "checkbox":
                # 勾选框：勾选即得分
                if item_data:
                    score += criterion.points_per_unit
            elif criterion.item_type in ("text_list", "text_number"):
                # 列表型：按条目数计分
                if isinstance(item_data, list):
                    count = len(item_data)
                    pts = count * criterion.points_per_unit
                    if criterion.max_points is not None:
                        pts = min(pts, criterion.max_points)
                    score += pts
                elif item_data:
                    score += criterion.points_per_unit

        # 经理审核评分作为额外加分
        if sub.review_score:
            score += sub.review_score

        scored.append((sub, score))

    # 4. 排序取前N名
    scored.sort(key=lambda x: x[1], reverse=True)
    winners = scored[:max_winners]

    user_ids = [s.applicant_id for s, _ in winners]
    names = await _get_user_names(db, user_ids)

    results = []
    for rank, (sub, score) in enumerate(winners, 1):
        results.append({
            "user_id": sub.applicant_id,
            "user_name": names.get(sub.applicant_id, sub.applicant_id),
            "rank": rank,
            "score": score,
            "points": points,
            "submission_id": sub.id,
        })
    return results


# ── 年度渠道之星评选 ─────────────────────────────────────────────────────

async def calculate_annual_star(db: AsyncSession, year: int) -> list[dict]:
    """综合加权：积分40% + 获奖20% + 人气王15% + 微光之星10% + 经理评定15%."""
    max_winners = int(await get_rule_value(db, "annual_max_winners", "1"))
    points = int(await get_rule_value(db, "annual_points", "100"))

    w_score = float(await get_rule_value(db, "annual_weight_score", "0.4"))
    w_awards = float(await get_rule_value(db, "annual_weight_awards", "0.2"))
    w_mvp = float(await get_rule_value(db, "annual_weight_mvp", "0.15"))
    w_nomination = float(await get_rule_value(db, "annual_weight_nomination", "0.1"))
    w_manager = float(await get_rule_value(db, "annual_weight_manager", "0.15"))

    # 获取所有专员
    spec_result = await db.execute(
        select(User).where(User.recognition_role == "specialist")
    )
    specialists = spec_result.scalars().all()
    if not specialists:
        return []

    # 获取年度积分排行
    scores = {}
    for sp in specialists:
        scores[sp.id] = sp.recognition_score

    max_score = max(scores.values()) if scores else 1

    # 获取获奖次数
    award_result = await db.execute(
        select(RecognitionAward.user_id, func.count(RecognitionAward.id).label("cnt"))
        .where(RecognitionAward.award_year == year, RecognitionAward.published == True)
        .group_by(RecognitionAward.user_id)
    )
    award_counts = {row.user_id: row.cnt for row in award_result}
    max_awards = max(award_counts.values()) if award_counts else 1

    # 人气王获奖次数
    mvp_result = await db.execute(
        select(RecognitionAward.user_id, func.count(RecognitionAward.id).label("cnt"))
        .where(
            RecognitionAward.award_type == "monthly_mvp",
            RecognitionAward.award_year == year,
            RecognitionAward.published == True,
        )
        .group_by(RecognitionAward.user_id)
    )
    mvp_counts = {row.user_id: row.cnt for row in mvp_result}
    max_mvp = max(mvp_counts.values()) if mvp_counts else 1

    # 微光之星获奖次数
    nom_result = await db.execute(
        select(RecognitionAward.user_id, func.count(RecognitionAward.id).label("cnt"))
        .where(
            RecognitionAward.award_type == "monthly_star",
            RecognitionAward.award_year == year,
            RecognitionAward.published == True,
        )
        .group_by(RecognitionAward.user_id)
    )
    nom_counts = {row.user_id: row.cnt for row in nom_result}
    max_nom = max(nom_counts.values()) if nom_counts else 1

    # 综合计算
    user_ids = [sp.id for sp in specialists]
    names = await _get_user_names(db, user_ids)

    composites = []
    for sp in specialists:
        uid = sp.id
        score_norm = scores.get(uid, 0) / max_score if max_score else 0
        award_norm = award_counts.get(uid, 0) / max_awards if max_awards else 0
        mvp_norm = mvp_counts.get(uid, 0) / max_mvp if max_mvp else 0
        nom_norm = nom_counts.get(uid, 0) / max_nom if max_nom else 0
        manager_norm = 0.5  # 默认 0.5，经理可通过管理后台调整

        weighted = (
            score_norm * w_score * 100
            + award_norm * w_awards * 100
            + mvp_norm * w_mvp * 100
            + nom_norm * w_nomination * 100
            + manager_norm * w_manager * 100
        )
        composites.append((uid, weighted, scores.get(uid, 0)))

    composites.sort(key=lambda x: x[1], reverse=True)
    winners = composites[:max_winners]

    results = []
    for rank, (uid, weighted, total_score) in enumerate(winners, 1):
        results.append({
            "user_id": uid,
            "user_name": names.get(uid, uid),
            "rank": rank,
            "weighted_score": round(weighted, 2),
            "total_score": total_score,
            "points": points,
        })
    return results


# ── 积分发放 ─────────────────────────────────────────────────────────────

async def award_points(
    db: AsyncSession,
    user_id: str,
    award_type: str,
    rank: int = 1,
    related_month: Optional[str] = None,
    related_quarter: Optional[str] = None,
    award_year: Optional[int] = None,
) -> int:
    """从 rules_config 读取积分规则，发放积分并记录."""
    # 根据类型获取积分
    point_map = {
        "monthly_star": "monthly_nomination_points",
        "monthly_mvp_rank1": "monthly_mvp_rank1_points",
        "monthly_mvp_rank2": "monthly_mvp_rank2_points",
        "quarterly": "quarterly_points",
        "annual": "annual_points",
    }

    if award_type == "monthly_mvp":
        rule_key = "monthly_mvp_rank1_points" if rank <= 1 else "monthly_mvp_rank2_points"
    else:
        rule_key = point_map.get(award_type, "quarterly_points")

    pts = int(await get_rule_value(db, rule_key, "50"))

    # 更新用户积分
    user = await db.execute(select(User).where(User.id == user_id))
    user = user.scalar_one_or_none()
    if user:
        user.recognition_score = (user.recognition_score or 0) + pts

    # 创建积分记录
    award_name = AWARD_TYPE_MAP.get(award_type, award_type)
    point_record = RecognitionPoints(
        user_id=user_id,
        point_change=pts,
        reason=award_name,
        award_type=award_type,
        related_month=related_month,
        related_quarter=related_quarter,
        created_at=datetime.now(timezone.utc),
    )
    db.add(point_record)

    return pts


# ── 评分中位数计算（含 N/A 处理）─────────────────────────────────────────

def _calculate_survey_median(surveys: list[RecognitionSurvey]) -> Optional[float]:
    """计算评分中位数，忽略 N/A 维度."""
    dims = ["score_efficiency", "score_response", "score_training", "score_communication"]
    all_totals = []
    for s in surveys:
        valid = [getattr(s, d) for d in dims if getattr(s, d) is not None]
        if valid:
            all_totals.append(sum(valid))
    if not all_totals:
        return None
    return statistics.median(all_totals)


# ── 表单配置获取 ─────────────────────────────────────────────────────────

FORM_CONFIGS = {
    "nomination": {
        "award_name": "微光之星",
        "description": "提名同事的微小正向贡献，随时提名，月度评选",
    },
    "order_guardian": {
        "award_name": "报备秩序卫士",
        "description": "申报报备冲突解决案例、典型文档，季度评选",
    },
    "distributor_pioneer": {
        "award_name": "分销商支持先锋",
        "description": "申报新问题处理、痛点推动案例，季度评选",
    },
    "distributor_mentor": {
        "award_name": "分销商成长伯乐",
        "description": "申报合规改善、业绩增长、能力提升案例，季度评选",
    },
    "efficiency_innovator": {
        "award_name": "效率提升创新",
        "description": "申报制度完善、流程优化、工具分享建议，季度评选",
    },
}


async def get_form_config(db: AsyncSession, submission_type: str) -> dict:
    """获取申报表单配置（预定义选项+基础信息）."""
    config = FORM_CONFIGS.get(submission_type, {
        "award_name": submission_type,
        "description": "",
    })

    criteria = await db.execute(
        select(RecognitionScoringCriteria).where(
            RecognitionScoringCriteria.award_type == submission_type,
            RecognitionScoringCriteria.is_active == True,
        ).order_by(RecognitionScoringCriteria.sort_order)
    )
    items = criteria.scalars().all()

    return {
        "submission_type": submission_type,
        "award_name": config["award_name"],
        "description": config["description"],
        "items": [
            {
                "id": item.id,
                "item_name": item.item_name,
                "item_key": item.item_key,
                "item_type": item.item_type,
                "item_placeholder": item.item_placeholder,
                "item_help_text": item.item_help_text,
                "allow_multiple": item.allow_multiple,
                "sort_order": item.sort_order,
            }
            for item in items
        ],
    }