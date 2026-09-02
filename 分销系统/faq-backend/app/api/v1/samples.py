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

# callContainer 响应包上限为 1000KiB，单次分片控制在 786KB，留足余量
CHUNK_SIZE = 786 * 1024

# 分片数量上限（防止异常 URL 造成大量请求）
MAX_PARTS = 200

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


def _infer_cos_bucket_from_host(hostname: str) -> str | None:
    """从 COS/云托管 URL 的 host 推断 bucket 名。

    - https://{bucket}.tcb.qcloud.la/{key}
    - https://{bucket}.cos.{region}.myqcloud.com/{key}
    """
    host = (hostname or "").lower()
    if host.endswith(".tcb.qcloud.la"):
        return host[: -len(".tcb.qcloud.la")]
    if host.endswith(".myqcloud.com"):
        return host.split(".myqcloud.com")[0].split(".")[0]
    return None


def _infer_cos_region_from_host(hostname: str) -> str | None:
    match = re.search(r"\.cos\.([^.]+)\.myqcloud\.com$", (hostname or "").lower())
    if match:
        return match.group(1)
    return None


async def _fetch_stream(url: str, client: httpx.AsyncClient, range_header: str | None = None):
    """请求目标 URL 并返回响应对象。

    range_header 形如 "bytes=0-99"，用于分片下载（源支持 Range 时返回 206）。
    """
    try:
        request = client.build_request(
            "GET",
            url,
            headers={"Range": range_header} if range_header else None,
            timeout=60,
        )
        # 注意：follow_redirects 是 send() 的参数，不是 build_request() 的参数
        response = await client.send(request, stream=True, follow_redirects=True)
        return response
    except httpx.HTTPError as exc:
        logger.error("sample_proxy_fetch_failed", url=url[:120], error=str(exc))
        raise HTTPException(status_code=502, detail="下载源文件失败，请稍后重试") from exc


@router.get("/samples/download")
async def proxy_download_sample(
    url: str = Query(..., min_length=1),
    filename: str = Query(default="", max_length=255),
    action: str = Query("download", pattern="^(meta|download)$"),
    part: int = Query(0, ge=0),
    part_size: int = Query(CHUNK_SIZE, ge=1024, le=CHUNK_SIZE),
    current_user_id: str = Depends(get_current_user_id),
):
    """代理下载智能体返回的样本/资料链接（分片）。支持对已过期的 COS 临时签名自动重签。

    微信云托管 callContainer 响应包上限 1000KiB，因此大文件按 part 切片返回，
    每片不超过 part_size（默认 786KB）。
    - action=meta     : 返回 {"size": N}，用于前端计算分片数
    - action=download : 返回第 part 片二进制（字节区间 [part*part_size, (part+1)*part_size-1]）
    """
    try:
        return await _proxy_download_sample_inner(
            url=url,
            filename=filename,
            action=action,
            part=part,
            part_size=part_size,
            current_user_id=current_user_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # 兜底：任何未预期异常都打印完整 traceback，便于线上定位
        logger.exception(
            "sample_proxy_unexpected_error",
            url=url[:120],
            filename=filename[:80],
            action=action,
            part=part,
            user_id=current_user_id[:16],
        )
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{type(exc).__name__}") from exc


async def _resolve_response(
    url: str,
    parsed,
    object_key: str,
    client: httpx.AsyncClient,
    current_user_id: str,
    range_header: str | None = None,
) -> httpx.Response:
    """请求目标内容；对 COS 过期签名（401/403）自动用 COS SDK 重新签发。"""
    response = await _fetch_stream(url, client, range_header=range_header)

    if response.status_code in (401, 403) and object_key:
        await response.aclose()
        try:
            from qcloud_cos import CosConfig, CosS3Client

            secret_id = settings.COS_SECRET_ID
            secret_key = settings.COS_SECRET_KEY
            if not (secret_id and secret_key):
                host_bucket = _infer_cos_bucket_from_host(parsed.hostname or "")
                logger.warning(
                    "sample_proxy_cos_resign_skipped_missing_credentials",
                    key=object_key[:60],
                    inferred_bucket=(host_bucket or "")[:60],
                )
            else:
                # 候选 bucket/region：优先从链接 host 推断，其次用配置兜底
                candidates = [
                    (
                        _infer_cos_bucket_from_host(parsed.hostname or "") or settings.COS_BUCKET,
                        _infer_cos_region_from_host(parsed.hostname or "") or settings.COS_REGION,
                    )
                ]
                if candidates[0] != (settings.COS_BUCKET, settings.COS_REGION):
                    candidates.append((settings.COS_BUCKET, settings.COS_REGION))

                reps_res: httpx.Response | None = None
                for bucket, region in candidates:
                    if not bucket or not region:
                        continue
                    try:
                        config = CosConfig(
                            Region=region,
                            SecretId=secret_id,
                            SecretKey=secret_key,
                            Token=settings.COS_SESSION_TOKEN,
                            Scheme="https",
                        )
                        client_sdk = CosS3Client(config)
                        new_url = client_sdk.get_presigned_download_url(
                            Bucket=bucket,
                            Key=object_key,
                            Expired=900,
                        )
                        logger.info(
                            "sample_proxy_cos_repair",
                            bucket=bucket,
                            key=object_key[:60],
                            user_id=current_user_id[:16],
                        )
                        reps_res = await _fetch_stream(new_url, client, range_header=range_header)
                        if 200 <= reps_res.status_code < 300:
                            break
                        await reps_res.aclose()
                        reps_res = None
                    except Exception as slot_exc:
                        logger.warning(
                            "sample_proxy_cos_repair_slot_failed",
                            bucket=bucket,
                            key=(object_key or "")[:60],
                            error=str(slot_exc),
                        )

                if reps_res is not None:
                    response = reps_res
        except Exception as exc:
            logger.warning("sample_proxy_cos_repair_failed", key=(object_key or "")[:60], error=str(exc))

    if response.status_code < 200 or response.status_code >= 300:
        detail = f"下载失败（HTTP {response.status_code}），请稍后重试"
        await response.aclose()
        raise HTTPException(status_code=response.status_code, detail=detail)

    return response


async def _proxy_download_sample_inner(
    url: str,
    filename: str,
    action: str,
    part: int,
    part_size: int,
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
        if action == "meta":
            response = await _resolve_response(url, parsed, object_key, client, current_user_id)
            size_str = response.headers.get("content-length")
            try:
                size = int(size_str) if size_str else 0
            except (TypeError, ValueError):
                size = 0
            await response.aclose()

            if size > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="文件过大，无法下载")
            if size <= 0:
                raise HTTPException(status_code=400, detail="文件为空，无法下载")

            parts = max(1, (size + part_size - 1) // part_size)
            if parts > MAX_PARTS:
                raise HTTPException(status_code=413, detail="文件过大，无法下载")
            logger.info(
                "sample_proxy_meta_ok",
                size=size,
                parts=parts,
                filename=(filename or _extract_filename(url)),
                user_id=current_user_id[:16],
            )
            from fastapi.responses import JSONResponse  # noqa: PLC0415

            # version 用于让前端/用户确认后端已部署分片协议（旧版会整包返回，触发 -606002）
            return JSONResponse({"size": size, "parts": parts, "version": 2})

        # action == "download": 返回第 part 片
        start = part * part_size
        if start >= MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="文件过大，无法下载")
        end = start + part_size - 1
        range_header = f"bytes={start}-{end}"

        response = await _resolve_response(
            url,
            parsed,
            object_key,
            client,
            current_user_id,
            range_header=range_header,
        )
        content = await response.aread()
        await response.aclose()

        # 源若忽略 Range 而返回全量，则本地截取所需片段，避免超限
        if len(content) > part_size:
            content = content[start : start + part_size]

        safe_name = _secure_filename(filename) if filename else _extract_filename(url)
        logger.info(
            "sample_proxy_part_ok",
            part=part,
            size=len(content),
            filename=safe_name,
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