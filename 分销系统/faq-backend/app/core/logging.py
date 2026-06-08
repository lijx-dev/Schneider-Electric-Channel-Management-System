"""
结构化日志模块 - 使用 structlog 输出 JSON 格式日志
"""
import logging
import re
import sys
import structlog
from typing import Any

SENSITIVE_LOG_KEYS = {
    "access_token",
    "answer",
    "authorization",
    "avatar",
    "avatar_url",
    "body",
    "data",
    "feedback_info",
    "openid",
    "password",
    "phone",
    "query",
    "receiver_address",
    "receiver_phone",
    "reply",
    "secret",
    "session_key",
    "token",
    "unionid",
    "user_id",
}

PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def _mask_identifier(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _redact_string(value: str) -> str:
    value = PHONE_PATTERN.sub(lambda match: f"{match.group(0)[:3]}****{match.group(0)[-4:]}", value)
    return BEARER_PATTERN.sub("Bearer ***", value)


def _redact_log_value(key: str, value: Any) -> Any:
    normalized_key = key.lower()
    if normalized_key in {"body", "data", "query", "answer", "reply", "feedback_info"}:
        return "[redacted]"

    if normalized_key in SENSITIVE_LOG_KEYS:
        if value is None:
            return None
        return _mask_identifier(str(value))

    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {item_key: _redact_log_value(str(item_key), item_value) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_log_value("", item) for item in value]
    return value


def redact_sensitive_fields(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    return {key: _redact_log_value(str(key), value) for key, value in event_dict.items()}


def setup_logging(debug: bool = False) -> None:
    """
    配置结构化日志
    
    Args:
        debug: 是否为调试模式，调试模式下输出更友好的格式
    """
    # 配置标准 logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # 选择渲染器：开发环境用彩色控制台，生产环境用JSON
    if debug:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            redact_sensitive_fields,
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> Any:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称，通常使用 __name__
        
    Returns:
        structlog 日志记录器
    """
    return structlog.get_logger(name)
