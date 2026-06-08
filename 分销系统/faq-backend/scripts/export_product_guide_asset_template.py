"""Export active leaf nodes into a CSV template for manual COS URL entry."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
DEFAULT_OUTPUT = WORKSPACE_ROOT / "tmp" / "product_guide_assets_template.csv"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import AsyncSessionLocal, close_db
from app.models.guide import ProductGuideAsset, ProductGuideNode


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _build_path(node: ProductGuideNode, node_map: dict[int, ProductGuideNode]) -> str:
    labels: list[str] = []
    current: ProductGuideNode | None = node
    while current is not None:
        labels.append(_normalize_text(current.label) or _normalize_text(current.node_key))
        current = node_map.get(current.parent_id) if current.parent_id else None
    return " / ".join(reversed(labels))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export product guide leaf nodes into a CSV template.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Target CSV output path")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        async with AsyncSessionLocal() as session:
            node_result = await session.execute(
                select(ProductGuideNode)
                .where(ProductGuideNode.is_active.is_(True))
                .order_by(
                    ProductGuideNode.product_key.asc(),
                    ProductGuideNode.parent_id.asc(),
                    ProductGuideNode.sort_order.asc(),
                    ProductGuideNode.id.asc(),
                )
            )
            asset_result = await session.execute(
                select(ProductGuideAsset)
                .where(ProductGuideAsset.is_active.is_(True))
                .order_by(
                    ProductGuideAsset.node_id.asc(),
                    ProductGuideAsset.sort_order.asc(),
                    ProductGuideAsset.id.asc(),
                )
            )

            nodes = node_result.scalars().all()
            assets = asset_result.scalars().all()

            node_map = {node.id: node for node in nodes}
            assets_by_node_id: dict[int, list[ProductGuideAsset]] = {}
            for asset in assets:
                assets_by_node_id.setdefault(asset.node_id, []).append(asset)

            rows: list[dict[str, str | int]] = []
            leaf_count = 0

            for node in nodes:
                if node.node_type != "leaf":
                    continue

                leaf_count += 1
                base_row = {
                    "product_key": node.product_key,
                    "node_id": node.id,
                    "node_key": node.node_key,
                    "path": _build_path(node, node_map),
                    "label": node.label,
                    "response_mode": node.response_mode,
                }
                node_assets = assets_by_node_id.get(node.id) or []

                if node_assets:
                    for asset in node_assets:
                        rows.append(
                            {
                                **base_row,
                                "asset_type": asset.asset_type,
                                "title": _normalize_text(asset.title) or node.label,
                                "sort_order": asset.sort_order,
                                "cos_url": _normalize_text(asset.cos_url),
                            }
                        )
                    continue

                rows.append(
                    {
                        **base_row,
                        "asset_type": "image",
                        "title": node.label,
                        "sort_order": 0,
                        "cos_url": "",
                    }
                )

        with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(
                fp,
                fieldnames=[
                    "product_key",
                    "node_id",
                    "node_key",
                    "path",
                    "label",
                    "response_mode",
                    "asset_type",
                    "title",
                    "sort_order",
                    "cos_url",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        print(
            json.dumps(
                {
                    "output": str(output_path),
                    "leaf_nodes": leaf_count,
                    "rows": len(rows),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
