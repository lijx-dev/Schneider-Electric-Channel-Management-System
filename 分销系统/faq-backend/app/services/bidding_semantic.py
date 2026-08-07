"""
招标文件语义分析模块
提供否定句式检测、条件句式解析、章节结构解析、同义词映射等功能。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# 否定句式模式
# 用于检测关键词是否处于否定语境中
# ============================================================
NEGATION_PATTERNS = [
    # 前置否定
    re.compile(r'(?:不应|不得|禁止|不允许|不可|不能|严禁|切勿|谢绝|拒绝).{0,20}?{keyword}', re.IGNORECASE),
    re.compile(r'(?:不\s*得|不\s*应|不\s*能).{0,20}?{keyword}', re.IGNORECASE),
    # 后置否定
    re.compile(r'{keyword}.{0,30}?(?:不接受|不被允许|不予考虑|不被认可|无效|不适用)', re.IGNORECASE),
    # 不接受OEM
    re.compile(r'(?:不接受|不允许|不采用|禁止).{0,10}?{keyword}', re.IGNORECASE),
]


def is_negated(text: str, keyword: str, context_window: int = 150) -> bool:
    """
    检测关键词是否处于否定语境中。

    返回 True 表示该关键词被否定（即不应出现/不应要求）。
    """
    # 在文本中定位关键词的位置
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return False

    # 提取上下文窗口
    start = max(0, idx - context_window)
    end = min(len(text), idx + len(keyword) + context_window)
    ctx = text[start:end]

    # 检查否定模式
    for pattern in NEGATION_PATTERNS:
        pattern_str = pattern.pattern.replace("{keyword}", re.escape(keyword))
        if re.search(pattern_str, ctx, re.IGNORECASE):
            return True

    return False


# ============================================================
# 条件句式解析
# ============================================================
CONDITION_PATTERNS = [
    re.compile(r'若.*?({keyword}).*?[，,].*?(?:需|应|须|必须|要求|提供).*?({requirement})', re.IGNORECASE),
    re.compile(r'如.*?({keyword}).*?[，,].*?(?:需|应|须|必须|要求|提供).*?({requirement})', re.IGNORECASE),
    re.compile(r'当.*?({keyword}).*?[，,].*?(?:需|应|须|必须|要求|提供).*?({requirement})', re.IGNORECASE),
    re.compile(r'({keyword}).*?时[，,].*?(?:需|应|须|必须|要求|提供).*?({requirement})', re.IGNORECASE),
]


def detect_conditional_requirements(text: str, keywords: list[str], requirements: list[str]) -> list[dict]:
    """
    检测条件句式中隐含的要求。

    例如："若采用OEM，需提供授权书" → {keyword: "OEM", requirement: "授权书", is_conditional: True}
    """
    results: list[dict] = []
    for kw in keywords:
        for req in requirements:
            for pattern in CONDITION_PATTERNS:
                pattern_str = pattern.pattern.replace("{keyword}", re.escape(kw)).replace("{requirement}", re.escape(req))
                for m in re.finditer(pattern_str, text, re.IGNORECASE):
                    results.append({
                        "keyword": kw,
                        "requirement": req,
                        "context": m.group(0).strip()[:100],
                        "is_conditional": True,
                    })
    return results


# ============================================================
# 章节结构解析
# ============================================================
@dataclass
class Section:
    """标书章节"""
    title: str
    level: int          # 1=章, 2=节, 3=小节
    start_pos: int
    end_pos: int
    page: int
    children: list[Section] = field(default_factory=list)


# 章节编号模式
SECTION_PATTERNS: list[tuple[re.Pattern, int]] = [
    # 第一章、第二章...
    (re.compile(r'^第[一二三四五六七八九十百]+章\s*.*$', re.MULTILINE), 1),
    # 6.9.2.3 编号体系
    (re.compile(r'^(\d+\.){2,}\d+\s+.*$', re.MULTILINE), 3),
    # 6.9 编号体系
    (re.compile(r'^\d+\.\d+\s+.*$', re.MULTILINE), 2),
    # （一）（二）...
    (re.compile(r'^[（(]\s*[一二三四五六七八九十]+\s*[）)]\s*.*$', re.MULTILINE), 2),
    # 一、二、三、...
    (re.compile(r'^[一二三四五六七八九十]+[、．.]\s*.*$', re.MULTILINE), 1),
    # 1. 2. 3. ...
    (re.compile(r'^\d+[、．.]\s*.*$', re.MULTILINE), 2),
    # a. b. c. 或 (a) (b) (c)
    (re.compile(r'^[a-z][、．.)）]\s*.*$', re.MULTILINE), 3),
]


def parse_sections(text: str) -> list[Section]:
    """
    解析文本的章节层级结构。

    返回章节列表，每个 Section 包含标题、层级、起止位置和页码。
    """
    lines = text.split("\n")
    sections: list[Section] = []
    section_stack: list[Section] = []

    offset = 0
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            offset += len(line) + 1
            continue

        matched_level = 0
        for pattern, level in SECTION_PATTERNS:
            if pattern.match(line_stripped):
                matched_level = level
                break

        if matched_level > 0:
            # 找到页码
            page_match = re.search(r"=== 第(\d+)页 ===", line)
            page = int(page_match.group(1)) if page_match else 0
            if page == 0:
                before = text[:offset]
                page_before = re.findall(r"=== 第(\d+)页 ===", before)
                page = int(page_before[-1]) if page_before else 0

            section = Section(
                title=line_stripped[:100],
                level=matched_level,
                start_pos=offset,
                end_pos=offset + len(line),
                page=page,
            )
            sections.append(section)

        offset += len(line) + 1

    return sections


def find_section_for_keyword(text: str, keyword: str, sections: list[Section]) -> Section | None:
    """找到包含关键词的章节。"""
    idx = text.find(keyword)
    if idx == -1:
        return None

    # 找到包含该位置的最近章节
    best_section = None
    for section in sections:
        if section.start_pos <= idx:
            best_section = section
        else:
            break
    return best_section


# ============================================================
# 投标资料类型同义词映射
# 将招标文件中的各种表述统一映射到标准资料类型
# ============================================================
DOCUMENT_SYNONYM_MAP: dict[str, dict] = {
    "母线槽整体型式试验报告": {
        "keywords": [
            "型式试验报告", "型式试验", "型式检验报告", "型式检验",
            "CCC报告", "3C报告", "CCC认证报告", "3C认证报告",
            "CCC型式试验", "3C型式试验", "强制认证报告",
            "CCC认证", "3C认证", "强制认证", "CCC型式检验",
            "国家权威机构出具的型式试验报告", "国家权威机构出具有效的型式试验报告",
            "国家强制性产品认证CCC", "国家强制性产品认证",
        ],
        "regex": r'(?:CCC|3C|型式).*?(?:试验|检验|认证|报告)',
        "required_key": "type_test_report",
    },
    "铜材第三方检测报告": {
        "keywords": [
            "铜材检测", "铜材测试", "铜材检验", "铜纯度检测",
            "铜导体检测", "铜材第三方", "铜材报告", "导体铜含量",
            "铜材第三方检测", "铜排检测", "铜排测试",
            "铜排纯度", "铜导体纯度", "铜材检测报告",
        ],
        "regex": r'铜.*?(?:检测|测试|检验|报告|纯度)',
        "required_key": "copper_test_report",
    },
    "绝缘材料第三方检测报告": {
        "keywords": [
            "绝缘材料检测", "绝缘材料第三方", "绝缘材料测试",
            "绝缘强度", "绝缘电阻", "绝缘检测", "绝缘测试",
            "绝缘材料检验", "绝缘报告",
        ],
        "regex": r'绝缘.*?(?:检测|测试|检验|报告|强度|电阻)',
        "required_key": "insulation_test_report",
    },
    "绝缘材料阻燃报告": {
        "keywords": [
            "阻燃报告", "阻燃检测", "阻燃试验", "阻燃等级",
            "防火等级", "耐火等级", "火焰蔓延", "阻燃测试",
            "阻燃检验", "阻燃性能",
        ],
        "regex": r'阻燃.*?(?:报告|检测|试验|测试|等级)',
        "required_key": "insulation_flame_report",
    },
    "外壳盐雾试验报告": {
        "keywords": [
            "盐雾试验", "盐雾测试", "盐雾检测", "耐腐蚀试验",
            "盐雾报告", "耐腐蚀报告", "防腐试验", "防腐测试",
            "盐雾等级", "盐雾", "盐雾认证",
        ],
        "regex": r'盐雾.*?(?:试验|测试|检测|报告|等级|认证)',
        "required_key": "salt_spray_report",
    },
    "制造商制造经验证明": {
        "keywords": [
            "制造经验", "生产经验", "成立年限", "经营年限",
            "制造商资格", "制造商资质", "从事母线", "制造历史",
            "制造经验证明", "生产经验证明", "制造商经验",
            "制造商证明", "制造经验材料",
            "生产供应经验", "至少.*年", "专业生产.*年",
            "生产的成熟性", "制造的成熟性",
        ],
        "regex": r'(?:制造|生产).*?(?:经验|年限|历史|资格|资质|供应|成熟性)|至少.*年.*?(?:经验|证明)|专业生产.*年',
        "required_key": "manufacturing_experience",
    },
    "抗震测试报告": {
        "keywords": [
            "抗震测试", "抗震试验", "抗震检测", "地震测试",
            "抗震报告", "UBC", "抗震设防", "抗震等级",
            "抗震认证", "抗震鉴定",
        ],
        "regex": r'抗震.*?(?:测试|试验|检测|报告|设防|等级|认证)',
        "required_key": "seismic_report",
    },
    "消防喷淋检测报告": {
        "keywords": [
            "消防喷淋", "喷淋试验", "喷淋测试", "消防水试验",
            "消防喷淋检测", "喷淋检测报告", "消防喷淋试验",
            "喷淋检测", "消防喷淋报告",
        ],
        "regex": r'(?:消防)?喷淋.*?(?:试验|测试|检测|报告)',
        "required_key": "fire_spray_report",
    },
    "耐火检测报告": {
        "keywords": [
            "耐火试验", "耐火测试", "耐火检测", "耐火报告",
            "耐火等级", "XF/T537", "J19216", "耐火认证",
            "耐火时间", "耐火极限",
        ],
        "regex": r'耐火.*?(?:试验|测试|检测|报告|等级|认证|时间)',
        "required_key": "fire_resistance_report",
    },
    "OHSAS认证": {
        "keywords": [
            "OHSAS18001", "OHSAS", "ISO45001", "职业健康安全",
            "职业健康", "OHSAS 18001", "ISO 45001",
            "ISO045001", "职业健康安全管理体系", "职业安全卫生",
        ],
        # 兼容空格/换行/连字符格式，以及可能的OCR识别错误"ISO0 45001"
        "regex": r'(?:OHSAS\s*(?:18001)?|ISO\s*0?45001|职业健康安全|职业安全卫生)',
        "required_key": "ohsas_cert",
    },
    "带电插拔检测报告": {
        "keywords": [
            "带电插拔", "热插拔", "带电热插拔", "即插即用",
            "带电插拔检测", "热插拔测试",
        ],
        "regex": r'(?:带电|热)插拔.*?(?:检测|测试|报告)?',
        "required_key": "hot_swap_report",
    },
    "连接器力矩测试报告": {
        "keywords": [
            "力矩测试", "力矩检测", "扭矩测试", "力矩螺栓",
            "力矩报告", "力矩试验", "扭矩检测",
        ],
        "regex": r'(?:力矩|扭矩).*?(?:测试|检测|试验|报告)',
        "required_key": "torque_test_report",
    },
    "IK碰撞等级测试报告": {
        "keywords": [
            "IK测试", "IK检测", "IK等级", "IK10", "IK08",
            "碰撞测试", "碰撞等级", "机械碰撞测试",
        ],
        "regex": r'IK.*?(?:测试|检测|等级|报告)|碰撞.*?(?:测试|检测|等级)',
        "required_key": "ik_rating_report",
    },
    "CQC节能认证": {
        "keywords": [
            "CQC", "节能认证", "节能产品", "能效认证",
            "CQC认证", "节能检测",
        ],
        "regex": r'CQC.*?(?:认证|节能)|节能.*?(?:认证|产品)',
        "required_key": "cqc_energy_cert",
    },
    "RoHS环保认证": {
        "keywords": [
            "RoHS", "环保认证", "有害物质", "环保要求",
            "RoHS认证", "RoHS检测",
        ],
        "regex": r'RoHS.*?(?:认证|检测|报告)?|环保.*?认证',
        "required_key": "rohs_cert",
    },
    "产品样本": {
        "keywords": [
            "产品样本", "产品手册", "产品说明", "产品目录",
            "产品选型", "样本册", "技术手册", "样本图册",
            "产品介绍", "产品资料", "产品技术资料",
        ],
        "regex": r'产品.*?(?:样本|手册|说明|目录|选型|资料)',
        "required_key": "product_catalog",
    },
    "ISO认证": {
        "keywords": [
            "ISO9001", "ISO 9001", "ISO9001-2000", "ISO 9001-2000",
            "ISO9001-14000", "ISO 9001-14000", "ISO14001", "ISO 14001",
            "质量管理体系", "质量体系认证", "质量体系",
            "ISO9000", "ISO 9000", "环境管理体系", "ISO14000", "ISO 14000",
        ],
        # 兼容空格、换行符（PDF换行可能导致ISO和编号之间插入\n）
        "regex": r'ISO[\s\n]*(?:900[01]|1400[01]|9000)|质量.*?(?:管理)?体系|环境管理体系',
        "required_key": "iso_cert",
    },
    "CE认证": {
        "keywords": [
            "CE认证", "CE证书", "CE mark", "CE marking",
            "CE 认证", "CE 证书", "CE标志", "符合性声明CE",
        ],
        "regex": r'CE\s*(?:认证|证书|mark|标志|符合性)?|CE标志',
        "required_key": "ce_cert",
    },
    "KEMA认证": {
        "keywords": [
            "KEMA", "KEMA-KEUR", "国际认证", "KEMA认证",
        ],
        "regex": r'KEMA.*?(?:认证|KEUR|报告)?',
        "required_key": "kema_cert",
    },
    "ASTA认证": {
        "keywords": [
            "ASTA", "ASTA-DIAMOND", "ASTA认证", "ASTA 认证",
        ],
        "regex": r'ASTA.*?(?:认证|DIAMOND|报告)?',
        "required_key": "kema_cert",
    },
    "营业执照": {
        "keywords": [
            "营业执照", "工商注册", "营业执照副本",
            "工商营业执照", "企业法人营业执照", "统一社会信用代码",
            "营业执照正本", "三证合一", "五证合一",
        ],
        "regex": r'营业执照|企业法人|统一社会信用代码|三证合一|五证合一|工商注册',
        "required_key": "business_license",
    },
}


def match_document_requirements(text: str) -> dict[str, dict]:
    """
    使用同义词映射检测标书中要求的所有投标资料。

    返回:
        {
            "母线槽整体型式试验报告": {
                "matched_keywords": ["型式试验报告", "CCC认证"],
                "matched_context": "原文片段...",
                "page": 3,
                "required_key": "type_test_report",
                "is_negated": False,
            },
            ...
        }
    """
    results: dict[str, dict] = {}

    for doc_name, mapping in DOCUMENT_SYNONYM_MAP.items():
        matched_kws: list[str] = []
        matched_ctx: list[str] = []
        pages: list[int] = []
        negated = False

        # 先用简单关键词匹配
        for kw in mapping["keywords"]:
            idx = text.lower().find(kw.lower())
            if idx >= 0:
                # 检查否定语境
                if is_negated(text, kw):
                    negated = True
                    continue

                matched_kws.append(kw)
                ctx_start = max(0, idx - 30)
                ctx_end = min(len(text), idx + len(kw) + 30)
                matched_ctx.append(text[ctx_start:ctx_end].replace("\n", " ").strip())

                # 找页码
                before = text[:idx]
                page_markers = re.findall(r"=== 第(\d+)页 ===", before)
                if page_markers:
                    pages.append(int(page_markers[-1]))

        # 再用正则模式匹配
        if "regex" in mapping:
            regex_pattern = mapping["regex"]
            for m in re.finditer(regex_pattern, text, re.IGNORECASE):
                matched_text = m.group(0)
                if matched_text not in matched_kws:
                    if is_negated(text, matched_text):
                        continue
                    matched_kws.append(matched_text)

        if matched_kws and not negated:
            results[doc_name] = {
                "matched_keywords": list(set(matched_kws)),
                "matched_context": matched_ctx[:3],  # 最多保留3条上下文
                "page": pages[0] if pages else 0,
                "required_key": mapping["required_key"],
                "is_negated": False,
                "standard_name": doc_name,
            }

    return results


# ============================================================
# 品牌上下文分析
# ============================================================
def analyze_brand_context(text: str, brand_keywords: list[str]) -> dict[str, Any]:
    """
    分析品牌在文本中的出现上下文，判断品牌是作为推荐品牌、禁止品牌还是附件品牌。

    返回:
        {
            "brand": "施耐德",
            "occurrences": [
                {"keyword": "施耐德", "context": "...", "role": "recommended", "page": 3}
            ],
            "primary_role": "recommended" | "specified" | "attachment" | "unknown"
        }
    """
    occurrences: list[dict] = []

    for kw in brand_keywords:
        idx = 0
        while True:
            idx = text.lower().find(kw.lower(), idx)
            if idx == -1:
                break

            ctx_start = max(0, idx - 80)
            ctx_end = min(len(text), idx + len(kw) + 80)
            ctx = text[ctx_start:ctx_end].replace("\n", " ").strip()

            # 判断角色
            role = "unknown"
            if re.search(r'(?:推荐|建议|优先|拟推荐).{0,20}?' + re.escape(kw), ctx, re.IGNORECASE):
                role = "recommended"
            elif re.search(r'(?:附件|配件|辅材|断路器|开关).{0,30}?' + re.escape(kw), ctx, re.IGNORECASE):
                role = "attachment"
            elif re.search(r'(?:指定|采用|选用|使用).{0,10}?' + re.escape(kw), ctx, re.IGNORECASE):
                role = "specified"

            before = text[:idx]
            page_markers = re.findall(r"=== 第(\d+)页 ===", before)
            page = int(page_markers[-1]) if page_markers else 0

            occurrences.append({
                "keyword": kw,
                "context": ctx[:200],
                "role": role,
                "page": page,
            })
            idx += len(kw)

    # 确定主要角色
    roles = [o["role"] for o in occurrences]
    if "recommended" in roles:
        primary_role = "recommended"
    elif "specified" in roles:
        primary_role = "specified"
    elif "attachment" in roles:
        primary_role = "attachment"
    else:
        primary_role = "unknown"

    return {
        "occurrences": occurrences,
        "primary_role": primary_role,
        "total_count": len(occurrences),
    }