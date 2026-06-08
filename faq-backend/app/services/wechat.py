"""WeChat login and phone-number related service helpers."""

import time
from typing import Optional, Union

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

WECHAT_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_GET_PHONE_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"

_access_token_cache = {
    "token": None,
    "expires_at": 0,
}
_tls_warning_logged = False


class WeChatLoginResult:
    def __init__(
        self,
        openid: str,
        session_key: Optional[str] = None,
        unionid: Optional[str] = None,
    ):
        self.openid = openid
        self.session_key = session_key
        self.unionid = unionid


def _resolve_tls_verify() -> Union[bool, str]:
    if settings.WECHAT_CA_BUNDLE:
        return settings.WECHAT_CA_BUNDLE
    return settings.WECHAT_SSL_VERIFY


def _build_wechat_http_client() -> httpx.AsyncClient:
    global _tls_warning_logged

    verify = _resolve_tls_verify()
    if verify is False and not _tls_warning_logged:
        logger.warning("wechat_ssl_verify_disabled")
        _tls_warning_logged = True

    return httpx.AsyncClient(
        timeout=10.0,
        verify=verify,
        trust_env=settings.WECHAT_HTTP_TRUST_ENV,
    )


async def get_wechat_session(code: str) -> WeChatLoginResult:
    if settings.DEBUG and not settings.WECHAT_APPID:
        logger.info("wechat_login_mock", code=code[:8])
        return WeChatLoginResult(
            openid=f"mock_openid_{code[:16]}",
            session_key="mock_session_key",
        )

    if not settings.WECHAT_APPID or not settings.WECHAT_SECRET:
        raise ValueError("Missing WeChat config: WECHAT_APPID and WECHAT_SECRET are required")

    params = {
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }

    async with _build_wechat_http_client() as client:
        response = await client.get(WECHAT_JSCODE2SESSION_URL, params=params)
        data = response.json()

    if "errcode" in data and data["errcode"] != 0:
        logger.error(
            "wechat_login_error",
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        raise ValueError(f"WeChat login failed: {data.get('errmsg')}")

    logger.info("wechat_login_success", openid=data["openid"][:8])
    return WeChatLoginResult(
        openid=data["openid"],
        session_key=data.get("session_key"),
        unionid=data.get("unionid"),
    )


async def get_access_token() -> str:
    if settings.DEBUG and not settings.WECHAT_APPID:
        return "mock_access_token"

    current_time = time.time()
    if _access_token_cache["token"] and _access_token_cache["expires_at"] > current_time + 300:
        return _access_token_cache["token"]

    if not settings.WECHAT_APPID or not settings.WECHAT_SECRET:
        raise ValueError("Missing WeChat config: WECHAT_APPID and WECHAT_SECRET are required")

    params = {
        "grant_type": "client_credential",
        "appid": settings.WECHAT_APPID,
        "secret": settings.WECHAT_SECRET,
    }

    async with _build_wechat_http_client() as client:
        response = await client.get(WECHAT_TOKEN_URL, params=params)
        data = response.json()

    if "errcode" in data and data["errcode"] != 0:
        logger.error(
            "get_access_token_error",
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        raise ValueError(f"Failed to get access_token: {data.get('errmsg')}")

    _access_token_cache["token"] = data["access_token"]
    _access_token_cache["expires_at"] = current_time + data["expires_in"]
    return data["access_token"]


async def get_user_phone_number(code: str) -> str:
    if settings.DEBUG and not settings.WECHAT_APPID:
        logger.info("wechat_get_phone_mock", code=code[:8])
        return "13800000000"

    access_token = await get_access_token()
    url = f"{WECHAT_GET_PHONE_URL}?access_token={access_token}"
    payload = {"code": code}

    async with _build_wechat_http_client() as client:
        response = await client.post(url, json=payload)
        data = response.json()

    if "errcode" in data and data["errcode"] != 0:
        logger.error(
            "get_phone_error",
            errcode=data.get("errcode"),
            errmsg=data.get("errmsg"),
        )
        raise ValueError(f"Failed to get phone number: {data.get('errmsg')}")

    phone_info = data.get("phone_info", {})
    phone_number = phone_info.get("phoneNumber")
    if not phone_number:
        raise ValueError("No valid phone number returned by WeChat")

    logger.info("wechat_get_phone_success", phone=f"{phone_number[:3]}****{phone_number[-4:]}")
    return phone_number
