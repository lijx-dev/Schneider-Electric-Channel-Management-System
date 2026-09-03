#!/usr/bin/env python3
"""一次性脚本：刷新 product_guide_assets 中已过期的 COS 签名链接。

适用场景：智能体返回的样本/资料链接（tcb.qcloud.la 或 *.myqcloud.com）
的临时签名（?sign=..&t=..）已过期，小程序直连失败时反复 403。

运行方式（微信云托管容器内）：
    python scripts/refresh_guide_asset_urls.py

必需环境变量（在云托管控制台配置，勿写入代码）：
    DATABASE_URL              -- 数据库连接串（若未配置则沿用 app 配置）
    COS_SECRET_ID             -- COS 密钥 ID
    COS_SECRET_KEY            -- COS 密钥 Key
可选：
    COS_REGION                -- 默认 ap-shanghai，脚本会按对象 host 自动推断
                                 并轮询常见地域验证
    EXPIRED_DAYS              -- 新签名有效期（天），默认 90

说明：
- 只处理 https://{bucket}.tcb.qcloud.la/{key}?sign=..&t=.. 与
  https://{bucket}.cos.{region}.myqcloud.com/{key}?sign=..&t=.. 格式；
  其他（cloud://、空、代理路径）保持不变。
- 每个对象按 host 推断 bucket，并对常见地域逐一尝试签名 + Range GET 校验，
  取第一个可正常访问的新签名写入库；全部失败则保留原值并告警。
- 幂等：可重复运行，中途失败可重新执行。
"""

import asyncio
import os
import sys
from urllib.parse import unquote, urlsplit

import httpx

# 让脚本能以项目子目录代码直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_REGION = "ap-shanghai"
REGION_CANDIDATES = [
    "ap-shanghai",
    "ap-guangzhou",
    "ap-beijing",
    "ap-nanjing",
    "ap-chengdu",
    "ap-hongkong",
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def parse_cos_reference(cos_url: str):
    """从链接解析 (bucket, key)；非 COS 链接返回 (None, None)。"""
    if not cos_url or not isinstance(cos_url, str):
        return None, None

    normalized = cos_url.strip()
    if not normalized.startswith("https://"):
        return None, None

    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").lower()
    if host.endswith(".tcb.qcloud.la"):
        bucket = host[: -len(".tcb.qcloud.la")]
    elif host.endswith(".myqcloud.com"):
        bucket = host.split(".myqcloud.com")[0].split(".")[0]
    else:
        return None, None

    key = unquote(parsed.path or "").lstrip("/")
    if not key:
        return None, None
    return bucket, key


async def _download_ok(client: httpx.AsyncClient, url: str) -> bool:
    """用 Range GET 校验对象可读。

    注意：get_presigned_download_url 签发的链接只授权 GET 方法，
    直接发 HEAD 会被 COS 以 403 拒绝（签名不匹配），产生误判。
    因此改为发 bytes=0-63 的 Range GET：200/206 表示可读；
    403/404 表示无权限或对象不存在。
    """
    try:
        resp = await client.get(
            url,
            timeout=15,
            follow_redirects=True,
            headers={"Range": "bytes=0-63"},
        )
        return resp.status_code in (200, 203, 206)
    except Exception:
        return False


def _sign(bucket: str, key: str, region: str, expire_seconds: int, secret_id: str, secret_key: str, token: str) -> str:
    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=region,
        SecretId=secret_id,
        SecretKey=secret_key,
        Token=token or None,
        Scheme="https",
    )
    client = CosS3Client(config)
    try:
        return client.get_presigned_download_url(
            Bucket=bucket,
            Key=key,
            Expired=expire_seconds,
        )
    except AttributeError:
        return client.get_presigned_url(
            Method="GET",
            Bucket=bucket,
            Key=key,
            Expired=expire_seconds,
        )


async def resolve_new_url(
    http: httpx.AsyncClient,
    bucket: str,
    key: str,
    secret_id: str,
    secret_key: str,
    token: str,
    expire_days: int,
    prefer_region: str,
) -> str | None:
    expire_seconds = expire_days * 24 * 3600
    candidate_regions = [r for r in (prefer_region,) if r] + REGION_CANDIDATES
    seen = set()
    for region in candidate_regions:
        if region in seen:
            continue
        seen.add(region)
        try:
            signed = _sign(bucket, key, region, expire_seconds, secret_id, secret_key, token)
        except Exception as exc:  # noqa: BLE001
            _log(f"  [warn] region={region} 签名失败: {exc}")
            continue
        if await _download_ok(http, signed):
            return signed
    return None


async def main() -> int:
    # 凭据一律来自环境变量（云托管注入），避免密钥进入代码
    secret_id = os.environ.get("COS_SECRET_ID", "").strip()
    secret_key = os.environ.get("COS_SECRET_KEY", "").strip()
    if not (secret_id and secret_key):
        _log("缺少 COS_SECRET_ID / COS_SECRET_KEY 环境变量，中止")
        return 2

    try:
        from app.core.config import settings
        from app.db.session import get_database_url
    except Exception as exc:  # noqa: BLE001
        _log(f"导入 app 配置失败（是否在项目根运行？）：{exc}")
        return 2

    database_url = os.environ.get("DATABASE_URL", "").strip() or get_database_url()
    # 同步直连用 aiomysql 驱动跑异步更复杂，这里直接用 aiosqlite 适配？不——
    # 容器内为 MySQL，使用 aiomysql 引擎即可；此处用 asyncio + aiomysql 简洁直白
    _log(f"数据库: {database_url.split('@')[-1] if '@' in database_url else 'memory/sqlite'}")

    from aiomysql import connect

    # 解析连接串（mysql+aiomysql://user:pass@host:port/db?charset=..）
    # 在容器内 DATABASE_URL 通常为 mysql+aiomysql://..，切换驱动前缀为 pymysql 逻辑
    raw = database_url.replace("mysql+aiomysql://", "mysql://", 1)
    from urllib.parse import parse_qs, urlsplit

    pinfo = urlsplit(raw)
    params = parse_qs(pinfo.query)
    password = pinfo.password or ""
    db_name = (pinfo.path or "").lstrip("/").split("/")[0].split("?")[0]

    conn = await connect(
        host=pinfo.hostname,
        port=pinfo.port or 3306,
        user=pinfo.username or "root",
        password=password,
        db=db_name or "faq_db",
        charset=params.get("charset", ["utf8mb4"])[0],
        autocommit=False,
    )

    prefer_region = os.environ.get("COS_REGION", "").strip() or DEFAULT_REGION
    expire_days = int(os.environ.get("EXPIRED_DAYS", "90").strip() or "90")
    token = os.environ.get("COS_SESSION_TOKEN", "").strip()

    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, node_id, cos_url FROM product_guide_assets "
                "WHERE cos_url LIKE '%%tcb.qcloud.la%%' OR cos_url LIKE '%%myqcloud.com%%'"
            )
            rows = await cur.fetchall()

        _log(f"待处理记录: {len(rows)} 条")
        concurrency = int(os.environ.get("REFRESH_CONCURRENCY", "10").strip() or "10")
        sem = asyncio.Semaphore(concurrency)

        async def refresh_one(item):
            row_id, node_id, cos_url = item
            bucket, key = parse_cos_reference(cos_url or "")
            if not bucket or not key:
                return "skip", row_id, node_id, ""
            async with sem:
                new_url = await resolve_new_url(
                    http, bucket, key, secret_id, secret_key, token, expire_days, prefer_region
                )
            if not new_url:
                return "fail", row_id, node_id, key
            return "ok", row_id, node_id, new_url

        async with httpx.AsyncClient() as http:
            results = await asyncio.gather(*(refresh_one(row) for row in rows))

        for status, row_id, node_id, new_url in sorted(results):
            if status == "skip":
                _log(f"[skip] id={row_id} 非 COS 外链，保持不变")
            elif status == "fail":
                _log(
                    f"[fail] id={row_id} node={node_id} key={new_url[:60]} "
                    "所有地域签名后 Range GET 均不可访问（对象可能已删除）"
                )
            else:
                _log(f"[ok]   id={row_id} node={node_id} -> 已刷新新签名（{len(new_url)}字符）")

        updated = sum(1 for s, *_ in results if s == "ok")
        failed = sum(1 for s, *_ in results if s == "fail")
        skipped = sum(1 for s, *_ in results if s == "skip")

        updates = [(new_url, row_id) for s, row_id, _, new_url in results if s == "ok"]
        if updates:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "UPDATE product_guide_assets SET cos_url=%s WHERE id=%s", updates
                )
            await conn.commit()

        _log(f"完成：已更新 {updated} 条，失败 {failed} 条，跳过 {skipped} 条")
        return 0 if failed == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))