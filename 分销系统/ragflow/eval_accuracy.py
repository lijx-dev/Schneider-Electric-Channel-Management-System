"""
RAGFlow 检索精度评测脚本

用法：
  python eval_accuracy.py

功能：
  1. 20 条测试用例覆盖 5 类场景（参数查询、产品对比、安装规范、认证标准、销售话术）
  2. 调用 RAGFlow 检索 API 获取 Top-5 文档片段
  3. 基于关键词自动判断相关性（模拟人工判断）
  4. 计算 Recall@5 和 Precision@5
  5. 输出评测报告

注意：
  - 自动相关性判断基于关键词匹配，仅作为近似参考
  - 精确评测需要人工逐条判断
"""

import os
import json
import requests
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / "faq-backend" / ".env")

API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
API_KEY = os.getenv("RAGFLOW_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# ============================================================
# 知识库 ID 配置
# ============================================================
KB_IDS = {
    "fact": os.getenv("DATASET_ID", ""),
    "talk": os.getenv("TALK_DATASET_ID", ""),
    "competitor": os.getenv("COMPETITOR_DATASET_ID", ""),
    "general": os.getenv("GENERAL_DATASET_ID", ""),
}

# 意图路由关键词规则（与 ragflow_retriever.py 保持一致）
INTENT_ROUTES = [
    ("competitor", ["对比", "vs", "区别", "哪个好", "哪个强", "哪个优", "优势", "比较",
                    "XAP", "XL-", "威腾", "Pro VS", "Lmax", "伊顿", "Eaton", "ABB",
                    "西门子", "Siemens", "友商", "竞品"]),
    ("talk", ["怎么推荐", "怎么说", "怎么推", "客户说", "客户问", "话术", "如何介绍",
              "怎么回答", "应对话术", "怎么卖", "销售", "如何向客户"]),
    ("general", ["安装", "测量", "数图", "施工", "维护", "OPEX", "检测",
                 "认证", "标准", "CCC", "3C", "CQC", "ASTA", "KEMA",
                 "报备", "KA", "商务政策", "银行承兑", "付款",
                 "工厂", "公司", "生产基地", "RoHS", "节能",
                 "降容", "海拔", "温升", "绝缘", "耐火", "防火",
                 "IP防护", "防护等级", "E-Temp", "智能母线", "数字化",
                 "配电房", "变压器房", "竖井", "Missing Link", "预留段"]),
]
DEFAULT_LAYERS = ["fact", "general"]


# ============================================================
# 20 条测试用例
# ============================================================
TEST_CASES = [
    # ── 参数查询（4 条）──
    {
        "id": "param-01",
        "category": "参数查询",
        "query": "I-Line H 630A 的短时耐受电流 Icw 是多少",
        "expected_layer": "fact",
        "relevant_keywords": ["Icw", "30", "kA", "630", "耐受"],
    },
    {
        "id": "param-02",
        "category": "参数查询",
        "query": "I-Line C 防护等级是多少",
        "expected_layer": "fact",
        "relevant_keywords": ["IP", "防护", "I-Line C", "IP54", "IP65"],
    },
    {
        "id": "param-03",
        "category": "参数查询",
        "query": "I-Line W 合金母线的导体电阻 R20 参数",
        "expected_layer": "fact",
        "relevant_keywords": ["R20", "电阻", "mΩ", "I-Line W", "合金"],
    },
    {
        "id": "param-04",
        "category": "参数查询",
        "query": "I-Line B 6300A 的峰值耐受电流 Ipk",
        "expected_layer": "fact",
        "relevant_keywords": ["Ipk", "峰值", "6300", "kA", "I-Line B"],
    },

    # ── 产品对比（4 条）──
    {
        "id": "compare-01",
        "category": "产品对比",
        "query": "I-Line H 和 Eaton XAP-S 对比哪个好",
        "expected_layer": "competitor",
        "relevant_keywords": ["I-Line H", "XAP-S", "对比", "Eaton", "伊顿"],
    },
    {
        "id": "compare-02",
        "category": "产品对比",
        "query": "I-Line H 和威腾 Pro VS 短时耐受电流对比",
        "expected_layer": "competitor",
        "relevant_keywords": ["威腾", "Pro VS", "Icw", "耐受", "对比"],
    },
    {
        "id": "compare-03",
        "category": "产品对比",
        "query": "I-Line H 和 XAP-C 的导体电阻区别",
        "expected_layer": "competitor",
        "relevant_keywords": ["XAP-C", "R20", "电阻", "区别", "I-Line H"],
    },
    {
        "id": "compare-04",
        "category": "产品对比",
        "query": "施耐德和 ABB Lmax 母线槽优势对比",
        "expected_layer": "competitor",
        "relevant_keywords": ["ABB", "Lmax", "优势", "对比", "施耐德"],
    },

    # ── 安装规范（4 条）──
    {
        "id": "install-01",
        "category": "安装规范",
        "query": "配电房母线槽安装测量步骤",
        "expected_layer": "general",
        "relevant_keywords": ["配电房", "测量", "安装", "步骤", "竖井"],
    },
    {
        "id": "install-02",
        "category": "安装规范",
        "query": "母线槽竖井安装有什么要求",
        "expected_layer": "general",
        "relevant_keywords": ["竖井", "安装", "要求", "施工"],
    },
    {
        "id": "install-03",
        "category": "安装规范",
        "query": "母线槽 Missing Link 预留段怎么处理",
        "expected_layer": "general",
        "relevant_keywords": ["Missing Link", "预留", "处理"],
    },
    {
        "id": "install-04",
        "category": "安装规范",
        "query": "高海拔地区母线槽安装注意事项",
        "expected_layer": "general",
        "relevant_keywords": ["海拔", "降容", "安装", "高海拔"],
    },

    # ── 认证标准（4 条）──
    {
        "id": "cert-01",
        "category": "认证标准",
        "query": "施耐德母线槽有哪些国际认证",
        "expected_layer": "general",
        "relevant_keywords": ["认证", "ASTA", "KEMA", "CCC", "IEC"],
    },
    {
        "id": "cert-02",
        "category": "认证标准",
        "query": "CCC 认证和 ASTA 认证的区别",
        "expected_layer": "general",
        "relevant_keywords": ["CCC", "ASTA", "认证", "区别"],
    },
    {
        "id": "cert-03",
        "category": "认证标准",
        "query": "RoHS 和节能认证要求",
        "expected_layer": "general",
        "relevant_keywords": ["RoHS", "节能", "认证", "环保"],
    },
    {
        "id": "cert-04",
        "category": "认证标准",
        "query": "母线槽耐火测试标准是什么",
        "expected_layer": "general",
        "relevant_keywords": ["耐火", "防火", "标准", "测试", "GB"],
    },

    # ── 销售话术（4 条）──
    {
        "id": "talk-01",
        "category": "销售话术",
        "query": "客户说 I-Line C 价格贵怎么推荐",
        "expected_layer": "talk",
        "relevant_keywords": ["价格", "全生命周期", "成本", "话术", "I-Line C"],
    },
    {
        "id": "talk-02",
        "category": "销售话术",
        "query": "客户问 I-Line H 和 XAP-S 怎么选，怎么回答",
        "expected_layer": "talk",
        "relevant_keywords": ["怎么选", "回答", "话术", "I-Line H", "XAP"],
    },
    {
        "id": "talk-03",
        "category": "销售话术",
        "query": "如何向客户介绍 I-Line B 的核心卖点",
        "expected_layer": "talk",
        "relevant_keywords": ["核心卖点", "介绍", "I-Line B", "特点"],
    },
    {
        "id": "talk-04",
        "category": "销售话术",
        "query": "客户担心潮湿环境影响母线，应对话术",
        "expected_layer": "talk",
        "relevant_keywords": ["潮湿", "防护", "IP", "话术", "客户"],
    },
]


# ============================================================
# 核心函数
# ============================================================

def route_intent(query: str) -> str:
    """意图路由（与 RAGFlowRetriever.route_intent 保持一致）"""
    for layer, keywords in INTENT_ROUTES:
        for kw in keywords:
            if kw.lower() in query.lower():
                return layer
    return ""


def retrieve_from_dataset(dataset_id: str, query: str, top_k: int = 5) -> list[dict]:
    """从单个知识库检索"""
    if not dataset_id:
        return []

    url = f"{API_URL}/api/v1/retrieval"
    payload = {
        "question": query,
        "dataset_ids": [dataset_id],
        "top_k": top_k,
        "similarity_threshold": 0.2,
        "keyword": True,
    }

    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=120)
        if resp.status_code != 200:
            return []

        data = resp.json()
        if data.get("code") != 0:
            msg = data.get("message", "")
            if "chat model" in msg.lower() or "not set" in msg.lower():
                raise RuntimeError(
                    f"RAGFlow 检索失败: 聊天模型未配置\n"
                    f"请在 RAGFlow 管理界面 (http://localhost:8080) 中:\n"
                    f"  1. 进入「模型提供商」页面\n"
                    f"  2. 添加一个聊天模型（如 DeepSeek、Qwen 等）\n"
                    f"  3. 进入「设置」页面\n"
                    f"  4. 在「系统模型设置」中指定默认聊天模型\n"
                    f"原始错误: {msg}"
                )
            return []

        chunks_data = data.get("data", {}).get("chunks", [])
        if not isinstance(chunks_data, list):
            return []

        chunks = []
        for c in chunks_data:
            content = (c.get("content") or "").strip()
            if not content:
                continue
            chunks.append({
                "content": content,
                "source": c.get("document_name") or c.get("doc_name") or "未知来源",
                "score": float(c.get("similarity") or c.get("score") or 0.0),
            })
        return chunks

    except Exception:
        return []


def retrieve_multi_kb(query: str, top_k: int = 5) -> list[dict]:
    """多知识库检索（模拟 RAGFlowRetriever.retrieve 逻辑）"""
    primary_layer = route_intent(query)

    # 确定检索的知识库列表
    layers_to_search = []
    if primary_layer:
        layers_to_search.append(primary_layer)
        for layer in DEFAULT_LAYERS:
            if layer != primary_layer:
                layers_to_search.append(layer)
    else:
        layers_to_search = DEFAULT_LAYERS

    primary_top_k = top_k
    other_top_k = max(1, top_k // 2)

    all_chunks = []
    for i, layer in enumerate(layers_to_search):
        ds_id = KB_IDS.get(layer, "")
        if not ds_id:
            continue
        k = primary_top_k if i == 0 else other_top_k
        chunks = retrieve_from_dataset(ds_id, query, k)
        for c in chunks:
            c["layer"] = layer
        all_chunks.extend(chunks)

    # 去重
    seen = {}
    for c in all_chunks:
        key = c.get("content", "")[:200]
        if key not in seen or c.get("score", 0) > seen[key].get("score", 0):
            seen[key] = c

    all_chunks = sorted(seen.values(), key=lambda c: c.get("score", 0), reverse=True)
    return all_chunks[:top_k]


def judge_relevance(content: str, relevant_keywords: list[str]) -> int:
    """
    基于关键词自动判断相关性（模拟人工判断）。
    返回 0（不相关）或 1（相关）。
    """
    if not content:
        return 0
    content_lower = content.lower()
    matched = sum(1 for kw in relevant_keywords if kw.lower() in content_lower)
    # 至少匹配 2 个关键词（或匹配到单个重要关键词也视为相关）
    return 1 if matched >= 2 else 0


def evaluate(test_cases: list[dict]) -> dict:
    """运行评测"""
    results = []
    category_stats = defaultdict(lambda: {"total": 0, "retrieved": 0, "relevant": 0, "hits": 0})

    total_retrieved = 0
    total_relevant = 0
    total_possible_hits = 0  # 命中的相关文档数

    for tc in test_cases:
        print(f"  [{tc['id']}] {tc['query'][:50]}...", end=" ", flush=True)

        chunks = retrieve_multi_kb(tc["query"], top_k=5)
        keywords = tc["relevant_keywords"]

        # 判断每条结果的相关性
        judged = []
        for i, chunk in enumerate(chunks):
            relevance = judge_relevance(chunk["content"], keywords)
            judged.append({
                "rank": i + 1,
                "relevance": relevance,
                "source": chunk["source"],
                "score": round(chunk["score"], 3),
                "layer": chunk.get("layer", ""),
                "snippet": chunk["content"][:80],
            })

        # 计算指标
        retrieved_count = len(chunks)
        relevant_count = sum(j["relevance"] for j in judged)
        hit_at_5 = 1 if relevant_count > 0 else 0

        total_retrieved += retrieved_count
        total_relevant += relevant_count
        total_possible_hits += hit_at_5

        cat = tc["category"]
        category_stats[cat]["total"] += 1
        category_stats[cat]["retrieved"] += retrieved_count
        category_stats[cat]["relevant"] += relevant_count
        category_stats[cat]["hits"] += hit_at_5

        status = "HIT" if hit_at_5 else "MISS"
        print(f"{status} ({retrieved_count} retrieved, {relevant_count} relevant)")

        results.append({
            "id": tc["id"],
            "category": tc["category"],
            "query": tc["query"],
            "retrieved_count": retrieved_count,
            "relevant_count": relevant_count,
            "hit_at_5": hit_at_5,
            "chunks": judged,
        })

    n = len(test_cases)
    precision = total_relevant / total_retrieved if total_retrieved > 0 else 0
    recall = total_possible_hits / n if n > 0 else 0

    return {
        "results": results,
        "overall": {
            "test_cases": n,
            "precision_at_5": round(precision, 4),
            "recall_at_5": round(recall, 4),
            "total_retrieved": total_retrieved,
            "total_relevant": total_relevant,
            "hit_count": total_possible_hits,
        },
        "category_stats": dict(category_stats),
    }


# ============================================================
# 主流程
# ============================================================

def main():
    if not API_KEY:
        print("错误: 未配置 RAGFLOW_API_KEY")
        return

    # 检查知识库可用性
    available_kbs = [k for k, v in KB_IDS.items() if v]
    if not available_kbs:
        print("错误: 无可用知识库，请检查 .env 配置")
        return

    print("=" * 70)
    print("RAGFlow 检索精度评测")
    print("=" * 70)
    print(f"知识库: {', '.join(available_kbs)}")
    print(f"测试用例: {len(TEST_CASES)} 条")
    print(f"检索策略: Top-5 混合检索（向量 + 关键词）")
    print(f"相关性判断: 关键词自动匹配（至少 2 个关键词命中）")
    print("-" * 70)

    # 运行评测
    print("-" * 70)
    try:
        report = evaluate(TEST_CASES)
    except RuntimeError as e:
        print(f"\n{'='*70}")
        print("评测中断")
        print(f"{'='*70}")
        print(f"\n{str(e)}")
        print(f"\n注意: 评测脚本代码正确，问题在于 RAGFlow 服务端配置。")
        return

    # ── 输出评测报告 ──
    print("\n" + "=" * 70)
    print("评测报告")
    print("=" * 70)

    overall = report["overall"]
    print(f"\n总体指标:")
    print(f"  Precision@5: {overall['precision_at_5']:.2%}")
    print(f"  Recall@5:   {overall['recall_at_5']:.2%}")
    print(f"  命中率:     {overall['hit_count']}/{overall['test_cases']}")
    print(f"  检索片段:   {overall['total_retrieved']} 条")
    print(f"  相关片段:   {overall['total_relevant']} 条")

    # ── 分类统计 ──
    print(f"\n分类精度:")
    print(f"  {'类别':<12} {'用例数':>6} {'Precision@5':>12} {'命中率':>8}")
    print(f"  {'-'*42}")

    for cat in ["参数查询", "产品对比", "安装规范", "认证标准", "销售话术"]:
        stats = report["category_stats"].get(cat, {})
        total = stats.get("total", 0)
        retrieved = stats.get("retrieved", 0)
        relevant = stats.get("relevant", 0)
        hits = stats.get("hits", 0)
        cat_precision = relevant / retrieved if retrieved > 0 else 0
        cat_hit_rate = hits / total if total > 0 else 0
        print(f"  {cat:<12} {total:>6} {cat_precision:>11.2%} {cat_hit_rate:>7.2%}")

    # ── 详细结果 ──
    print(f"\n{'='*70}")
    print("详细结果")
    print(f"{'='*70}")

    for r in report["results"]:
        status = "HIT" if r["hit_at_5"] else "MISS"
        print(f"\n[{r['id']}] [{status}] {r['category']}")
        print(f"  Q: {r['query']}")
        print(f"  Retrieved: {r['retrieved_count']}, Relevant: {r['relevant_count']}")

        if r["chunks"]:
            for j in r["chunks"]:
                rel = "R" if j["relevance"] else "N"
                print(f"    #{j['rank']} [{rel}] [{j['layer']}] {j['source']} "
                      f"(score={j['score']:.3f})")
                print(f"        {j['snippet']}")
        else:
            print(f"    (无检索结果)")

    # ── 改进建议 ──
    print(f"\n{'='*70}")
    print("改进建议")
    print(f"{'='*70}")

    # 分析各分类精度
    weak_categories = []
    for cat in ["参数查询", "产品对比", "安装规范", "认证标准", "销售话术"]:
        stats = report["category_stats"].get(cat, {})
        total = stats.get("total", 0)
        hits = stats.get("hits", 0)
        if total > 0:
            hit_rate = hits / total
            if hit_rate < 0.75:
                weak_categories.append((cat, hit_rate))

    if weak_categories:
        print(f"\n低精度类别（命中率 < 75%）:")
        for cat, rate in weak_categories:
            print(f"  - {cat}: {rate:.0%}")
            if cat == "参数查询":
                print(f"    建议: 增大事实层 chunk_size（当前 512 tokens → 800 tokens），")
                print(f"          保留更多完整参数行")
            elif cat == "产品对比":
                print(f"    建议: 友商层 PDF 解析完成后重新评测，")
                print(f"          考虑降低 similarity_threshold（当前 0.2 → 0.15）")
            elif cat == "安装规范":
                print(f"    建议: 增加通用知识层安装施工类文档，")
                print(f"          chunk_overlap 从 48 → 64 tokens")
            elif cat == "认证标准":
                print(f"    建议: 补充认证标准相关问答对，")
                print(f"          当前通用知识层认证类文档较少")
            elif cat == "销售话术":
                print(f"    建议: 话术层 chunk_size 从 384 → 512 tokens，")
                print(f"          保留完整话术段落")
    else:
        print("\n所有类别精度均达标（>= 75%）")

    print(f"\n注意: 自动相关性判断基于关键词匹配，仅供参考。")
    print(f"精确评测建议人工逐条复核。")

    # 保存报告
    report_path = Path(__file__).parent / "eval_report.json"
    # 转换 category_stats 为可序列化格式
    serializable_report = {
        "overall": report["overall"],
        "category_stats": {
            k: dict(v) for k, v in report["category_stats"].items()
        },
        "results": report["results"],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(serializable_report, f, ensure_ascii=False, indent=2)
    print(f"\n评测报告已保存: {report_path}")


if __name__ == "__main__":
    main()