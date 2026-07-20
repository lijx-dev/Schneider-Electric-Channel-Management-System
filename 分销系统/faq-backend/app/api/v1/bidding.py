"""招标文件上传与分析 API"""
import glob
import os
from typing import Optional

import requests
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import enforce_rate_limit, require_bidding_whitelist
from app.core.logging import get_logger
from app.services.bidding_analyzer import BiddingAnalyzer

router = APIRouter(tags=["招标分析"])

logger = get_logger(__name__)

BIDDING_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "bidding-docs")
BIDDING_DOCS_DIR = os.path.abspath(BIDDING_DOCS_DIR)


class BiddingUploadRequest(BaseModel):
    download_url: str
    filename: str = ""


@router.post("/bidding/upload")
async def upload_tender_file(
    body: Optional[BiddingUploadRequest] = Body(None),
    current_user_id: str = Depends(require_bidding_whitelist),
):
    """
    上传招标文件并进行分析（模式一：资料提取）。
    保留用于向后兼容，建议使用 /bidding/extract。

    流程：
      1. 从云存储下载链接获取文件内容
      2. 验证文件类型和大小
      3. 提取文本（自动识别 PDF / Word 格式）
      4. 关键词匹配检测
      5. 返回分析报告 + 推荐文件列表
    """
    return await _handle_extract_analysis(body, current_user_id)


async def _download_and_extract_text(body: BiddingUploadRequest, current_user_id: str) -> tuple[str, bytes]:
    """下载文件并提取文本，返回 (text, content)。"""
    enforce_rate_limit("bidding_upload", current_user_id, limit=10, window_seconds=600)

    if not body or not body.download_url:
        raise HTTPException(status_code=400, detail="请提供文件下载链接")

    # 1. 从云存储下载文件
    try:
        logger.info("bidding_download_cloud_file", url=body.download_url[:80])
        resp = requests.get(body.download_url, timeout=60)
        resp.raise_for_status()
        content = resp.content
    except requests.RequestException as exc:
        logger.error("bidding_download_failed", error=str(exc))
        raise HTTPException(status_code=400, detail="文件下载失败，请重试") from exc

    filename = body.filename or "文件"

    # 2. 验证文件
    error = BiddingAnalyzer.validate_file(
        filename=filename,
        content_type="",
        file_size=len(content),
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 3. 提取文本
    try:
        text = BiddingAnalyzer.extract_text(content, filename=filename)
    except RuntimeError as exc:
        logger.error("bidding_extract_failed", error=str(exc), user_id=current_user_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="该文件无法提取文字内容，可能是扫描件（图片格式）或空文件，暂不支持分析。请使用文字版 PDF 或 Word 文档。",
        )

    return text, content


async def _handle_extract_analysis(body: BiddingUploadRequest, current_user_id: str):
    """模式一：资料提取 — 识别招标文件要求的证书/报告，提供下载。"""
    text, content = await _download_and_extract_text(body, current_user_id)
    filename = body.filename or "文件"

    keyword_result = BiddingAnalyzer.keyword_match(text)
    recommended_docs = BiddingAnalyzer.get_recommended_documents(keyword_result)

    logger.info(
        "bidding_extract_complete",
        user_id=current_user_id,
        filename=filename,
        risk_level=keyword_result["risk_level"],
        requirements_count=len(keyword_result.get("bidding_requirements", {})),
    )

    return {
        "code": 0,
        "message": "资料提取完成",
        "data": {
            "filename": filename,
            "file_size": len(content),
            "analysis": keyword_result,
            "recommended_documents": recommended_docs,
        },
    }


@router.post("/bidding/extract")
async def extract_tender_documents(
    body: Optional[BiddingUploadRequest] = Body(None),
    current_user_id: str = Depends(require_bidding_whitelist),
):
    """
    模式一：招标文件资料提取。
    上传招标文件后，识别文件中要求投标人提供的证书和报告，
    匹配已有文件并提供下载链接。
    """
    return await _handle_extract_analysis(body, current_user_id)


@router.post("/bidding/analyze")
async def analyze_tender_deep(
    body: Optional[BiddingUploadRequest] = Body(None),
    current_user_id: str = Depends(require_bidding_whitelist),
):
    """
    模式二：招标文件智能分析。
    上传招标文件后，深度分析：
      - 施耐德有利条款检测（已植入 vs 缺失）
      - 友商植入痕迹检测
      - 产品匹配推荐（I-Line B/H/W）
      - 投标策略建议
    """
    text, content = await _download_and_extract_text(body, current_user_id)
    filename = body.filename or "文件"

    # 深度分析
    deep_result = BiddingAnalyzer.deep_analyze(text, filename=filename)

    logger.info(
        "bidding_deep_analyze_complete",
        user_id=current_user_id,
        filename=filename,
        risk_level=deep_result["risk_level"],
        favorable_count=len(deep_result["favorable_clauses"]),
        best_product=deep_result["product_match"].get("best_match", ""),
    )

    return {
        "code": 0,
        "message": "智能分析完成",
        "data": {
            "filename": filename,
            "file_size": len(content),
            "analysis": deep_result,
        },
    }


@router.get("/bidding/docs")
async def list_available_documents(
    current_user_id: str = Depends(require_bidding_whitelist),
):
    """
    获取可下载的投标文件清单。
    自动检测 static/bidding-docs/ 目录下的文件，支持每个 key 对应多个文件。
    """
    from app.services.bidding_features import REQUIRED_DOCUMENTS

    docs = []
    base_url = "/static/bidding-docs"

    for doc_name, doc_info in REQUIRED_DOCUMENTS.items():
        key = doc_info["key"]
        # 使用 glob 匹配所有以 key 开头的文件（支持多文件：key.pdf, key_xxx.pdf 等）
        pattern = os.path.join(BIDDING_DOCS_DIR, f"{key}*.pdf")
        matched_files = sorted(glob.glob(pattern))

        if matched_files:
            # 有多个文件时，返回文件列表
            files = []
            for fpath in matched_files:
                fname = os.path.basename(fpath)
                # 提取子标签（如 type_test_report_1350-800A.pdf → "1350-800A"）
                stem = fname.replace(".pdf", "")
                if stem == key:
                    sub_label = ""
                else:
                    sub_label = stem[len(key) + 1:]  # 去掉 key_ 前缀
                files.append({
                    "filename": fname,
                    "label": sub_label,
                    "download_url": f"{base_url}/{fname}",
                })
            docs.append({
                "name": doc_name,
                "key": key,
                "description": doc_info["description"],
                "download_url": f"{base_url}/{os.path.basename(matched_files[0])}",
                "available": True,
                "files": files,
            })
        else:
            docs.append({
                "name": doc_name,
                "key": key,
                "description": doc_info["description"],
                "download_url": f"{base_url}/{key}.pdf",
                "available": False,
                "files": [],
            })

    return {
        "code": 0,
        "message": "获取成功",
        "data": {"documents": docs},
    }