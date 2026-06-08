"""Tests for the energy product seed loader."""

from __future__ import annotations

from scripts.seed_energy_products import load_seed_products


def test_load_seed_products_returns_catalog_data():
    products = load_seed_products()

    assert products
    assert products[0]["product_id"]
    assert products[0]["name"]
    assert isinstance(products[0]["cost"], int)
    assert any(item["is_featured"] for item in products)
