import asyncio

from fastapi.testclient import TestClient

from app.api.v1 import chat as chat_api
from app.core.security import create_access_token
from app.main import app


def test_chat_websocket_emits_ping_while_waiting_for_first_chunk(monkeypatch):
    token = create_access_token("ws-heartbeat-user")

    async def fake_chat_stream(user_message: str, user_id: str = "default_user"):
        await asyncio.sleep(0.03)
        yield "测试"

    monkeypatch.setattr(
        chat_api.AgentService,
        "chat_stream",
        staticmethod(fake_chat_stream),
    )
    monkeypatch.setattr(chat_api, "CHAT_WS_HEARTBEAT_SECONDS", 0.01)

    with TestClient(app) as test_client:
        with test_client.websocket_connect("/api/chat/ws") as websocket:
            websocket.send_text('{"token": "%s", "message": "ping"}' % token)

            received = [websocket.receive_json()]

            while received[-1].get("type") != "chunk":
                received.append(websocket.receive_json())

            done = websocket.receive_json()

    assert received[0] == {"type": "ping"}
    assert received[-1] == {"type": "chunk", "chunk": "测试"}
    assert all(item.get("type") == "ping" for item in received[:-1])
    assert done == {"type": "done"}
