"""
HiAgent FAQ 问答对迁移为结构化 Markdown 文档并导入 RAGFlow

用法：
  1. 确保 RAGFlow 已启动且 API Key 在 .env 中配置
  2. python migrate_faq.py --generate  # 仅生成文档
  3. python migrate_faq.py --import    # 仅导入已有文档
  4. python migrate_faq.py --all       # 生成 + 导入

数据源：D:\交接内容\分销系统\分销系统\FAQ集\
输出目录：D:\交接内容\分销系统\分销系统\ragflow\knowledge_docs\
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

# ============================================================
# 配置
# ============================================================

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
API_KEY = os.getenv("RAGFLOW_API_KEY", "")
CHUNK_METHOD = os.getenv("CHUNK_METHOD", "naive")

FAQ_BASE = Path(r"D:\交接内容\分销系统\分销系统\FAQ集")
OUTPUT_DIR = Path(__file__).parent / "knowledge_docs"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# 知识库定义
KB_DEFS = {
    "talk": {"name": "施耐德话术层", "folder": "话术层"},
    "competitor": {"name": "施耐德友商层", "folder": "友商层"},
    "general": {"name": "施耐德通用知识层", "folder": "通用知识层"},
}

# ============================================================
# 工具函数
# ============================================================

# Series 标签归一化映射
SERIES_NORMALIZE = {
    "I-LINE C": "I-Line C",
    "I-Line C": "I-Line C",
    "I-LINE B": "I-Line B",
    "I-Line B": "I-Line B",
    "I-LINE HL（新HL）": "I-Line HL (新/N型)",
    "I-LINE HL（原HL）": "I-Line HL (原/中)",
    "I-LINE H（老）": "I-Line H (老/大)",
    "I-LINE W（合金）": "I-Line W-合金",
    "I-LINE W（铜）": "I-Line W-铜",
    "I-LINE V": "I-Line V",
    "I-Line V": "I-Line V",
    "I-Line W-铜母线": "I-Line W-铜",
    "I-Line W-合金": "I-Line W-合金",
    "I-Line W": "I-Line W",
    "I-Line D": "I-Line D",
    "I-Line Track": "I-Line Track",
    "I-Line H": "I-Line H (老/大)",
    "耐火母线": "耐火母线",
    "Canalis KB": "Canalis KB",
}


def load_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件"""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def get_series(item: dict) -> str:
    """从 Labels 中提取 Series 标签并归一化"""
    labels = item.get("Labels") or []
    for lbl in labels:
        if lbl.get("Name") == "Series":
            val = (lbl.get("Value") or "").strip()
            if not val:
                return "未分类"
            return SERIES_NORMALIZE.get(val, val)
    return "未分类"


def classify_question(question: str, answer: str) -> str:
    """
    按主题聚类问答对：
    - 客户疑虑：包含"如果"、"担心"、"质疑"、"说"等
    - 竞品对比：包含"对比"、"vs"、"区别"、"电缆"、"其他品牌"等
    - 选型指导：包含"选型"、"参数"、"推荐"、"适合"、"怎么"等
    - 应用场景：包含"项目"、"场景"、"楼宇"、"数据中心"、"工业"等
    """
    q = question + answer
    q_lower = q.lower()

    if any(kw in q_lower for kw in ["vs", "对比", "区别", "电缆方案", "其他品牌", "竞品"]):
        return "竞品对比"
    if any(kw in q for kw in ["如果客户", "担心", "质疑", "客户说", "顾虑", "疑虑"]):
        return "客户疑虑"
    if any(kw in q for kw in ["选型", "参数", "推荐", "适合", "怎么判断", "怎么选", "如何选择"]):
        return "选型指导"
    if any(kw in q for kw in ["项目", "场景", "楼宇", "数据中心", "工业", "应用", "场合"]):
        return "应用场景"
    return "客户疑虑"  # 默认归入客户疑虑


def count_lines_in_file(path: Path) -> int:
    """统计文件行数"""
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


# ============================================================
# 步骤 1：产品库FAQ → 话术层文档
# ============================================================

def generate_talk_docs(items: list[dict]) -> dict[str, str]:
    """
    按 Series 分组，每组内按主题聚类，生成 Markdown 文档。
    返回 {filename: content}
    """
    # 按 Series 分组
    series_groups = defaultdict(list)
    for item in items:
        series = get_series(item)
        if series == "未分类":
            series_groups["通用"].append(item)
        else:
            series_groups[series].append(item)

    docs = {}

    # 系列描述信息
    series_info = {
        "I-Line C": {
            "title": "I-Line C 系列",
            "subtitle": "智能化密集型母线槽",
            "current": "630A-6000A",
            "features": [
                "整体式接地母线(IGB)结构",
                "高纯度电解铜，全长镀银",
                "防护等级 IP40/IP41/IP54/IP65/IP66",
                "无线温湿度测量、电能监测、EcoStruxure监控平台",
                "EZ连接理念，安装便捷",
                "插接箱范围 15A-1600A",
            ],
            "scenarios": "会展、商业楼宇、交通运输、教育科研、电子信息、石化、冶金",
        },
        "I-Line B": {
            "title": "I-Line B 系列",
            "subtitle": "基于分子渗透连接技术的高电流母线平台",
            "current": "800A-6300A",
            "features": [
                "分子渗透连接技术，连接可靠性极高",
                "防护等级 IP40/IP41/IP54/IP65/IP66",
                "适用于能源及基础设施、工业、数据中心、商业及民用建筑",
            ],
            "scenarios": "能源及基础设施、工业、数据中心、商业及民用建筑",
        },
        "I-Line W-铜": {
            "title": "I-Line W-铜 系列",
            "subtitle": "高性价比铜导体母线槽",
            "current": "400A-5000A",
            "features": [
                "高纯度高导电率电解铜，连接部位表面镀银",
                "防护等级 IP54/IP65/IP66",
                "商业建筑及中高电流主干配电场景",
            ],
            "scenarios": "商业建筑、中高电流主干配电",
        },
        "I-Line W-合金": {
            "title": "I-Line W-合金 系列",
            "subtitle": "高性价比合金导体母线槽",
            "current": "400A-3200A",
            "features": [
                "合金导体，关键电气搭接采用合金金属片与分子渗透技术",
                "防护等级 IP54/IP65",
                "高性价比住宅主干、楼宇集群管理",
            ],
            "scenarios": "高性价比住宅主干、楼宇集群管理",
        },
        "I-Line Track": {
            "title": "I-Line Track 系列",
            "subtitle": "滑轨式母线槽",
            "current": "—",
            "features": [
                "滑轨式安装，灵活性极高",
                "获得ASTA-DIAMOND认证（全系列）",
                "适用于数据中心等需要灵活配电的场景",
            ],
            "scenarios": "数据中心、需灵活配电的场合",
        },
        "I-Line V": {
            "title": "I-Line V 系列",
            "subtitle": "紧凑型密集型母线槽",
            "current": "400A-3200A",
            "features": [
                "高纯度高导电率电解铜，连接部位表面镀银",
                "防护等级 IP54/IP55/IP65",
                "适用于数据中心、停车场、超市、会展中心、地铁、船舶等",
            ],
            "scenarios": "数据中心、停车场、超市、会展中心、地铁、船舶",
        },
        "I-Line D": {
            "title": "I-Line D 系列",
            "subtitle": "直流母线槽",
            "current": "—",
            "features": [
                "直流配电专用母线",
                "适用于数据中心直流供电场景",
            ],
            "scenarios": "数据中心直流供电",
        },
        "I-Line HL (原/中)": {
            "title": "I-Line HL (原/中) 系列",
            "subtitle": "中电流母线槽系统",
            "current": "400A-5000A",
            "features": [
                "高纯度电解铜，全长镀银",
                "防护等级 IP54/IP55/IP65/IP66",
                "频率 50/60Hz",
                "结构紧凑防腐蚀，灵活安装",
                "安全热插拔，故障预报警和定位",
            ],
            "scenarios": "高层楼宇供电、配电设备连接、工艺设备配电",
        },
        "I-Line HL (新/N型)": {
            "title": "I-Line HL (新/N型) 系列",
            "subtitle": "高电流母线槽系统（N型）",
            "current": "400A-6300A",
            "features": [
                "优质铜导体，表面镀银",
                "防护等级 IP54/IP65",
                "频率 50Hz",
                "创新外壳设计，可适应任意安装方向",
                "即插即用插接口",
            ],
            "scenarios": "主干输配电、大面积照明主干线",
        },
        "I-Line H (老/大)": {
            "title": "I-Line H (老/大) 系列",
            "subtitle": "高电流母线槽系统",
            "current": "400A-5000A",
            "features": [
                "高纯度电解铜，全长镀银",
                "防护等级 IP54/IP55/IP65/IP66",
                "频率 50/60Hz",
                "插接箱范围 15A-1250A",
            ],
            "scenarios": "水平配电、上行配电、大面积照明",
        },
        "I-Line W": {
            "title": "I-Line W 系列",
            "subtitle": "母线槽统称",
            "current": "—",
            "features": [
                "包含铜导体和合金导体两种配置",
                "详见 I-Line W-铜 和 I-Line W-合金 子系列",
            ],
            "scenarios": "综合应用",
        },
        "耐火母线": {
            "title": "耐火母线系列",
            "subtitle": "耐火型母线槽",
            "current": "—",
            "features": [
                "经耐火包覆构造，满足国标线路完整性试验",
                "火灾规定时限内可持续为消防设备供电",
                "兼具防火隔断性能",
                "遵循 GB/T 19216.21-2003 标准",
            ],
            "scenarios": "消防电梯、排烟风机、消防泵房等消防重要负荷主干配电",
        },
        "Canalis KB": {
            "title": "Canalis KB 系列",
            "subtitle": "照明母线槽",
            "current": "—",
            "features": [
                "低压照明母线槽",
                "适用于商业照明配电",
            ],
            "scenarios": "商业照明配电",
        },
        "通用": {
            "title": "通用产品FAQ",
            "subtitle": "未归类到具体系列的产品问答",
            "current": "—",
            "features": [
                "涵盖多个产品系列的通用问题",
                "包括防护等级、安装方式等跨系列知识",
            ],
            "scenarios": "综合应用",
        },
    }

    # 为每个系列生成文档
    for series, s_items in sorted(series_groups.items()):
        if not s_items:
            continue

        info = series_info.get(series, {
            "title": series,
            "subtitle": "",
            "current": "—",
            "features": [],
            "scenarios": "综合应用",
        })

        # 按主题聚类
        topic_groups = defaultdict(list)
        for item in s_items:
            topic = classify_question(item.get("Question", ""), item.get("Answer", ""))
            topic_groups[topic].append(item)

        # 合并同类系列生成1-2份文档
        # 如果系列问答数少，合并到主文档
        if len(s_items) <= 50:
            # 生成单份文档
            filename = f"talk-{series.replace(' ', '-').replace('/', '-')}.md"
            content = _build_talk_doc(series, info, topic_groups, s_items)
            docs[filename] = content
        else:
            # 生成两份文档：话术指南 + 竞品对比
            # 话术指南
            talk_items = topic_groups.get("客户疑虑", []) + topic_groups.get("选型指导", []) + topic_groups.get("应用场景", [])
            talk_groups = {
                "客户疑虑": topic_groups.get("客户疑虑", []),
                "选型指导": topic_groups.get("选型指导", []),
                "应用场景": topic_groups.get("应用场景", []),
            }
            filename1 = f"talk-{series.replace(' ', '-').replace('/', '-')}-话术指南.md"
            docs[filename1] = _build_talk_doc(series, info, talk_groups, talk_items)

            # 竞品对比
            comp_items = topic_groups.get("竞品对比", [])
            if comp_items:
                comp_groups = {"竞品对比": comp_items}
                filename2 = f"talk-{series.replace(' ', '-').replace('/', '-')}-竞品对比.md"
                docs[filename2] = _build_talk_doc(series, info, comp_groups, comp_items)

    return docs


def _build_talk_doc(series: str, info: dict, topic_groups: dict, all_items: list) -> str:
    """构建话术层 Markdown 文档"""
    lines = []
    lines.append(f"# {info['title']} — {info['subtitle']}")
    lines.append("")

    # 核心参数
    lines.append("## 核心参数")
    lines.append("")
    lines.append(f"- 电流范围：{info['current']}")
    if info["features"]:
        lines.append("- 核心卖点：")
        for feat in info["features"]:
            lines.append(f"  - {feat}")
    if info["scenarios"]:
        lines.append(f"- 适用场景：{info['scenarios']}")
    lines.append("")

    # 按主题输出
    topic_order = ["客户疑虑", "竞品对比", "选型指导", "应用场景"]
    topic_names = {
        "客户疑虑": "常见客户疑虑及应对话术",
        "竞品对比": "竞品对比要点",
        "选型指导": "选型指导",
        "应用场景": "应用场景推荐",
    }

    for topic in topic_order:
        items = topic_groups.get(topic, [])
        if not items:
            continue

        lines.append(f"## {topic_names.get(topic, topic)}")
        lines.append("")

        for item in items:
            q = item.get("Question", "")
            a = item.get("Answer", "")
            xid = item.get("XID", "")

            # 简化问题作为子标题
            short_q = _shorten_question(q)
            lines.append(f"### {short_q}")
            lines.append("")
            lines.append(a.strip())
            lines.append("")
            lines.append(f"*来源QA: {xid}*")
            lines.append("")

    # 统计
    lines.append("---")
    lines.append(f"*本文档共收录 {len(all_items)} 条问答对*")
    lines.append("")

    return "\n".join(lines)


def _shorten_question(q: str, max_len: int = 40) -> str:
    """简化问题为简短标题"""
    # 移除常见前缀
    for prefix in ["如果客户", "客户问", "客户", "如果"]:
        if q.startswith(prefix):
            q = q[len(prefix):]
            break
    # 截断到合适长度
    if len(q) > max_len:
        q = q[:max_len] + "..."
    return q.strip().rstrip("，。？！")


# ============================================================
# 步骤 2：友商数据 → 友商层文档
# ============================================================

def generate_competitor_docs(items: list[dict]) -> dict[str, str]:
    """生成友商参数对比文档"""
    docs = {}

    # 分类
    param_queries = []      # 具体参数查询 (R20, Icw, Ipk)
    comparison_queries = [] # 对比类问题
    product_info = []       # 产品基本信息
    general_competitor = [] # 通用友商信息

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")

        if any(kw in q for kw in ["R20", "Icw", "Ipk", "导体电阻", "短时耐受", "峰值耐受"]):
            if any(kw in q for kw in ["vs", "对比", "优势", "XAP", "XL-", "威腾", "Pro VS", "Lmax"]):
                comparison_queries.append(item)
            else:
                param_queries.append(item)
        elif any(kw in q for kw in ["基本参数", "产品型号", "是什么", "有哪些"]):
            product_info.append(item)
        else:
            general_competitor.append(item)

    # 1. 产品系列概览
    if product_info:
        docs["competitor-施耐德母线系列概览.md"] = _build_competitor_overview(product_info)

    # 2. I-Line H 电气参数速查表
    if param_queries:
        docs["competitor-I-Line-H-电气参数速查.md"] = _build_param_lookup(param_queries)

    # 3. 竞品对比文档（按友商分组）
    comp_groups = defaultdict(list)
    for item in comparison_queries:
        q = item.get("Question", "")
        if "XAP-S" in q:
            comp_groups["XAP-S"].append(item)
        elif "XAP-C" in q:
            comp_groups["XAP-C"].append(item)
        elif "XAP-B" in q:
            comp_groups["XAP-B"].append(item)
        elif "XL-III" in q and "XL-IIIS" not in q:
            comp_groups["XL-III"].append(item)
        elif "XL-IIIS" in q:
            comp_groups["XL-IIIS"].append(item)
        elif "XLC-IIIH" in q:
            comp_groups["XLC-IIIH"].append(item)
        elif "威腾" in q or "Pro VS" in q:
            comp_groups["威腾-Pro-VS"].append(item)
        elif "Lmax" in q:
            comp_groups["ABB-Lmax"].append(item)
        elif "西门子" in q:
            comp_groups["西门子"].append(item)
        elif "ABB" in q:
            comp_groups["ABB"].append(item)
        else:
            comp_groups["其他友商"].append(item)

    for comp_name, comp_items in comp_groups.items():
        if comp_items:
            safe_name = comp_name.replace(" ", "-").replace("/", "-")
            docs[f"competitor-对比-{safe_name}.md"] = _build_comparison_doc(comp_name, comp_items)

    # 4. 通用友商知识
    if general_competitor:
        docs["competitor-友商通用知识.md"] = _build_general_competitor_doc(general_competitor)

    return docs


def _build_competitor_overview(items: list[dict]) -> str:
    """构建产品系列概览"""
    lines = ["# 施耐德 I-Line 母线系列概览", ""]
    lines.append("## 产品系列总览")
    lines.append("")

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        xid = item.get("XID", "")
        lines.append(f"### {q}")
        lines.append("")
        lines.append(a.strip())
        lines.append("")
        lines.append(f"*来源QA: {xid}*")
        lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条问答对*")
    return "\n".join(lines)


def _build_param_lookup(items: list[dict]) -> str:
    """构建参数速查表"""
    lines = ["# I-Line H 电气参数速查表", ""]
    lines.append("*以下数据来源于 I-Line H（老/大）系列 PDF 样本，逐电流等级确认。*")
    lines.append("")

    # 按电流等级分组
    current_groups = defaultdict(list)
    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        for current in ["6300A", "5000A", "4000A", "3200A", "2500A", "2000A", "1600A", "1250A", "1000A", "800A", "630A", "400A"]:
            if current in q:
                current_groups[current].append(item)
                break

    for current in ["6300A", "5000A", "4000A", "3200A", "2500A", "2000A", "1600A", "1250A", "1000A", "800A", "630A", "400A"]:
        if current in current_groups:
            lines.append(f"## {current}")
            lines.append("")
            for item in current_groups[current]:
                a = item.get("Answer", "")
                xid = item.get("XID", "")
                lines.append(a.strip())
                lines.append(f"*来源QA: {xid}*")
                lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条问答对*")
    return "\n".join(lines)


def _build_comparison_doc(comp_name: str, items: list[dict]) -> str:
    """构建竞品对比文档"""
    lines = [f"# I-Line H vs {comp_name} 参数对比", ""]
    lines.append(f"*以下对比数据基于施耐德 I-Line H（大）系列 PDF 样本与 {comp_name} 产品样本逐项对比。*")
    lines.append("")

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        xid = item.get("XID", "")
        lines.append(f"## {q}")
        lines.append("")
        lines.append(a.strip())
        lines.append("")
        lines.append(f"*来源QA: {xid}*")
        lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条对比数据*")
    return "\n".join(lines)


def _build_general_competitor_doc(items: list[dict]) -> str:
    """构建通用友商知识"""
    lines = ["# 友商通用知识", ""]
    lines.append("*涉及友商品牌、产品型号、行业对比等通用知识。*")
    lines.append("")

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        xid = item.get("XID", "")
        lines.append(f"## {q}")
        lines.append("")
        lines.append(a.strip())
        lines.append("")
        lines.append(f"*来源QA: {xid}*")
        lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条问答对*")
    return "\n".join(lines)


# ============================================================
# 步骤 3：政策库 → 通用知识层文档
# ============================================================

def generate_policy_docs(items: list[dict]) -> dict[str, str]:
    """生成政策类文档"""
    docs = {}

    # 按主题分类
    cert_items = []      # 认证标准
    business_items = []  # 商务政策（报备、KA等）
    compliance_items = [] # 产品合规

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")

        if any(kw in q for kw in ["CCC", "3C", "CQC", "认证", "标准", "IEC", "ASTA", "KEMA", "型式试验", "RoHS", "CE", "测试", "报告", "节能", "GB"]):
            cert_items.append(item)
        elif any(kw in q for kw in ["报备", "KA", "项目", "银行", "付款", "询价", "投标", "报价", "渠道", "分销商", "主导权", "池", "下单", "增补", "审批"]):
            business_items.append(item)
        else:
            compliance_items.append(item)

    if cert_items:
        docs["general-认证体系总览.md"] = _build_topic_doc("认证体系总览", cert_items)
    if business_items:
        docs["general-商务政策问答.md"] = _build_topic_doc("商务政策问答", business_items)
    if compliance_items:
        docs["general-产品合规要求.md"] = _build_topic_doc("产品合规要求", compliance_items)

    return docs


def _build_topic_doc(title: str, items: list[dict]) -> str:
    """构建主题文档"""
    lines = [f"# {title}", ""]

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        xid = item.get("XID", "")
        lines.append(f"## {q}")
        lines.append("")
        lines.append(a.strip())
        lines.append("")
        lines.append(f"*来源QA: {xid}*")
        lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条问答对*")
    return "\n".join(lines)


# ============================================================
# 步骤 4：无具体型号FAQ → 通用知识层文档
# ============================================================

def generate_general_docs(items: list[dict]) -> dict[str, str]:
    """生成通用知识文档"""
    docs = {}

    # 按主题分类
    topics = {
        "现场测量指南": [],
        "通用技术原理": [],
        "安装施工规范": [],
        "智能母线方案": [],
        "商业建筑配电": [],
        "产品认证查询": [],
        "工厂与公司介绍": [],
        "客户常见质疑": [],
    }

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")

        if any(kw in q for kw in ["测量", "数图", "Missing Link", "预留段", "投影法", "拉线法"]):
            topics["现场测量指南"].append(item)
        elif any(kw in q for kw in ["绝缘", "温升", "降容", "防护等级", "IP", "电流密度", "载流", "集肤效应", "导体", "铜排", "寿命", "电阻"]):
            topics["通用技术原理"].append(item)
        elif any(kw in q for kw in ["安装", "竖井", "沉降节", "支架", "法兰", "膨胀节", "变容节", "转向", "伸缩缝"]):
            topics["安装施工规范"].append(item)
        elif any(kw in q for kw in ["E-Temp", "F-Temp", "PO", "Busway", "智能母线", "数字化", "OPEX", "检测维护", "预测性维护", "预防性维护"]):
            topics["智能母线方案"].append(item)
        elif any(kw in q for kw in ["商业建筑", "综合体", "建筑配电", "机房", "数据中心", "医院", "照明母线"]):
            topics["商业建筑配电"].append(item)
        elif any(kw in q for kw in ["认证", "标准", "CCC", "3C", "CQC", "ASTA", "KEMA", "CE", "报告", "证书"]):
            topics["产品认证查询"].append(item)
        elif any(kw in q for kw in ["工厂", "公司", "施耐德（广州）", "生产基地", "投产", "生产线", "股份"]):
            topics["工厂与公司介绍"].append(item)
        else:
            topics["客户常见质疑"].append(item)

    # 调整：将"客户常见质疑"中的一些重新分类
    for item in topics["客户常见质疑"][:]:
        q = item.get("Question", "")
        if any(kw in q for kw in ["价格", "优势", "为什么", "解释"]):
            pass  # 保持
        elif any(kw in q for kw in ["方案", "选型", "配置", "如何"]):
            topics.setdefault("安装施工规范", []).append(item)
            topics["客户常见质疑"].remove(item)

    for topic, t_items in topics.items():
        if t_items:
            safe_topic = topic.replace(" ", "-").replace("/", "-")
            docs[f"general-{safe_topic}.md"] = _build_general_topic_doc(topic, t_items)

    return docs


def _build_general_topic_doc(topic: str, items: list[dict]) -> str:
    """构建通用知识文档，保留图片 URL"""
    lines = [f"# {topic}", ""]

    for item in items:
        q = item.get("Question", "")
        a = item.get("Answer", "")
        xid = item.get("XID", "")

        lines.append(f"## {q}")
        lines.append("")

        # 保留图片URL（Markdown 格式）
        # 自动检测 Answer 中的图片 URL 并转换为 Markdown 格式
        processed_a = _process_images_in_answer(a)
        lines.append(processed_a.strip())
        lines.append("")
        lines.append(f"*来源QA: {xid}*")
        lines.append("")

    lines.append("---")
    lines.append(f"*本文档共收录 {len(items)} 条问答对*")
    return "\n".join(lines)


def _process_images_in_answer(text: str) -> str:
    """处理 Answer 中的图片 URL，确保使用 Markdown 格式"""
    # 已经使用 ![](url) 格式的保持不变
    # 腾讯云 COS 链接保持不变
    return text


# ============================================================
# 步骤 5：写入文档
# ============================================================

def write_docs(docs: dict[str, str], folder: str):
    """将文档写入指定文件夹"""
    target_dir = OUTPUT_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in docs.items():
        filepath = target_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [写入] {folder}/{filename} ({len(content.splitlines())} 行)")


# ============================================================
# 步骤 6：导入 RAGFlow
# ============================================================

def api_request(method: str, path: str, **kwargs) -> dict:
    """通用 API 请求封装"""
    url = f"{API_URL}/api/v1{path}"
    resp = requests.request(method, url, headers=HEADERS, timeout=120, **kwargs)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"API 错误 [{path}]: {data.get('message', 'unknown')} (code={data.get('code')})")
    result = data.get("data", data)
    return result


def find_or_create_dataset(name: str) -> str:
    """查找或创建知识库，返回 dataset_id"""
    datasets = api_request("GET", "/datasets", params={"page": 1, "page_size": 100})
    dataset_list = datasets if isinstance(datasets, list) else datasets.get("datasets", [])

    for ds in dataset_list:
        if ds.get("name") == name:
            print(f"  [OK] 知识库已存在: {name} (id={ds['id']})")
            return ds["id"]

    print(f"  [创建] 知识库: {name}")
    payload = {
        "name": name,
        "chunk_method": CHUNK_METHOD,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "parser_config": {
            "chunk_token_count": 1024,
            "chunk_overlap_token_count": 128,
            "delimiter": "\n## ",
        },
    }
    result = api_request("POST", "/datasets", json=payload)
    dataset_id = result.get("id") or result.get("dataset_id")
    print(f"  [OK] 知识库创建成功: id={dataset_id}")
    return dataset_id


def upload_document(dataset_id: str, file_path: str) -> str:
    """上传单个 Markdown 文档"""
    fname = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        upload_headers = {"Authorization": f"Bearer {API_KEY}"}
        url = f"{API_URL}/api/v1/datasets/{dataset_id}/documents"
        files = {"file": (fname, f, "text/markdown")}
        resp = requests.post(url, headers=upload_headers, files=files, timeout=300)
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"上传失败: {data.get('message', 'unknown')}")

    result_data = data.get("data", {})
    if isinstance(result_data, list):
        doc_id = result_data[0].get("id") if result_data else None
    else:
        doc_id = result_data.get("id") or result_data.get("document_id")
    return doc_id


def start_parsing(dataset_id: str, document_ids: list) -> None:
    """启动文档解析"""
    try:
        api_request("POST", f"/datasets/{dataset_id}/chunks", json={"document_ids": document_ids})
    except Exception as e:
        print(f"  [警告] 启动解析失败: {e}")


def import_to_ragflow(docs_dir: str, kb_name: str, kb_type: str):
    """导入文档到 RAGFlow"""
    print(f"\n导入到 RAGFlow: {kb_name}")
    print("-" * 60)

    target_dir = Path(docs_dir)
    if not target_dir.exists():
        print(f"  错误: 目录不存在: {docs_dir}")
        return

    md_files = sorted(target_dir.glob("*.md"))
    if not md_files:
        print(f"  警告: 未找到 Markdown 文件")
        return

    print(f"  找到 {len(md_files)} 个文档")

    # 创建知识库
    dataset_id = find_or_create_dataset(kb_name)

    # 上传文档
    document_ids = []
    for md_file in md_files:
        try:
            print(f"  [上传] {md_file.name} ...", end=" ", flush=True)
            doc_id = upload_document(dataset_id, str(md_file))
            document_ids.append(doc_id)
            print(f"OK (doc_id={doc_id})")
        except Exception as e:
            print(f"失败: {e}")

    if not document_ids:
        print("  错误: 没有文档上传成功")
        return

    print(f"  上传完成: {len(document_ids)}/{len(md_files)} 个文档")

    # 启动解析
    start_parsing(dataset_id, document_ids)

    print(f"  知识库 ID: {dataset_id}")
    print(f"  请在 .env 中记录: {kb_type.upper()}_DATASET_ID={dataset_id}")
    return dataset_id


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="FAQ 迁移工具")
    parser.add_argument("--generate", action="store_true", help="仅生成文档")
    parser.add_argument("--import-docs", dest="import_docs", action="store_true", help="仅导入已有文档")
    parser.add_argument("--all", action="store_true", help="生成 + 导入", default=True)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.generate or args.all:
        print("=" * 60)
        print("步骤 1-4：生成结构化 Markdown 文档")
        print("=" * 60)

        # 1. 产品库FAQ → 话术层
        print("\n[1/4] 处理产品库FAQ (1269 条)...")
        product_items = load_jsonl(FAQ_BASE / "产品库FAQ" / "qa.jsonl")
        talk_docs = generate_talk_docs(product_items)
        write_docs(talk_docs, "话术层")
        print(f"  生成 {len(talk_docs)} 份话术层文档")

        # 2. 友商数据 → 友商层
        print("\n[2/4] 处理友商数据 (1316 条)...")
        comp_items = load_jsonl(FAQ_BASE / "友商数据" / "qa.jsonl")
        comp_docs = generate_competitor_docs(comp_items)
        write_docs(comp_docs, "友商层")
        print(f"  生成 {len(comp_docs)} 份友商层文档")

        # 3. 政策库 → 通用知识层
        print("\n[3/4] 处理政策库 (108 条)...")
        policy_items = load_jsonl(FAQ_BASE / "政策库" / "qa.jsonl")
        policy_docs = generate_policy_docs(policy_items)
        write_docs(policy_docs, "通用知识层")
        print(f"  生成 {len(policy_docs)} 份政策文档")

        # 4. 无具体型号FAQ → 通用知识层
        print("\n[4/4] 处理无具体型号FAQ (199 条)...")
        general_items = load_jsonl(FAQ_BASE / "无具体型号的FAQ库" / "qa.jsonl")
        general_docs = generate_general_docs(general_items)
        write_docs(general_docs, "通用知识层")
        print(f"  生成 {len(general_docs)} 份通用知识文档")

        # 统计
        total = len(talk_docs) + len(comp_docs) + len(policy_docs) + len(general_docs)
        print(f"\n总计生成 {total} 份文档")

    if args.import_docs or args.all:
        if not API_KEY:
            print("\n" + "=" * 60)
            print("警告: 未配置 RAGFLOW_API_KEY，跳过导入步骤")
            print("请在 .env 文件中填入 API Key 后重新运行 --import")
            print("=" * 60)
            return

        print("\n" + "=" * 60)
        print("步骤 5：导入 RAGFlow")
        print("=" * 60)

        # 导入话术层
        talk_dir = OUTPUT_DIR / "话术层"
        if talk_dir.exists():
            import_to_ragflow(str(talk_dir), "施耐德话术层", "talk")

        # 导入友商层
        comp_dir = OUTPUT_DIR / "友商层"
        if comp_dir.exists():
            import_to_ragflow(str(comp_dir), "施耐德友商层", "competitor")

        # 导入通用知识层
        general_dir = OUTPUT_DIR / "通用知识层"
        if general_dir.exists():
            import_to_ragflow(str(general_dir), "施耐德通用知识层", "general")

    # 打印目录树
    print("\n" + "=" * 60)
    print("文档目录树")
    print("=" * 60)
    _print_tree(OUTPUT_DIR)


def _print_tree(directory: Path, prefix: str = ""):
    """打印目录树"""
    items = sorted(directory.iterdir())
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "
        if item.is_dir():
            line_count = ""
            print(f"{prefix}{connector}{item.name}/{line_count}")
            _print_tree(item, prefix + ("    " if is_last else "│   "))
        else:
            line_count = count_lines_in_file(item)
            print(f"{prefix}{connector}{item.name} ({line_count} 行)")


if __name__ == "__main__":
    main()