"""认可计划系统 API 路由."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user_id,
    require_manager_role,
    require_sales_role,
    require_specialist_or_manager,
    require_specialist_role,
)
from app.db.session import get_db
from app.models.recognition import (
    RecognitionAnnualSnapshot,
    RecognitionAward,
    RecognitionPoints,
    RecognitionRulesConfig,
    RecognitionScoringCriteria,
    RecognitionSubmission,
    RecognitionSurvey,
    SalesSpecialistMapping,
)
from app.models.user import User
from app.schemas.recognition import (
    AnnualSnapshotResponse,
    AwardResultResponse,
    CalculateRequest,
    FormConfigResponse,
    MappingCreate,
    MappingResponse,
    NominationStatsResponse,
    PointsAdjustRequest,
    PointsStatusResponse,
    PointsTransactionResponse,
    PublishRequest,
    RankingEntry,
    RankingPageResponse,
    RecognitionUserResponse,
    RoleUpdateRequest,
    RuleConfigResponse,
    RuleConfigUpdate,
    ScoringCriteriaCreate,
    ScoringCriteriaFullResponse,
    ScoringCriteriaUpdate,
    SubmissionCreate,
    SubmissionResponse,
    SubmissionReview,
    SubmissionUpdate,
    SurveyCreate,
    SurveyDetailResponse,
    SurveyProgressResponse,
    SurveyResultResponse,
    SurveyStatusResponse,
)
from app.services.recognition import (
    QUARTERLY_AWARD_TYPES,
    SUBMISSION_TYPE_MAP,
    AWARD_TYPE_MAP,
    calculate_monthly_star,
    calculate_sales_mvp,
    calculate_quarterly_award,
    calculate_annual_star,
    award_points,
    get_form_config,
    get_level_info,
    get_rule_value,
    _get_user_names,
)

router = APIRouter(prefix="/recognition", tags=["认可计划"])

# ── 角色校验别名（从 deps.py 导入） ────────────────────────────────────────

VALID_ROLES = {"distributor", "sales", "specialist", "manager"}

require_manager = require_manager_role
require_sales = require_sales_role
require_specialist = require_specialist_role


# ── 辅助函数 ─────────────────────────────────────────────────────────────

async def _get_user_name(db: AsyncSession, user_id: str) -> str:
    result = await db.execute(select(User.real_name).where(User.id == user_id))
    name = result.scalar_one_or_none()
    return name or user_id


async def _build_submission_response(db: AsyncSession, sub: RecognitionSubmission) -> dict:
    try:
        content = json.loads(sub.content_json) if isinstance(sub.content_json, str) else sub.content_json
    except (json.JSONDecodeError, AttributeError):
        content = sub.content_json

    return {
        "id": sub.id,
        "applicant_id": sub.applicant_id,
        "applicant_name": await _get_user_name(db, sub.applicant_id),
        "submission_type": sub.submission_type,
        "content_json": content,
        "attachments": sub.attachments,
        "status": sub.status,
        "reviewed_by": sub.reviewed_by,
        "reviewer_name": await _get_user_name(db, sub.reviewed_by) if sub.reviewed_by else None,
        "reviewed_at": sub.reviewed_at,
        "review_comment": sub.review_comment,
        "review_score": sub.review_score,
        "quarter": sub.quarter,
        "year": sub.year,
        "submission_month": sub.submission_month,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 成就申报
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/submissions/form-config")
async def get_submission_form_config(
    type: str = Query(..., description="申报类型"),
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """获取某类型申报表单的预定义选项（从scoring_criteria动态加载）."""
    if type == "nomination":
        # 微光提名不适用预定义选项，返回特殊结构
        return {
            "code": 0,
            "data": {
                "submission_type": "nomination",
                "award_name": "微光之星",
                "description": "提名同事的微小正向贡献，随时提名，不限次数",
                "items": [],  # 微光提名用自由文本模式
                "is_nomination": True,
            },
        }

    if type not in SUBMISSION_TYPE_MAP:
        return {"code": 1, "message": f"不支持的申报类型: {type}"}

    config = await get_form_config(db, type)
    return {"code": 0, "data": config}


@router.post("/submissions")
async def create_submission(
    body: SubmissionCreate,
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """提交申报（含5种类型）."""
    if body.submission_type not in SUBMISSION_TYPE_MAP:
        return {"code": 1, "message": f"不支持的申报类型: {body.submission_type}"}

    # 微光提名校验：不可自提
    if body.submission_type == "nomination":
        nominee_id = body.content_json.get("nominee_id", "")
        if nominee_id == user_id:
            return {"code": 1, "message": "不可提名自己"}

    sub = RecognitionSubmission(
        applicant_id=user_id,
        submission_type=body.submission_type,
        content_json=json.dumps(body.content_json, ensure_ascii=False),
        attachments=body.attachments,
        status="submitted",
        quarter=body.quarter,
        year=body.year,
        submission_month=body.submission_month,
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)

    data = await _build_submission_response(db, sub)
    return {"code": 0, "data": data}


@router.put("/submissions/{submission_id}")
async def update_submission(
    submission_id: int,
    body: SubmissionUpdate,
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """修改申报（仅草稿状态可修改）."""
    result = await db.execute(
        select(RecognitionSubmission).where(
            RecognitionSubmission.id == submission_id,
            RecognitionSubmission.applicant_id == user_id,
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"code": 1, "message": "申报不存在或无权修改"}

    if sub.status not in ("draft",):
        return {"code": 1, "message": "仅草稿状态可修改"}

    if body.content_json is not None:
        sub.content_json = json.dumps(body.content_json, ensure_ascii=False)
    if body.attachments is not None:
        sub.attachments = body.attachments
    if body.quarter is not None:
        sub.quarter = body.quarter
    if body.year is not None:
        sub.year = body.year
    if body.submission_month is not None:
        sub.submission_month = body.submission_month

    await db.flush()
    await db.refresh(sub)
    data = await _build_submission_response(db, sub)
    return {"code": 0, "data": data}


@router.get("/submissions")
async def get_my_submissions(
    type: Optional[str] = Query(None, description="按类型筛选"),
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """获取我的申报列表."""
    conditions = [RecognitionSubmission.applicant_id == user_id]
    if type:
        conditions.append(RecognitionSubmission.submission_type == type)

    result = await db.execute(
        select(RecognitionSubmission)
        .where(*conditions)
        .order_by(RecognitionSubmission.created_at.desc())
    )
    subs = result.scalars().all()

    data = [await _build_submission_response(db, s) for s in subs]
    return {"code": 0, "data": data}


@router.get("/submissions/stats")
async def get_nomination_stats(
    month: str = Query(..., description="月份 yyyy-mm"),
    user_id: str = Depends(require_specialist_or_manager),
    db: AsyncSession = Depends(get_db),
):
    """当月提名统计."""
    result = await db.execute(
        select(RecognitionSubmission).where(
            RecognitionSubmission.submission_type == "nomination",
            RecognitionSubmission.submission_month == month,
            RecognitionSubmission.status == "approved",
        )
    )
    subs = result.scalars().all()

    counts: dict[str, dict] = {}
    for s in subs:
        try:
            content = json.loads(s.content_json) if isinstance(s.content_json, str) else s.content_json
            nominee_id = content.get("nominee_id", "")
            if nominee_id:
                if nominee_id not in counts:
                    counts[nominee_id] = {"nominee_id": nominee_id, "nominee_name": "", "count": 0}
                counts[nominee_id]["count"] += 1
        except (json.JSONDecodeError, AttributeError):
            pass

    # 补全名称
    if counts:
        names = await _get_user_names(db, list(counts.keys()))
        for uid, info in counts.items():
            info["nominee_name"] = names.get(uid, uid)

    return {
        "code": 0,
        "data": {
            "month": month,
            "nominations": sorted(counts.values(), key=lambda x: x["count"], reverse=True),
        },
    }


@router.get("/submissions/all")
async def get_all_submissions(
    status: Optional[str] = Query(None, description="按状态筛选"),
    type: Optional[str] = Query(None, description="按类型筛选"),
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取全部申报（审核用）."""
    conditions = []
    if status:
        conditions.append(RecognitionSubmission.status == status)
    if type:
        conditions.append(RecognitionSubmission.submission_type == type)

    result = await db.execute(
        select(RecognitionSubmission)
        .where(*conditions)
        .order_by(RecognitionSubmission.created_at.desc())
    )
    subs = result.scalars().all()

    data = [await _build_submission_response(db, s) for s in subs]
    return {"code": 0, "data": data}


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: int,
    body: SubmissionReview,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """审核申报."""
    result = await db.execute(
        select(RecognitionSubmission).where(RecognitionSubmission.id == submission_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"code": 1, "message": "申报不存在"}

    if body.action == "approve":
        sub.status = "approved"
    elif body.action == "reject":
        sub.status = "rejected"
    else:
        return {"code": 1, "message": "无效的审核操作"}

    sub.reviewed_by = user_id
    sub.reviewed_at = datetime.now(timezone.utc)
    sub.review_comment = body.review_comment
    sub.review_score = body.review_score

    await db.flush()
    await db.refresh(sub)
    data = await _build_submission_response(db, sub)
    return {"code": 0, "data": data}


# ═══════════════════════════════════════════════════════════════════════════
# 销售评分
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/surveys/status")
async def get_survey_status(
    month: Optional[str] = Query(None, description="月份 yyyy-mm，默认本月"),
    user_id: str = Depends(require_sales),
    db: AsyncSession = Depends(get_db),
):
    """获取本月评分状态 + 对接专员列表."""
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    # 获取该销售对接的专员
    mapping_result = await db.execute(
        select(SalesSpecialistMapping).where(SalesSpecialistMapping.sales_id == user_id)
    )
    mappings = mapping_result.scalars().all()

    specialist_ids = [m.specialist_id for m in mappings]
    names = await _get_user_names(db, specialist_ids)

    # 检查是否已提交
    survey_result = await db.execute(
        select(RecognitionSurvey).where(
            RecognitionSurvey.rater_id == user_id,
            RecognitionSurvey.survey_month == month,
        )
    )
    submitted_surveys = survey_result.scalars().all()
    submitted = len(submitted_surveys) > 0

    submitted_map = {s.target_id: s for s in submitted_surveys}

    specialists = []
    for sp_id in specialist_ids:
        sp_info = {
            "specialist_id": sp_id,
            "specialist_name": names.get(sp_id, sp_id),
        }
        if sp_id in submitted_map:
            sp_info["scores"] = {
                "efficiency": submitted_map[sp_id].score_efficiency,
                "response": submitted_map[sp_id].score_response,
                "training": submitted_map[sp_id].score_training,
                "communication": submitted_map[sp_id].score_communication,
            }
        specialists.append(sp_info)

    return {
        "code": 0,
        "data": {
            "survey_month": month,
            "submitted": submitted,
            "specialists": specialists,
        },
    }


@router.post("/surveys")
async def submit_survey(
    body: SurveyCreate,
    user_id: str = Depends(require_sales),
    db: AsyncSession = Depends(get_db),
):
    """提交满意度评分."""
    # 校验对接关系
    mapping_result = await db.execute(
        select(SalesSpecialistMapping).where(
            SalesSpecialistMapping.sales_id == user_id,
            SalesSpecialistMapping.specialist_id == body.target_id,
        )
    )
    if not mapping_result.scalar_one_or_none():
        return {"code": 1, "message": "您与该专员无对接关系，无法评分"}

    # 唯一约束校验
    existing = await db.execute(
        select(RecognitionSurvey).where(
            RecognitionSurvey.rater_id == user_id,
            RecognitionSurvey.target_id == body.target_id,
            RecognitionSurvey.survey_month == body.survey_month,
        )
    )
    if existing.scalar_one_or_none():
        return {"code": 1, "message": "本月已提交评分，不可修改"}

    survey = RecognitionSurvey(
        rater_id=user_id,
        target_id=body.target_id,
        survey_month=body.survey_month,
        score_efficiency=body.score_efficiency,
        score_response=body.score_response,
        score_training=body.score_training,
        score_communication=body.score_communication,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(survey)
    await db.flush()
    return {"code": 0, "data": {"message": "评分提交成功"}}


@router.get("/surveys/results")
async def get_survey_results(
    month: Optional[str] = Query(None, description="月份"),
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """获取评分汇总（专员端匿名）."""
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    result = await db.execute(
        select(RecognitionSurvey).where(RecognitionSurvey.survey_month == month)
    )
    surveys = result.scalars().all()

    # 按 target_id 分组
    grouped: dict[str, list] = {}
    for s in surveys:
        grouped.setdefault(s.target_id, []).append(s)

    names = await _get_user_names(db, list(grouped.keys()))

    results = []
    for target_id, items in grouped.items():
        dims = {
            "efficiency": [s.score_efficiency for s in items if s.score_efficiency is not None],
            "response": [s.score_response for s in items if s.score_response is not None],
            "training": [s.score_training for s in items if s.score_training is not None],
            "communication": [s.score_communication for s in items if s.score_communication is not None],
        }
        avg = {}
        for key, vals in dims.items():
            avg[key] = round(sum(vals) / len(vals), 2) if vals else None

        # 计算中位数总分
        totals = []
        for s in items:
            valid = [getattr(s, d) for d in ["score_efficiency", "score_response", "score_training", "score_communication"] if getattr(s, d) is not None]
            if valid:
                totals.append(sum(valid))
        import statistics
        median = statistics.median(totals) if totals else None

        results.append({
            "survey_month": month,
            "target_id": target_id,
            "target_name": names.get(target_id, target_id),
            "avg_scores": avg,
            "median_score": round(median, 2) if median else None,
            "rater_count": len(items),
        })

    return {"code": 0, "data": results}


@router.get("/surveys/details")
async def get_survey_details(
    month: Optional[str] = Query(None, description="月份"),
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取评分明细（经理端含提交人）."""
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    result = await db.execute(
        select(RecognitionSurvey).where(RecognitionSurvey.survey_month == month)
    )
    surveys = result.scalars().all()

    rater_ids = list(set(s.rater_id for s in surveys))
    target_ids = list(set(s.target_id for s in surveys))
    all_ids = rater_ids + target_ids
    names = await _get_user_names(db, all_ids)

    results = []
    for s in surveys:
        results.append({
            "survey_month": s.survey_month,
            "rater_id": s.rater_id,
            "rater_name": names.get(s.rater_id, s.rater_id),
            "target_id": s.target_id,
            "target_name": names.get(s.target_id, s.target_id),
            "scores": {
                "efficiency": s.score_efficiency,
                "response": s.score_response,
                "training": s.score_training,
                "communication": s.score_communication,
            },
            "submitted_at": s.submitted_at,
        })

    return {"code": 0, "data": results}


@router.get("/surveys/progress")
async def get_survey_progress(
    month: Optional[str] = Query(None, description="月份"),
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取评分进度."""
    if not month:
        now = datetime.now()
        month = f"{now.year}-{now.month:02d}"

    # 所有销售
    sales_result = await db.execute(
        select(User).where(User.recognition_role == "sales")
    )
    all_sales = sales_result.scalars().all()

    # 已提交的销售
    submitted_result = await db.execute(
        select(RecognitionSurvey.rater_id).where(
            RecognitionSurvey.survey_month == month
        ).distinct()
    )
    submitted_ids = set(row[0] for row in submitted_result)

    unsubmitted = []
    for s in all_sales:
        if s.id not in submitted_ids:
            unsubmitted.append({
                "sales_id": s.id,
                "sales_name": s.real_name or s.id,
            })

    return {
        "code": 0,
        "data": {
            "survey_month": month,
            "total_sales": len(all_sales),
            "submitted_count": len(submitted_ids),
            "unsubmitted_sales": unsubmitted,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 销售-专员对接关系
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/mappings")
async def get_mappings(
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取对接关系列表."""
    result = await db.execute(select(SalesSpecialistMapping))
    mappings = result.scalars().all()

    all_ids = list(set(m.sales_id for m in mappings)) + list(set(m.specialist_id for m in mappings))
    names = await _get_user_names(db, all_ids)

    data = []
    for m in mappings:
        data.append({
            "id": m.id,
            "sales_id": m.sales_id,
            "sales_name": names.get(m.sales_id, m.sales_id),
            "specialist_id": m.specialist_id,
            "specialist_name": names.get(m.specialist_id, m.specialist_id),
            "created_at": m.created_at,
        })
    return {"code": 0, "data": data}


@router.post("/mappings")
async def create_mapping(
    body: MappingCreate,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """添加对接关系."""
    # 校验唯一约束
    existing = await db.execute(
        select(SalesSpecialistMapping).where(
            SalesSpecialistMapping.sales_id == body.sales_id,
            SalesSpecialistMapping.specialist_id == body.specialist_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"code": 1, "message": "该对接关系已存在"}

    mapping = SalesSpecialistMapping(
        sales_id=body.sales_id,
        specialist_id=body.specialist_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(mapping)
    await db.flush()
    return {"code": 0, "data": {"message": "添加成功"}}


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(
    mapping_id: int,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """删除对接关系."""
    result = await db.execute(
        select(SalesSpecialistMapping).where(SalesSpecialistMapping.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        return {"code": 1, "message": "对接关系不存在"}

    await db.delete(mapping)
    await db.flush()
    return {"code": 0, "data": {"message": "删除成功"}}


# ═══════════════════════════════════════════════════════════════════════════
# 积分相关
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/points")
async def get_my_points(
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """获取我的积分和等级."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"code": 1, "message": "用户不存在"}

    score = user.recognition_score or 0
    level_info = get_level_info(score)

    next_level = None
    points_to_next = None
    for name, icon, low, high in [
        ("启明星", "☆", 0, 100),
        ("灿星", "★", 101, 300),
        ("耀星", "✦", 301, 600),
        ("极星", "✧", 601, None),
    ]:
        if score <= (high or float("inf")):
            idx = ["启明星", "灿星", "耀星", "极星"].index(name)
            if idx < 3:
                next_level = ["灿星", "耀星", "极星"][idx]
                points_to_next = ["101", "301", "601"][idx]
                points_to_next = int(points_to_next) - score
            break

    return {
        "code": 0,
        "data": {
            "user_id": user_id,
            "total_score": score,
            "level": level_info["level"],
            "level_icon": level_info["level_icon"],
            "next_level": next_level,
            "points_to_next": points_to_next,
        },
    }


@router.get("/points/ranking")
async def get_points_ranking(
    user_id: str = Depends(require_specialist_or_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取积分排行（所有专员）."""
    result = await db.execute(
        select(User)
        .where(User.recognition_role == "specialist")
        .order_by(User.recognition_score.desc())
    )
    specialists = result.scalars().all()

    ranking = []
    for rank, sp in enumerate(specialists, 1):
        score = sp.recognition_score or 0
        level_info = get_level_info(score)
        ranking.append({
            "rank": rank,
            "user_id": sp.id,
            "user_name": sp.real_name or sp.id,
            "total_score": score,
            "level": level_info["level"],
            "level_icon": level_info["level_icon"],
        })

    return {"code": 0, "data": ranking}


@router.get("/points/transactions")
async def get_points_transactions(
    user_id: str = Depends(require_specialist),
    db: AsyncSession = Depends(get_db),
):
    """获取积分明细."""
    result = await db.execute(
        select(RecognitionPoints)
        .where(RecognitionPoints.user_id == user_id)
        .order_by(RecognitionPoints.created_at.desc())
    )
    transactions = result.scalars().all()

    return {
        "code": 0,
        "data": [
            {
                "id": t.id,
                "point_change": t.point_change,
                "reason": t.reason,
                "award_type": t.award_type,
                "related_month": t.related_month,
                "related_quarter": t.related_quarter,
                "created_at": t.created_at,
            }
            for t in transactions
        ],
    }


@router.post("/points/adjust")
async def adjust_points(
    body: PointsAdjustRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """手动调整积分."""
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"code": 1, "message": "用户不存在"}

    user.recognition_score = (user.recognition_score or 0) + body.point_change

    record = RecognitionPoints(
        user_id=body.user_id,
        point_change=body.point_change,
        reason=body.reason,
        award_type="manual_adjust",
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.flush()

    return {"code": 0, "data": {"message": "积分调整成功", "new_score": user.recognition_score}}


# ═══════════════════════════════════════════════════════════════════════════
# 评选发布
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/awards/calculate-monthly")
async def calculate_monthly(
    body: CalculateRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """触发月度评选计算（微光之星 + 销圈人气王）."""
    if not body.month:
        return {"code": 1, "message": "请指定月份"}

    month = body.month
    year = int(month.split("-")[0])

    results = []

    # 微光之星
    stars = await calculate_monthly_star(db, month)
    for s in stars:
        award = RecognitionAward(
            user_id=s["user_id"],
            award_type="monthly_star",
            award_name="微光之星",
            rank=s["rank"],
            points_awarded=s["points"],
            award_month=month,
            award_year=year,
            published=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(award)
        results.append({"type": "monthly_star", "user_name": s["user_name"], "rank": s["rank"]})

    # 销圈人气王
    mvps = await calculate_sales_mvp(db, month)
    for mvp in mvps:
        award = RecognitionAward(
            user_id=mvp["user_id"],
            award_type="monthly_mvp",
            award_name="销圈人气王",
            rank=mvp["rank"],
            score=mvp["median_score"],
            points_awarded=mvp["points"],
            award_month=month,
            award_year=year,
            published=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(award)
        results.append({"type": "monthly_mvp", "user_name": mvp["user_name"], "rank": mvp["rank"]})

    await db.flush()
    return {"code": 0, "data": {"month": month, "results": results}}


@router.post("/awards/calculate-quarterly")
async def calculate_quarterly(
    body: CalculateRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """触发季度评选计算."""
    if not body.quarter or not body.year:
        return {"code": 1, "message": "请指定季度和年份"}

    results = []
    for award_type in QUARTERLY_AWARD_TYPES:
        winners = await calculate_quarterly_award(db, award_type, body.quarter, body.year)
        for w in winners:
            award = RecognitionAward(
                user_id=w["user_id"],
                award_type=award_type,
                award_name=AWARD_TYPE_MAP.get(award_type, award_type),
                rank=w["rank"],
                score=w["score"],
                points_awarded=w["points"],
                award_quarter=f"{body.year}-Q{body.quarter}",
                award_year=body.year,
                published=False,
                created_at=datetime.now(timezone.utc),
            )
            db.add(award)
            results.append({
                "type": award_type,
                "user_name": w["user_name"],
                "rank": w["rank"],
                "score": w["score"],
            })

    await db.flush()
    return {"code": 0, "data": {"quarter": f"{body.year}-Q{body.quarter}", "results": results}}


@router.post("/awards/calculate-annual")
async def calculate_annual(
    body: CalculateRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """触发年度评选计算."""
    if not body.year:
        return {"code": 1, "message": "请指定年份"}

    winners = await calculate_annual_star(db, body.year)
    results = []
    for w in winners:
        award = RecognitionAward(
            user_id=w["user_id"],
            award_type="annual_star",
            award_name="年度渠道之星",
            rank=w["rank"],
            score=w["weighted_score"],
            points_awarded=w["points"],
            award_year=body.year,
            published=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(award)
        results.append({
            "type": "annual_star",
            "user_name": w["user_name"],
            "rank": w["rank"],
            "weighted_score": w["weighted_score"],
        })

    await db.flush()
    return {"code": 0, "data": {"year": body.year, "results": results}}


@router.post("/awards/publish")
async def publish_awards(
    body: PublishRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """发布评选结果并发放积分."""
    if not body.award_ids:
        return {"code": 1, "message": "请指定要发布的获奖记录"}

    result = await db.execute(
        select(RecognitionAward).where(
            RecognitionAward.id.in_(body.award_ids),
            RecognitionAward.published == False,
        )
    )
    awards = result.scalars().all()

    if not awards:
        return {"code": 1, "message": "没有可发布的获奖记录"}

    published_count = 0
    for award in awards:
        award.published = True
        # 发放积分
        await award_points(
            db,
            award.user_id,
            award.award_type,
            award.rank or 1,
            related_month=award.award_month,
            related_quarter=award.award_quarter,
            award_year=award.award_year,
        )
        published_count += 1

    await db.flush()
    return {"code": 0, "data": {"message": f"已发布 {published_count} 条获奖记录并发放积分"}}


@router.get("/awards/results")
async def get_award_results(
    year: Optional[int] = Query(None),
    month: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    published: Optional[bool] = Query(None),
    user_id: str = Depends(require_specialist_or_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取评选结果."""
    conditions = []
    if year:
        conditions.append(RecognitionAward.award_year == year)
    if month:
        conditions.append(RecognitionAward.award_month == month)
    if type:
        conditions.append(RecognitionAward.award_type == type)
    if published is not None:
        conditions.append(RecognitionAward.published == published)

    result = await db.execute(
        select(RecognitionAward)
        .where(*conditions)
        .order_by(RecognitionAward.created_at.desc())
    )
    awards = result.scalars().all()

    user_ids = list(set(a.user_id for a in awards))
    names = await _get_user_names(db, user_ids)

    data = []
    for a in awards:
        data.append({
            "id": a.id,
            "user_id": a.user_id,
            "user_name": names.get(a.user_id, a.user_id),
            "award_type": a.award_type,
            "award_name": a.award_name,
            "rank": a.rank,
            "score": float(a.score) if a.score is not None else None,
            "points_awarded": a.points_awarded,
            "award_month": a.award_month,
            "award_quarter": a.award_quarter,
            "award_year": a.award_year,
            "certificate_url": a.certificate_url,
            "published": a.published,
            "created_at": a.created_at,
        })

    return {"code": 0, "data": data}


@router.get("/ranking")
async def get_ranking_page(
    year: Optional[int] = Query(None),
    month: Optional[str] = Query(None),
    user_id: str = Depends(require_specialist_or_manager),
    db: AsyncSession = Depends(get_db),
):
    """认可排行页面完整数据."""
    now = datetime.now()
    if not year:
        year = now.year
    if not month:
        month = f"{now.year}-{now.month:02d}"

    # 积分排行
    ranking_result = await db.execute(
        select(User)
        .where(User.recognition_role == "specialist")
        .order_by(User.recognition_score.desc())
    )
    specialists = ranking_result.scalars().all()
    points_ranking = []
    for rank, sp in enumerate(specialists, 1):
        score = sp.recognition_score or 0
        level_info = get_level_info(score)
        points_ranking.append({
            "rank": rank,
            "user_id": sp.id,
            "user_name": sp.real_name or sp.id,
            "total_score": score,
            "level": level_info["level"],
            "level_icon": level_info["level_icon"],
        })

    # 月度微光之星
    monthly_stars = None
    star_result = await db.execute(
        select(RecognitionAward).where(
            RecognitionAward.award_type == "monthly_star",
            RecognitionAward.award_month == month,
            RecognitionAward.published == True,
        ).order_by(RecognitionAward.rank)
    )
    star_awards = star_result.scalars().all()
    if star_awards:
        user_ids = list(set(a.user_id for a in star_awards))
        names = await _get_user_names(db, user_ids)
        monthly_stars = []
        for a in star_awards:
            monthly_stars.append({
                "id": a.id, "user_id": a.user_id,
                "user_name": names.get(a.user_id, a.user_id),
                "award_type": a.award_type, "award_name": a.award_name,
                "rank": a.rank, "score": float(a.score) if a.score else None,
                "points_awarded": a.points_awarded, "award_month": a.award_month,
                "award_quarter": a.award_quarter, "award_year": a.award_year,
                "certificate_url": a.certificate_url, "published": a.published,
                "created_at": a.created_at,
            })

    # 月度销圈人气王
    monthly_mvp = None
    mvp_result = await db.execute(
        select(RecognitionAward).where(
            RecognitionAward.award_type == "monthly_mvp",
            RecognitionAward.award_month == month,
            RecognitionAward.published == True,
        ).order_by(RecognitionAward.rank)
    )
    mvp_awards = mvp_result.scalars().all()
    if mvp_awards:
        user_ids = list(set(a.user_id for a in mvp_awards))
        names = await _get_user_names(db, user_ids)
        monthly_mvp = []
        for a in mvp_awards:
            monthly_mvp.append({
                "id": a.id, "user_id": a.user_id,
                "user_name": names.get(a.user_id, a.user_id),
                "award_type": a.award_type, "award_name": a.award_name,
                "rank": a.rank, "score": float(a.score) if a.score else None,
                "points_awarded": a.points_awarded, "award_month": a.award_month,
                "award_quarter": a.award_quarter, "award_year": a.award_year,
                "certificate_url": a.certificate_url, "published": a.published,
                "created_at": a.created_at,
            })

    # 季度奖项（仅 3/6/9/12 月）
    current_month = int(month.split("-")[1])
    quarterly_awards = None
    if current_month in (3, 6, 9, 12):
        quarter = current_month // 3
        q_result = await db.execute(
            select(RecognitionAward).where(
                RecognitionAward.award_type.in_(QUARTERLY_AWARD_TYPES),
                RecognitionAward.award_quarter == f"{year}-Q{quarter}",
                RecognitionAward.published == True,
            ).order_by(RecognitionAward.award_type, RecognitionAward.rank)
        )
        q_awards = q_result.scalars().all()
        if q_awards:
            user_ids = list(set(a.user_id for a in q_awards))
            names = await _get_user_names(db, user_ids)
            quarterly_awards = []
            for a in q_awards:
                quarterly_awards.append({
                    "id": a.id, "user_id": a.user_id,
                    "user_name": names.get(a.user_id, a.user_id),
                    "award_type": a.award_type, "award_name": a.award_name,
                    "rank": a.rank, "score": float(a.score) if a.score else None,
                    "points_awarded": a.points_awarded, "award_month": a.award_month,
                    "award_quarter": a.award_quarter, "award_year": a.award_year,
                    "certificate_url": a.certificate_url, "published": a.published,
                    "created_at": a.created_at,
                })

    return {
        "code": 0,
        "data": {
            "year": year,
            "month": month,
            "points_ranking": points_ranking,
            "monthly_stars": monthly_stars,
            "monthly_mvp": monthly_mvp,
            "quarterly_awards": quarterly_awards,
            "annual_awards": None,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 规则配置
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/rules")
async def get_rules(
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取所有规则配置."""
    result = await db.execute(select(RecognitionRulesConfig).order_by(RecognitionRulesConfig.rule_key))
    rules = result.scalars().all()
    return {
        "code": 0,
        "data": [
            {
                "id": r.id,
                "rule_key": r.rule_key,
                "rule_value": r.rule_value,
                "description": r.description,
                "updated_by": r.updated_by,
                "updated_at": r.updated_at,
            }
            for r in rules
        ],
    }


@router.put("/rules/{rule_key}")
async def update_rule(
    rule_key: str,
    body: RuleConfigUpdate,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """修改规则配置."""
    result = await db.execute(
        select(RecognitionRulesConfig).where(RecognitionRulesConfig.rule_key == rule_key)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return {"code": 1, "message": "规则不存在"}

    rule.rule_value = body.rule_value
    if body.description is not None:
        rule.description = body.description
    rule.updated_by = user_id
    rule.updated_at = datetime.now(timezone.utc)

    await db.flush()
    return {"code": 0, "data": {"message": "规则更新成功"}}


# ═══════════════════════════════════════════════════════════════════════════
# 评分标准管理
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/scoring-criteria")
async def get_scoring_criteria(
    award_type: Optional[str] = Query(None, description="按奖项类型筛选"),
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取评分标准列表."""
    conditions = []
    if award_type:
        conditions.append(RecognitionScoringCriteria.award_type == award_type)

    result = await db.execute(
        select(RecognitionScoringCriteria)
        .where(*conditions)
        .order_by(RecognitionScoringCriteria.award_type, RecognitionScoringCriteria.sort_order)
    )
    criteria = result.scalars().all()

    return {
        "code": 0,
        "data": [
            {
                "id": c.id, "award_type": c.award_type,
                "item_name": c.item_name, "item_key": c.item_key,
                "item_type": c.item_type, "item_placeholder": c.item_placeholder,
                "item_help_text": c.item_help_text, "allow_multiple": c.allow_multiple,
                "points_per_unit": c.points_per_unit, "unit_description": c.unit_description,
                "max_points": c.max_points, "sort_order": c.sort_order,
                "is_active": c.is_active, "created_at": c.created_at, "updated_at": c.updated_at,
            }
            for c in criteria
        ],
    }


@router.post("/scoring-criteria")
async def create_scoring_criteria(
    body: ScoringCriteriaCreate,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """新增评分标准项."""
    if body.award_type not in QUARTERLY_AWARD_TYPES:
        return {"code": 1, "message": f"无效的奖项类型: {body.award_type}"}

    criteria = RecognitionScoringCriteria(
        award_type=body.award_type,
        item_name=body.item_name,
        item_key=body.item_key,
        item_type=body.item_type,
        item_placeholder=body.item_placeholder,
        item_help_text=body.item_help_text,
        allow_multiple=body.allow_multiple,
        points_per_unit=body.points_per_unit,
        unit_description=body.unit_description,
        max_points=body.max_points,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    db.add(criteria)
    await db.flush()
    await db.refresh(criteria)

    return {"code": 0, "data": {"id": criteria.id, "message": "评分标准创建成功"}}


@router.put("/scoring-criteria/{criteria_id}")
async def update_scoring_criteria(
    criteria_id: int,
    body: ScoringCriteriaUpdate,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """修改评分标准项."""
    result = await db.execute(
        select(RecognitionScoringCriteria).where(RecognitionScoringCriteria.id == criteria_id)
    )
    criteria = result.scalar_one_or_none()
    if not criteria:
        return {"code": 1, "message": "评分标准不存在"}

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(criteria, key, value)

    await db.flush()
    return {"code": 0, "data": {"message": "评分标准更新成功"}}


@router.delete("/scoring-criteria/{criteria_id}")
async def delete_scoring_criteria(
    criteria_id: int,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """删除评分标准项."""
    result = await db.execute(
        select(RecognitionScoringCriteria).where(RecognitionScoringCriteria.id == criteria_id)
    )
    criteria = result.scalar_one_or_none()
    if not criteria:
        return {"code": 1, "message": "评分标准不存在"}

    await db.delete(criteria)
    await db.flush()
    return {"code": 0, "data": {"message": "评分标准删除成功"}}


# ═══════════════════════════════════════════════════════════════════════════
# 用户管理
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/users")
async def get_recognition_users(
    role: Optional[str] = Query(None, description="按角色筛选"),
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """获取认可计划用户列表."""
    conditions = [User.recognition_role != "distributor"]
    if role:
        conditions.append(User.recognition_role == role)

    result = await db.execute(
        select(User).where(*conditions).order_by(User.recognition_score.desc())
    )
    users = result.scalars().all()

    return {
        "code": 0,
        "data": [
            {
                "id": u.id,
                "real_name": u.real_name,
                "company": u.company,
                "recognition_role": u.recognition_role,
                "recognition_score": u.recognition_score or 0,
            }
            for u in users
        ],
    }


@router.put("/users/{target_user_id}/role")
async def update_user_role(
    target_user_id: str,
    body: RoleUpdateRequest,
    user_id: str = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
):
    """修改用户角色."""
    if body.recognition_role not in VALID_ROLES:
        return {"code": 1, "message": f"无效的角色: {body.recognition_role}"}

    result = await db.execute(select(User).where(User.id == target_user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"code": 1, "message": "用户不存在"}

    user.recognition_role = body.recognition_role
    await db.flush()
    return {"code": 0, "data": {"message": "角色更新成功"}}