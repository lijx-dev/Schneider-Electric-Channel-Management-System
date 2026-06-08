from __future__ import annotations

import json
import os
import random
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Any

from locust import HttpUser, between, task

ROOT_DIR = Path(__file__).resolve().parents[1]
TOKEN_FILE = Path(
    os.getenv(
        "LOADTEST_TOKEN_FILE",
        str(ROOT_DIR / "loadtests" / "data" / "loadtest_users.json"),
    )
)


def load_credentials() -> list[dict[str, Any]]:
    payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    users = payload.get("users", [])
    if not users:
        raise RuntimeError(f"No users found in token file: {TOKEN_FILE}")
    return users


class CredentialPool:
    def __init__(self, credentials: list[dict[str, Any]]) -> None:
        self._credentials = {item["user_id"]: item for item in credentials}
        self._available_ids = deque(item["user_id"] for item in credentials)
        self._all_ids = list(self._credentials.keys())
        self._checked_out: set[str] = set()
        self._lock = Lock()

    def acquire(self) -> dict[str, Any]:
        with self._lock:
            if self._available_ids:
                user_id = self._available_ids.popleft()
                self._checked_out.add(user_id)
                return self._credentials[user_id]
            return self._credentials[random.choice(self._all_ids)]

    def release(self, user_id: str | None) -> None:
        if not user_id:
            return
        with self._lock:
            if user_id in self._checked_out:
                self._checked_out.remove(user_id)
                self._available_ids.append(user_id)


CREDENTIAL_POOL = CredentialPool(load_credentials())


class AiOnlyUser(HttpUser):
    wait_time = between(20, 30)

    def on_start(self) -> None:
        self.credential = CREDENTIAL_POOL.acquire()
        self.user_id = self.credential["user_id"]
        self.headers = {
            "Authorization": f"Bearer {self.credential['token']}",
            "Content-Type": "application/json",
        }

    def on_stop(self) -> None:
        CREDENTIAL_POOL.release(getattr(self, "user_id", None))

    @task
    def ask_ai(self) -> None:
        payload = {
            "user_id": self.user_id,
            "message": "Please answer in one short Chinese sentence: what is a low-voltage circuit breaker?",
        }
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=self.headers,
            name="POST /api/chat",
            catch_response=True,
            timeout=180,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {response.text[:200]}")
                return

            try:
                body = response.json()
            except ValueError:
                response.failure("non-JSON response")
                return

            if body.get("code") != 0:
                response.failure(f"business failure: {body}")
                return

            response.success()

