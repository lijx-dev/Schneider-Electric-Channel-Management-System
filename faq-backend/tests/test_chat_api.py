import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import chat as chat_api
from app.core.security import create_access_token
from app.main import app


@pytest.mark.asyncio
async def test_chat_stream_emits_keepalive_before_answer(client, test_user, monkeypatch):
    user, token = test_user

    async def fake_chat_stream(user_message: str, user_id: str = "default_user"):
        await asyncio.sleep(0.05)
        yield "测试回复"

    monkeypatch.setattr(
        chat_api.AgentService,
        "chat_stream",
        staticmethod(fake_chat_stream),
    )

    async with client.stream(
        "POST",
        "/api/chat/stream",
        json={
            "user_id": user.id,
            "message": "你好",
        },
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        assert response.status_code == 200

        chunks = []
        async for text in response.aiter_text():
            if not text:
                continue

            chunks.append(text)
            if "测试回复" in "".join(chunks):
                break

    payload = "".join(chunks)
    assert ": keepalive" in payload
    assert '"chunk": "测试回复"' in payload


def test_chat_websocket_streams_chunks(monkeypatch):
    token = create_access_token("ws-test-user")

    async def fake_chat_stream(user_message: str, user_id: str = "default_user"):
        yield "你好"
        yield "，世界"

    monkeypatch.setattr(
        chat_api.AgentService,
        "chat_stream",
        staticmethod(fake_chat_stream),
    )

    with TestClient(app) as test_client:
        with test_client.websocket_connect("/api/chat/ws") as websocket:
            websocket.send_text('{"token": "%s", "message": "你好"}' % token)

            first = websocket.receive_json()
            second = websocket.receive_json()
            done = websocket.receive_json()

    assert first == {"type": "chunk", "chunk": "你好"}
    assert second == {"type": "chunk", "chunk": "，世界"}
    assert done == {"type": "done"}
