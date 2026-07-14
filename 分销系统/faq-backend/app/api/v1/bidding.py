"""招标文件上传与分析 API"""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.api.deps import enforce_rate_limit, get_current_user_id
from app.core.logging import get_logger
from app.services.bidding_analyzer import BiddingAnalyzer
from app.services.storage import StorageService

router = APIRouter(tags=["招标分析"])

logger = get_logger(__name__)


@router.post("/bidding/upload")
async def upload_tender_file(
    request: Request,
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user_id),
):
    """
    上传招标文件（PDF）并进行分析。

    流程：
      1. 验证文件类型和大小
      2. 读取文件内容
      3. 提取 PDF 文本
      4. 关键词匹配检测
      5. 返回分析报告 + 推荐文件列表
    """
    enforce_rate_limit("bidding_upload", current_user_id, limit=10, window_seconds=600)

    # 1. 读取文件内容
    content = await file.read()

    # 2. 验证文件
    error = BiddingAnalyzer.validate_file(
        filename=file.filename or "",
        content_type=file.content_type or "",
        file_size=len(content),
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 3. 提取文本（自动识别 PDF / Word 格式）
    try:
        text = BiddingAnalyzer.extract_text(content, filename=file.filename or "")
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
        filename=file.filename,
        risk_level=keyword_result["risk_level"],
        competitors_count=len(keyword_result["competitors"]),
        pages=keyword_result["total_pages"],
    )

    return {
        "code": 0,
        "message": "分析完成",
        "data": {
            "filename": file.filename,
            "file_size": len(content),
            "analysis": keyword_result,
            "recommended_documents": recommended_docs,
        },
    }


@router.get("/bidding/docs")
async def list_available_documents(
    current_user_id: str = Depends(get_current_user_id),
):
    """
    获取可下载的投标文件清单。
    返回当前可用的投标文件列表，包含文件名和下载链接。
    """
    from app.services.bidding_features import REQUIRED_DOCUMENTS

    docs = []
    base_url = "/static/bidding-docs"

    for doc_name, doc_info in REQUIRED_DOCUMENTS.items():
        docs.append({
            "name": doc_name,
            "key": doc_info["key"],
            "description": doc_info["description"],
            "download_url": f"{base_url}/{doc_info['key']}.pdf",
            "available": False,  # 默认不可用，需管理员上传文件后设为 True
        })

    return {
        "code": 0,
        "message": "获取成功",
        "data": {"documents": docs},
    }