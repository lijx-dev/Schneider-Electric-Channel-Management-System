"""
投标文件参数提取器
从招标文件文本中提取数值型参数，支持单位识别、范围比较和领域取值。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedParam:
    """提取到的参数"""
    name: str           # 参数名称（如 "盐雾试验时间"）
    raw_value: str      # 原始匹配到的值（如 "≥2400"）
    value: float        # 数值
    unit: str           # 单位（如 "小时"）
    operator: str       # 运算符（≥, ≤, >, <, =, 范围）
    context: str        # 上下文文本（前后80字）
    page: int           # 所在页码（0 表示未知）


# ============================================================
# 参数提取正则模式库
# 每个参数包含多个正则模式，按优先级排列
# ============================================================
PARAM_PATTERNS: dict[str, list[str]] = {
    # --- 盐雾 ---
    "盐雾试验时间": [
        r'盐雾[试验|测试|等级|要求|认证].*?[≥≥]?\s*(\d{3,4})\s*(小时|h|H)',
        r'耐腐蚀.*?[≥≥]?\s*(\d{3,4})\s*(小时|h|H)',
        r'盐雾.*?不低于\s*(\d{3,4})\s*(小时|h)',
        r'盐雾.*?≥\s*(\d{3,4})\s*(小时|h)',
        r'盐雾.*?(\d{3,4})\s*小时.*?盐雾',
        r'(\d{3,4})\s*小时.*?盐雾',
    ],
    # --- 制造经验 ---
    "制造经验年限": [
        r'(?:制造|生产).*?经验.*?[≥≥]?\s*(\d+)\s*年',
        r'从事.*?母线.*?[≥≥]?\s*(\d+)\s*年',
        r'从事.*?生产.*?母线.*?[≥≥]?\s*(\d+)\s*年',
        r'成立.*?[≥≥]?\s*(\d+)\s*年',
        r'经营.*?年限.*?[≥≥]?\s*(\d+)\s*年',
        r'制造.*?历史.*?[≥≥]?\s*(\d+)\s*年',
        r'制造商.*?资格.*?[≥≥]?\s*(\d+)\s*年',
        r'生产.*?母线.*?[≥≥]?\s*(\d+)\s*年',
        r'制造商.*?具备.*?(\d+)\s*年.*?以上',
        r'具备.*?(\d+)\s*年.*?以上.*?制造',
        r'应.*?(\d+)\s*年.*?以上.*?制造',
        r'(\d+)\s*年.*?以上.*?制造.*?经验',
    ],
    # --- 短时耐受电流 ---
    "短时耐受电流": [
        r'短时耐受.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
        r'Icw.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
        r'额定短时耐受.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
    ],
    # --- 峰值耐受电流 ---
    "峰值耐受电流": [
        r'峰值耐受.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
        r'Ipk.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
        r'额定峰值.*?[≥≥]?\s*(\d+)\s*(KA|kA)',
    ],
    # --- 导体厚度 ---
    "导体厚度": [
        r'(?:铜排|导体|导电排).*?厚度.*?[≥≥]?\s*(\d+\.?\d*)\s*(mm|毫米)',
        r'厚度.*?不低于\s*(\d+\.?\d*)\s*(mm|毫米)',
        r'(?:铜排|导体).*?≥\s*(\d+\.?\d*)\s*(mm|毫米)',
        r'铜排厚度.*?[≥≥]?\s*(\d+\.?\d*)\s*(mm|毫米)',
    ],
    # --- IK碰撞等级 ---
    "IK碰撞等级": [
        r'IK\s*(\d{2})',
        r'碰撞.*?防护.*?IK\s*(\d{2})',
        r'机械碰撞.*?IK\s*(\d{2})',
        r'IK\s*代码.*?IK\s*(\d{2})',
    ],
    # --- IP防护等级 ---
    "IP防护等级": [
        r'(?:防护等级|外壳防护).*?[≥≥]?\s*IP\s*(\d{2})',
        r'IP\s*(\d{2}).*?(?:防护|等级)',
        r'(?:不低于|≥)\s*IP\s*(\d{2})',
    ],
    # --- 消防喷淋 ---
    "消防喷淋时间": [
        r'消防喷淋.*?(\d+)\s*(小时|分钟|h|min)',
        r'喷淋.*?试验.*?(\d+)\s*(小时|分钟|h|min)',
        r'消防.*?喷淋.*?[≥≥]?\s*(\d+)\s*(小时|h)',
        r'喷淋.*?检测.*?(\d+)\s*(小时|分钟|h|min)',
    ],
    # --- 耐火时间 ---
    "耐火时间": [
        r'耐火.*?(\d+)\s*(分钟|min|小时|h)',
        r'XF/T537.*?(\d+)\s*(分钟|min)',
        r'J19216.*?(\d+)\s*(分钟|min)',
        r'耐火.*?等级.*?(\d+)\s*(分钟|min|小时|h)',
        r'线路完整性.*?(\d+)\s*℃.*?(\d+)\s*(分钟|min)',
    ],
    # --- 绝缘老化 ---
    "绝缘老化时间": [
        r'老化.*?[≥≥]?\s*(\d+)\s*(小时|h)',
        r'(\d+)\s*小时.*?老化',
        r'绝缘.*?老化.*?[≥≥]?\s*(\d+)\s*(小时|h)',
    ],
    # --- 抗震等级 ---
    "抗震等级": [
        r'AG\s*(\d+)',
        r'ZPA.*?[≥≥]?\s*(\d+\.?\d*)\s*g',
        r'里氏\s*(\d+)\s*级',
        r'烈度\s*(\d+)\s*度',
        r'抗震.*?设防.*?(\d+)\s*度',
        r'抗震.*?等级.*?(\d+)\s*级',
    ],
    # --- 导率截面积 ---
    "导体截面积": [
        r'[Ss].*?[≥≥]?\s*(\d+)\s*mm2',
        r'截面积.*?[≥≥]?\s*(\d+)\s*mm2',
        r'导体截面.*?[≥≥]?\s*(\d+)\s*mm2',
        r'铜排截面.*?[≥≥]?\s*(\d+)\s*mm2',
    ],
    # --- 连接器力矩 ---
    "连接器力矩": [
        r'(?:力矩|扭矩).*?[≥≥]?\s*(\d+\.?\d*)\s*(?:N\.m|N·m|Nm)',
        r'(?:力矩螺栓|定扭矩).*?[≥≥]?\s*(\d+\.?\d*)\s*(?:N\.m|N·m|Nm)',
    ],
    # --- 额定工作电压 ---
    "额定工作电压": [
        r'额定工作电压.*?(\d+)\s*V',
        r'额定电压.*?(\d+)\s*V\s*(?:AC|ac)',
    ],
    # --- 额定绝缘电压 ---
    "额定绝缘电压": [
        r'额定绝缘电压.*?[≥≥]?\s*(\d+)\s*V',
        r'绝缘电压.*?[≥≥]?\s*(\d+)\s*V',
    ],
    # --- 中性线容量 ---
    "中性线容量": [
        r'中性线.*?容量.*?(\d+)\s*%',
        r'N线.*?(\d+)\s*%.*?相线',
        r'100%.*?中性线|中性线.*?100%',
    ],
    # --- 导体纯度 ---
    "铜导体纯度": [
        r'(?:铜|T2).*?纯度.*?(\d+\.?\d*)\s*%',
        r'导电率.*?(\d+\.?\d*)\s*%',
        r'铜含量.*?[≥≥]?\s*(\d+\.?\d*)\s*%',
    ],
    # --- 海拔高度 ---
    "海拔高度": [
        r'海拔.*?[≤≤]?\s*(\d+)\s*(米|m)',
        r'海拔.*?不超过\s*(\d+)\s*(米|m)',
    ],
    # --- 电阻率 ---
    "电阻率": [
        r'电阻率.*?[≤≤]?\s*(\d+\.?\d*)\s*(?:Ω·mm2/m|Ω\.mm2/m)',
        r'导电率.*?[≥≥]?\s*(\d+\.?\d*)\s*%',
    ],
}


# ============================================================
# 短时耐受电流和峰值耐受电流按安培分档提取
# 用于从参数表中提取各电流档位的耐受值
# ============================================================
_AMPERE_PATTERN = re.compile(
    r'(\d{3,4})\s*A.*?'
    r'(?:短时耐受|Icw).*?[≥≥]?\s*(\d+)\s*(?:KA|kA)',
    re.IGNORECASE,
)
_PEAK_PATTERN = re.compile(
    r'(\d{3,4})\s*A.*?'
    r'(?:峰值耐受|峰值|Ipk).*?[≥≥]?\s*(\d+)\s*(?:KA|kA)',
    re.IGNORECASE,
)


def _find_page(text: str, position: int) -> int:
    """根据文本位置查找所在页码。"""
    before = text[:position]
    page_markers = re.findall(r"=== 第(\d+)页 ===", before)
    return int(page_markers[-1]) if page_markers else 0


def _normalize_unit(unit: str) -> str:
    """标准化单位名称。"""
    unit_map = {
        "h": "小时", "H": "小时",
        "min": "分钟", "分钟": "分钟",
        "小时": "小时", "年": "年",
        "mm": "mm", "毫米": "mm",
        "米": "m", "m": "m",
        "KA": "KA", "kA": "KA",
        "V": "V",
    }
    return unit_map.get(unit, unit)


def _detect_operator(raw: str, match_start: int, match_end: int) -> str:
    """检测运算符（≥, ≤, >, <, =, 范围）。"""
    before = raw[max(0, match_start - 10):match_start]
    if "≥" in before or ">=" in before or "不低于" in before or "不小于" in before:
        return "≥"
    if "≤" in before or "<=" in before or "不超过" in before or "不大于" in before:
        return "≤"
    if ">" in before:
        return ">"
    if "<" in before:
        return "<"
    return "="


def extract_all_params(text: str) -> dict[str, list[ExtractedParam]]:
    """
    从文本中提取所有参数。

    返回:
        { "盐雾试验时间": [ExtractedParam, ...], "制造经验年限": [...], ... }
    """
    results: dict[str, list[ExtractedParam]] = {}

    for param_name, patterns in PARAM_PATTERNS.items():
        extracted: list[ExtractedParam] = []
        seen_values: set[tuple[float, str]] = set()

        for pattern in patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                groups = m.groups()
                if not groups or groups[0] is None:
                    continue
                value_str = groups[0]
                unit = _normalize_unit(groups[1]) if len(groups) > 1 and groups[1] else ""

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                # 去重
                key = (value, unit)
                if key in seen_values:
                    continue
                seen_values.add(key)

                # 获取上下文
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(text), m.end() + 40)
                context = text[ctx_start:ctx_end].replace("\n", " ").strip()

                page = _find_page(text, m.start())
                operator = _detect_operator(text, m.start(), m.end())

                extracted.append(ExtractedParam(
                    name=param_name,
                    raw_value=m.group(0).strip()[:50],
                    value=value,
                    unit=unit,
                    operator=operator,
                    context=context,
                    page=page,
                ))

        if extracted:
            results[param_name] = extracted

    # --- 额外提取：按安培分档的短时耐受和峰值耐受 ---
    ampere_results: list[dict] = []
    for m in _AMPERE_PATTERN.finditer(text):
        ampere_results.append({
            "ampere": int(m.group(1)),
            "short_time_current": int(m.group(2)),
            "unit": "KA",
            "page": _find_page(text, m.start()),
        })
    if ampere_results:
        results["短时耐受电流_按安培"] = ampere_results  # type: ignore[assignment]

    peak_results: list[dict] = []
    for m in _PEAK_PATTERN.finditer(text):
        peak_results.append({
            "ampere": int(m.group(1)),
            "peak_current": int(m.group(2)),
            "unit": "KA",
            "page": _find_page(text, m.start()),
        })
    if peak_results:
        results["峰值耐受电流_按安培"] = peak_results  # type: ignore[assignment]

    return results


def compare_param_with_schneider(
    param_name: str,
    extracted_value: float,
    extracted_unit: str,
    schneider_value: str,
) -> dict[str, Any]:
    """
    比较提取的参数值与施耐德产品参数。

    返回:
        {"status": "advantage"|"match"|"disadvantage"|"unknown",
         "detail": "解释说明"}
    """
    # 施耐德产品参数基准值
    SCHNEIDER_THRESHOLDS = {
        "盐雾试验时间": {"B": 1800, "H": 2000, "W": 1800, "unit": "小时", "higher_better": True},
        "制造经验年限": {"B": 15, "H": 15, "W": 15, "unit": "年", "higher_better": True},
        "IK碰撞等级": {"B": 10, "H": 10, "W": 8, "unit": "", "higher_better": True},
        "IP防护等级": {"B": 55, "H": 54, "W": 54, "unit": "", "higher_better": True},
        "导体厚度": {"B": 3, "H": 4, "W": 3, "unit": "mm", "higher_better": True},
        "连接器力矩": {"B": 95, "H": 80, "W": 80, "unit": "N.m", "higher_better": True},
        "绝缘老化时间": {"B": 5000, "H": 5000, "W": 3000, "unit": "小时", "higher_better": True},
        "消防喷淋时间": {"B": 1, "H": 1, "W": 1, "unit": "小时", "higher_better": True},
        "铜导体纯度": {"B": 99.9, "H": 99.9, "W": 99.9, "unit": "%", "higher_better": True},
    }

    threshold = SCHNEIDER_THRESHOLDS.get(param_name)
    if not threshold:
        return {"status": "unknown", "detail": "该参数暂无施耐德基准值"}

    higher_better = threshold.get("higher_better", True)
    # 取最严格的产品值作为基准
    if higher_better:
        best_value = max(v for k, v in threshold.items() if k != "unit" and k != "higher_better")
    else:
        best_value = min(v for k, v in threshold.items() if k != "unit" and k != "higher_better")

    if higher_better:
        if extracted_value >= best_value:
            return {"status": "advantage", "detail": f"标书要求{extracted_value}{extracted_unit}，我方产品满足（{best_value}{extracted_unit}），对施耐德有利"}
        elif extracted_value >= best_value * 0.7:
            return {"status": "match", "detail": f"标书要求{extracted_value}{extracted_unit}，我方产品{best_value}{extracted_unit}，基本满足"}
        else:
            return {"status": "disadvantage", "detail": f"标书要求{extracted_value}{extracted_unit}偏低，我方产品{best_value}{extracted_unit}优势无法体现"}
    else:
        if extracted_value <= best_value:
            return {"status": "advantage", "detail": f"标书要求{extracted_value}{extracted_unit}，我方产品满足（{best_value}{extracted_unit}），对施耐德有利"}
        else:
            return {"status": "disadvantage", "detail": f"标书要求{extracted_value}{extracted_unit}，我方产品{best_value}{extracted_unit}，可能不满足"}