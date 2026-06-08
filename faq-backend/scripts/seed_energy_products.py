"""Seed energy products from the repository seed JSON."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.energy_product import EnergyProduct

ROOT = Path(__file__).resolve().parents[2]
SEED_FILE = ROOT / "faq-backend" / "scripts" / "energy_products_seed.json"


def load_seed_products() -> list[dict[str, object]]:
    raw_items = json.loads(SEED_FILE.read_text(encoding="utf-8-sig"))
    products: list[dict[str, object]] = []
    for index, item in enumerate(raw_items, start=1):
        products.append(
            {
                "id": str(uuid.uuid4()),
                "product_id": str(item["product_id"]).strip(),
                "name": str(item["name"]).strip(),
                "description": str(item.get("description", "")).strip(),
                "category": str(item.get("category", "")).strip(),
                "cost": int(item.get("cost", 0)),
                "image_url": str(item.get("image_url", "")).strip(),
                "badge": str(item.get("badge", "")).strip(),
                "tag": str(item.get("tag", "")).strip(),
                "art_label": str(item.get("art_label", "")).strip(),
                "art_class": str(item.get("art_class", "")).strip(),
                "sort_order": int(item.get("sort_order", index)),
                "is_featured": bool(item.get("is_featured", False)),
                "is_active": bool(item.get("is_active", True)),
            }
        )
    return products


async def main() -> None:
    products = load_seed_products()
    if not products:
        raise RuntimeError(f"No products loaded from {SEED_FILE}")

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(EnergyProduct.id).limit(1))
        if existing:
            await session.execute(delete(EnergyProduct))

        session.add_all(EnergyProduct(**item) for item in products)
        await session.commit()

    print(f"Seeded {len(products)} energy products.")


if __name__ == "__main__":
    asyncio.run(main())
