"""样本/资料文件代理下载接口。

智能体（HiAgent 数据库查询工作流）返回的"样本下载"链接通常是带时效签名的
腾讯云对象存储地址（如 https://{bucket}-{env}.tcb.qcloud.la/{key}?sign=...&t=...）。
该链接直接交给 wx.downloadFile 会因以下原因失败：
  1. 签名链接已过期（t 为毫秒级过期时间戳），返回 403；
  2. 微信小程序 downloadFile 需要配置合法域名，COS 域名若不配置会被客户端直接拦截。

因此统一通过本接口代理下载：由后端代为请求原链接（必要时基于 COS SDK 重新签名），
以二进制流返回给小程序的 wx.cloud.callContainer（云托管调用不受 downloadFile
合法域名限制），前端写临时文件后打开预览。
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote, unquote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter(tags=["样本下载"])

logger = get_logger(__name__)

# 文件大小上限（字节）：保护内存，避免下载超大文件导致 OOM
MAX_FILE_SIZE = 50 * 1024 * 1024

# SSRF 防护：只允许腾讯云对象存储/云托管域名
DEFAULT_ALLOWED_HOST_SUFFIXES = (
    ".tcb.qcloud.la",
    ".myqcloud.com",
    ".qcloud.la",
    ".qcloud.com",
)

_BLOCKED_CIDR_PATTERNS = (
    "127.",
    "10.",
    "192.168.",
    "172.",
)


def _get_allowed_suffixes() -> tuple[str, ...]:
    extra = (settings.SAMPLE_DOWNLOAD_ALLOWED_SUFFIXES or "").strip()
    suffixes = list(DEFAULT_ALLOWED_HOST_SUFFIXES)
    if extra:
        suffixes.extend(s.strip().lower() for s in extra.split(",") if s.strip())
    return tuple(suffixes)


def _is_allowed_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False

    # 拒绝内网地址（含 localhost 与通用内网网段）
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.startswith(_BLOCKED_CIDR_PATTERNS):
        return False

    return any(host.endswith(suffix) for suffix in _get_allowed_suffixes())


def _extract_filename(url: str, fallback: str = "样本文件.pdf") -> str:
    name = fallback or ""
    try:
        path = urlsplit(url).path or ""
        stem = path.rstrip("/").split("/")[-1]
        if stem:
            name = unquote(stem)
    except Exception:
        pass
    if not name or name == "/":
        name = fallback
    # 防止文件名注入 header
    name = re.sub(r'[\r\n"\']+', "", name).strip()
    return name or "样本文件.pdf"


def _secure_filename(filename: str) -> str:
    clean = os.path.basename(filename or "").replace("\\", "/").split("/")[-1]
    clean = re.sub(r'[\r\n"\']+', "", clean).strip()
    return clean or "样本文件.pdf"


async def _fetch_stream(url: str, client: httpx.AsyncClient):
    """请求目标 URL 并返回响应对象。"""
    try:
        request = client.build_request("GET", url, follow_redirects=True, timeout=60)
        response = await client.send(request, stream=True)
        return response
    except httpx.HTTPError as exc:
        logger.error("sample_proxy_fetch_failed", url=url[:120], error=str(exc))
        raise HTTPException(status_code=502, detail="下载源文件失败，请稍后重试") from exc


@router.get("/samples/download")
async def proxy_download_sample(
    url: str = Query(..., min_length=1),
    filename: str = Query(default="", max_length=255),
    current_user_id: str = Depends(get_current_user_id),
):
    """代理下载智能体返回的样本/资料链接。支持对已过期的 COS 临时签名自动重签。"""
    try:
        return await _proxy_download_sample_inner(url, filename, current_user_id)
    except HTTPException:
        raise
    except Exception as exc:  # 兜底：任何未预期异常都打印完整 traceback，便于线上定位
        logger.exception(
            "sample_proxy_unexpected_error",
            url=url[:120],
            filename=filename[:80],
            user_id=current_user_id[:16],
        )
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{type(exc).__name__}") from exc


async def _proxy_download_sample_inner(
    url: str,
    filename: str,
    current_user_id: str,
):
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="仅支持 https 下载链接")

    parsed = urlsplit(url)
    if not _is_allowed_host(parsed.hostname or ""):
        logger.warning("sample_proxy_blocked_host", host=(parsed.hostname or "")[:80], user_id=current_user_id[:16])
        raise HTTPException(status_code=403, detail="下载链接域名未在白名单中")

    object_key = unquote(parsed.path or "").lstrip("/")

    async with httpx.AsyncClient() as client:
        response = await _fetch_stream(url, client)

        # COS 临时签名过期（401/403）时，尝试用 COS SDK 基于对象 key 重新签发
        if response.status_code in (401, 403) and object_key:
            try:
                from qcloud_cos import CosConfig, CosS3Client

                if settings.COS_BUCKET and settings.COS_REGION:
                    config = CosConfig(
                        Region=settings.COS_REGION,
                        SecretId=settings.COS_SECRET_ID,
                        SecretKey=settings.COS_SECRET_KEY,
                        Token=settings.COS_SESSION_TOKEN,
                        Scheme="https",
                    )
                    client_sdk = CosS3Client(config)
                    new_url = client_sdk.get_presigned_download_url(
                        Bucket=settings.COS_BUCKET,
                        Key=object_key,
                        Expired=900,
                    )
                    logger.info("sample_proxy_cos_repair", key=object_key[:60], user_id=current_user_id[:16])
                    await response.aclose()
                    response = await _fetch_stream(new_url, client)
            except Exception as exc:
                logger.warning("sample_proxy_cos_repair_failed", key=(object_key or "")[:60], error=str(exc))

        if response.status_code < 200 or response.status_code >= 300:
            detail = f"下载失败（HTTP {response.status_code}），请稍后重试"
            await response.aclose()
            raise HTTPException(status_code=response.status_code, detail=detail)

        # 关键：必须在 AsyncClient 关闭前把完整内容读入内存，
        # 不能在返回 StreamingResponse 后再读取（客户端已关闭会抛错导致 500）。
        content = await response.aread()
        await response.aclose()

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="文件过大，无法下载")

        safe_name = _secure_filename(filename) if filename else _extract_filename(url)
        logger.info(
            "sample_proxy_download_ok",
            filename=safe_name,
            size=len(content),
            user_id=current_user_id[:16],
        )
        return Response(
            content=content,
            media_type=response.headers.get("content-type") or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_name)}",
                "Cache-Control": "no-cache",
            },
        )