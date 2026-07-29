"""Helpers for backend-synced energy products and redemption records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.energy import EnergyRedemptionRecord
from app.models.energy_product import EnergyProduct

ACTIVE_REDEMPTION_STATUSES = {"pending", "approved", "delivered", "completed"}
VALID_REDEMPTION_STATUSES = ACTIVE_REDEMPTION_STATUSES | {"cancelled"}

ENERGY_PRODUCT_TIERS = [
    {
        "tier": 0,
        "tier_label": "<50 能量",
        "section_id": "tier-under-50",
        "title": "轻量好物",
        "subtitle": "精选低门槛礼品",
        "layout": "grid",
        "min_cost": 0,
        "max_cost": 49,
    },
    {
        "tier": 1,
        "tier_label": "50-100 能量",
        "section_id": "tier-50-100",
        "title": "实用优选",
        "subtitle": "适合日常兑换",
        "layout": "grid",
        "min_cost": 50,
        "max_cost": 100,
    },
    {
        "tier": 2,
        "tier_label": "100-150 能量",
        "section_id": "tier-100-150",
        "title": "人气好礼",
        "subtitle": "热门兑换区间",
        "layout": "grid",
        "min_cost": 101,
        "max_cost": 150,
    },
    {
        "tier": 3,
        "tier_label": "150-200 能量",
        "section_id": "tier-150-200",
        "title": "品质生活",
        "subtitle": "进阶兑换选择",
        "layout": "grid",
        "min_cost": 151,
        "max_cost": 200,
    },
    {
        "tier": 4,
        "tier_label": "200-300 能量",
        "section_id": "tier-200-300",
        "title": "精选进阶",
        "subtitle": "更高价值礼品",
        "layout": "grid",
        "min_cost": 201,
        "max_cost": 300,
    },
    {
        "tier": 5,
        "tier_label": "300-400 能量",
        "section_id": "tier-300-400",
        "title": "高阶甄选",
        "subtitle": "高能量精品",
        "layout": "grid",
        "min_cost": 301,
        "max_cost": 400,
    },
    {
        "tier": 6,
        "tier_label": "400-700 能量",
        "section_id": "tier-400-700",
        "title": "臻选礼遇",
        "subtitle": "高价值礼盒与数码",
        "layout": "grid",
        "min_cost": 401,
        "max_cost": 700,
    },
    {
        "tier": 7,
        "tier_label": ">700 能量",
        "section_id": "tier-above-700",
        "title": "尊享礼遇",
        "subtitle": "高端兑换专区",
        "layout": "grid",
        "min_cost": 701,
        "max_cost": None,
    },
]


def normalize_redemption_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    return normalized if normalized in VALID_REDEMPTION_STATUSES else "pending"


def normalize_redemption_created_at(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _redemption_quantity(record: EnergyRedemptionRecord) -> int:
    return max(1, int(record.quantity or 1))


def _redemption_unit_cost(record: EnergyRedemptionRecord) -> int:
    return max(0, int(record.unit_cost or record.cost or 0))


def _redemption_total_cost(record: EnergyRedemptionRecord) -> int:
    fallback_cost = _redemption_unit_cost(record)
    quantity = _redemption_quantity(record)
    total_cost = int(record.total_cost or 0)
    if total_cost <= 0:
        total_cost = fallback_cost * quantity if fallback_cost else fallback_cost
    return max(0, total_cost)


def serialize_redemption(record: EnergyRedemptionRecord) -> dict[str, object]:
    created_at = record.created_at
    created_at_text = ""
    if created_at:
        if created_at.tzinfo is None:
            created_at_text = created_at.replace(tzinfo=timezone.utc).isoformat()
        else:
            created_at_text = created_at.astimezone(timezone.utc).isoformat()

    return {
        "id": record.id,
        "batch_id": record.batch_id or "",
        "client_record_id": record.client_record_id,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "cost": _redemption_unit_cost(record),
        "quantity": _redemption_quantity(record),
        "unit_cost": _redemption_unit_cost(record),
        "total_cost": _redemption_total_cost(record),
        "status": record.status,
        "receiver_name": record.receiver_name or "",
        "receiver_phone": record.receiver_phone or "",
        "receiver_region": record.receiver_region or "",
        "receiver_address": record.receiver_address or "",
        "receiver_note": record.receiver_note or "",
        "created_at": created_at_text,
    }


def build_energy_summary(
    total_score: int | float | None,
    records: Iterable[EnergyRedemptionRecord] | None,
) -> dict[str, int]:
    safe_total_score = max(0, int(total_score or 0))
    items = list(records or [])
    redeemed_energy = sum(
        _redemption_total_cost(record)
        for record in items
        if normalize_redemption_status(record.status) in ACTIVE_REDEMPTION_STATUSES
    )
    pending_count = sum(1 for record in items if normalize_redemption_status(record.status) == "pending")

    return {
        "total_energy": safe_total_score,
        "redeemed_energy": redeemed_energy,
        "available_energy": max(0, safe_total_score - redeemed_energy),
        "redemption_count": len(items),
        "total": len(items),
        "pending": pending_count,
        "spent": redeemed_energy,
    }


def _serialize_product(product: EnergyProduct) -> dict[str, object]:
    return {
        "id": product.product_id,
        "name": product.name,
        "description": product.description or "",
        "category": product.category or "",
        "cost": product.cost,
        "imageUrl": product.image_url or "",
        "badge": product.badge or "",
        "tag": product.tag or "",
        "artLabel": product.art_label or "",
        "artClass": product.art_class or "",
        "sortOrder": product.sort_order,
        "isFeatured": bool(product.is_featured),
    }


def build_energy_product_catalog(products: Iterable[EnergyProduct]) -> dict[str, object]:
    active_products = list(products or [])
    featured_product = next((item for item in active_products if item.is_featured), None)
    if not featured_product and active_products:
        featured_product = active_products[0]

    tier_groups: list[dict[str, object]] = []
    for tier in ENERGY_PRODUCT_TIERS:
        items = [
            _serialize_product(product)
            for product in active_products
            if product.cost >= tier["min_cost"]
            and (tier["max_cost"] is None or product.cost <= tier["max_cost"])
        ]
        if not items:
            continue
        tier_groups.append(
            {
                "tier": tier["tier"],
                "tierLabel": tier["tier_label"],
                "sectionId": tier["section_id"],
                "title": tier["title"],
                "subtitle": tier["subtitle"],
                "layout": tier["layout"],
                "products": items,
            }
        )

    return {
        "featured_product": _serialize_product(featured_product) if featured_product else {},
        "tier_groups": tier_groups,
    }


async def fetch_user_redemptions(
    db: AsyncSession,
    user_id: str,
) -> list[EnergyRedemptionRecord]:
    result = await db.execute(
        select(EnergyRedemptionRecord)
        .where(EnergyRedemptionRecord.user_id == user_id)
        .order_by(EnergyRedemptionRecord.created_at.desc(), EnergyRedemptionRecord.id.desc())
    )
    return list(result.scalars().all())


async def fetch_active_energy_products(db: AsyncSession) -> list[EnergyProduct]:
    result = await db.execute(
        select(EnergyProduct)
        .where(EnergyProduct.is_active.is_(True))
        .order_by(EnergyProduct.sort_order.asc(), EnergyProduct.cost.asc(), EnergyProduct.product_id.asc())
    )
    return list(result.scalars().all())
