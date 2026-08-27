"""Tests for backend-owned energy product catalog APIs."""

from __future__ import annotations

import pytest

from app.models.energy_product import EnergyProduct


@pytest.mark.asyncio
async def test_list_energy_products_returns_only_active_products(client, test_db):
    async with test_db() as session:
        session.add_all(
            [
                EnergyProduct(
                    product_id="active_001",
                    name="已上架商品",
                    description="上架中",
                    category="数码",
                    cost=120,
                    image_url="",
                    badge="热门",
                    tag="数码",
                    art_label="数码",
                    art_class="art-digital",
                    sort_order=10,
                    is_featured=True,
                    is_active=True,
                ),
                EnergyProduct(
                    product_id="inactive_001",
                    name="已下架商品",
                    description="下架中",
                    category="家居",
                    cost=80,
                    image_url="",
                    badge="",
                    tag="家居",
                    art_label="家居",
                    art_class="art-home",
                    sort_order=20,
                    is_featured=False,
                    is_active=False,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/energy/products")

    assert response.status_code == 200
    payload = response.json()["data"]
    product_ids = [
        product["id"]
        for group in payload["tier_groups"]
        for product in group["products"]
    ]
    assert "active_001" in product_ids
    assert "inactive_001" not in product_ids
    assert payload["featured_product"]["id"] == "active_001"


@pytest.mark.asyncio
async def test_energy_products_sorted_by_cost_within_each_tier(client, test_db):
    async with test_db() as session:
        session.add_all(
            [
                EnergyProduct(
                    product_id="cheap_late",  # low cost but appended later in sort_order
                    name="低价商品",
                    cost=55,
                    category="日用",
                    image_url="",
                    tag="日用",
                    art_label="日用",
                    art_class="art-life",
                    sort_order=999,
                    is_active=True,
                ),
                EnergyProduct(
                    product_id="expensive_early",  # higher cost but earlier sort_order
                    name="高价商品",
                    cost=90,
                    category="日用",
                    image_url="",
                    tag="日用",
                    art_label="日用",
                    art_class="art-life",
                    sort_order=1,
                    is_active=True,
                ),
                EnergyProduct(
                    product_id="mid_cost",
                    name="中间商品",
                    cost=70,
                    category="日用",
                    image_url="",
                    tag="日用",
                    art_label="日用",
                    art_class="art-life",
                    sort_order=500,
                    is_active=True,
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/energy/products")
    assert response.status_code == 200
    payload = response.json()["data"]
    group = next(g for g in payload["tier_groups"] if g["sectionId"] == "tier-50-100")
    costs = [p["cost"] for p in group["products"]]
    assert costs == sorted(costs), f"分档内应按能量升序，实际: {costs}"
    ids = [p["id"] for p in group["products"]]
    assert ids == ["cheap_late", "mid_cost", "expensive_early"]
