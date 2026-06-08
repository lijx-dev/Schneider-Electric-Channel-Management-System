"""Energy redemption and product APIs."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.session import get_db
from app.models.energy import EnergyRedemptionRecord
from app.models.energy_product import EnergyProduct
from app.models.user import User
from app.services.energy import (
    build_energy_product_catalog,
    build_energy_summary,
    fetch_active_energy_products,
    fetch_user_redemptions,
    normalize_redemption_created_at,
    normalize_redemption_status,
    serialize_redemption,
)

router = APIRouter(tags=["energy"])


def _normalize_contact_text(value: str | None) -> str:
    return str(value or "").strip()


class EnergyRedemptionCreateRequest(BaseModel):
    client_record_id: str = Field(min_length=1, max_length=80)
    product_id: str = Field(min_length=1, max_length=64)
    receiver_name: str = Field(min_length=1, max_length=100)
    receiver_phone: str = Field(min_length=1, max_length=30)
    receiver_region: str = Field(min_length=1, max_length=120)
    receiver_address: str = Field(min_length=1, max_length=255)
    receiver_note: str = Field(default="", max_length=255)

    @field_validator("receiver_name", "receiver_region", "receiver_address")
    @classmethod
    def validate_required_contact_text(cls, value: str) -> str:
        normalized = _normalize_contact_text(value)
        if normalized == "":
            raise ValueError("field required")
        return normalized

    @field_validator("receiver_note")
    @classmethod
    def validate_optional_contact_text(cls, value: str) -> str:
        return _normalize_contact_text(value)

    @field_validator("receiver_phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = _normalize_contact_text(value)
        digits_only = "".join(char for char in normalized if char.isdigit())
        if len(digits_only) < 11:
            raise ValueError("invalid phone")
        return normalized


class EnergyRedemptionBatchItem(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(default=1, ge=1, le=100000)

    @field_validator("product_id")
    @classmethod
    def validate_product_id(cls, value: str) -> str:
        normalized = _normalize_contact_text(value)
        if normalized == "":
            raise ValueError("field required")
        return normalized


class EnergyRedemptionBatchRequest(BaseModel):
    client_batch_id: str = Field(min_length=1, max_length=80)
    items: list[EnergyRedemptionBatchItem] = Field(min_length=1)
    receiver_name: str = Field(min_length=1, max_length=100)
    receiver_phone: str = Field(min_length=1, max_length=30)
    receiver_region: str = Field(min_length=1, max_length=120)
    receiver_address: str = Field(min_length=1, max_length=255)
    receiver_note: str = Field(default="", max_length=255)

    @field_validator("receiver_name", "receiver_region", "receiver_address")
    @classmethod
    def validate_required_contact_text(cls, value: str) -> str:
        normalized = _normalize_contact_text(value)
        if normalized == "":
            raise ValueError("field required")
        return normalized

    @field_validator("receiver_note")
    @classmethod
    def validate_optional_contact_text(cls, value: str) -> str:
        return _normalize_contact_text(value)

    @field_validator("receiver_phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = _normalize_contact_text(value)
        digits_only = "".join(char for char in normalized if char.isdigit())
        if len(digits_only) < 11:
            raise ValueError("invalid phone")
        return normalized


class EnergyRedemptionPayload(BaseModel):
    client_record_id: str = Field(min_length=1, max_length=80)
    batch_id: str = Field(default="", max_length=80)
    product_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=200)
    cost: int = Field(gt=0, le=100000)
    quantity: int = Field(default=1, ge=1, le=100000)
    unit_cost: int = Field(default=0, ge=0, le=100000)
    total_cost: int = Field(default=0, ge=0)
    status: str = Field(default="pending", min_length=1, max_length=20)
    receiver_name: str = Field(default="", max_length=100)
    receiver_phone: str = Field(default="", max_length=30)
    receiver_region: str = Field(default="", max_length=120)
    receiver_address: str = Field(default="", max_length=255)
    receiver_note: str = Field(default="", max_length=255)
    created_at: datetime | None = None


class EnergyRedemptionSyncRequest(BaseModel):
    records: list[EnergyRedemptionPayload] = Field(default_factory=list)


def _build_batch_client_record_id(batch_id: str, product_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"energy-redemption:{batch_id}:{product_id}"))


async def _get_user_or_404(db: AsyncSession, user_id: str) -> User:
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


async def _get_product_or_error(db: AsyncSession, product_id: str) -> EnergyProduct:
    product = await db.scalar(select(EnergyProduct).where(EnergyProduct.product_id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="product not found")
    if not product.is_active:
        raise HTTPException(status_code=400, detail="product inactive")
    return product


async def _get_or_create_redemption(
    db: AsyncSession,
    user_id: str,
    payload: EnergyRedemptionPayload,
) -> tuple[EnergyRedemptionRecord, bool]:
    existing = await db.scalar(
        select(EnergyRedemptionRecord).where(
            EnergyRedemptionRecord.user_id == user_id,
            EnergyRedemptionRecord.client_record_id == payload.client_record_id,
        )
    )
    if existing:
        return existing, False

    record = EnergyRedemptionRecord(
        user_id=user_id,
        client_record_id=str(payload.client_record_id).strip(),
        batch_id=str(payload.batch_id or "").strip(),
        product_id=str(payload.product_id).strip(),
        product_name=str(payload.product_name).strip(),
        cost=max(0, int(payload.unit_cost or payload.cost or 0)),
        quantity=max(1, int(payload.quantity or 1)),
        unit_cost=max(0, int(payload.unit_cost or payload.cost or 0)),
        total_cost=max(
            0,
            int(
                payload.total_cost
                or (max(0, int(payload.unit_cost or payload.cost or 0)) * max(1, int(payload.quantity or 1)))
                or payload.cost
                or 0
            ),
        ),
        status=normalize_redemption_status(payload.status),
        receiver_name=_normalize_contact_text(payload.receiver_name),
        receiver_phone=_normalize_contact_text(payload.receiver_phone),
        receiver_region=_normalize_contact_text(payload.receiver_region),
        receiver_address=_normalize_contact_text(payload.receiver_address),
        receiver_note=_normalize_contact_text(payload.receiver_note),
    )
    normalized_created_at = normalize_redemption_created_at(payload.created_at)
    if normalized_created_at:
        record.created_at = normalized_created_at
        record.updated_at = normalized_created_at

    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record, True


@router.get("/energy/products")
async def list_energy_products(db: AsyncSession = Depends(get_db)):
    products = await fetch_active_energy_products(db)
    return {
        "code": 0,
        "data": build_energy_product_catalog(products),
    }


@router.get("/energy/redemptions")
async def list_energy_redemptions(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user = await _get_user_or_404(db, current_user_id)
    records = await fetch_user_redemptions(db, user.id)
    return {
        "code": 0,
        "data": {
            "records": [serialize_redemption(record) for record in records],
            "summary": build_energy_summary(user.total_score, records),
        },
    }


@router.post("/energy/redemptions")
async def create_energy_redemption(
    payload: EnergyRedemptionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user = await _get_user_or_404(db, current_user_id)
    product = await _get_product_or_error(db, payload.product_id)
    records = await fetch_user_redemptions(db, user.id)
    summary = build_energy_summary(user.total_score, records)
    if summary["available_energy"] < product.cost:
        raise HTTPException(status_code=400, detail="insufficient energy")

    canonical_payload = EnergyRedemptionPayload(
        client_record_id=payload.client_record_id,
        batch_id="",
        product_id=product.product_id,
        product_name=product.name,
        cost=product.cost,
        quantity=1,
        unit_cost=product.cost,
        total_cost=product.cost,
        status="pending",
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        receiver_region=payload.receiver_region,
        receiver_address=payload.receiver_address,
        receiver_note=payload.receiver_note,
    )
    record, created = await _get_or_create_redemption(db, user.id, canonical_payload)
    records = await fetch_user_redemptions(db, user.id)
    return {
        "code": 0,
        "data": {
            "created": created,
            "record": serialize_redemption(record),
            "summary": build_energy_summary(user.total_score, records),
        },
    }


@router.post("/energy/redemptions/batch")
async def create_energy_redemption_batch(
    payload: EnergyRedemptionBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user = await _get_user_or_404(db, current_user_id)
    batch_id = _normalize_contact_text(payload.client_batch_id)

    merged_items: dict[str, int] = {}
    for item in payload.items:
        product_id = _normalize_contact_text(item.product_id)
        merged_items[product_id] = merged_items.get(product_id, 0) + max(1, int(item.quantity or 1))

    if not merged_items:
        raise HTTPException(status_code=400, detail="cart items required")

    product_ids = list(merged_items.keys())
    result = await db.execute(select(EnergyProduct).where(EnergyProduct.product_id.in_(product_ids)))
    products = {product.product_id: product for product in result.scalars().all()}

    missing_product_id = next((product_id for product_id in product_ids if product_id not in products), None)
    if missing_product_id:
        raise HTTPException(status_code=404, detail="product not found")

    inactive_product_id = next((product_id for product_id, product in products.items() if not product.is_active), None)
    if inactive_product_id:
        raise HTTPException(status_code=400, detail="product inactive")

    records = await fetch_user_redemptions(db, user.id)
    summary = build_energy_summary(user.total_score, records)

    existing_result = await db.execute(
        select(EnergyRedemptionRecord).where(
            EnergyRedemptionRecord.user_id == user.id,
            EnergyRedemptionRecord.batch_id == batch_id,
            EnergyRedemptionRecord.product_id.in_(product_ids),
        )
    )
    existing_by_product: dict[str, EnergyRedemptionRecord] = {}
    for record in existing_result.scalars().all():
        existing_by_product.setdefault(record.product_id, record)

    remaining_total_cost = 0
    for product_id, quantity in merged_items.items():
        existing_record = existing_by_product.get(product_id)
        product = products[product_id]
        if existing_record:
            expected_unit_cost = max(0, int(product.cost or 0))
            expected_quantity = max(1, int(quantity or 1))
            existing_unit_cost = max(0, int(existing_record.unit_cost or existing_record.cost or 0))
            existing_quantity = max(1, int(existing_record.quantity or 1))
            if existing_unit_cost != expected_unit_cost or existing_quantity != expected_quantity:
                raise HTTPException(status_code=409, detail="batch conflict")
            continue
        remaining_total_cost += max(0, int(product.cost or 0)) * quantity

    if summary["available_energy"] < remaining_total_cost:
        raise HTTPException(status_code=400, detail="insufficient energy")

    created_records: list[EnergyRedemptionRecord] = []
    created_count = 0
    for product_id, quantity in merged_items.items():
        existing_record = existing_by_product.get(product_id)
        if existing_record:
            created_records.append(existing_record)
            continue

        product = products[product_id]
        canonical_payload = EnergyRedemptionPayload(
            client_record_id=_build_batch_client_record_id(batch_id, product.product_id),
            batch_id=batch_id,
            product_id=product.product_id,
            product_name=product.name,
            cost=product.cost,
            quantity=quantity,
            unit_cost=product.cost,
            total_cost=product.cost * quantity,
            status="pending",
            receiver_name=payload.receiver_name,
            receiver_phone=payload.receiver_phone,
            receiver_region=payload.receiver_region,
            receiver_address=payload.receiver_address,
            receiver_note=payload.receiver_note,
        )
        record, created = await _get_or_create_redemption(db, user.id, canonical_payload)
        created_records.append(record)
        if created:
            created_count += 1

    records = await fetch_user_redemptions(db, user.id)
    return {
        "code": 0,
        "data": {
            "batch_id": batch_id,
            "created_count": created_count,
            "records": [serialize_redemption(record) for record in created_records],
            "summary": build_energy_summary(user.total_score, records),
        },
    }


@router.post("/energy/redemptions/sync")
async def sync_energy_redemptions(
    body: EnergyRedemptionSyncRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    user = await _get_user_or_404(db, current_user_id)
    created_count = 0

    for payload in body.records:
        _, created = await _get_or_create_redemption(db, user.id, payload)
        if created:
            created_count += 1

    records = await fetch_user_redemptions(db, user.id)
    return {
        "code": 0,
        "data": {
            "created_count": created_count,
            "summary": build_energy_summary(user.total_score, records),
        },
    }
