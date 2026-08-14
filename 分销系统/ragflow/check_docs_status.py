"""检查各知识库文档解析状态"""
import os, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

API_URL = os.getenv('RAGFLOW_API_URL', 'http://localhost:9380')
HEADERS = {
    'Authorization': f"Bearer {os.getenv('RAGFLOW_API_KEY')}",
    'Content-Type': 'application/json',
}

kb_ids = {
    '事实层': os.getenv('DATASET_ID'),
    '话术层': os.getenv('TALK_DATASET_ID'),
    '友商层': os.getenv('COMPETITOR_DATASET_ID'),
    '通用知识层': os.getenv('GENERAL_DATASET_ID'),
}

for name, ds_id in kb_ids.items():
    if not ds_id:
        print(f'[{name}] 未配置')
        continue
    try:
        resp = requests.get(
            f'{API_URL}/api/v1/datasets/{ds_id}/documents',
            headers=HEADERS,
            params={'page': 1, 'page_size': 100},
            timeout=30
        )
        if resp.status_code != 200:
            print(f'[{name}] HTTP {resp.status_code}')
            continue

        data = resp.json()
        docs = data.get('data', {}).get('docs', []) if isinstance(data.get('data'), dict) else data.get('data', [])

        status_counts = {}
        for d in docs:
            status = d.get('run') or d.get('status', '?')
            status_counts[status] = status_counts.get(status, 0) + 1

        print(f'\n[{name}] (id={ds_id}) - {len(docs)} 个文档')
        for status, count in sorted(status_counts.items()):
            print(f'  {status}: {count}')
    except Exception as e:
        print(f'[{name}] 错误: {e}')