"""测试 RAGFlow 检索 - 尝试不同端点格式"""
import os, requests, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

API_URL = os.getenv('RAGFLOW_API_URL', 'http://localhost:9380')
HEADERS = {
    'Authorization': f"Bearer {os.getenv('RAGFLOW_API_KEY')}",
    'Content-Type': 'application/json',
}
DATASET_ID = os.getenv('DATASET_ID', '')

# 测试不同检索端点格式
endpoints = [
    "/api/v1/retrieval",
    f"/api/v1/datasets/{DATASET_ID}/retrieval",
    f"/api/v1/datasets/{DATASET_ID}/search",
]

payload = {
    "question": "母线",
    "dataset_ids": [DATASET_ID],
    "top_k": 3,
    "similarity_threshold": 0.2,
    "keyword": True,
}

for endpoint in endpoints:
    url = f"{API_URL}{endpoint}"
    print(f"\nPOST {url}")
    try:
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=180)
        print(f"  Status: {resp.status_code}")
        text = resp.text[:300]
        print(f"  Response: {text}")
    except Exception as e:
        print(f"  Error: {e}")

# 也尝试 GET 检索
print(f"\nGET {API_URL}/api/v1/datasets/{DATASET_ID}/chunks")
try:
    resp = requests.get(
        f"{API_URL}/api/v1/datasets/{DATASET_ID}/chunks",
        headers=HEADERS,
        params={"doc_id": "test", "page": 1, "page_size": 5},
        timeout=30
    )
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")

# 检查 RAGFlow 版本
print(f"\nGET {API_URL}/api/v1/version")
try:
    resp = requests.get(f"{API_URL}/api/v1/version", headers=HEADERS, timeout=10)
    print(f"  Status: {resp.status_code}")
    print(f"  Response: {resp.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")