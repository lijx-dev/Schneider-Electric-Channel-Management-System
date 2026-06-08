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
