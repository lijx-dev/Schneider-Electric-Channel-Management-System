"""Admin auth, account management, rankings, and participation reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import BaseModel, Field
from sqlalchemy import case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.energy import EnergyRedemptionRecord, EnergyTransaction
from app.models.lottery import LotteryWinner
from app.models.monthly import MonthlyRankSnapshot
from app.models.record import AnswerRecord
from app.models.user import User
from app.services.admin_auth import create_admin_token, verify_admin_token
from app.services.energy import VALID_REDEMPTION_STATUSES
from app.services.monthly_leaderboard import (
    fetch_live_month_entries,
    fetch_month_snapshots,
    validate_month_key,
)
from app.services.ranking import (
    fetch_weekly_rank_entries,
    get_display_name,
    is_ranking_excluded_user,
)
from app.utils.province import normalize_province_name

router = APIRouter(prefix="/admin", tags=["admin"])
bearer_scheme = HTTPBearer(auto_error=False)

ADMIN_SPECIAL_PROVINCE = "施耐德电气"
ADMIN_INTERNAL_ROLE = "施耐德内部"
VALID_ADMIN_PROVINCES = {
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
}


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AdminUserPayload(BaseModel):
    phone: str = Field(default="", max_length=20)
    login_username: str = Field(default="", max_length=80)
    login_password: str = Field(default="", max_length=128)
    real_name: str = Field(default="", max_length=50)
    nickname: str = Field(default="", max_length=100)
    province: str = Field(default="", max_length=20)
    company: str = Field(default="", max_length=100)
    job_role: str = Field(default="", max_length=20)
    profile_verified: bool = False


class AdminUserUpdatePayload(BaseModel):
    phone: str = Field(default="", max_length=20)
    login_username: str = Field(default="", max_length=80)
    login_password: str = Field(default="", max_length=128)
    real_name: str = Field(default="", max_length=50)
    nickname: str = Field(default="", max_length=100)
    province: str = Field(default="", max_length=20)
    company: str = Field(default="", max_length=100)
    job_role: str = Field(default="", max_length=20)
    profile_verified: bool = False


class AdminRedemptionStatusPayload(BaseModel):
    status: str = Field(min_length=1, max_length=20)


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")

    admin_username = verify_admin_token(credentials.credentials)
    if not admin_username:
        raise HTTPException(status_code=401, detail="Could not validate admin credentials")
    return admin_username


def _clean(value: object) -> str:
    return str(value or "").strip()


def _normalize_admin_province(value: object, company: object = "") -> str:
    province = normalize_province_name(_clean(value))
    company_text = _clean(company)
    if ADMIN_SPECIAL_PROVINCE in province or ADMIN_SPECIAL_PROVINCE in company_text:
        return ADMIN_SPECIAL_PROVINCE
    if province in VALID_ADMIN_PROVINCES:
        return province
    return ""


async def _matching_raw_provinces(db: AsyncSession, province: str) -> list[str]:
    normalized = _normalize_admin_province(province)
    if not normalized:
        return []

    result = await db.execute(
        select(User.province, User.company)
        .where(User.province.isnot(None))
        .where(User.province != "")
    )
    matches = {
        raw_province
        for raw_province, company in result.all()
        if raw_province and _normalize_admin_province(raw_province, company) == normalized
    }
    return sorted(matches)


async def _apply_province_filter(
    stmt,
    db: AsyncSession,
    province: str,
):
    normalized = _normalize_admin_province(province)
    if not normalized:
        return stmt

    raw_provinces = await _matching_raw_provinces(db, normalized)
    if normalized == ADMIN_SPECIAL_PROVINCE:
        filters = [User.company.like(f"%{ADMIN_SPECIAL_PROVINCE}%")]
        if raw_provinces:
            filters.append(User.province.in_(raw_provinces))
        return stmt.where(or_(*filters))

    if not raw_provinces:
        return stmt.where(User.province == "__no_matching_province__")
    return stmt.where(User.province.in_(raw_provinces))


def _normalize_role(value: str) -> str:
    return _clean(value)[:20]


def _is_schneider_user(user: User) -> bool:
    return _normalize_admin_province(user.province, user.company) == ADMIN_SPECIAL_PROVINCE


def _effective_job_role(user: User) -> str:
    if _is_schneider_user(user):
        return ADMIN_INTERNAL_ROLE
    return getattr(user, "job_role", None) or "other"


def _normalize_user_role(value: str, province: object = "", company: object = "") -> str:
    if _normalize_admin_province(province, company) == ADMIN_SPECIAL_PROVINCE:
        return ADMIN_INTERNAL_ROLE
    return _normalize_role(value)


def _normalize_roles(value: str) -> list[str]:
    return [role for role in (_normalize_role(item) for item in _clean(value).split(",")) if role]


def _role_label(role: str | None) -> str:
    return _clean(role) or "未填写"


def _user_keyword_condition(keyword: str):
    return or_(
        User.real_name.like(keyword),
        User.nickname.like(keyword),
        User.phone.like(keyword),
        User.company.like(keyword),
    )


def _matches_keyword(values: list[object], query: str) -> bool:
    text = _clean(query).lower()
    if not text:
        return True
    return any(text in _clean(value).lower() for value in values)


def _normalize_order_status(value: str) -> str:
    status = _clean(value).lower()
    if status not in VALID_REDEMPTION_STATUSES:
        raise HTTPException(status_code=400, detail="订单状态只能是 pending、approved、delivered 或 cancelled")
    return status


def _order_status_label(status: str | None) -> str:
    return {
        "pending": "待处理",
        "approved": "已确认",
        "delivered": "已发货",
        "cancelled": "已取消",
    }.get(status or "", "待处理")


def _parse_date_start(value: str) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式必须是 YYYY-MM-DD") from exc


def _week_bounds_from_date(value: str) -> tuple[str, str]:
    try:
        date_value = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式必须是 YYYY-MM-DD") from exc
    week_start = date_value - timedelta(days=date_value.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start.isoformat(), week_end.isoformat()


def _serialize_admin_redemption(record: EnergyRedemptionRecord, user: User) -> dict[str, object]:
    status = record.status or "pending"
    return {
        "id": record.id,
        "user_id": user.id,
        "user_name": get_display_name(user),
        "real_name": user.real_name or "",
        "phone": user.phone or "",
        "province": _normalize_admin_province(user.province, user.company) or user.province or "",
        "company": user.company or "",
        "job_role": _effective_job_role(user),
        "job_role_label": _role_label(_effective_job_role(user)),
        "client_record_id": record.client_record_id,
        "batch_id": record.batch_id or "",
        "product_id": record.product_id,
        "product_name": record.product_name,
        "quantity": record.quantity or 1,
        "unit_cost": record.unit_cost or record.cost or 0,
        "total_cost": record.total_cost or (record.unit_cost or record.cost or 0) * (record.quantity or 1),
        "status": status,
        "status_label": _order_status_label(status),
        "receiver_name": record.receiver_name or "",
        "receiver_phone": record.receiver_phone or "",
        "receiver_region": record.receiver_region or "",
        "receiver_address": record.receiver_address or "",
        "receiver_note": record.receiver_note or "",
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }


def _append_xlsx_rows(sheet, headers: list[str], rows: list[list[object]]) -> None:
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    sheet.auto_filter.ref = sheet.dimensions
    sheet.freeze_panes = "A2"
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 10), 36)


def serialize_admin_user(user: User) -> dict[str, object]:
    role = _effective_job_role(user)
    return {
        "id": user.id,
        "phone": user.phone or "",
        "login_username": user.login_username or "",
        "real_name": user.real_name or "",
        "nickname": user.nickname or "",
        "province": _normalize_admin_province(user.province, user.company) or user.province or "",
        "company": user.company or "",
        "job_role": role,
        "job_role_label": _role_label(role),
        "profile_verified": bool(user.profile_verified),
        "total_score": user.total_score or 0,
        "correct_count": user.correct_count or 0,
        "total_count": user.total_count or 0,
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


async def _ensure_unique_user_fields(
    db: AsyncSession,
    *,
    phone: str,
    login_username: str,
    exclude_user_id: str | None = None,
) -> None:
    conditions = []
    if phone:
        conditions.append(User.phone == phone)
    if login_username:
        conditions.append(User.login_username == login_username)
    if not conditions:
        return

    stmt = select(User).where(or_(*conditions))
    if exclude_user_id:
        stmt = stmt.where(User.id != exclude_user_id)

    existing = await db.scalar(stmt)
    if not existing:
        return
    if phone and existing.phone == phone:
        raise HTTPException(status_code=400, detail="手机号已存在")
    raise HTTPException(status_code=400, detail="登录账号已存在")


async def _get_user_or_404(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="账户不存在")
    return user


@router.post("/auth/login")
async def admin_login(payload: AdminLoginRequest) -> dict[str, object]:
    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="管理员账号未配置")

    if payload.username != settings.ADMIN_USERNAME or payload.password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="账号或密码错误")

    return {
        "code": 0,
        "data": {
            "token": create_admin_token(payload.username),
            "username": payload.username,
        },
    }


@router.get("/companies")
async def list_admin_companies(
    province: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    stmt = (
        select(User.company)
        .where(User.company.isnot(None))
        .where(User.company != "")
        .group_by(User.company)
        .order_by(User.company.asc())
    )
    if _clean(province):
        stmt = await _apply_province_filter(stmt, db, province)

    result = await db.execute(stmt)
    companies = [_clean(company) for company in result.scalars().all() if _clean(company)]
    return {"code": 0, "data": {"items": companies}}


@router.get("/provinces")
async def list_admin_provinces(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    result = await db.execute(
        select(User.province, User.company)
        .where(
            or_(
                User.province.isnot(None),
                User.company.isnot(None),
            )
        )
    )
    provinces = sorted(
        {
            normalized
            for raw_province, company in result.all()
            for normalized in [_normalize_admin_province(raw_province, company)]
            if normalized
        }
    )
    if ADMIN_SPECIAL_PROVINCE in provinces:
        provinces = [ADMIN_SPECIAL_PROVINCE] + [
            province for province in provinces if province != ADMIN_SPECIAL_PROVINCE
        ]
    return {"code": 0, "data": {"items": provinces}}


@router.get("/job-roles")
async def list_admin_job_roles(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    result = await db.execute(
        select(User.job_role)
        .where(User.job_role.isnot(None))
        .where(User.job_role != "")
        .group_by(User.job_role)
        .order_by(User.job_role.asc())
    )
    roles = [_clean(role) for role in result.scalars().all() if _clean(role)]
    return {"code": 0, "data": {"items": roles}}


@router.get("/users")
async def list_admin_users(
    province: str = "",
    company: str = "",
    role: str = "",
    q: str = "",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    filters = []
    if _clean(company):
        filters.append(User.company == _clean(company))
    if _clean(role):
        roles = _normalize_roles(role)
        if roles:
            filters.append(User.job_role.in_(roles))
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.login_username.like(keyword),
                User.company.like(keyword),
            )
        )

    total_stmt = select(func.count(User.id))
    list_stmt = select(User).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
    if _clean(province):
        total_stmt = await _apply_province_filter(total_stmt, db, province)
        list_stmt = await _apply_province_filter(list_stmt, db, province)
    if filters:
        total_stmt = total_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int(await db.scalar(total_stmt) or 0)
    result = await db.execute(list_stmt)
    return {
        "code": 0,
        "data": {
            "items": [serialize_admin_user(user) for user in result.scalars().all()],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/users/export")
async def export_admin_users(
    province: str = "",
    company: str = "",
    role: str = "",
    q: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    filters = []
    if _clean(company):
        filters.append(User.company == _clean(company))
    if _clean(role):
        roles = _normalize_roles(role)
        if roles:
            filters.append(User.job_role.in_(roles))
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.login_username.like(keyword),
                User.company.like(keyword),
            )
        )

    stmt = select(User).order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    if _clean(province):
        stmt = await _apply_province_filter(stmt, db, province)
    if filters:
        stmt = stmt.where(*filters)

    result = await db.execute(stmt)
    rows = [serialize_admin_user(user) for user in result.scalars().all()]

    headers = ["姓名", "昵称", "手机号", "省份", "公司", "岗位", "资料认证", "能量值", "答对数", "答题数", "创建时间"]
    xlsx_rows = []
    for item in rows:
        xlsx_rows.append([
            item["real_name"],
            item["nickname"],
            item["phone"],
            item["province"],
            item["company"],
            item["job_role_label"],
            "已认证" if item["profile_verified"] else "未认证",
            item["total_score"],
            item["correct_count"],
            item["total_count"],
            item["created_at"],
        ])

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "账户名单"
    _append_xlsx_rows(sheet, headers, xlsx_rows)
    sheet.auto_filter.ref = f"D1:G{max(1, sheet.max_row)}"

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"账户名单-{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/energy-stats")
async def list_admin_energy_stats(
    province: str = "",
    company: str = "",
    q: str = "",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    filters = []
    if _clean(company):
        filters.append(User.company == _clean(company))
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.company.like(keyword),
            )
        )

    total_stmt = select(func.count(User.id))
    list_stmt = (
        select(User)
        .order_by(User.total_score.desc(), User.correct_count.desc(), User.total_count.desc(), User.real_name.asc(), User.id.asc())
        .offset(offset)
        .limit(limit)
    )
    if _clean(province):
        total_stmt = await _apply_province_filter(total_stmt, db, province)
        list_stmt = await _apply_province_filter(list_stmt, db, province)
    if filters:
        total_stmt = total_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int(await db.scalar(total_stmt) or 0)
    result = await db.execute(list_stmt)
    items = []
    for user in result.scalars().all():
        role = _effective_job_role(user)
        items.append(
            {
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "phone": user.phone or "",
                "province": _normalize_admin_province(user.province, user.company) or user.province or "",
                "company": user.company or "",
                "job_role": role,
                "job_role_label": _role_label(role),
                "total_score": user.total_score or 0,
                "correct_count": user.correct_count or 0,
                "total_count": user.total_count or 0,
            }
        )

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "score_note": "total_score is cumulative earned energy and does not subtract redeemed energy.",
        },
    }


@router.get("/energy-stats/export")
async def export_admin_energy_stats(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    stmt = select(User).order_by(
        User.total_score.desc(),
        User.correct_count.desc(),
        User.total_count.desc(),
        User.real_name.asc(),
        User.id.asc(),
    )
    result = await db.execute(stmt)
    users = [user for user in result.scalars().all() if not _is_schneider_user(user)]

    headers = ["排名", "学员", "省份", "公司", "岗位", "手机号", "已获得总能量", "答对数", "答题数"]
    rows = [
        [
            index,
            get_display_name(user),
            _normalize_admin_province(user.province, user.company) or user.province or "",
            user.company or "",
            _role_label(_effective_job_role(user)),
            user.phone or "",
            user.total_score or 0,
            user.correct_count or 0,
            user.total_count or 0,
        ]
        for index, user in enumerate(users, start=1)
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "学员能量统计"
    _append_xlsx_rows(sheet, headers, rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"学员能量统计-{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/reward-records")
async def list_admin_reward_records(
    month: str = Query(default=""),
    reward_type: str = Query(default="all"),
    q: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    month_key = validate_month_key(month or datetime.now().strftime("%Y-%m"))
    allowed_types = {"monthly_rank_reward", "lottery_reward"}
    selected_types = allowed_types if reward_type == "all" else {reward_type}
    selected_types = selected_types & allowed_types
    if not selected_types:
        selected_types = allowed_types

    filters = [
        EnergyTransaction.related_month == month_key,
        EnergyTransaction.type.in_(sorted(selected_types)),
    ]
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.company.like(keyword),
                EnergyTransaction.title.like(keyword),
                EnergyTransaction.description.like(keyword),
            )
        )

    result = await db.execute(
        select(EnergyTransaction, User)
        .join(User, User.id == EnergyTransaction.user_id)
        .where(*filters)
        .order_by(
            EnergyTransaction.type.asc(),
            EnergyTransaction.amount.desc(),
            EnergyTransaction.created_at.desc(),
            EnergyTransaction.id.desc(),
        )
    )
    rows = result.all()
    user_ids = [user.id for _, user in rows]

    snapshot_by_user: dict[str, MonthlyRankSnapshot] = {}
    lottery_by_user: dict[str, LotteryWinner] = {}
    if user_ids:
        snapshot_result = await db.execute(
            select(MonthlyRankSnapshot).where(
                MonthlyRankSnapshot.month_key == month_key,
                MonthlyRankSnapshot.user_id.in_(user_ids),
            )
        )
        snapshot_by_user = {item.user_id: item for item in snapshot_result.scalars().all()}

        lottery_result = await db.execute(
            select(LotteryWinner).where(
                LotteryWinner.month_key == month_key,
                LotteryWinner.user_id.in_(user_ids),
            )
        )
        lottery_by_user = {item.user_id: item for item in lottery_result.scalars().all()}

    items = []
    for transaction, user in rows:
        snapshot = snapshot_by_user.get(user.id)
        lottery = lottery_by_user.get(user.id)
        is_lottery = transaction.type == "lottery_reward"
        items.append(
            {
                "id": transaction.id,
                "month": month_key,
                "type": transaction.type,
                "type_label": "月初抽奖" if is_lottery else "月底奖励",
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "phone": user.phone or "",
                "province": _normalize_admin_province(user.province, user.company) or user.province or "",
                "company": user.company or "",
                "job_role": _effective_job_role(user),
                "job_role_label": _role_label(_effective_job_role(user)),
                "amount": transaction.amount or 0,
                "title": transaction.title or "",
                "description": transaction.description or "",
                "status": transaction.status or "",
                "rank": snapshot.rank if snapshot else None,
                "monthly_correct_count": snapshot.monthly_correct_count if snapshot else None,
                "monthly_total_count": snapshot.monthly_total_count if snapshot else None,
                "prize_name": lottery.prize_name if lottery else "",
                "prize_level": lottery.prize_level if lottery else "",
                "winner_order": lottery.winner_order if lottery else None,
                "created_at": transaction.created_at.isoformat() if transaction.created_at else "",
            }
        )

    monthly_count = sum(1 for item in items if item["type"] == "monthly_rank_reward")
    lottery_count = sum(1 for item in items if item["type"] == "lottery_reward")
    return {
        "code": 0,
        "data": {
            "month": month_key,
            "items": items,
            "total": len(items),
            "monthly_count": monthly_count,
            "lottery_count": lottery_count,
            "total_amount": sum(int(item["amount"] or 0) for item in items),
            "monthly_amount": sum(int(item["amount"] or 0) for item in items if item["type"] == "monthly_rank_reward"),
            "lottery_amount": sum(int(item["amount"] or 0) for item in items if item["type"] == "lottery_reward"),
        },
    }


@router.get("/reward-records/export")
async def export_admin_reward_records(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    reward_types = ("monthly_rank_reward", "lottery_reward")
    result = await db.execute(
        select(EnergyTransaction, User)
        .join(User, User.id == EnergyTransaction.user_id)
        .where(EnergyTransaction.type.in_(reward_types))
        .order_by(
            EnergyTransaction.related_month.desc(),
            EnergyTransaction.type.asc(),
            EnergyTransaction.amount.desc(),
            EnergyTransaction.created_at.desc(),
            EnergyTransaction.id.desc(),
        )
    )
    records = result.all()

    user_ids = {user.id for _, user in records}
    month_keys = {transaction.related_month for transaction, _ in records if transaction.related_month}
    snapshots_by_key: dict[tuple[str, str], MonthlyRankSnapshot] = {}
    if user_ids and month_keys:
        snapshot_result = await db.execute(
            select(MonthlyRankSnapshot).where(
                MonthlyRankSnapshot.month_key.in_(month_keys),
                MonthlyRankSnapshot.user_id.in_(user_ids),
            )
        )
        snapshots_by_key = {
            (snapshot.month_key, snapshot.user_id): snapshot
            for snapshot in snapshot_result.scalars().all()
        }

    lottery_by_transaction_id: dict[int, LotteryWinner] = {}
    lottery_by_key: dict[tuple[str, str], LotteryWinner] = {}
    if user_ids and month_keys:
        lottery_result = await db.execute(
            select(LotteryWinner).where(
                LotteryWinner.month_key.in_(month_keys),
                LotteryWinner.user_id.in_(user_ids),
            )
        )
        lottery_winners = lottery_result.scalars().all()
        lottery_by_transaction_id = {
            winner.energy_transaction_id: winner
            for winner in lottery_winners
            if winner.energy_transaction_id is not None
        }
        lottery_by_key = {
            (winner.month_key, winner.user_id): winner
            for winner in lottery_winners
        }

    headers = [
        "月份",
        "发放时间",
        "用户",
        "手机号",
        "公司",
        "岗位",
        "奖励类型",
        "名次/奖项",
        "奖励能量",
        "标题",
        "说明",
        "状态",
    ]
    rows: list[list[object]] = []
    for transaction, user in records:
        month_key = transaction.related_month or ""
        is_lottery = transaction.type == "lottery_reward"
        snapshot = snapshots_by_key.get((month_key, user.id))
        lottery = lottery_by_transaction_id.get(transaction.id) or lottery_by_key.get((month_key, user.id))
        rank_or_prize = ""
        if is_lottery and lottery:
            rank_or_prize = lottery.prize_name or lottery.prize_level or ""
        elif snapshot and snapshot.rank:
            rank_or_prize = f"第{snapshot.rank}名"
        created_at = transaction.created_at.strftime("%Y-%m-%d %H:%M:%S") if transaction.created_at else ""
        rows.append(
            [
                month_key,
                created_at,
                get_display_name(user),
                user.phone or "",
                user.company or "",
                _role_label(_effective_job_role(user)),
                "月初抽奖" if is_lottery else "月底奖励",
                rank_or_prize,
                transaction.amount or 0,
                transaction.title or "",
                transaction.description or "",
                transaction.status or "",
            ]
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "奖励记录"
    _append_xlsx_rows(sheet, headers, rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"奖励记录-{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/users")
async def create_admin_user(
    payload: AdminUserPayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    phone = _clean(payload.phone)
    login_username = _clean(payload.login_username)
    await _ensure_unique_user_fields(db, phone=phone, login_username=login_username)

    user = User(
        openid=f"admin:{uuid.uuid4()}",
        phone=phone or None,
        login_username=login_username or None,
        login_password=_clean(payload.login_password) or None,
        real_name=_clean(payload.real_name) or None,
        nickname=_clean(payload.nickname) or _clean(payload.real_name) or None,
        province=_clean(payload.province) or None,
        company=_clean(payload.company) or None,
        job_role=_normalize_user_role(payload.job_role, payload.province, payload.company),
        profile_verified=bool(payload.profile_verified),
        total_score=0,
        correct_count=0,
        total_count=0,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return {"code": 0, "data": serialize_admin_user(user)}


@router.put("/users/{user_id}")
async def update_admin_user(
    user_id: str,
    payload: AdminUserUpdatePayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    user = await _get_user_or_404(db, user_id)
    phone = _clean(payload.phone)
    login_username = _clean(payload.login_username)
    await _ensure_unique_user_fields(db, phone=phone, login_username=login_username, exclude_user_id=user.id)

    user.phone = phone or None
    user.login_username = login_username or None
    if _clean(payload.login_password):
        user.login_password = _clean(payload.login_password)
    user.real_name = _clean(payload.real_name) or None
    user.nickname = _clean(payload.nickname) or _clean(payload.real_name) or None
    user.province = _clean(payload.province) or None
    user.company = _clean(payload.company) or None
    user.job_role = _normalize_user_role(payload.job_role, payload.province, payload.company)
    user.profile_verified = bool(payload.profile_verified)

    await db.flush()
    await db.refresh(user)
    return {"code": 0, "data": serialize_admin_user(user)}


@router.delete("/users/{user_id}")
async def delete_admin_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    user = await _get_user_or_404(db, user_id)
    await db.delete(user)
    await db.flush()
    return {"code": 0, "data": {"deleted": True, "user_id": user_id}}


@router.get("/company-leaderboard")
async def get_admin_company_leaderboard(
    company: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    clean_company = _clean(company)
    entries = (await fetch_weekly_rank_entries(db, company=clean_company))[:limit]
    rows = []
    previous_rank_key = None
    current_rank = 0
    for index, entry in enumerate(entries, start=1):
        user = entry.user
        rank_key = (entry.weekly_correct_count, entry.weekly_time_spent)
        if previous_rank_key is None or rank_key != previous_rank_key:
            current_rank = index
            previous_rank_key = rank_key
        rows.append(
            {
                "rank": current_rank,
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "company": user.company or "",
                "job_role": _effective_job_role(user),
                "job_role_label": _role_label(_effective_job_role(user)),
                "weekly_correct_count": entry.weekly_correct_count,
                "weekly_total_count": entry.weekly_total_count,
                "weekly_time_spent": entry.weekly_time_spent,
                "total_score": user.total_score or 0,
            }
        )
    return {"code": 0, "data": {"company": clean_company, "items": rows}}


@router.get("/global-leaderboard")
async def get_admin_global_leaderboard(
    scope: str = Query("total", pattern="^(total|month)$"),
    month: str = "",
    q: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    offset = (page - 1) * page_size
    rows: list[dict[str, object]] = []
    total = 0

    if scope == "month":
        try:
            month_key = validate_month_key(month or datetime.now().strftime("%Y-%m"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        snapshots = await fetch_month_snapshots(db, month_key)
        if snapshots:
            user_map: dict[str, User] = {}
            if _clean(q):
                user_ids = [snapshot.user_id for snapshot in snapshots]
                user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
                user_map = {user.id: user for user in user_result.scalars().all()}
                snapshots = [
                    snapshot
                    for snapshot in snapshots
                    if _matches_keyword(
                        [
                            snapshot.real_name,
                            snapshot.nickname,
                            snapshot.company,
                            user_map.get(snapshot.user_id).phone if user_map.get(snapshot.user_id) else "",
                        ],
                        q,
                    )
                ]
            total = len(snapshots)
            for snapshot in snapshots[offset : offset + page_size]:
                rows.append(
                    {
                        "rank": snapshot.rank,
                        "user_id": snapshot.user_id,
                        "name": snapshot.real_name or snapshot.nickname or "学员",
                        "real_name": snapshot.real_name or "",
                        "company": snapshot.company or "",
                        "job_role": "",
                        "job_role_label": _role_label(""),
                        "monthly_correct_count": snapshot.monthly_correct_count,
                        "monthly_total_count": snapshot.monthly_total_count,
                        "monthly_time_spent": snapshot.monthly_time_spent,
                        "total_score": 0,
                    }
                )
        else:
            entries = await fetch_live_month_entries(db, month_key)
            if _clean(q):
                entries = [
                    entry
                    for entry in entries
                    if _matches_keyword(
                        [entry.user.real_name, entry.user.nickname, entry.user.phone, entry.user.company],
                        q,
                    )
                ]
            total = len(entries)
            for entry in entries[offset : offset + page_size]:
                user = entry.user
                rows.append(
                    {
                        "rank": entry.rank,
                        "user_id": user.id,
                        "name": get_display_name(user),
                        "real_name": user.real_name or "",
                        "company": user.company or "",
                        "job_role": _effective_job_role(user),
                        "job_role_label": _role_label(_effective_job_role(user)),
                        "monthly_correct_count": entry.monthly_correct_count,
                        "monthly_total_count": entry.monthly_total_count,
                        "monthly_time_spent": entry.monthly_time_spent,
                        "total_score": user.total_score or 0,
                    }
                )
        return {
            "code": 0,
            "data": {
                "scope": "month",
                "month": month_key,
                "page": page,
                "page_size": page_size,
                "total": total,
                "items": rows,
            },
        }

    leaderboard_rows = [
        {
            "user": entry.user,
            "correct_count": entry.weekly_correct_count,
            "total_count": entry.weekly_total_count,
            "total_time_spent": entry.weekly_time_spent,
            "total_score": entry.user.total_score or 0,
        }
        for entry in await fetch_weekly_rank_entries(db)
    ]
    previous_rank_key = None
    current_rank = 0
    rank_map: dict[str, int] = {}
    for index, item in enumerate(leaderboard_rows, start=1):
        user = item["user"]
        rank_key = (
            int(item["correct_count"] or 0),
            int(item["total_time_spent"] or 0),
            int(item["total_score"] or 0),
        )
        if previous_rank_key is None or rank_key != previous_rank_key:
            current_rank = index
            previous_rank_key = rank_key
        rank_map[user.id] = current_rank

    if _clean(q):
        leaderboard_rows = [
            item
            for item in leaderboard_rows
            if _matches_keyword(
                [
                    item["user"].real_name,
                    item["user"].nickname,
                    item["user"].phone,
                    item["user"].company,
                ],
                q,
            )
        ]
    total = len(leaderboard_rows)

    for item in leaderboard_rows[offset : offset + page_size]:
        user = item["user"]
        rows.append(
            {
                "rank": rank_map[user.id],
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "company": user.company or "",
                "job_role": _effective_job_role(user),
                "job_role_label": _role_label(_effective_job_role(user)),
                "correct_count": int(item["correct_count"] or 0),
                "total_count": int(item["total_count"] or 0),
                "total_time_spent": int(item["total_time_spent"] or 0),
                "weekly_correct_count": int(item["correct_count"] or 0),
                "weekly_total_count": int(item["total_count"] or 0),
                "weekly_time_spent": int(item["total_time_spent"] or 0),
                "total_score": int(item["total_score"] or 0),
            }
        )
    return {
        "code": 0,
        "data": {
            "scope": "total",
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": rows,
        },
    }


from app.services.lottery import run_monthly_lottery, fetch_lottery_draw
from app.services.monthly_leaderboard import settle_monthly_rewards, validate_month_key, get_month_reward_amount
from datetime import date, datetime, timezone, timedelta


class ManualTriggerLotteryRequest(BaseModel):
    month: str = Field(default="", description="指定抽奖月份 YYYY-MM，默认取当月")


@router.post("/lottery/trigger-monthly")
async def admin_trigger_monthly_lottery(
    payload: ManualTriggerLotteryRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    """管理员手动触发当月抽奖。已当月执行过则直接返回提示不可重复执行，防止重复发放能量。"""
    today = datetime.now(timezone(timedelta(hours=8)))
    month_key = validate_month_key(payload.month) if payload.month else today.strftime("%Y-%m")

    existing = await fetch_lottery_draw(db, month_key)
    if existing and existing.status == "completed":
        return {
            "code": 0,
            "data": {
                "month": month_key,
                "already_drawn": True,
                "eligible_count": existing.eligible_count or 0,
                "winner_count": existing.winner_count or 0,
                "total_energy": 0,
                "message": f"{month_key}月份的抽奖已经执行过，不可重复执行"
            }
        }

    result = await run_monthly_lottery(db, month_key=month_key)
    already_drawn = bool(result.get("already_drawn", False))
    total_energy = 0
    if not already_drawn:
        total_energy = sum(
            30 if prize == "first" else 20 if prize == "second" else 10
            for _, prize, _ in (result.get("_raw_winners") or [])
        )

    await db.commit()
    return {
        "code": 0,
        "data": {
            "month": result["month"],
            "participant_month": result["participant_month"],
            "eligible_count": result.get("eligible_count", 0),
            "winner_count": result.get("winner_count", 0),
            "total_energy": total_energy,
            "already_drawn": already_drawn,
            "message": "当月抽奖执行完成" if not already_drawn else "该月抽奖已存在，跳过执行"
        }
    }


class ManualTriggerMonthlyRankRewardRequest(BaseModel):
    month: str = Field(default="", description="指定排名结算月份 YYYY-MM，默认取当月")


@router.post("/monthly-rank/trigger-settle")
async def admin_trigger_monthly_rank_reward(
    payload: ManualTriggerMonthlyRankRewardRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    """管理员手动触发月底月榜排名奖励结算。
    规则：前3名奖励30格，4-10名奖励20格，11-20名奖励10格，21-50名奖励5格。
    已当月执行过则直接返回提示不可重复执行，防止重复发放能量。
    """
    today = datetime.now(timezone(timedelta(hours=8)))
    month_key = validate_month_key(payload.month) if payload.month else today.strftime("%Y-%m")

    result = await settle_monthly_rewards(db, month_key=month_key)
    already_settled = bool(result.get("already_settled", False))
    total_energy = 0
    if not already_settled:
        total_energy = sum(
            get_month_reward_amount(rank) for rank in range(1, 51)
        ) // 2  # 按实际排名统计总能量

    await db.commit()
    return {
        "code": 0,
        "data": {
            "month": result.get("month", month_key),
            "snapshot_count": result.get("snapshot_count", 0),
            "reward_count": result.get("reward_count", 0),
            "total_energy": total_energy,
            "already_settled": already_settled,
            "message": "当月月榜排名奖励结算完成" if not already_settled else "该月排名奖励已经结算过，跳过执行"
        }
    }


@router.get("/redemption-orders")
async def list_admin_redemption_orders(
    province: str = "",
    company: str = "",
    status: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    filters = []
    if _clean(company):
        filters.append(User.company == _clean(company))
    if _clean(status):
        filters.append(EnergyRedemptionRecord.status == _normalize_order_status(status))
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.company.like(keyword),
                EnergyRedemptionRecord.product_name.like(keyword),
                EnergyRedemptionRecord.receiver_name.like(keyword),
                EnergyRedemptionRecord.receiver_phone.like(keyword),
                EnergyRedemptionRecord.receiver_address.like(keyword),
                EnergyRedemptionRecord.receiver_note.like(keyword),
            )
        )

    from_date = _parse_date_start(date_from)
    to_date = _parse_date_start(date_to)
    if from_date:
        filters.append(EnergyRedemptionRecord.created_at >= from_date)
    if to_date:
        filters.append(EnergyRedemptionRecord.created_at < to_date + timedelta(days=1))

    total_stmt = select(func.count(EnergyRedemptionRecord.id)).join(User, EnergyRedemptionRecord.user_id == User.id)
    list_stmt = (
        select(EnergyRedemptionRecord, User)
        .join(User, EnergyRedemptionRecord.user_id == User.id)
        .order_by(EnergyRedemptionRecord.created_at.desc(), EnergyRedemptionRecord.id.desc())
        .offset(offset)
        .limit(limit)
    )
    if _clean(province):
        total_stmt = await _apply_province_filter(total_stmt, db, province)
        list_stmt = await _apply_province_filter(list_stmt, db, province)
    if filters:
        total_stmt = total_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int(await db.scalar(total_stmt) or 0)
    result = await db.execute(list_stmt)
    rows = [
        _serialize_admin_redemption(record, user)
        for record, user in result.all()
    ]
    return {
        "code": 0,
        "data": {
            "items": rows,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/redemption-orders/pending-count")
async def get_admin_redemption_pending_count(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    pending_count = int(
        await db.scalar(
            select(func.count(EnergyRedemptionRecord.id)).where(EnergyRedemptionRecord.status == "pending")
        )
        or 0
    )
    return {"code": 0, "data": {"pending_count": pending_count}}


@router.get("/redemption-orders/export")
async def export_admin_redemption_orders(
    province: str = "",
    company: str = "",
    status: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    filters = []
    if _clean(company):
        filters.append(User.company == _clean(company))
    if _clean(status):
        filters.append(EnergyRedemptionRecord.status == _normalize_order_status(status))
    if _clean(q):
        keyword = f"%{_clean(q)}%"
        filters.append(
            or_(
                User.real_name.like(keyword),
                User.nickname.like(keyword),
                User.phone.like(keyword),
                User.company.like(keyword),
                EnergyRedemptionRecord.product_name.like(keyword),
                EnergyRedemptionRecord.receiver_name.like(keyword),
                EnergyRedemptionRecord.receiver_phone.like(keyword),
                EnergyRedemptionRecord.receiver_address.like(keyword),
                EnergyRedemptionRecord.receiver_note.like(keyword),
            )
        )

    from_date = _parse_date_start(date_from)
    to_date = _parse_date_start(date_to)
    if from_date:
        filters.append(EnergyRedemptionRecord.created_at >= from_date)
    if to_date:
        filters.append(EnergyRedemptionRecord.created_at < to_date + timedelta(days=1))

    stmt = (
        select(EnergyRedemptionRecord, User)
        .join(User, EnergyRedemptionRecord.user_id == User.id)
        .order_by(EnergyRedemptionRecord.created_at.desc(), EnergyRedemptionRecord.id.desc())
    )
    if _clean(province):
        stmt = await _apply_province_filter(stmt, db, province)
    if filters:
        stmt = stmt.where(*filters)

    result = await db.execute(stmt)
    orders = [
        _serialize_admin_redemption(record, user)
        for record, user in result.all()
    ]

    headers = [
        "提交日期",
        "状态",
        "用户",
        "手机号",
        "公司",
        "岗位",
        "商品",
        "商品ID",
        "数量",
        "单价能量",
        "总能量",
        "收货人",
        "收货电话",
        "地区",
        "地址",
        "备注",
    ]
    rows = [
        [
            item["created_at"],
            item["status_label"],
            item["user_name"],
            item["phone"],
            item["company"],
            item["job_role_label"],
            item["product_name"],
            item["product_id"],
            item["quantity"],
            item["unit_cost"],
            item["total_cost"],
            item["receiver_name"],
            item["receiver_phone"],
            item["receiver_region"],
            item["receiver_address"],
            item["receiver_note"],
        ]
        for item in orders
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "兑换订单"
    _append_xlsx_rows(sheet, headers, rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"兑换订单-{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.put("/redemption-orders/{order_id}/status")
async def update_admin_redemption_order_status(
    order_id: int,
    payload: AdminRedemptionStatusPayload,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    status = _normalize_order_status(payload.status)
    result = await db.execute(
        select(EnergyRedemptionRecord, User)
        .join(User, EnergyRedemptionRecord.user_id == User.id)
        .where(EnergyRedemptionRecord.id == order_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="兑换订单不存在")

    record, user = row
    record.status = status
    await db.flush()
    await db.refresh(record)
    return {"code": 0, "data": _serialize_admin_redemption(record, user)}


@router.get("/reports/quiz-participation/weekly")
async def get_weekly_participation_report(
    quiz_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    role: str = "",
    q: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    week_start, week_end = _week_bounds_from_date(quiz_date)
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("correct_count")  # noqa: E712
    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(AnswerRecord.id).label("answered_count"),
            correct_expr,
        )
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date >= week_start)
        .where(AnswerRecord.quiz_date <= week_end)
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    stmt = (
        select(User, stats_subquery.c.answered_count, stats_subquery.c.correct_count)
        .join(stats_subquery, stats_subquery.c.user_id == User.id)
        .order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    )
    roles = _normalize_roles(role)
    if roles:
        stmt = stmt.where(User.job_role.in_(roles))
    if _clean(q):
        stmt = stmt.where(_user_keyword_condition(f"%{_clean(q)}%"))

    result = await db.execute(stmt)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    total_users = 0
    for user, answered_count, correct_count in result.all():
        total_users += 1
        company = user.company or "未填写公司"
        grouped[company].append(
            {
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "job_role": _effective_job_role(user),
                "job_role_label": _role_label(_effective_job_role(user)),
                "answered_count": int(answered_count or 0),
                "correct_count": int(correct_count or 0),
            }
        )

    companies = [
        {"company": company, "participants": participants}
        for company, participants in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return {
        "code": 0,
        "data": {
            "quiz_date": quiz_date,
            "week_start": week_start,
            "week_end": week_end,
            "total_companies": len(companies),
            "total_users": total_users,
            "companies": companies,
        },
    }


@router.get("/reports/quiz-participation/weekly/export")
async def export_weekly_participation_report(
    quiz_date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    role: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    week_start, week_end = _week_bounds_from_date(quiz_date)
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("correct_count")  # noqa: E712
    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(AnswerRecord.id).label("answered_count"),
            correct_expr,
        )
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date >= week_start)
        .where(AnswerRecord.quiz_date <= week_end)
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    stmt = (
        select(User, stats_subquery.c.answered_count, stats_subquery.c.correct_count)
        .outerjoin(stats_subquery, stats_subquery.c.user_id == User.id)
        .order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    )
    roles = _normalize_roles(role)
    if roles:
        stmt = stmt.where(User.job_role.in_(roles))

    result = await db.execute(stmt)
    headers = ["周开始", "周结束", "公司", "员工", "岗位", "手机号", "答题数", "答对数"]
    answered_rows: list[list[object]] = []
    unanswered_rows: list[list[object]] = []
    for user, answered_count, correct_count in result.all():
        row = [
            week_start,
            week_end,
            user.company or "未填写公司",
            get_display_name(user),
            _role_label(_effective_job_role(user)),
            user.phone or "",
            int(answered_count or 0),
            int(correct_count or 0),
        ]
        if int(answered_count or 0) > 0:
            answered_rows.append(row)
        else:
            unanswered_rows.append(row)

    workbook = Workbook()
    answered_sheet = workbook.active
    answered_sheet.title = "本周已答题"
    _append_xlsx_rows(answered_sheet, headers, answered_rows)

    unanswered_sheet = workbook.create_sheet("本周未答题")
    _append_xlsx_rows(unanswered_sheet, headers, unanswered_rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"答题参与周报-{week_start}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/reports/quiz-participation/monthly")
async def get_monthly_participation_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    province: str = "",
    company: str = "",
    role: str = "",
    q: str = "",
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> dict[str, object]:
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("correct_count")  # noqa: E712
    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(distinct(AnswerRecord.quiz_date)).label("participated_weeks"),
            func.group_concat(distinct(AnswerRecord.quiz_date)).label("weeks"),
            func.count(AnswerRecord.id).label("answered_count"),
            correct_expr,
        )
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date.like(f"{month}-%"))
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    stmt = (
        select(
            User,
            stats_subquery.c.participated_weeks,
            stats_subquery.c.weeks,
            stats_subquery.c.answered_count,
            stats_subquery.c.correct_count,
        )
        .join(stats_subquery, stats_subquery.c.user_id == User.id)
        .order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    )
    if _clean(province):
        stmt = await _apply_province_filter(stmt, db, province)
    if _clean(company):
        stmt = stmt.where(User.company == _clean(company))
    roles = _normalize_roles(role)
    if roles:
        stmt = stmt.where(User.job_role.in_(roles))
    if _clean(q):
        stmt = stmt.where(_user_keyword_condition(f"%{_clean(q)}%"))

    result = await db.execute(stmt)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    total_users = 0
    for user, participated_weeks, weeks, answered_count, correct_count in result.all():
        total_users += 1
        week_list = sorted([week for week in str(weeks or "").split(",") if week])
        company_name = user.company or "未填写公司"
        grouped[company_name].append(
            {
                "user_id": user.id,
                "name": get_display_name(user),
                "real_name": user.real_name or "",
                "job_role": _effective_job_role(user),
                "job_role_label": _role_label(_effective_job_role(user)),
                "participated_weeks": int(participated_weeks or 0),
                "weeks": week_list,
                "answered_count": int(answered_count or 0),
                "correct_count": int(correct_count or 0),
            }
        )

    companies = [
        {"company": company_name, "employees": employees}
        for company_name, employees in sorted(grouped.items(), key=lambda item: item[0])
    ]
    return {
        "code": 0,
        "data": {
            "month": month,
            "total_companies": len(companies),
            "total_users": total_users,
            "companies": companies,
        },
    }


@router.get("/reports/quiz-participation/monthly/export")
async def export_monthly_participation_report(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("correct_count")  # noqa: E712
    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(distinct(AnswerRecord.quiz_date)).label("participated_weeks"),
            func.group_concat(distinct(AnswerRecord.quiz_date)).label("weeks"),
            func.count(AnswerRecord.id).label("answered_count"),
            correct_expr,
        )
        .where(AnswerRecord.source == "daily")
        .where(AnswerRecord.quiz_date.like(f"{month}-%"))
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    result = await db.execute(
        select(
            User,
            stats_subquery.c.participated_weeks,
            stats_subquery.c.weeks,
            stats_subquery.c.answered_count,
            stats_subquery.c.correct_count,
        )
        .outerjoin(stats_subquery, stats_subquery.c.user_id == User.id)
        .order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    )

    answered_rows: list[list[object]] = []
    unanswered_rows: list[list[object]] = []
    headers = ["公司", "员工", "岗位", "手机号", "参加周数", "参加周次", "答题数", "答对数"]

    for user, participated_weeks, weeks, answered_count, correct_count in result.all():
        week_list = sorted([week for week in str(weeks or "").split(",") if week])
        row = [
            user.company or "未填写公司",
            get_display_name(user),
            _role_label(_effective_job_role(user)),
            user.phone or "",
            int(participated_weeks or 0),
            " / ".join(week_list),
            int(answered_count or 0),
            int(correct_count or 0),
        ]
        if int(answered_count or 0) > 0:
            answered_rows.append(row)
        else:
            unanswered_rows.append(row)

    workbook = Workbook()
    answered_sheet = workbook.active
    answered_sheet.title = "本月已答题"
    _append_xlsx_rows(answered_sheet, headers, answered_rows)
    unanswered_sheet = workbook.create_sheet("本月未答题")
    _append_xlsx_rows(unanswered_sheet, headers, unanswered_rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"答题参与月报-{month}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/reports/quiz-participation/all/export")
async def export_all_participation_report(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
) -> StreamingResponse:
    correct_expr = func.sum(case((AnswerRecord.is_correct == True, 1), else_=0)).label("correct_count")  # noqa: E712
    participated_weeks_expr = func.count(
        distinct(
            case(
                (
                    AnswerRecord.quiz_date.isnot(None),
                    AnswerRecord.quiz_date,
                ),
                else_=None,
            )
        )
    ).label("participated_weeks")
    stats_subquery = (
        select(
            AnswerRecord.user_id.label("user_id"),
            func.count(AnswerRecord.id).label("answered_count"),
            correct_expr,
            func.sum(func.coalesce(AnswerRecord.time_spent, 0)).label("total_time_spent"),
            participated_weeks_expr,
            func.max(AnswerRecord.created_at).label("last_answered_at"),
        )
        .where(AnswerRecord.source == "daily")
        .group_by(AnswerRecord.user_id)
        .subquery()
    )
    result = await db.execute(
        select(
            User,
            stats_subquery.c.participated_weeks,
            stats_subquery.c.answered_count,
            stats_subquery.c.correct_count,
            stats_subquery.c.total_time_spent,
            stats_subquery.c.last_answered_at,
        )
        .outerjoin(stats_subquery, stats_subquery.c.user_id == User.id)
        .order_by(User.company.asc(), User.real_name.asc(), User.id.asc())
    )

    headers = ["公司", "员工", "岗位", "手机号", "参加周数", "答题总数", "答对总数", "正确率", "总用时(秒)", "平均用时(秒)", "最近答题时间"]
    rows = []
    for user, participated_weeks, answered_count, correct_count, total_time_spent, last_answered_at in result.all():
        total_answers = int(answered_count or 0)
        total_correct = int(correct_count or 0)
        total_time = int(total_time_spent or 0)
        rows.append(
            [
                user.company or "未填写公司",
                get_display_name(user),
                _role_label(_effective_job_role(user)),
                user.phone or "",
                int(participated_weeks or 0),
                total_answers,
                total_correct,
                f"{(total_correct / total_answers * 100):.1f}%" if total_answers else "0.0%",
                total_time,
                round(total_time / total_answers, 1) if total_answers else 0,
                last_answered_at.isoformat() if last_answered_at else "",
            ]
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "全部答题统计"
    _append_xlsx_rows(sheet, headers, rows)

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    filename = f"全部答题统计-{datetime.now():%Y%m%d}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
