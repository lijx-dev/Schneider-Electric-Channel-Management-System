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
WAIT_MIN_SECONDS = float(os.getenv("LOADTEST_WAIT_MIN_SECONDS", "3"))
WAIT_MAX_SECONDS = float(os.getenv("LOADTEST_WAIT_MAX_SECONDS", "9"))
OPT_LABELS = ["A", "B", "C", "D", "E", "F"]


def load_credentials() -> list[dict[str, Any]]:
    if not TOKEN_FILE.exists():
        raise RuntimeError(
            f"Token file not found: {TOKEN_FILE}. Run scripts/prepare_locust_users.py first."
        )

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

            fallback_id = random.choice(self._all_ids)
            return self._credentials[fallback_id]

    def release(self, user_id: str | None) -> None:
        if not user_id:
            return
        with self._lock:
            if user_id in self._checked_out:
                self._checked_out.remove(user_id)
                self._available_ids.append(user_id)


CREDENTIAL_POOL = CredentialPool(load_credentials())


class FaqDailyUser(HttpUser):
    """
    Realistic load profile for a 500-user mini program backend:
    - read-heavy daily quiz fetches
    - a smaller but real amount of daily submissions
    - profile/study record lookups
    - leaderboard refreshes

    Notes:
    - /auth/login* is intentionally excluded because it depends on WeChat APIs.
    - Re-run scripts/prepare_locust_users.py before each test if you want a clean daily submit state.
    """

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self) -> None:
        self.credential = CREDENTIAL_POOL.acquire()
        self.user_id = self.credential["user_id"]
        self.headers = {
            "Authorization": f"Bearer {self.credential['token']}",
            "Content-Type": "application/json",
        }
        self.quiz_date = ""
        self.pending_questions: list[dict[str, Any]] = []
        self.refresh_daily_quiz()

    def on_stop(self) -> None:
        CREDENTIAL_POOL.release(getattr(self, "user_id", None))

    def refresh_daily_quiz(self) -> None:
        with self.client.get(
            "/api/daily/quiz",
            params={"user_id": self.user_id},
            headers=self.headers,
            name="GET /api/daily/quiz",
            catch_response=True,
        ) as response:
            is_ok, payload = self._validate_response(response, "获取每周答题")
            if not is_ok or payload is None:
                return

            data = payload["data"]
            self.quiz_date = data.get("quiz_date", "")
            self.pending_questions = [
                question
                for question in data.get("questions", [])
                if question.get("user_answer") is None
            ]

    def _validate_response(self, response, action: str) -> tuple[bool, dict[str, Any] | None]:
        if response.status_code != 200:
            response.failure(f"{action} HTTP {response.status_code}: {response.text[:200]}")
            return False, None

        try:
            payload = response.json()
        except ValueError:
            response.failure(f"{action} 返回了非 JSON 数据")
            return False, None

        if payload.get("code") != 0:
            response.failure(f"{action}业务失败: {payload}")
            return False, payload

        response.success()
        return True, payload

    def build_answer(self, question: dict[str, Any]) -> str:
        question_type = question.get("question_type")
        options = question.get("options") or []

        if question_type == "multiple_choice" and options:
            option_count = min(len(options), len(OPT_LABELS))
            pick_count = min(option_count, random.choice([1, 1, 2, 2, 3]))
            selected_indexes = sorted(random.sample(range(option_count), pick_count))
            return "".join(OPT_LABELS[index] for index in selected_indexes)

        if question_type == "true_false":
            if options:
                return options[random.randrange(len(options))]
            return random.choice(["正确", "错误"])

        if question_type in {"fill_blank", "short_answer"}:
            return "压测答案"

        if options:
            selected_index = random.randrange(min(len(options), len(OPT_LABELS)))
            return OPT_LABELS[selected_index]

        return "A"

    @task(50)
    def get_daily_quiz(self) -> None:
        self.refresh_daily_quiz()

    @task(25)
    def submit_daily_answer(self) -> None:
        if not self.pending_questions:
            self.refresh_daily_quiz()
            if not self.pending_questions:
                return

        question = random.choice(self.pending_questions)
        payload = {
            "user_id": self.user_id,
            "question_id": question["id"],
            "selected_answer": self.build_answer(question),
            "time_spent": random.randint(6, 45),
        }

        with self.client.post(
            "/api/daily/submit",
            json=payload,
            headers=self.headers,
            name="POST /api/daily/submit",
            catch_response=True,
        ) as response:
            is_ok, _ = self._validate_response(response, "提交每周答题")
            if not is_ok:
                return

            self.pending_questions = [
                item for item in self.pending_questions if item["id"] != question["id"]
            ]

    @task(15)
    def get_study_records(self) -> None:
        with self.client.get(
            "/api/study/records",
            params={"user_id": self.user_id},
            headers=self.headers,
            name="GET /api/study/records",
            catch_response=True,
        ) as response:
            self._validate_response(response, "获取学习记录")

    @task(7)
    def get_total_leaderboard(self) -> None:
        with self.client.get(
            "/api/leaderboard",
            params={"limit": 20, "scope": "total"},
            headers=self.headers,
            name="GET /api/leaderboard?scope=total",
            catch_response=True,
        ) as response:
            self._validate_response(response, "获取总榜")

    @task(3)
    def get_company_leaderboard(self) -> None:
        with self.client.get(
            "/api/leaderboard",
            params={"limit": 20, "scope": "company"},
            headers=self.headers,
            name="GET /api/leaderboard?scope=company",
            catch_response=True,
        ) as response:
            self._validate_response(response, "获取公司榜")
