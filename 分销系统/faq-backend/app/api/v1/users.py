from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ensure_same_user, get_current_user_id
from app.db.session import get_db
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.energy import build_energy_summary, fetch_user_redemptions
from app.services.ranking import (
    build_weekly_competition_rank_map,
    fetch_weekly_rank_entries,
    get_display_name,
    is_ranking_excluded_user,
)
from app.services.storage import StorageService
from app.utils.province import normalize_province_name

router = APIRouter(tags=["用户"])


@router.get("/user/rank")
async def get_user_rank(
    request: Request,
    user_id: str | None = None,
    scope: str = Query("total", pattern="^(total|company)$"),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    base = str(request.base_url).rstrip("/")
    user_id = ensure_same_user(current_user_id, user_id)

    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        return {"code": 0, "data": None}

    company_filter = None
    if scope == "company":
        current_company = (user.company or "").strip()
        if current_company:
            company_filter = current_company
        else:
            company_filter = "__no_company__"

    entries = await fetch_weekly_rank_entries(db, company=company_filter)
    rank_map = build_weekly_competition_rank_map(entries)
    ranking_excluded = is_ranking_excluded_user(user)
    rank = "-" if ranking_excluded else rank_map.get(user.id, "-")
    user_entry = next((entry for entry in entries if entry.user.id == user.id), None)
    user_weekly_correct_count = user_entry.weekly_correct_count if user_entry else 0
    user_weekly_time_spent = user_entry.weekly_time_spent if user_entry else 0
    user_weekly_total_count = user_entry.weekly_total_count if user_entry else 0

    if ranking_excluded:
        stats_result = await db.execute(
            select(
                func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)),  # noqa: E712
                func.sum(func.coalesce(AnswerRecord.time_spent, 0)),
                func.count(AnswerRecord.id),
            )
            .where(AnswerRecord.user_id == user.id)
            .where(AnswerRecord.source == "daily")
        )
        correct_count, time_spent, total_count = stats_result.one()
        user_weekly_correct_count = int(correct_count or 0)
        user_weekly_time_spent = int(time_spent or 0)
        user_weekly_total_count = int(total_count or 0)

    avatar = StorageService.build_avatar_access_url(user.avatar_url, base)
    redemptions = await fetch_user_redemptions(db, user.id)
    energy_summary = build_energy_summary(user.total_score, redemptions)

    return {
        "code": 0,
        "data": {
            "user_id": user.id,
            "nickname": get_display_name(user),
            "avatar": avatar,
            "total_score": user.total_score or 0,
            "correct_count": user.correct_count or 0,
            "total_count": user.total_count or 0,
            "weekly_correct_count": user_weekly_correct_count,
            "weekly_time_spent": user_weekly_time_spent,
            "weekly_total_count": user_weekly_total_count,
            "rank": rank,
            "ranking_excluded": ranking_excluded,
            "real_name": user.real_name or "",
            "province": user.province or "",
            "company": user.company or "",
            "redeemed_energy": energy_summary["redeemed_energy"],
            "available_energy": energy_summary["available_energy"],
            "redemption_count": energy_summary["redemption_count"],
            "recognition_role": user.recognition_role or "distributor",
            "recognition_score": user.recognition_score or 0,
        },
    }


class ProfileUpdate(BaseModel):
    user_id: str
    nickname: str
    avatar: str = ""
    real_name: str = ""
    province: str = ""
    company: str = ""


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


@router.post("/user/profile")
async def update_profile(
    request: Request,
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user_id = ensure_same_user(current_user_id, body.user_id)

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return {"code": 1, "message": "用户不存在"}

    submitted_real_name = _normalize_text(body.real_name)
    submitted_province = normalize_province_name(body.province)
    submitted_company = _normalize_text(body.company)

    expected_real_name = _normalize_text(user.real_name)
    expected_province = normalize_province_name(user.province)
    expected_company = _normalize_text(user.company)

    if not (expected_real_name and expected_province and expected_company):
        return {
            "code": 1004,
            "message": "认证资料不完整",
            "detail": "当前白名单资料不完整，请联系管理员补全姓名、省份和公司信息后再认证。",
        }

    if (
        submitted_real_name != expected_real_name or
        submitted_province != expected_province or
        submitted_company != expected_company
    ):
        return {
            "code": 1003,
            "message": "资料填写错误，不予通过",
            "detail": "姓名、省份或公司与白名单资料不一致，请确认后重新填写。",
        }

    user.nickname = body.nickname
    user.avatar_url = StorageService.normalize_avatar_reference(body.avatar)
    user.real_name = expected_real_name
    user.province = expected_province
    user.company = expected_company
    user.profile_verified = True
    avatar_reference = StorageService.normalize_avatar_reference(user.avatar_url)
    avatar = StorageService.build_avatar_access_url(user.avatar_url, str(request.base_url).rstrip("/"))
    return {
        "code": 0,
        "message": "更新成功",
        "data": {
            "id": user.id,
            "nickname": user.nickname or "",
            "avatar_url": avatar,
            "avatar_file_id": avatar_reference,
            "real_name": user.real_name or "",
            "province": user.province or "",
            "company": user.company or "",
            "profile_verified": bool(user.profile_verified),
        },
    }
