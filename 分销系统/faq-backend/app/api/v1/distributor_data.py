"""
分销商省份-公司数据 API

从数据库动态读取已入库的分销商省份和公司列表。
"""
from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, distinct

from app.db.session import get_db
from app.models.user import User
from app.utils.province import normalize_province_name

router = APIRouter(prefix="/distributor", tags=["分销商数据"])


@router.get("/provinces")
async def get_provinces(db: AsyncSession = Depends(get_db)):
    """获取所有省份列表（从数据库中已有用户的 province 字段动态读取）"""
    stmt = (
        select(distinct(User.province))
        .where(User.province.isnot(None))
        .where(User.province != "")
        .order_by(User.province)
    )
    result = await db.execute(stmt)
    normalized = {
        normalize_province_name(row[0])
        for row in result.all()
        if normalize_province_name(row[0])
    }
    provinces = sorted(normalized)
    return {"code": 0, "data": provinces}


@router.get("/companies")
async def get_companies(
    province: str = Query(..., description="省份名称"),
    db: AsyncSession = Depends(get_db)
):
    """根据省份获取该省份下的公司列表（从数据库中动态读取）"""
    normalized_province = normalize_province_name(province)
    stmt = (
        select(User.province, User.company)
        .where(User.province.isnot(None))
        .where(User.province != "")
        .where(User.company.isnot(None))
        .where(User.company != "")
    )
    result = await db.execute(stmt)
    companies = sorted(
        {
            company
            for raw_province, company in result.all()
            if normalize_province_name(raw_province) == normalized_province
        }
    )
    return {"code": 0, "data": companies}
