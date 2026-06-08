"""Admin authentication helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def create_admin_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(hours=12),
    }
    return jwt.encode(payload, settings.admin_secret_key, algorithm=ALGORITHM)


def verify_admin_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.admin_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None

    if payload.get("role") != "admin":
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None
