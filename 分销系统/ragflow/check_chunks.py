"""验证各知识库分块配置"""
import os, requests
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

API_URL = os.getenv('RAGFLOW_API_URL', 'http://localhost:9380')
HEADERS = {'Authorization': f"Bearer {os.getenv('RAGFLOW_API_KEY')}", 'Content-Type': 'application/json'}

kb_ids = {
    '事实层': os.getenv('DATASET_ID'),
    '话术层': os.getenv('TALK_DATASET_ID'),
    '友商层': os.getenv('COMPETITOR_DATASET_ID'),
    '通用知识层': os.getenv('GENERAL_DATASET_ID'),
}

# 通过 list 接口获取所有知识库
resp = requests.get(f'{API_URL}/api/v1/datasets', headers=HEADERS, params={'page': 1, 'page_size': 50}, timeout=30)
datasets = resp.json().get('data', [])
if isinstance(datasets, dict):
    datasets = datasets.get('datasets', [])

for name, ds_id in kb_ids.items():
    found = None
    for ds in datasets:
        if ds.get('id') == ds_id:
            found = ds
            break
    if not found:
        print(f'[{name}] 未找到 (id={ds_id})')
        continue
    pc = found.get('parser_config', {})
    print(f'[{name}] {found.get("name","?")}')
    print(f'  chunk_method: {found.get("chunk_method","?")}')
    print(f'  chunk_token_count: {pc.get("chunk_token_count","?")}')
    print(f'  chunk_overlap_count: {pc.get("chunk_overlap_token_count","?")}')
    print(f'  embedding_model: {found.get("embedding_model","?")}')
    print()