from __future__ import annotations

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

ROOT_DIR = Path(__file__).resolve().parents[1]
TOKEN_FILE = Path(
    os.getenv(
        "LOADTEST_TOKEN_FILE",
        str(ROOT_DIR / "loadtests" / "data" / "loadtest_users.json"),
    )
)
WAIT_MIN_SECONDS = float(os.getenv("LOADTEST_WAIT_MIN_SECONDS", "1"))
WAIT_MAX_SECONDS = float(os.getenv("LOADTEST_WAIT_MAX_SECONDS", "4"))

# 大会默认打卡展区（答题题组）
QUIZ_ZONE_CODE = os.getenv("CONFERENCE_QUIZ_ZONE_CODE", "business")


def load_credentials() -> list[dict]:
    if not TOKEN_FILE.exists():
        raise RuntimeError(
            f"Token file not found: {TOKEN_FILE}. Run scripts/prepare_locust_users.py first."
        )
    payload = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    users = payload.get("users", [])
    if not users:
        raise RuntimeError(f"No users found in token file: {TOKEN_FILE}")
    return users


CREDENTIALS = load_credentials()


class ConferenceUser(HttpUser):
    """
    分销商大会压测：模拟 100 并发用户「登录 + 打卡」混合任务。

    验证目标：
    1. 登录不命中 429（RATE_LIMIT_LOGIN / RATE_LIMIT_LOGIN_PHONE 放宽生效）
    2. 无重复印记 / 重复勋章（数据库唯一约束兜底）
    3. submit-quiz P95 < 500ms

    注意：
    - login 任务使用占位 code，WeChat 校验会失败（400/500 属预期），
      但限流计数在调用微信前就已累加，因此可验证限流是否放宽。
    - 请先运行 scripts/prepare_locust_users.py 生成 token 池，
      并确保用户已开启 conference_whitelisted。
    """

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self) -> None:
        self.credential = random.choice(CREDENTIALS)
        self.user_id = self.credential["user_id"]
        self.headers = {
            "Authorization": f"Bearer {self.credential['token']}",
            "Content-Type": "application/json",
        }
        self._quiz_answers = None

    @task(2)
    def login(self) -> None:
        """登录接口压测：占位 code，重点验证限流放宽后不出现 429。"""
        with self.client.post(
            "/api/auth/login",
            json={"code": "locust-placeholder-code"},
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 429:
                resp.failure("LOGIN_RATE_LIMITED(429) — 限流未放宽")
            else:
                # 400/500 是微信校验占位 code 失败的预期结果，不视为压测失败
                resp.success()

    @task(3)
    def overview(self) -> None:
        """大会总览（白名单校验 + 展区 + 勋章状态）。"""
        with self.client.get(
            "/api/conference/overview",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 403:
                resp.failure("USER_NOT_WHITELISTED(403)")
            elif resp.status_code == 401:
                resp.failure("AUTH_FAILED(401)")

    @task(3)
    def submit_quiz(self) -> None:
        """答题打卡：先拉题组，再提交全部答案（幂等，可重复提交）。"""
        with self.client.get(
            f"/api/conference/zones/{QUIZ_ZONE_CODE}",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"ZONE_FETCH_FAILED({resp.status_code})")
                return
            try:
                questions = resp.json()["data"].get("questions", [])
            except (ValueError, KeyError, TypeError):
                resp.failure("ZONE_PAYLOAD_INVALID")
                return

        if not questions:
            return

        answers = [
            {"question_id": q["id"], "selected_answer": "A"} for q in questions
        ]
        with self.client.post(
            f"/api/conference/zones/{QUIZ_ZONE_CODE}/submit-quiz",
            json={"answers": answers},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"SUBMIT_FAILED({resp.status_code})")
                return
            data = resp.json().get("data", {})
            # mark_earned 只应在首次为 True；重复提交应返回 False（幂等）
            if data.get("medal_earned") and not data.get("medal_code"):
                resp.failure("MEDAL_MISSING_CODE")

    @task(2)
    def report_activity(self) -> None:
        """渠道展区施能量页浏览计数上报。"""
        with self.client.post(
            "/api/conference/activity",
            json={"action": "energy_view"},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 403:
                resp.failure("USER_NOT_WHITELISTED(403)")
            elif resp.status_code == 401:
                resp.failure("AUTH_FAILED(401)")
