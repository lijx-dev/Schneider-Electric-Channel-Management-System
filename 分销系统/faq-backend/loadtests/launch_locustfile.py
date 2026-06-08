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
            return self._credentials[random.choice(self._all_ids)]

    def release(self, user_id: str | None) -> None:
        if not user_id:
            return
        with self._lock:
            if user_id in self._checked_out:
                self._checked_out.remove(user_id)
                self._available_ids.append(user_id)


CREDENTIAL_POOL = CredentialPool(load_credentials())


class LaunchReadinessUser(HttpUser):
    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self) -> None:
        self.credential = CREDENTIAL_POOL.acquire()
        self.user_id = self.credential["user_id"]
        self.headers = {
            "Authorization": f"Bearer {self.credential['token']}",
            "Content-Type": "application/json",
        }
        self.pending_questions: list[dict[str, Any]] = []
        self.company_key = ""
        self.cert_type = ""
        self.category_name = ""
        self.model = ""
        self.refresh_daily_quiz()

    def on_stop(self) -> None:
        CREDENTIAL_POOL.release(getattr(self, "user_id", None))

    def _validate_response(self, response, action: str) -> tuple[bool, dict[str, Any] | None]:
        if response.status_code != 200:
            response.failure(f"{action} HTTP {response.status_code}: {response.text[:200]}")
            return False, None

        try:
            payload = response.json()
        except ValueError:
            response.failure(f"{action} returned non-JSON")
            return False, None

        if payload.get("code") != 0:
            response.failure(f"{action} business failure: {payload}")
            return False, payload

        response.success()
        return True, payload

    def refresh_daily_quiz(self) -> None:
        with self.client.get(
            "/api/daily/quiz",
            params={"user_id": self.user_id},
            headers=self.headers,
            name="GET /api/daily/quiz",
            catch_response=True,
        ) as response:
            is_ok, payload = self._validate_response(response, "daily quiz")
            if not is_ok or payload is None:
                return

            questions = payload.get("data", {}).get("questions", [])
            self.pending_questions = [
                question for question in questions if question.get("user_answer") is None
            ]

    def build_answer(self, question: dict[str, Any]) -> str:
        question_type = question.get("question_type")
        options = question.get("options") or []

        if question_type == "multiple_choice" and options:
            option_count = min(len(options), len(OPT_LABELS))
            pick_count = min(option_count, random.choice([1, 1, 2, 2, 3]))
            selected_indexes = sorted(random.sample(range(option_count), pick_count))
            return "".join(OPT_LABELS[index] for index in selected_indexes)

        if question_type == "true_false":
            return random.choice(["正确", "错误"])

        if question_type in {"fill_blank", "short_answer"}:
            return "load-test-answer"

        if options:
            selected_index = random.randrange(min(len(options), len(OPT_LABELS)))
            return OPT_LABELS[selected_index]

        return "A"

    @task(18)
    def get_home_rank(self) -> None:
        with self.client.get(
            "/api/user/rank",
            params={"user_id": self.user_id, "scope": "total"},
            headers=self.headers,
            name="GET /api/user/rank",
            catch_response=True,
        ) as response:
            self._validate_response(response, "home rank")

    @task(28)
    def get_daily_quiz(self) -> None:
        self.refresh_daily_quiz()

    @task(12)
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
            is_ok, _ = self._validate_response(response, "daily submit")
            if not is_ok:
                return
            self.pending_questions = [
                item for item in self.pending_questions if item["id"] != question["id"]
            ]

    @task(8)
    def get_study_records(self) -> None:
        with self.client.get(
            "/api/study/records",
            params={"user_id": self.user_id},
            headers=self.headers,
            name="GET /api/study/records",
            catch_response=True,
        ) as response:
            self._validate_response(response, "study records")

    @task(10)
    def get_total_leaderboard(self) -> None:
        with self.client.get(
            "/api/leaderboard",
            params={"limit": 20, "scope": "total"},
            headers=self.headers,
            name="GET /api/leaderboard?scope=total",
            catch_response=True,
        ) as response:
            self._validate_response(response, "total leaderboard")

    @task(4)
    def get_company_leaderboard(self) -> None:
        with self.client.get(
            "/api/leaderboard",
            params={"limit": 20, "scope": "company"},
            headers=self.headers,
            name="GET /api/leaderboard?scope=company",
            catch_response=True,
        ) as response:
            self._validate_response(response, "company leaderboard")

    @task(12)
    def get_energy_products(self) -> None:
        with self.client.get(
            "/api/energy/products",
            headers=self.headers,
            name="GET /api/energy/products",
            catch_response=True,
        ) as response:
            self._validate_response(response, "energy products")

    @task(8)
    def get_certificate_companies(self) -> None:
        with self.client.get(
            "/api/certificates/companies",
            headers=self.headers,
            name="GET /api/certificates/companies",
            catch_response=True,
        ) as response:
            is_ok, payload = self._validate_response(response, "certificate companies")
            if not is_ok or payload is None:
                return
            companies = payload.get("data") or []
            if companies:
                self.company_key = str(random.choice(companies).get("id") or "")

    @task(5)
    def get_certificate_types(self) -> None:
        if not self.company_key:
            self.get_certificate_companies()
            if not self.company_key:
                return

        with self.client.get(
            "/api/certificates/cert-types",
            params={"company_key": self.company_key},
            headers=self.headers,
            name="GET /api/certificates/cert-types",
            catch_response=True,
        ) as response:
            is_ok, payload = self._validate_response(response, "certificate types")
            if not is_ok or payload is None:
                return
            cert_types = payload.get("data") or []
            if cert_types:
                self.cert_type = str(random.choice(cert_types).get("id") or "")

    @task(3)
    def get_certificate_categories(self) -> None:
        if not self.cert_type:
            self.get_certificate_types()
            if not self.cert_type:
                return

        with self.client.get(
            "/api/certificates/categories",
            params={"company_key": self.company_key, "cert_type": self.cert_type},
            headers=self.headers,
            name="GET /api/certificates/categories",
            catch_response=True,
        ) as response:
            is_ok, payload = self._validate_response(response, "certificate categories")
            if not is_ok or payload is None:
                return
            categories = payload.get("data") or []
            if categories:
                self.category_name = str(random.choice(categories).get("id") or "")

