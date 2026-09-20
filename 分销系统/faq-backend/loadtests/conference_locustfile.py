"""
分销商大会「能量印章·集章」压测脚本（手机号自助签到版）

模拟 100 并发用户同时 join + 同时 submit-quiz：
- 每个虚拟用户使用唯一手机号（1[3-9] + 8 位随机），无需鉴权
- join 幂等（重复 join 不产生重复参会人）
- submit-quiz 全题作答 → 印章发放（stamp_earned=true 首次、false 幂等）
- 预期：唯一约束生效，无重复印章/勋章；submit-quiz P95 < 500ms

运行：
  cd faq-backend
  locust -f loadtests/conference_locustfile.py --host https://<backend-host> --users 100 --spawn-rate 50 -t 3m
（--host 指向云托管后端；本脚本目标路径带 /api 前缀）

判读标准：
- submit-quiz 响应时间 P95 < 500ms
- 无 500 错误；业务 code=0
- 压测后数据库无重复印章（(phone, zone_id) 唯一约束）、无重复勋章
"""
from __future__ import annotations

import random
from typing import Any

from locust import HttpUser, between, task

ZONE_CODES = ["business", "new_v", "digital", "channel"]
PHONE_SEED = "139%08d"


def _random_phone() -> str:
    # 生成 1[3-9] 开头 11 位手机号
    prefix = random.choice("3456789")
    return f"1{prefix}{random.randint(10**8, 10**9 - 1)}"


class ConferenceKioskUser(HttpUser):
    """单打卡点扫码用户：join → 拉题 → submit-quiz（含幂等重提）。"""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.phone = _random_phone()
        self.name = f"压测用户{self.phone[-4:]}"
        self.zone_code = random.choice(ZONE_CODES)
        self.answers: list[dict[str, Any]] = []

    def _is_ok(self, response, action: str) -> bool:
        if response.status_code != 200:
            response.failure(f"{action} HTTP {response.status_code}: {response.text[:200]}")
            return False
        try:
            payload = response.json()
        except ValueError:
            response.failure(f"{action} 非 JSON 响应")
            return False
        if payload.get("code") != 0:
            response.failure(f"{action} 业务失败: {payload}")
            return False
        response.success()
        return True

    @task(10)
    def join_and_submit(self) -> None:
        # 1. join（重复两次验证幂等）
        for _ in range(2):
            with self.client.post(
                "/api/conference/join",
                json={"name": self.name, "phone": self.phone},
                name="POST /api/conference/join",
                catch_response=True,
            ) as resp:
                if not self._is_ok(resp, "join"):
                    return

        # 2. 拉题目
        with self.client.get(
            f"/api/conference/zones/{self.zone_code}",
            params={"phone": self.phone},
            name="GET /api/conference/zones/{code}",
            catch_response=True,
        ) as resp:
            if not self._is_ok(resp, "拉取题目"):
                return
            questions = resp.json()["data"].get("questions", [])

        answers = [
            {
                "question_id": q["id"],
                "selected_answer": "AB" if q["question_type"] == "multiple_choice" else "A",
            }
            for q in questions
        ]
        if not answers:
            return

        # 3. submit-quiz
        for _ in range(2):  # 重复提交验证幂等
            with self.client.post(
                f"/api/conference/zones/{self.zone_code}/submit-quiz",
                json={"phone": self.phone, "name": self.name, "answers": answers},
                name="POST /api/conference/zones/{code}/submit-quiz",
                catch_response=True,
            ) as resp:
                if not self._is_ok(resp, "submit-quiz"):
                    return

    @task(2)
    def overview(self) -> None:
        with self.client.get(
            "/api/conference/overview",
            params={"phone": self.phone},
            name="GET /api/conference/overview",
            catch_response=True,
        ) as resp:
            self._is_ok(resp, "overview")
