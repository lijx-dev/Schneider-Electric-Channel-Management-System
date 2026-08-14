"""
批量导入 PDF 样本到 RAGFlow 知识库 + 分块策略配置

用法：
  python import_pdfs.py                      # 导入施耐德 PDF（事实层，默认）
  python import_pdfs.py --competitor         # 导入友商 PDF（友商层）
  python import_pdfs.py --configure-chunks   # 配置所有知识库的分块策略
  python import_pdfs.py --competitor --configure-chunks  # 导入友商 + 配置分块

工作流：
  1. 遍历 PDF 目录下所有 .pdf 文件
  2. 上传到 RAGFlow 知识库
  3. 轮询文档解析状态直到完成
  4. 输出每个文档的导入状态
"""

import os
import sys
import time
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 配置
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

API_URL = os.getenv("RAGFLOW_API_URL", "http://localhost:9380")
API_KEY = os.getenv("RAGFLOW_API_KEY", "")
CHUNK_METHOD = os.getenv("CHUNK_METHOD", "naive")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ============================================================
# 知识库配置
# ============================================================

# 各知识库的默认分块策略
KB_CHUNK_CONFIGS = {
    "施耐德事实层": {
        "dataset_id_env": "DATASET_ID",
        "chunk_token_count": 512,
        "chunk_overlap_token_count": 64,
        "delimiter": "\n## ",
        "description": "PDF 电气参数样本",
    },
    "施耐德话术层": {
        "dataset_id_env": "TALK_DATASET_ID",
        "chunk_token_count": 384,
        "chunk_overlap_token_count": 48,
        "delimiter": "\n## ",
        "description": "销售话术指南",
    },
    "施耐德友商层": {
        "dataset_id_env": "COMPETITOR_DATASET_ID",
        "chunk_token_count": 512,
        "chunk_overlap_token_count": 64,
        "delimiter": "\n## ",
        "description": "友商参数对比 + 友商 PDF 样本",
    },
    "施耐德通用知识层": {
        "dataset_id_env": "GENERAL_DATASET_ID",
        "chunk_token_count": 320,
        "chunk_overlap_token_count": 48,
        "delimiter": "\n## ",
        "description": "安装、测量、认证、政策",
    },
}

# 友商 PDF 导入时排除的文件
COMPETITOR_EXCLUDES = {
    "SCDOC1896_I-LINE H 样本(400A-5000A)(L)web0705.pdf",  # 与施耐德目录重复
}

# 友商 PDF 目录
COMPETITOR_PDF_DIR = r"D:\交接内容\分销系统\分销系统\友商产品样本"


# ============================================================
# 工具函数
# ============================================================

def api_request_raw(method: str, path: str, **kwargs) -> requests.Response:
    """API 请求（返回原始 Response）"""
    url = f"{API_URL}/api/v1{path}"
    kwargs.setdefault("timeout", 120)
    return requests.request(method, url, headers=HEADERS, **kwargs)


def api_request(method: str, path: str, **kwargs) -> dict:
    """通用 API 请求封装"""
    resp = api_request_raw(method, path, **kwargs)
    text = resp.text.strip()
    if not text:
        raise RuntimeError(f"API 返回空响应 [{path}] status={resp.status_code}")
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"API 返回非 JSON [{path}]: {text[:200]}")
    if data.get("code") != 0:
        raise RuntimeError(f"API 错误 [{path}]: {data.get('message', 'unknown')} (code={data.get('code')})")
    return data.get("data", data)


def get_dataset_id_by_name(name: str) -> str:
    """按名称查找知识库 ID"""
    datasets = api_request("GET", "/datasets", params={"page": 1, "page_size": 100})
    dataset_list = datasets if isinstance(datasets, list) else datasets.get("datasets", [])
    for ds in dataset_list:
        if ds.get("name") == name:
            return ds["id"]
    return ""


def find_or_create_dataset(name: str, config: dict = None) -> str:
    """查找或创建知识库，返回 dataset_id"""
    existing_id = get_dataset_id_by_name(name)
    if existing_id:
        print(f"  [OK] 知识库已存在: {name} (id={existing_id})")
        return existing_id

    print(f"  [创建] 知识库: {name}")
    cfg = config or KB_CHUNK_CONFIGS.get(name, {})
    payload = {
        "name": name,
        "chunk_method": CHUNK_METHOD,
        "embedding_model": "BAAI/bge-large-zh-v1.5",
        "parser_config": {
            "chunk_token_count": cfg.get("chunk_token_count", 512),
            "chunk_overlap_token_count": cfg.get("chunk_overlap_token_count", 64),
            "delimiter": cfg.get("delimiter", "\n"),
        },
    }
    result = api_request("POST", "/datasets", json=payload)
    dataset_id = result.get("id") or result.get("dataset_id")
    print(f"  [OK] 知识库创建成功: id={dataset_id}")
    return dataset_id


def update_dataset_chunk_config(dataset_id: str, config: dict) -> bool:
    """更新知识库的分块配置"""
    print(f"  [配置] 更新知识库分块策略 (id={dataset_id}) ...", end=" ", flush=True)
    try:
        payload = {
            "parser_config": {
                "chunk_token_count": config["chunk_token_count"],
                "chunk_overlap_token_count": config["chunk_overlap_token_count"],
                "delimiter": config.get("delimiter", "\n## "),
            },
        }
        api_request("PUT", f"/datasets/{dataset_id}", json=payload)
        print(f"OK (chunk={config['chunk_token_count']}, overlap={config['chunk_overlap_token_count']})")
        return True
    except Exception as e:
        print(f"失败: {e}")
        return False


def upload_document(dataset_id: str, file_path: str) -> str:
    """上传单个 PDF 文档，返回 document_id"""
    fname = os.path.basename(file_path)
    print(f"  [上传] {fname} ...", end=" ", flush=True)

    with open(file_path, "rb") as f:
        files = {"file": (fname, f, "application/pdf")}
        upload_headers = {"Authorization": f"Bearer {API_KEY}"}
        url = f"{API_URL}/api/v1/datasets/{dataset_id}/documents"
        resp = requests.post(url, headers=upload_headers, files=files, timeout=300)
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"上传失败: {data.get('message', 'unknown')}")

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
    consecutive_errors = 0

    print(f"  [等待] 文档解析中 (最多等待 {timeout}s) ...")

    while pending and (time.time() - start_time) < timeout:
        for doc_id in list(pending):
            try:
                doc_info = api_request("GET", f"/datasets/{dataset_id}/documents/{doc_id}")
                status = doc_info.get("run") or doc_info.get("status")
                status_map[doc_id] = status
                consecutive_errors = 0

                if status == "DONE" or status == "1":
                    pending.discard(doc_id)
                    print(f"    [完成] {doc_id}")
                elif status in ("FAIL", "CANCEL", "3"):
                    pending.discard(doc_id)
                    print(f"    [失败] {doc_id}: status={status}")
                elif status == "RUNNING":
                    print(f"    [解析中] {doc_id}")
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors > 5:
                    print(f"    [轮询异常] 连续 {consecutive_errors} 次错误，停止轮询")
                    break
                # 短暂等待后重试
                time.sleep(2)

        if pending:
            time.sleep(5)

    if pending:
        print(f"  [超时] {len(pending)} 个文档仍在解析中: {pending}")

    return status_map


def import_pdfs_to_dataset(pdf_dir: str, dataset_id: str, excludes: set = None) -> dict:
    """导入 PDF 文件到指定知识库，返回导入结果"""
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.exists():
        print(f"  错误: PDF 目录不存在: {pdf_dir}")
        return {"success": 0, "fail": 0, "details": []}

    excludes = excludes or set()
    pdf_files = sorted([
        f for f in pdf_dir.iterdir()
        if f.suffix.lower() == ".pdf" and f.name not in excludes
    ])

    if not pdf_files:
        print(f"  警告: 未找到 PDF 文件")
        return {"success": 0, "fail": 0, "details": []}

    print(f"  找到 {len(pdf_files)} 个 PDF 文件")

    # 批量上传
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
        print("  错误: 没有文档上传成功")
        return {"success": 0, "fail": len(upload_results), "details": upload_results}

    print(f"  上传完成: {len(document_ids)}/{len(pdf_files)} 个文档")

    # 启动解析
    try:
        start_parsing(dataset_id, document_ids)
    except Exception as e:
        print(f"  启动解析失败: {e}")

    # 等待解析完成
    status_map = wait_for_parsing(dataset_id, document_ids)

    # 汇总结果
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

    return {"success": success_count, "fail": fail_count, "details": upload_results}


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="PDF 导入与分块策略配置工具")
    parser.add_argument("--competitor", action="store_true", help="导入友商 PDF 到友商层")
    parser.add_argument("--configure-chunks", action="store_true",
                        help="配置所有知识库的分块策略")
    parser.add_argument("--no-import", action="store_true",
                        help="跳过 PDF 导入，仅执行配置操作")
    args = parser.parse_args()

    # 校验 API Key
    if not API_KEY:
        print("=" * 60)
        print("错误: 未配置 RAGFLOW_API_KEY")
        print("请在 .env 文件中填入 API Key")
        print("=" * 60)
        sys.exit(1)

    # ============================================================
    # 步骤 1: PDF 导入
    # ============================================================
    if not args.no_import:
        if args.competitor:
            # 导入友商 PDF 到友商层
            print("=" * 60)
            print("友商 PDF 导入 — 施耐德友商层")
            print("=" * 60)

            dataset_id = os.getenv("COMPETITOR_DATASET_ID", "")
            if dataset_id:
                print(f"  使用已配置知识库: id={dataset_id}")
            else:
                dataset_id = find_or_create_dataset("施耐德友商层")

            print("-" * 60)
            excluded = list(COMPETITOR_EXCLUDES)
            if excluded:
                print(f"  排除文件: {excluded}")

            result = import_pdfs_to_dataset(COMPETITOR_PDF_DIR, dataset_id, COMPETITOR_EXCLUDES)
            print(f"\n友商 PDF 导入结果: {result['success']} 成功, {result['fail']} 失败")
        else:
            # 导入施耐德 PDF（默认行为）
            print("=" * 60)
            print("施耐德 PDF 导入 — 施耐德事实层")
            print("=" * 60)

            kb_name = os.getenv("KNOWLEDGE_BASE_NAME", "施耐德事实层")
            dataset_id = os.getenv("DATASET_ID", "")
            pdf_dir = os.getenv("PDF_DIR", r"D:\交接内容\分销系统\分销系统\schneider_pdfs\00 2026")

            if dataset_id:
                print(f"  使用已配置知识库: id={dataset_id}")
            else:
                dataset_id = find_or_create_dataset(kb_name)

            print(f"  PDF 目录: {pdf_dir}")
            print("-" * 60)

            result = import_pdfs_to_dataset(pdf_dir, dataset_id)
            print(f"\n施耐德 PDF 导入结果: {result['success']} 成功, {result['fail']} 失败")

    # ============================================================
    # 步骤 2: 分块策略配置
    # ============================================================
    if args.configure_chunks:
        print("\n" + "=" * 60)
        print("分块策略配置")
        print("=" * 60)

        for kb_name, config in KB_CHUNK_CONFIGS.items():
            env_key = config["dataset_id_env"]
            dataset_id = os.getenv(env_key, "")

            if not dataset_id:
                # 尝试按名称查找
                dataset_id = get_dataset_id_by_name(kb_name)

            if not dataset_id:
                print(f"  [跳过] {kb_name} — 未配置 dataset_id")
                continue

            print(f"\n  {kb_name} ({config['description']})")
            print(f"    chunk_token_count={config['chunk_token_count']}, "
                  f"overlap={config['chunk_overlap_token_count']}")
            update_dataset_chunk_config(dataset_id, config)

        print("\n分块策略配置完成")

    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)


if __name__ == "__main__":
    main()