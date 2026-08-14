"""
RAGFlow 检索测试脚本

用法：
  1. 确保 PDF 已导入并解析完成
  2. 在 .env 中配置 API Key 和 Knowledge Base ID
  3. python test_retrieval.py

测试 5 个施耐德 I-Line 产品相关问题，输出 Top-3 检索结果及来源文件。
"""

import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 配置
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
API_KEY = os.getenv("RAGFLOW_API_KEY", "")
KB_ID = os.getenv("DATASET_ID", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ============================================================
# 测试问题（5 个 I-Line 产品参数问题）
# ============================================================

TEST_QUESTIONS = [
    {
        "id": 1,
        "question": "I-Line H 630A 的短时耐受电流 Icw 是多少",
        "expected_source": "I-LINE H 样本",
        "category": "I-Line H 技术参数",
    },
    {
        "id": 2,
        "question": "I-Line B 系列适用的电流范围是多少",
        "expected_source": "I-Line B 样本",
        "category": "I-Line B 技术参数",
    },
    {
        "id": 3,
        "question": "I-Line W 铜母线系列支持哪些防护等级",
        "expected_source": "I-LINE W 铜母线样本",
        "category": "I-Line W 技术参数",
    },
    {
        "id": 4,
        "question": "I-Line C 系列的插接箱范围是多少",
        "expected_source": "I-Line C 样本",
        "category": "I-Line C 技术参数",
    },
    {
        "id": 5,
        "question": "I-Line HN 新HL系列的导体材料是什么",
        "expected_source": "I-LINE 新HL 样本",
        "category": "I-Line HN 技术参数",
    },
]


# ============================================================
# 检索函数
# ============================================================

def retrieve(question: str, dataset_id: str, top_k: int = 3) -> dict:
    """调用 RAGFlow 检索 API"""
    url = f"{API_URL}/api/v1/retrieval"
    payload = {
        "question": question,
        "dataset_ids": [dataset_id],
        "top_k": top_k,
    }
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=300)
    data = resp.json()
    return data


def format_result(data: dict, top_k: int = 3) -> str:
    """格式化检索结果为可读文本"""
    if data.get("code") != 0:
        return f"  检索失败: {data.get('message', 'unknown')}"
    
    chunks = data.get("data", {}).get("chunks", [])
    if not chunks:
        return "  无检索结果"
    
    lines = []
    for i, chunk in enumerate(chunks[:top_k], 1):
        content = chunk.get("content", "")[:300]
        doc_name = chunk.get("document_name", chunk.get("doc_name", "未知"))
        similarity = chunk.get("similarity", chunk.get("score", "N/A"))
        
        lines.append(f"  [{i}] 来源: {doc_name}")
        if similarity and similarity != "N/A":
            sim_str = f"{float(similarity):.4f}" if isinstance(similarity, (int, float)) else str(similarity)
            lines.append(f"      相似度: {sim_str}")
        lines.append(f"      内容: {content[:200]}...")
        lines.append("")
    
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    if not API_KEY:
        print("错误: 未配置 RAGFLOW_API_KEY")
        sys.exit(1)
    
    if not KB_ID:
        print("错误: 未配置 DATASET_ID")
        print("请先在 .env 中填入知识库 ID")
        sys.exit(1)
    
    print("=" * 70)
    print("  RAGFlow 检索精度测试 — 施耐德 I-Line 产品参数")
    print("=" * 70)
    print(f"  API: {API_URL}")
    print(f"  知识库 ID: {KB_ID}")
    print(f"  测试问题数: {len(TEST_QUESTIONS)}")
    print("=" * 70)
    
    for tq in TEST_QUESTIONS:
        qid = tq["id"]
        question = tq["question"]
        expected = tq["expected_source"]
        category = tq["category"]
        
        print(f"\n{'─' * 70}")
        print(f"问题 {qid}: {question}")
        print(f"类型: {category} | 期望来源: {expected}")
        print(f"{'─' * 70}")
        
        try:
            result = retrieve(question, KB_ID, top_k=3)
            formatted = format_result(result, top_k=3)
            print(formatted)
        except Exception as e:
            print(f"  检索异常: {e}")
    
    print("\n" + "=" * 70)
    print("  测试完成")
    print("=" * 70)
    print("\n请人工核查以上结果:")
    print("  1. 检索结果是否来自期望的 PDF 文件")
    print("  2. 检索内容是否包含正确答案")
    print("  3. 相似度分数是否合理")
    print("\n如需调整分块策略，请修改 RAGFlow Web UI 中的知识库配置。")


if __name__ == "__main__":
    main()