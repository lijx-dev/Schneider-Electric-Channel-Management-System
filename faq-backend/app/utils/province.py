"""Province normalization helpers."""

from __future__ import annotations


SPECIAL_MAPPINGS = {
    "北京市": "北京",
    "上海市": "上海",
    "天津市": "天津",
    "重庆市": "重庆",
    "广西壮族自治区": "广西",
    "内蒙古自治区": "内蒙古",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "西藏自治区": "西藏",
    "香港特别行政区": "香港",
    "澳门特别行政区": "澳门",
}


def normalize_province_name(value: str | None) -> str:
    """Normalize province names for display and matching."""
    if value is None:
        return ""

    text = str(value).strip()
    if not text:
        return ""

    compact = "".join(text.split())
    if compact in SPECIAL_MAPPINGS:
        return SPECIAL_MAPPINGS[compact]

    if compact.endswith("省"):
        return compact[:-1]

    if compact.endswith("市") and compact[:-1] in {"北京", "上海", "天津", "重庆"}:
        return compact[:-1]

    return compact
