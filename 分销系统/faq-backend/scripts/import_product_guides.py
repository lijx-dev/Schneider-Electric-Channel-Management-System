"""Import the mini-program quick-guide tree into product_guide_* tables."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import AsyncSessionLocal, close_db
from app.models.guide import ProductGuideNode


DEFAULT_SOURCE = (
    PROJECT_ROOT.parent / "faq-miniprogram" / "pages" / "zhinengwenda_AI_Assistant_Green" / "zhinengwenda_AI_Assistant_Green.js"
)
EXPORT_SCRIPT = PROJECT_ROOT / "scripts" / "export_product_guide_tree.js"


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _run_export(source_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(EXPORT_SCRIPT), str(source_path)],
        cwd=str(PROJECT_ROOT),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _infer_response_mode(node: dict[str, Any]) -> str:
    answer = _normalize_text(node.get("answer"))
    has_image = "![" in answer and "](" in answer
    text_without_markdown = answer.replace("\n", " ").strip()

    if has_image and text_without_markdown.startswith("!["):
        return "image"
    if has_image:
        return "mixed"
    return "text"


async def _sync_tree(tree: dict[str, Any], deactivate_missing: bool) -> tuple[int, int]:
    async with AsyncSessionLocal() as session:
        existing_result = await session.execute(select(ProductGuideNode))
        existing_nodes = existing_result.scalars().all()
        existing_map = {(node.product_key, node.node_key): node for node in existing_nodes}
        seen_keys: set[tuple[str, str]] = set()

        inserted = 0
        updated = 0

        async def sync_node(
            node_data: dict[str, Any],
            *,
            product_key: str,
            parent_id: int | None,
            sort_order: int,
        ) -> None:
            nonlocal inserted, updated

            node_key = _normalize_text(node_data.get("id"))
            if not node_key:
                return

            children = node_data.get("children") or []
            node_type = "branch" if children else "leaf"
            unique_key = (product_key, node_key)
            model = existing_map.get(unique_key)
            is_new = model is None

            if is_new:
                model = ProductGuideNode(product_key=product_key, node_key=node_key)
                session.add(model)
                existing_map[unique_key] = model
                inserted += 1
            else:
                updated += 1

            model.parent_id = parent_id
            model.label = _normalize_text(node_data.get("label")) or node_key
            model.node_type = node_type
            model.layout = _normalize_text(node_data.get("layout")) or None
            model.response_mode = _infer_response_mode(node_data)
            model.answer_text = _normalize_text(node_data.get("answer")) or None
            model.sort_order = sort_order
            model.is_active = True

            seen_keys.add(unique_key)
            await session.flush()

            for child_index, child in enumerate(children):
                await sync_node(
                    child,
                    product_key=product_key,
                    parent_id=model.id,
                    sort_order=child_index,
                )

        for root_index, child in enumerate(tree.get("children") or []):
            product_key = _normalize_text(child.get("id"))
            if not product_key:
                continue
            await sync_node(child, product_key=product_key, parent_id=None, sort_order=root_index)

        if deactivate_missing:
            for unique_key, node in existing_map.items():
                if unique_key not in seen_keys:
                    node.is_active = False

        await session.commit()
        return inserted, updated


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import product guide tree from the mini-program page file.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Source JS file containing PRODUCT_GUIDE_TREE")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Mark database nodes inactive when they are no longer present in the source tree",
    )
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Guide source file not found: {source_path}")
    if not EXPORT_SCRIPT.exists():
        raise FileNotFoundError(f"Guide export helper not found: {EXPORT_SCRIPT}")

    try:
        tree = _run_export(source_path)
        inserted, updated = await _sync_tree(tree, deactivate_missing=args.deactivate_missing)

        print(
            json.dumps(
                {
                    "source": str(source_path),
                    "inserted": inserted,
                    "updated": updated,
                    "deactivate_missing": bool(args.deactivate_missing),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
