"""Product guide tree APIs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_rate_limit, get_current_user_id
from app.db.session import get_db
from app.models.guide import ProductGuideAsset, ProductGuideNode

router = APIRouter(tags=["product_guides"])

GUIDE_ROOT = {
    "id": "root",
    "label": "产品选择",
    "title": "常见问题快速导航",
    "hint": "请先选择具体产品，再逐级点击到你想咨询的问题。",
    "layout": "grid",
}

PLACEHOLDER_MARKERS = (
    "内容正在整理中",
    "这个产品的快捷导航正在整理中",
)


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _is_placeholder_text(value: str | None) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    return any(marker in text for marker in PLACEHOLDER_MARKERS)


def _build_leaf_answer(node: ProductGuideNode, assets: list[ProductGuideAsset]) -> str:
    answer_text = _normalize_text(node.answer_text)
    lines: list[str] = []

    # If the node only has generic placeholder text and later挂了图片，
    # 优先直接展示资源，避免用户还要额外改 answer_text。
    if answer_text and not (assets and _is_placeholder_text(answer_text)):
        lines.append(answer_text)

    for asset in assets:
        title = _normalize_text(asset.title) or node.label
        url = _normalize_text(asset.cos_url)
        if not url:
            continue

        if asset.asset_type == "image":
            lines.append(f"![{title}]({url})")
        else:
            lines.append(f"[{title}]({url})")

    if lines:
        return "\n".join(lines)

    if answer_text:
        return answer_text

    return "该节点暂未配置答案。"


def _serialize_node(node: ProductGuideNode, assets: list[ProductGuideAsset]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": node.node_key,
        "label": node.label,
    }

    if node.layout:
        payload["layout"] = node.layout

    if node.node_type == "leaf":
        payload["answer"] = _build_leaf_answer(node, assets)
        payload["answer_text"] = _normalize_text(node.answer_text)
        payload["response_mode"] = node.response_mode
        payload["assets"] = [
            {
                "id": asset.id,
                "type": asset.asset_type,
                "title": _normalize_text(asset.title) or node.label,
                "url": _normalize_text(asset.cos_url),
            }
            for asset in assets
            if _normalize_text(asset.cos_url)
        ]

    return payload


@router.get("/product-guides/tree")
async def get_product_guide_tree(
    db: AsyncSession = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    enforce_rate_limit("product_guides_tree", current_user_id, limit=60, window_seconds=60)

    node_stmt = (
        select(ProductGuideNode)
        .where(ProductGuideNode.is_active.is_(True))
        .order_by(
            case((ProductGuideNode.parent_id.is_(None), 0), else_=1),
            ProductGuideNode.parent_id.asc(),
            ProductGuideNode.sort_order.asc(),
            ProductGuideNode.id.asc(),
        )
    )
    asset_stmt = (
        select(ProductGuideAsset)
        .where(ProductGuideAsset.is_active.is_(True))
        .order_by(
            ProductGuideAsset.node_id.asc(),
            ProductGuideAsset.sort_order.asc(),
            ProductGuideAsset.id.asc(),
        )
    )

    node_result = await db.execute(node_stmt)
    asset_result = await db.execute(asset_stmt)

    nodes = node_result.scalars().all()
    assets = asset_result.scalars().all()

    assets_by_node_id: dict[int, list[ProductGuideAsset]] = defaultdict(list)
    for asset in assets:
        assets_by_node_id[asset.node_id].append(asset)

    serialized_by_id: dict[int, dict[str, Any]] = {}
    children_by_parent: dict[int | None, list[dict[str, Any]]] = defaultdict(list)

    for node in nodes:
        serialized = _serialize_node(node, assets_by_node_id.get(node.id, []))
        serialized_by_id[node.id] = serialized
        children_by_parent[node.parent_id].append(serialized)

    for node in nodes:
        children = children_by_parent.get(node.id, [])
        if children:
            serialized_by_id[node.id]["children"] = children

    return {
        "code": 0,
        "data": {
            **GUIDE_ROOT,
            "children": children_by_parent.get(None, []),
        },
    }
