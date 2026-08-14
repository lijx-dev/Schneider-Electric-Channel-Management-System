"""
批量导入施耐德 PDF 样本到 RAGFlow 知识库

用法：
  1. 确保 RAGFlow 已启动且 API Key 已配置在 .env
  2. python import_pdfs.py

工作流：
  1. 遍历 PDF 目录下所有 .pdf 文件
  2. 上传到 RAGFlow 知识库
  3. 轮询文档解析状态直到完成
  4. 输出每个文档的导入状态
"""

import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 配置
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
API_KEY = os.getenv("RAGFLOW_API_KEY", "")
KB_NAME = os.getenv("KNOWLEDGE_BASE_NAME", "施耐德事实层")
DATASET_ID = os.getenv("DATASET_ID", "")
PDF_DIR = os.getenv("PDF_DIR", r"D:\交接内容\分销系统\分销系统\schneider_pdfs\00 2026")
CHUNK_METHOD = os.getenv("CHUNK_METHOD", "naive")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ============================================================
# 工具函数
# ============================================================

def api_request(method: str, path: str, **kwargs) -> dict:
    """通用 API 请求封装"""
    url = f"{API_URL}/api/v1{path}"
    resp = requests.request(method, url, headers=HEADERS, timeout=120, **kwargs)
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"API 错误 [{path}]: {data.get('message', 'unknown')}")
    return data.get("data", data)


def find_or_create_dataset(name: str) -> str:
    """查找或创建知识库，返回 dataset_id"""
    # 先列出已有知识库
    datasets = api_request("GET", "/datasets", params={"page": 1, "page_size": 100})
    # RAGFlow 返回格式可能是 list 或 dict
    dataset_list = datasets if isinstance(datasets, list) else datasets.get("datasets", [])
    
    for ds in dataset_list:
        if ds.get("name") == name:
            print(f"[OK] 知识库已存在: {name} (id={ds['id']})")
            return ds["id"]
    
    # 创建新知识库
    print(f"[创建] 知识库: {name}")
    payload = {
        "name": name,
        "chunk_method": CHUNK_METHOD,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "parser_config": {
            "chunk_token_count": 512,
            "chunk_overlap_token_count": 64,
            "delimiter": "\n",
        },
    }
    result = api_request("POST", "/datasets", json=payload)
    dataset_id = result.get("id") or result.get("dataset_id")
    print(f"[OK] 知识库创建成功: id={dataset_id}")
    return dataset_id


def upload_document(dataset_id: str, file_path: str) -> str:
    """上传单个 PDF 文档，返回 document_id"""
    fname = os.path.basename(file_path)
    print(f"  [上传] {fname} ...", end=" ", flush=True)
    
    with open(file_path, "rb") as f:
        files = {"file": (fname, f, "application/pdf")}
        # 上传时使用 multipart，不带 Content-Type 让 requests 自动设置
        upload_headers = {"Authorization": f"Bearer {API_KEY}"}
        url = f"{API_URL}/api/v1/datasets/{dataset_id}/documents"
        resp = requests.post(url, headers=upload_headers, files=files, timeout=300)
        data = resp.json()
    
    if data.get("code") != 0:
        raise RuntimeError(f"上传失败: {data.get('message', 'unknown')}")
    
    # RAGFlow 返回 data 可能是 list 或 dict
    result_data = data.get("data", {})
    if isinstance(result_data, list):
        doc_id = result_data[0].get("id") if result_data else None
    else:
        doc_id = result_data.get("id") or result_data.get("document_id")
    print(f"OK (doc_id={doc_id})")
    return doc_id


def start_parsing(dataset_id: str, document_ids: list) -> None:
    """启动文档解析任务（批量调用）"""
    print(f"  [解析] 启动 {len(document_ids)} 个文档的解析任务 ...", end=" ", flush=True)
    try:
        api_request("POST", f"/datasets/{dataset_id}/chunks", json={"document_ids": document_ids})
        print("OK")
    except Exception as e:
        print(f"失败: {e}")


def wait_for_parsing(dataset_id: str, document_ids: list, timeout: int = 1800) -> dict:
    """轮询等待所有文档解析完成，返回 {doc_id: status}"""
    start_time = time.time()
    status_map = {doc_id: "pending" for doc_id in document_ids}
    pending = set(document_ids)
    
    print(f"  [等待] 文档解析中 (最多等待 {timeout}s) ...")
    
    while pending and (time.time() - start_time) < timeout:
        for doc_id in list(pending):
            try:
                doc_info = api_request("GET", f"/datasets/{dataset_id}/documents/{doc_id}")
                # RAGFlow 文档状态: run="UNSTART"|"RUNNING"|"DONE"|"FAIL"|"CANCEL"
                status = doc_info.get("run") or doc_info.get("status")
                status_map[doc_id] = status
                
                if status == "DONE" or status == "1":
                    pending.discard(doc_id)
                    print(f"    [完成] {doc_id}")
                elif status in ("FAIL", "CANCEL", "3"):
                    pending.discard(doc_id)
                    print(f"    [失败] {doc_id}: status={status}")
                elif status == "RUNNING":
                    print(f"    [解析中] {doc_id}")
            except Exception as e:
                print(f"    [轮询异常] {doc_id}: {e}")
        
        if pending:
            time.sleep(5)
    
    if pending:
        print(f"  [超时] {len(pending)} 个文档仍在解析中: {pending}")
    
    return status_map


# ============================================================
# 主流程
# ============================================================

def main():
    # 校验 API Key
    if not API_KEY:
        print("=" * 60)
        print("错误: 未配置 RAGFLOW_API_KEY")
        print("请在 .env 文件中填入 API Key")
        print("获取方式: 访问 http://localhost:8080 → 设置 → API Key")
        print("=" * 60)
        sys.exit(1)
    
    # 校验 PDF 目录
    pdf_dir = Path(PDF_DIR)
    if not pdf_dir.exists():
        print(f"错误: PDF 目录不存在: {PDF_DIR}")
        sys.exit(1)
    
    pdf_files = sorted([f for f in pdf_dir.iterdir() if f.suffix.lower() == ".pdf"])
    if not pdf_files:
        print(f"错误: 未找到 PDF 文件: {PDF_DIR}")
        sys.exit(1)
    
    print(f"PDF 目录: {PDF_DIR}")
    print(f"找到 {len(pdf_files)} 个 PDF 文件")
    print(f"知识库: {KB_NAME}")
    print(f"分块策略: {CHUNK_METHOD}")
    print("=" * 60)
    
    # 1. 获取知识库 ID
    if DATASET_ID:
        dataset_id = DATASET_ID
        print(f"[OK] 使用已配置知识库: id={dataset_id}")
    else:
        dataset_id = find_or_create_dataset(KB_NAME)
    print("-" * 60)
    
    # 2. 批量上传文档
    document_ids = []
    upload_results = []
    
    for pdf_path in pdf_files:
        try:
            doc_id = upload_document(dataset_id, str(pdf_path))
            document_ids.append(doc_id)
            upload_results.append({"file": pdf_path.name, "doc_id": doc_id, "status": "uploaded"})
        except Exception as e:
            print(f"  [失败] {pdf_path.name}: {e}")
            upload_results.append({"file": pdf_path.name, "doc_id": None, "status": f"error: {e}"})
    
    if not document_ids:
        print("错误: 没有文档上传成功")
        sys.exit(1)
    
    print(f"\n上传完成: {len(document_ids)}/{len(pdf_files)} 个文档")
    print("-" * 60)
    
    # 3. 启动解析
    try:
        start_parsing(dataset_id, document_ids)
    except Exception as e:
        print(f"启动解析失败: {e}")
    
    # 4. 等待解析完成
    status_map = wait_for_parsing(dataset_id, document_ids)
    
    # 5. 输出最终结果
    print("\n" + "=" * 60)
    print("导入结果汇总")
    print("=" * 60)
    
    success_count = 0
    fail_count = 0
    
    for result in upload_results:
        fname = result["file"]
        doc_id = result.get("doc_id")
        if doc_id:
            status = status_map.get(doc_id, "unknown")
            if status == "DONE" or status == "1":
                print(f"  [成功] {fname}")
                success_count += 1
            elif status in ("FAIL", "CANCEL", "3"):
                print(f"  [失败] {fname} — 解析失败 (status={status})")
                fail_count += 1
            else:
                print(f"  [处理中] {fname} — status={status}")
        else:
            print(f"  [失败] {fname} — {result['status']}")
            fail_count += 1
    
    print(f"\n总计: {success_count} 成功, {fail_count} 失败, {len(pdf_files)} 总文件")
    print(f"知识库 ID: {dataset_id}")
    print(f"请在 .env 文件中记录: KNOWLEDGE_BASE_ID={dataset_id}")


if __name__ == "__main__":
    main()