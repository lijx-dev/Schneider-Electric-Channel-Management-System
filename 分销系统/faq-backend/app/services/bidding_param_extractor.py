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
        r'盐雾.*?(\d{3,4})\s*(小时|h|H).*?盐雾',
        r'(\d{3,4})\s*(小时|h|H).*?盐雾',
        # 新增：数字紧跟"小时"无空格（表格/紧凑格式）
        r'盐雾.*?[≥≥]?\s*(\d{3,4})(小时|h|H)',
        r'不低于\s*(\d{3,4})(小时|h|H).*?盐雾',
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
        # 新增："至少 X 年...经验"、"X 年生产供应经验" 等E-11文件格式
        r'至少\s*(\d+)\s*年.*?(?:经验|证明)',
        r'专业生产.*?(\d+)\s*年.*?(?:经验|供应|生产)',
        r'提供.*?(\d+)\s*年.*?(?:生产|供应|制造).*?经验',
        r'(\d+)\s*年.*?(?:生产供应|制造|生产).*?经验',
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
        r'(?:铜排|导体|导电排).*?厚度.*?[≥≥]?\s*(\d+\.?\d*)\s*(mm|毫米|㎜)',
        r'厚度.*?不低于\s*(\d+\.?\d*)\s*(mm|毫米|㎜)',
        r'(?:铜排|导体).*?≥\s*(\d+\.?\d*)\s*(mm|毫米|㎜)',
        r'铜排厚度.*?[≥≥]?\s*(\d+\.?\d*)\s*(mm|毫米|㎜)',
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
        # 新增："9烈度"紧凑格式（框招文件）
        r'不低于\s*(\d+)\s*烈度',
        r'(\d+)\s*烈度',
        r'抗震.*?设防.*?(\d+)\s*烈度',
    ],
    # --- 导率截面积 ---
    "导体截面积": [
        r'[Ss].*?[≥≥]?\s*(\d{3,4})\s*(mm2|mm²|平方毫米)',
        r'截面积.*?[≥≥]?\s*(\d{3,4})\s*(mm2|mm²|平方毫米)',
        r'导体截面.*?[≥≥]?\s*(\d{3,4})\s*(mm2|mm²|平方毫米)',
        r'铜排截面.*?[≥≥]?\s*(\d{3,4})\s*(mm2|mm²|平方毫米)',
        # 新增：表格行格式（如 "1 800 ≥200 mm2"）及紧凑格式（≥Xmm2），要求3-4位数
        r'[≥≥]\s*(\d{3,4})\s*(mm2|mm²|平方毫米)?',
        r'截面积要求.*?[≥≥]?\s*(\d{3,4})\s*(mm2|mm²|平方毫米)?',
        r'(?:单相母线容量|电流).*?(?:A|安).*?[≥≥]\s*(\d{3,4})',
    ],
    # --- 连接器力矩 ---
    "连接器力矩": [
        r'(?:力矩|扭矩).*?[≥≥]?\s*(\d+\.?\d*)\s*(N\.m|N·m|Nm|N\.M)',
        r'(?:力矩螺栓|定扭矩).*?[≥≥]?\s*(\d+\.?\d*)\s*(N\.m|N·m|Nm|N\.M)',
        # 新增："不应小于 72N.m" 等宽松格式
        r'(?:不应小于|不低于|≥)\s*(\d+\.?\d*)\s*(N\.m|N·m|Nm|N\.M)',
        r'额定压接力矩.*?(\d+\.?\d*)\s*(N\.m|N·m|Nm|N\.M)',
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
# 支持：表头顺序（容量 | 短时耐受kA | 峰值耐受kA）以及散文字句
# 【性能优化】严禁 re.DOTALL + 无限制 .*?，会触发灾难性回溯；统一限定在单行内最多80字符
# ============================================================
_AMPERE_PATTERN = re.compile(
    r'(?:序号[^\n\r]{0,20})?(\d{3,4})\s*[Aa][^\n\r]{0,80}?'
    r'(?:额定短时耐受|短时耐受|Icw)?[^\n\r]{0,20}?[≥≥]?\s*(\d{2,3})\s*(?:KA|kA|千安)',
    re.IGNORECASE,
)
_PEAK_PATTERN = re.compile(
    r'(?:序号[^\n\r]{0,20})?(\d{3,4})\s*[Aa][^\n\r]{0,80}?'
    r'(?:额定峰值耐受|峰值耐受|峰值|Ipk)?[^\n\r]{0,20}?[≥≥]?\s*(\d{2,3})\s*(?:KA|kA|千安)',
    re.IGNORECASE,
)
# 额外：表格行格式（容量 短时值 峰值值），从行尾回溯匹配
_TABLE_ROW_AMPERE_PATTERN = re.compile(
    r'^\s*\d+\s+(\d{3,4})\s+(\d{2,3})\s+(\d{2,3})\s*$',
    re.MULTILINE,
)


def _find_page(text: str, position: int) -> int:
    """根据文本位置查找所在页码。"""
    before = text[:position]
    page_markers = re.findall(r"=== 第(\d+)页 ===", before)
    return int(page_markers[-1]) if page_markers else 0


def _normalize_unit(unit: str) -> str:
    """标准化单位名称。"""
    unit_map = {
        "h": "小时", "H": "小时", "小时": "小时",
        "min": "分钟", "分钟": "分钟",
        "年": "年",
        "mm": "mm", "毫米": "mm", "㎜": "mm",  # 兼容全角毫米符号
        "米": "m", "m": "m",
        "KA": "KA", "kA": "KA", "ka": "KA", "千安": "KA",
        "V": "V", "v": "V",
        "N.m": "N.m", "N·m": "N.m", "Nm": "N.m", "N.M": "N.m",
    }
    return unit_map.get(unit, unit)


def _detect_operator(raw: str, match_start: int, match_end: int) -> str:
    """检测运算符（≥, ≤, >, <, =, 范围）。
    搜索范围覆盖：匹配位置前50字符 + 匹配文本本身 + 匹配后20字符。
    兼容 PDF 换行导致的词组拆分（如"不\n低于"、"不 低于"等）。"""
    search_start = max(0, match_start - 50)
    search_end = min(len(raw), match_end + 20)
    window = raw[search_start:search_end]
    after = raw[match_end:search_end]

    # 规范化窗口（去空白/换行/全角空格，便于"不 低于""不\n低于"这类拆分词组匹配）
    def _norm(s: str) -> str:
        return ''.join(ch for ch in s if ch and not ch.isspace())

    norm = _norm(window)
    norm_after = _norm(after)

    if ("≥" in window or ">=" in window
            or "不低于" in norm or "不小于" in norm or "不应小于" in norm or "至少" in norm):
        return "≥"
    if ("≤" in window or "<=" in window
            or "不超过" in norm or "不大于" in norm or "不应大于" in norm
            or "至多" in norm or "最多" in norm):
        return "≤"
    if ">" in window:
        return ">"
    if "<" in window:
        return "<"
    if "以上" in norm_after or "不低于" in norm_after:
        return "≥"
    if "以下" in norm_after or "不超过" in norm_after or "以内" in norm_after:
        return "≤"
    return "="


def _normalize_pdf_text_for_regex(text: str) -> str:
    """
    预处理 PDF 提取的原文：移除中文字词之间被 PDF 分页/断行插入的单个换行符。
    典型场景："不\n低于"、"厚\n度"、"生产供应\n的经验" 等，这些换行在语义上不应该存在，
    会导致正则 `.*?` 在非 DOTALL 模式下断链，从而提取失败。
    保留双换行（段落分隔）、行末数字后换行、英文间换行、==页码标记== 前后换行。
    """
    # 先把 \r\n 统一成 \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # 规则：左侧字符是中文/中文标点，右侧字符也是中文/中文标点，中间只有一个 \n → 合并
    # 这样不会影响"4\n㎜"、"IP54\n2.2" 这种数字-符号-中文的正常断行
    text = re.sub(
        r'(?<=[\u4e00-\u9fff，。；：、（）【】《》""''!?·—…-])\n(?=[\u4e00-\u9fff，。；：、（）【】《》""''!?·—…-])',
        '',
        text,
    )
    return text


def _operator_strictness(op: str) -> int:
    """严格性优先级（严格=提供更多判定信息）。数字越大越优先作为相同参数的 canonical。"""
    return {"≥": 3, "≤": 3, ">": 2, "<": 2, "=": 1}.get(op, 0)


def extract_all_params(text: str) -> dict[str, list[ExtractedParam]]:
    """
    从文本中提取所有参数。

    返回:
        { "盐雾试验时间": [ExtractedParam, ...], "制造经验年限": [...], ... }
    """
    results: dict[str, list[ExtractedParam]] = {}

    # 对 PDF 断行的中文字词做正则友好化（保留原文用于后续 context 展示，副本用于 re 匹配）
    regex_text = _normalize_pdf_text_for_regex(text)

    for param_name, patterns in PARAM_PATTERNS.items():
        # 改为 dict 存：key=(value,unit) -> ExtractedParam，支持"相同参数取更严格 operator"覆盖
        extracted_map: dict[tuple[float, str], ExtractedParam] = {}

        for pattern in patterns:
            for m in re.finditer(pattern, regex_text, re.IGNORECASE):
                groups = m.groups()
                if not groups or groups[0] is None:
                    continue
                value_str = groups[0]
                unit = _normalize_unit(groups[1]) if len(groups) > 1 and groups[1] else ""

                try:
                    value = float(value_str)
                except ValueError:
                    continue

                # ---- 参数特定的合理性过滤 & 默认单位补齐 ----
                if param_name == "导体截面积" and value < 100:
                    continue
                if param_name == "制造经验年限" and not unit:
                    unit = "年"

                page = _find_page(regex_text, m.start())
                operator = _detect_operator(regex_text, m.start(), m.end())

                key = (value, unit)
                existing = extracted_map.get(key)
                if existing is not None:
                    # 同值同单位时，保留更严格的 operator（含 operator 的项比纯 = 更具信息量）
                    if _operator_strictness(operator) <= _operator_strictness(existing.operator):
                        continue
                    # 用更严格的 operator 覆盖旧条目（同时更新 context/page 信息为更匹配这一项的值）
                ctx_start = max(0, m.start() - 40)
                ctx_end = min(len(regex_text), m.end() + 40)
                context = regex_text[ctx_start:ctx_end].replace("\n", " ").strip()

                extracted_map[key] = ExtractedParam(
                    name=param_name,
                    raw_value=m.group(0).strip()[:50],
                    value=value,
                    unit=unit,
                    operator=operator,
                    context=context,
                    page=page,
                )

        if extracted_map:
            results[param_name] = list(extracted_map.values())

    # --- 额外提取：按安培分档的短时耐受和峰值耐受（统一用正则友好文本） ---
    seen_amperes_short: set[int] = set()
    ampere_results: list[dict] = []
    for m in _AMPERE_PATTERN.finditer(regex_text):
        amp = int(m.group(1))
        if amp in seen_amperes_short:
            continue
        seen_amperes_short.add(amp)
        ampere_results.append({
            "ampere": amp,
            "short_time_current": int(m.group(2)),
            "unit": "KA",
            "page": _find_page(regex_text, m.start()),
        })

    seen_amperes_peak: set[int] = set()
    peak_results: list[dict] = []
    for m in _PEAK_PATTERN.finditer(regex_text):
        amp = int(m.group(1))
        if amp in seen_amperes_peak:
            continue
        seen_amperes_peak.add(amp)
        peak_results.append({
            "ampere": amp,
            "peak_current": int(m.group(2)),
            "unit": "KA",
            "page": _find_page(regex_text, m.start()),
        })

    # 表格行格式补充："序号 容量A 短时kA 峰值kA" 四列
    for m in _TABLE_ROW_AMPERE_PATTERN.finditer(regex_text):
        amp = int(m.group(1))
        if amp not in seen_amperes_short:
            ampere_results.append({
                "ampere": amp,
                "short_time_current": int(m.group(2)),
                "unit": "KA",
                "page": _find_page(regex_text, m.start()),
            })
            seen_amperes_short.add(amp)
        if amp not in seen_amperes_peak:
            peak_results.append({
                "ampere": amp,
                "peak_current": int(m.group(3)),
                "unit": "KA",
                "page": _find_page(regex_text, m.start()),
            })
            seen_amperes_peak.add(amp)

    if ampere_results:
        results["短时耐受电流_按安培"] = ampere_results  # type: ignore[assignment]
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