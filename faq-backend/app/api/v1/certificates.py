"""Certificate query APIs."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_rate_limit, get_current_user_id
from app.db.session import get_db
from app.models.certificate import CertificateRecord

router = APIRouter(prefix="/certificates", tags=["certificates"])

DETAIL_FIELD_ORDER = [
    "证书编号",
    "证书类型",
    "企业名称",
    "制造商",
    "产品描述",
    "标准",
    "证书数量",
    "额定参数",
    "In（A）",
    "In(A)",
    "额定工作电压 Ue",
    "Ue",
    "额定冲击耐受电压 Uimp",
    "Uimp",
    "Icw(kA)",
    "Icw(kA）",
    "系统",
    "IP",
    "with PIU？",
    "with PIU?",
    "防火焰蔓延",
    "建筑结构防火",
    "耐火",
    "线路完整性",
    "初始获证时间",
    "说明",
    "备注",
]

DETAIL_FIELD_ORDER_MAP = {
    label.lower().replace(" ", ""): index
    for index, label in enumerate(DETAIL_FIELD_ORDER)
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _field_sort_key(label: str) -> tuple[int, str]:
    normalized = label.lower().replace(" ", "")
    return (DETAIL_FIELD_ORDER_MAP.get(normalized, len(DETAIL_FIELD_ORDER_MAP)), normalized)


def _pairs_from_detail(detail: dict[str, Any]) -> list[dict[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in (detail or {}).items():
        label = _clean_text(key)
        text = _clean_text(value)
        if not label or not text:
            continue
        pairs.append((label, text))
    return [
        {"label": label, "value": text}
        for label, text in sorted(pairs, key=lambda item: _field_sort_key(item[0]))
    ]


def _dedupe_by_key(records: list[CertificateRecord], key_name: str) -> list[dict[str, Any]]:
    grouped: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for record in records:
        key = _clean_text(getattr(record, key_name))
        if not key:
            continue

        if key not in grouped:
            grouped[key] = {
                "id": key,
                "name": key,
                "count": 0,
            }
        grouped[key]["count"] += 1

    return list(grouped.values())


@router.get("/companies")
async def list_certificate_companies(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("certificate_companies", current_user_id, limit=80, window_seconds=60)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.is_active.is_(True))
        .order_by(CertificateRecord.company_key.asc(), CertificateRecord.sort_order.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    grouped: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for record in records:
        key = _clean_text(record.company_key)
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "id": key,
                "name": _clean_text(record.company_name) or key,
                "count": 0,
            }
        grouped[key]["count"] += 1

    return {"code": 0, "data": list(grouped.values())}


@router.get("/cert-types")
async def list_certificate_types(
    company_key: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("certificate_cert_types", current_user_id, limit=100, window_seconds=60)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.is_active.is_(True))
        .where(CertificateRecord.company_key == company_key)
        .order_by(CertificateRecord.sort_order.asc(), CertificateRecord.id.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return {"code": 0, "data": _dedupe_by_key(records, "cert_type")}


@router.get("/categories")
async def list_certificate_categories(
    company_key: str = Query(..., min_length=1),
    cert_type: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("certificate_categories", current_user_id, limit=120, window_seconds=60)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.is_active.is_(True))
        .where(CertificateRecord.company_key == company_key)
        .where(CertificateRecord.cert_type == cert_type)
        .order_by(CertificateRecord.sort_order.asc(), CertificateRecord.id.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return {"code": 0, "data": _dedupe_by_key(records, "category_name")}


@router.get("/models")
async def list_certificate_models(
    company_key: str = Query(..., min_length=1),
    cert_type: str = Query(..., min_length=1),
    category_name: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("certificate_models", current_user_id, limit=120, window_seconds=60)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.is_active.is_(True))
        .where(CertificateRecord.company_key == company_key)
        .where(CertificateRecord.cert_type == cert_type)
        .where(CertificateRecord.category_name == category_name)
        .order_by(CertificateRecord.sort_order.asc(), CertificateRecord.id.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return {"code": 0, "data": _dedupe_by_key(records, "model")}


@router.get("/details")
async def get_certificate_details(
    company_key: str = Query(..., min_length=1),
    cert_type: str = Query(..., min_length=1),
    category_name: str = Query(..., min_length=1),
    model: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("certificate_details", current_user_id, limit=120, window_seconds=60)

    stmt = (
        select(CertificateRecord)
        .where(CertificateRecord.is_active.is_(True))
        .where(CertificateRecord.company_key == company_key)
        .where(CertificateRecord.cert_type == cert_type)
        .where(CertificateRecord.category_name == category_name)
        .where(CertificateRecord.model == model)
        .order_by(CertificateRecord.sort_order.asc(), CertificateRecord.source_row.asc(), CertificateRecord.id.asc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "company_key": company_key,
            "company_name": _clean_text(records[0].company_name) if records else "",
            "cert_type": cert_type,
            "category_name": category_name,
            "model": model,
            "records": [
                {
                    "id": record.id,
                    "source_row": record.source_row,
                    "details": record.detail_json or {},
                    "detail_pairs": _pairs_from_detail(record.detail_json or {}),
                }
                for record in records
            ],
        },
    }
