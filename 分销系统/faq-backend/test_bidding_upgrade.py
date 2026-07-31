"""
招标文件分析系统升级测试脚本
测试4份可读示例标书，验证：
1. 文本提取（PDF/Word）
2. 关键词匹配检测（含语义分析）
3. 参数值精确提取
4. 深度分析（含参数对比）
5. 智能推荐
"""
import json
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "faq-backend"))

from app.services.bidding_analyzer import BiddingAnalyzer
from app.services.bidding_param_extractor import extract_all_params, compare_param_with_schneider
from app.services.bidding_semantic import match_document_requirements, is_negated, parse_sections

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "资料分析示例文件")
SAMPLES = [
    "密集母线技术规范.pdf",
    "低压母线槽规范及技术要求.pdf",
    "母线槽技术要求.pdf",
    "第四章 母线槽技术要求.pdf",
]

def test_text_extraction():
    """测试1：文本提取"""
    print("=" * 70)
    print("测试1：文本提取")
    print("=" * 70)
    for filename in SAMPLES:
        filepath = os.path.join(SAMPLE_DIR, filename)
        if not os.path.exists(filepath):
            print(f"  [SKIP] {filename} — 文件不存在")
            continue
        with open(filepath, "rb") as f:
            content = f.read()
        try:
            text = BiddingAnalyzer.extract_text(content, filename=filename)
            pages = text.count("=== 第")
            print(f"  [OK] {filename}")
            print(f"       提取字符数: {len(text)}, 页数: {pages}")
            if len(text) < 100:
                print(f"       [WARN] 文本过短，可能是扫描件")
        except Exception as e:
            print(f"  [FAIL] {filename}: {e}")
    print()

def test_keyword_match():
    """测试2：关键词匹配检测（含语义分析）"""
    print("=" * 70)
    print("测试2：关键词匹配检测（v2.0 含语义分析）")
    print("=" * 70)
    for filename in SAMPLES:
        filepath = os.path.join(SAMPLE_DIR, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, "rb") as f:
            content = f.read()
        try:
            text = BiddingAnalyzer.extract_text(content, filename=filename)
            if not text.strip():
                print(f"  [SKIP] {filename} — 无文本内容")
                continue
        except Exception:
            continue

        result = BiddingAnalyzer.keyword_match(text)

        print(f"\n  📄 {filename}")
        print(f"     风险等级: {result['risk_level']}")
        print(f"     友商检测: {len(result['competitors'])}家")
        for c in result["competitors"]:
            print(f"       - {c['brand']}: {c['matched_keywords']}")
        print(f"     施耐德检测: {len(result['schneider']['matched_keywords'])}个关键词")
        if result['schneider']['matched_keywords']:
            print(f"       - {result['schneider']['matched_keywords'][:5]}")

        # 关键词匹配结果
        kw_reqs = result.get("bidding_requirements", {})
        print(f"     关键词资料要求: {len(kw_reqs)}项")
        for req_name in list(kw_reqs.keys())[:5]:
            print(f"       - {req_name}")

        # 语义分析结果
        sem_reqs = result.get("semantic_requirements", {})
        print(f"     语义分析资料要求: {len(sem_reqs)}项")
        for doc_name in list(sem_reqs.keys())[:5]:
            print(f"       - {doc_name}")

        # 参数提取结果
        params = result.get("extracted_params", {})
        print(f"     参数提取: {len(params)}项")
        for param_name, values in list(params.items())[:5]:
            if isinstance(values, list) and values:
                print(f"       - {param_name}: {values[0]['value']}{values[0]['unit']}")

        # 统计信息
        stats = result.get("_stats", {})
        print(f"     统计: 关键词{stats.get('keyword_req_count', 0)}项 + 语义{stats.get('semantic_req_count', 0)}项 = 共{stats.get('total_req_count', 0)}项")

    print()

def test_deep_analyze():
    """测试3：深度分析（含参数对比）"""
    print("=" * 70)
    print("测试3：深度分析（v2.0 含参数对比）")
    print("=" * 70)
    for filename in SAMPLES:
        filepath = os.path.join(SAMPLE_DIR, filename)
        if not os.path.exists(filepath):
            continue
        with open(filepath, "rb") as f:
            content = f.read()
        try:
            text = BiddingAnalyzer.extract_text(content, filename=filename)
            if not text.strip():
                continue
        except Exception:
            continue

        result = BiddingAnalyzer.deep_analyze(text, filename=filename)

        print(f"\n  📄 {filename}")
        print(f"     风险等级: {result['risk_level']}")
        print(f"     有利条款: {len(result['favorable_clauses'])}项已植入, {len(result['missing_clauses'])}项缺失")
        print(f"     友商痕迹: {len(result['competitor_traces'])}项")
        print(f"     产品匹配: {result['product_match']['best_match']} " +
              f"({result['product_match']['best_full_name']})")

        # 参数对比
        param_comp = result.get("param_comparison", {})
        print(f"     参数对比: {len(param_comp)}项")
        for param_name, comp in list(param_comp.items())[:5]:
            if isinstance(comp, dict) and "schneider_comparison" in comp:
                sc = comp["schneider_comparison"]
                print(f"       - {param_name}: {sc['status']} — {sc['detail'][:60]}")

        print(f"     总结: {result['summary'][:120]}...")
        print(f"     策略建议: {len(result['strategy'])}条")
    print()

def test_negation_detection():
    """测试4：否定句式检测"""
    print("=" * 70)
    print("测试4：否定句式检测")
    print("=" * 70)
    test_cases = [
        ("不应采用铝合金导体作为母线导体", "铝合金", True),
        ("母线导体应采用铜导体，不应采用铝合金导体", "铝合金", True),
        ("不得使用OEM贴牌产品", "OEM", True),
        ("若采用OEM方式，需提供制造商授权书", "OEM", False),
        ("母线槽应采用铜导体，导电率不低于99.9%", "铜导体", False),
        ("不接受双拼结构母线槽", "双拼", True),
    ]
    for text, kw, expected in test_cases:
        result = is_negated(text, kw)
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] '{kw}' in '{text[:50]}...' → negated={result} (expected={expected})")
    print()

def test_semantic_matching():
    """测试5：同义词映射匹配"""
    print("=" * 70)
    print("测试5：同义词映射匹配")
    print("=" * 70)
    test_texts = [
        "投标人需提供国家权威机构出具的型式试验报告（CCC认证），并附铜材第三方检测报告。",
        "须提供盐雾试验报告，测试时间不低于1800小时。",
        "制造商应具备ISO9001质量管理体系认证和OHSAS18001职业健康安全认证。",
        "母线槽需通过耐火试验（XF/T537标准），并提供消防喷淋检测报告。",
        "插接箱应支持带电热插拔功能，并提供相应的检测报告。",
    ]
    for text in test_texts:
        results = match_document_requirements(text)
        print(f"\n  原文: {text[:80]}...")
        print(f"  匹配到 {len(results)} 项资料:")
        for doc_name, info in results.items():
            print(f"    - {doc_name}: {info['matched_keywords']}")
    print()

def test_parameter_extraction():
    """测试6：参数值精确提取"""
    print("=" * 70)
    print("测试6：参数值精确提取")
    print("=" * 70)
    test_texts = [
        "盐雾试验时间不低于2400小时，外壳防护等级IP65，IK碰撞等级IK10。",
        "制造商应具备15年以上母线槽制造经验，铜导体纯度不低于99.9%。",
        "额定短时耐受电流Icw≥50KA，额定峰值耐受电流Ipk≥105KA。",
        "导体厚度不小于4mm，连接器力矩≥95N.m，绝缘老化≥5000小时。",
        "400A短时耐受20KA，800A短时耐受30KA，1600A短时耐受50KA。",
    ]
    for text in test_texts:
        params = extract_all_params(text)
        print(f"\n  原文: {text[:80]}...")
        for param_name, param_list in params.items():
            if param_name.endswith("_按安培"):
                print(f"    {param_name}:")
                for item in param_list:
                    print(f"      - {item.get('ampere', '')}A: {item.get('short_time_current', item.get('peak_current', ''))}KA")
            else:
                for p in param_list:
                    print(f"    {param_name}: {p.operator}{p.value}{p.unit} (页码:{p.page})")
    print()

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  施耐德招标文件分析系统 — 升级测试 v2.0")
    print("=" * 70)
    print(f"  样本目录: {SAMPLE_DIR}")
    print(f"  样本文件: {len(SAMPLES)}份")
    print()

    test_text_extraction()
    test_keyword_match()
    test_deep_analyze()
    test_negation_detection()
    test_semantic_matching()
    test_parameter_extraction()

    print("=" * 70)
    print("  测试完成！")
    print("=" * 70)