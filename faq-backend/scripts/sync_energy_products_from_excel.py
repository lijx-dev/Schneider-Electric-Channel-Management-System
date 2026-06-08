"""Add/update energy mall products from an Excel product list and local images.

Usage:
    python -m scripts.sync_energy_products_from_excel --dry-run
    python -m scripts.sync_energy_products_from_excel --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote

import xlrd
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal, close_db, init_db
from app.models.energy_product import EnergyProduct
from app.services.energy import ENERGY_PRODUCT_TIERS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXCEL = (
    r"C:\Users\86135\Documents\WeChat Files\wxid_stm8la2kv7jr22"
    r"\FileStorage\File\2026-06\产品清单5.29.xls"
)
DEFAULT_IMAGE_DIR = ROOT / "商品图" / "商品图-update"
SEED_FILE = ROOT / "faq-backend" / "scripts" / "energy_products_seed.json"

ART_BY_CATEGORY = {
    "潮流数码": ("数码", "art-digital"),
    "健康管理": ("健康", "art-health"),
    "米面粮油": ("粮油", "art-grocery"),
    "商务办公": ("办公", "art-office"),
    "生活日用": ("日用", "art-life"),
    "运动户外": ("户外", "art-outdoor"),
}


@dataclass(frozen=True)
class SourceProduct:
    name: str
    cost: int
    category: str
    source_row: int
    image_path: Path


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def round_cost(value: object) -> int:
    decimal = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(decimal)


def product_id_for(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"p20260529_{digest}"


def tier_label_for(cost: int) -> str:
    for tier in ENERGY_PRODUCT_TIERS:
        if cost >= int(tier["min_cost"]) and (tier["max_cost"] is None or cost <= int(tier["max_cost"])):
            return str(tier["tier_label"])
    return ""


def load_target_image_names(image_dir: Path) -> dict[str, Path]:
    images: dict[str, Path] = {}
    for path in image_dir.glob("*"):
        if path.is_file():
            images[normalize_name(path.stem)] = path
    return images


def load_excel_products(excel_path: Path, image_dir: Path) -> tuple[list[SourceProduct], list[str]]:
    images = load_target_image_names(image_dir)
    book = xlrd.open_workbook(str(excel_path))
    sheet = book.sheet_by_index(0)
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    header_map = {header: index for index, header in enumerate(headers)}
    missing = [header for header in ("产品名称", "产品价格", "礼品类别") if header not in header_map]
    if missing:
        raise RuntimeError(f"Excel 缺少必要列: {', '.join(missing)}")

    rows_by_name: dict[str, tuple[str, object, str, int]] = {}
    for row_index in range(1, sheet.nrows):
        name = str(sheet.cell_value(row_index, header_map["产品名称"])).strip()
        if not name:
            continue
        rows_by_name[normalize_name(name)] = (
            name,
            sheet.cell_value(row_index, header_map["产品价格"]),
            str(sheet.cell_value(row_index, header_map["礼品类别"])).strip(),
            row_index + 1,
        )

    matched: list[SourceProduct] = []
    missing_names: list[str] = []
    for normalized, image_path in sorted(images.items(), key=lambda item: item[1].name):
        row = rows_by_name.get(normalized)
        if not row:
            missing_names.append(image_path.stem)
            continue
        name, price, category, source_row = row
        matched.append(
            SourceProduct(
                name=name,
                cost=round_cost(price),
                category=category,
                source_row=source_row,
                image_path=image_path,
            )
        )
    return matched, missing_names


def upload_image_to_cos(product: SourceProduct) -> str:
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=settings.COS_REGION,
        SecretId=settings.COS_SECRET_ID,
        SecretKey=settings.COS_SECRET_KEY,
        Token=settings.COS_SESSION_TOKEN,
        Scheme="https",
    )
    client = CosS3Client(config)
    object_key = f"商品图-update/{product.image_path.name}"
    content_type = mimetypes.guess_type(product.image_path.name)[0] or "image/jpeg"
    client.put_object(
        Bucket=settings.COS_BUCKET,
        Body=product.image_path.read_bytes(),
        Key=object_key,
        ContentType=content_type,
    )
    return f"https://{settings.COS_BUCKET}.cos.{settings.COS_REGION}.myqcloud.com/{quote(object_key)}"


def to_seed_item(product: SourceProduct, image_url: str, sort_order: int) -> dict[str, object]:
    art_label, art_class = ART_BY_CATEGORY.get(product.category, ("礼品", "art-life"))
    return {
        "product_id": product_id_for(product.name),
        "name": product.name,
        "description": f"礼品类别：{product.category}",
        "category": product.category,
        "cost": product.cost,
        "image_url": image_url,
        "badge": "",
        "tag": product.category,
        "art_label": art_label,
        "art_class": art_class,
        "sort_order": sort_order,
        "is_featured": False,
        "is_active": True,
    }


def resequence_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
    def tier_index(item: dict[str, object]) -> int:
        cost = int(item.get("cost") or 0)
        for tier in ENERGY_PRODUCT_TIERS:
            if cost >= int(tier["min_cost"]) and (tier["max_cost"] is None or cost <= int(tier["max_cost"])):
                return int(tier["tier"])
        return 999

    sorted_items = sorted(
        items,
        key=lambda item: (
            tier_index(item),
            int(item.get("cost") or 0),
            str(item.get("name") or ""),
            str(item.get("product_id") or ""),
        ),
    )
    for index, item in enumerate(sorted_items, 1):
        item["sort_order"] = index
    return sorted_items


async def sync_database(seed_items: list[dict[str, object]]) -> None:
    async with AsyncSessionLocal() as session:
        existing_result = await session.execute(select(EnergyProduct))
        existing_by_product_id = {item.product_id: item for item in existing_result.scalars().all()}

        for item in seed_items:
            product_id = str(item["product_id"])
            product = existing_by_product_id.get(product_id)
            if not product:
                session.add(EnergyProduct(**item))
                continue
            for key, value in item.items():
                if key == "id":
                    continue
                setattr(product, key, value)
        await session.commit()


def print_tier_preview(items: list[dict[str, object]]) -> None:
    for tier in ENERGY_PRODUCT_TIERS:
        tier_items = [
            item
            for item in items
            if int(item["cost"]) >= int(tier["min_cost"])
            and (tier["max_cost"] is None or int(item["cost"]) <= int(tier["max_cost"]))
        ]
        costs = [int(item["cost"]) for item in tier_items]
        print(f"{tier['tier_label']}: {len(tier_items)} items, sorted={costs == sorted(costs)}, costs={costs}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=DEFAULT_EXCEL)
    parser.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        raise SystemExit("Choose either --apply or --dry-run, not both.")

    excel_path = Path(args.excel)
    image_dir = Path(args.image_dir)
    source_products, missing_names = load_excel_products(excel_path, image_dir)
    if missing_names:
        raise RuntimeError(f"以下图片名称未在 Excel 中匹配到商品: {missing_names}")

    await init_db()
    try:
        async with AsyncSessionLocal() as session:
            current_db_items = [
                {
                    "product_id": product.product_id,
                    "name": product.name,
                    "description": product.description,
                    "category": product.category,
                    "cost": product.cost,
                    "image_url": product.image_url,
                    "badge": product.badge,
                    "tag": product.tag,
                    "art_label": product.art_label,
                    "art_class": product.art_class,
                    "sort_order": product.sort_order,
                    "is_featured": bool(product.is_featured),
                    "is_active": bool(product.is_active),
                }
                for product in (await session.execute(select(EnergyProduct))).scalars().all()
            ]

        existing_by_name = {normalize_name(str(item["name"])): item for item in current_db_items}
        additions = [product for product in source_products if normalize_name(product.name) not in existing_by_name]
        updates = [product for product in source_products if normalize_name(product.name) in existing_by_name]

        print(f"Matched source products: {len(source_products)}")
        for product in source_products:
            print(f"- row {product.source_row}: {product.name} | {product.cost} | {product.category} | {tier_label_for(product.cost)}")
        print(f"Will add: {len(additions)}")
        print(f"Already exists/update metadata: {len(updates)}")

        next_items = list(current_db_items)
        if args.apply:
            uploaded_urls = {product.name: upload_image_to_cos(product) for product in source_products}
        else:
            uploaded_urls = {product.name: "" for product in source_products}

        by_name_index = {normalize_name(str(item["name"])): index for index, item in enumerate(next_items)}
        for product in source_products:
            image_url = uploaded_urls[product.name]
            if normalize_name(product.name) in by_name_index:
                item = next_items[by_name_index[normalize_name(product.name)]]
                item.update(to_seed_item(product, image_url or str(item.get("image_url") or ""), int(item.get("sort_order") or 0)))
            else:
                next_items.append(to_seed_item(product, image_url, len(next_items) + 1))

        next_items = resequence_items(next_items)
        print("\nTier preview after resequence:")
        print_tier_preview([item for item in next_items if bool(item.get("is_active", True))])

        if not args.apply:
            print("\nDry run only. Re-run with --apply to upload images and write DB/seed JSON.")
            return

        SEED_FILE.write_text(json.dumps(next_items, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        await sync_database(next_items)
        print(f"\nWrote seed file: {SEED_FILE}")
        print("Database updated.")
    finally:
        await close_db()


if __name__ == "__main__":
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    asyncio.run(main())
