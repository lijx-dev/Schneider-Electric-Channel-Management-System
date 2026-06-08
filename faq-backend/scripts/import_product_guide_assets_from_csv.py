"""Upsert product guide asset rows from a CSV template."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_SOURCE = WORKSPACE_ROOT / "tmp" / "product_guide_assets_template.csv"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import AsyncSessionLocal, close_db
from app.models.guide import ProductGuideAsset, ProductGuideNode


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def _split_multi_value(value: str | None) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []

    parts = re.split(r"(?:\r?\n|\|+|；|;)", text)
    return [item.strip() for item in parts if item and item.strip()]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import product guide asset rows from a CSV file.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source CSV path")
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"CSV file not found: {source_path}")

    try:
        async with AsyncSessionLocal() as session:
            node_result = await session.execute(select(ProductGuideNode))
            asset_result = await session.execute(select(ProductGuideAsset))

            nodes = node_result.scalars().all()
            assets = asset_result.scalars().all()

            node_by_id = {node.id: node for node in nodes}
            node_by_key = {(node.product_key, node.node_key): node for node in nodes}
            asset_by_slot = {
                (asset.node_id, asset.asset_type, asset.sort_order): asset
                for asset in assets
            }

            inserted = 0
            updated = 0
            skipped_blank = 0

            with source_path.open("r", encoding="utf-8-sig", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    cos_urls = _split_multi_value(row.get("cos_url"))
                    if not cos_urls:
                        skipped_blank += 1
                        continue

                    node_id = _parse_int(row.get("node_id"), default=0)
                    product_key = _normalize_text(row.get("product_key"))
                    node_key = _normalize_text(row.get("node_key"))
                    asset_type = _normalize_text(row.get("asset_type")) or "image"
                    title = _normalize_text(row.get("title"))
                    titles = _split_multi_value(title)
                    sort_order = _parse_int(row.get("sort_order"), default=0)

                    node = node_by_id.get(node_id)
                    if node is None:
                        node = node_by_key.get((product_key, node_key))
                    if node is None:
                        raise ValueError(
                            f"Cannot match guide node for row: product_key={product_key}, "
                            f"node_key={node_key}, node_id={node_id}"
                        )

                    for offset, cos_url in enumerate(cos_urls):
                        asset_sort_order = sort_order + offset
                        slot_key = (node.id, asset_type, asset_sort_order)
                        asset = asset_by_slot.get(slot_key)
                        if asset is None:
                            asset = ProductGuideAsset(
                                node_id=node.id,
                                asset_type=asset_type,
                                sort_order=asset_sort_order,
                            )
                            session.add(asset)
                            asset_by_slot[slot_key] = asset
                            inserted += 1
                        else:
                            updated += 1

                        if len(titles) == len(cos_urls):
                            asset_title = titles[offset]
                        elif titles:
                            asset_title = titles[0]
                        else:
                            asset_title = title or node.label

                        asset.title = asset_title or node.label
                        asset.cos_url = cos_url
                        asset.is_active = True

            await session.commit()

        print(
            json.dumps(
                {
                    "source": str(source_path),
                    "inserted": inserted,
                    "updated": updated,
                    "skipped_blank": skipped_blank,
                },
                ensure_ascii=False,
            )
        )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
