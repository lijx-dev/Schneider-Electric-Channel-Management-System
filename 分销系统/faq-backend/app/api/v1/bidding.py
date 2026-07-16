"""招标文件上传与分析 API"""
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
    上传招标文件并进行分析。

    流程：
      1. 从云存储下载链接获取文件内容
      2. 验证文件类型和大小
      3. 提取文本（自动识别 PDF / Word 格式）
      4. 关键词匹配检测
      5. 返回分析报告 + 推荐文件列表
    """
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
        raise HTTPException(status_code=400, detail=f"文件下载失败，请重试") from exc

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

    # 4. 关键词匹配分析
    keyword_result = BiddingAnalyzer.keyword_match(text)

    # 5. 推荐投标文件
    recommended_docs = BiddingAnalyzer.get_recommended_documents(keyword_result)

    logger.info(
        "bidding_analysis_complete",
        user_id=current_user_id,
        filename=filename,
        risk_level=keyword_result["risk_level"],
        competitors_count=len(keyword_result["competitors"]),
        pages=keyword_result["total_pages"],
    )

    return {
        "code": 0,
        "message": "分析完成",
        "data": {
            "filename": filename,
            "file_size": len(content),
            "analysis": keyword_result,
            "recommended_documents": recommended_docs,
        },
    }


@router.get("/bidding/docs")
async def list_available_documents(
    current_user_id: str = Depends(require_bidding_whitelist),
):
    """
    获取可下载的投标文件清单。
    自动检测 static/bidding-docs/ 目录下的文件，返回实际可用状态。
    """
    from app.services.bidding_features import REQUIRED_DOCUMENTS

    docs = []
    base_url = "/static/bidding-docs"

    for doc_name, doc_info in REQUIRED_DOCUMENTS.items():
        file_path = os.path.join(BIDDING_DOCS_DIR, f"{doc_info['key']}.pdf")
        available = os.path.isfile(file_path)
        docs.append({
            "name": doc_name,
            "key": doc_info["key"],
            "description": doc_info["description"],
            "download_url": f"{base_url}/{doc_info['key']}.pdf",
            "available": available,
        })

    return {
        "code": 0,
        "message": "获取成功",
        "data": {"documents": docs},
    }