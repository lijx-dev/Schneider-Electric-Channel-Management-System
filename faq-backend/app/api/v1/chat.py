import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.api.deps import enforce_rate_limit, get_current_user_id
from app.core.logging import get_logger
from app.core.security import verify_token
from app.schemas.chat import ChatFeedback, ChatMessage
from app.services.agent import AgentService

logger = get_logger(__name__)
CHAT_WS_HEARTBEAT_SECONDS = 10

router = APIRouter(tags=["AI问答"])


@router.post("/chat")
async def chat(
    request: Request,
    msg: ChatMessage,
    current_user_id: str = Depends(get_current_user_id),
):
    """Blocking chat endpoint."""
    enforce_rate_limit("chat", current_user_id, limit=20, window_seconds=60)

    result = await AgentService.chat(
        user_message=msg.message,
        user_id=current_user_id,
    )
    return {"code": 0, "data": result}


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    msg: ChatMessage,
    current_user_id: str = Depends(get_current_user_id),
):
    """Streaming chat endpoint (SSE)."""
    enforce_rate_limit("chat_stream", current_user_id, limit=10, window_seconds=60)

    async def event_generator():
        import asyncio
        import json

        queue: asyncio.Queue[dict | str | None] = asyncio.Queue()

        async def produce_chunks():
            async for chunk in AgentService.chat_stream(
                user_message=msg.message,
                user_id=current_user_id,
            ):
                await queue.put(chunk)

            await queue.put(None)

        producer = asyncio.create_task(produce_chunks())

        try:
            # Send an immediate SSE heartbeat so callContainer sees response activity
            # even when the upstream AI takes several seconds to produce its first token.
            yield ": keepalive\n\n"

            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if chunk is None:
                    break

                if isinstance(chunk, dict):
                    if chunk.get("type") == "meta":
                        yield f"data: {json.dumps({'message_id': chunk.get('message_id', '')}, ensure_ascii=False)}\n\n"
                    continue

                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'chunk': '[DONE]'})}\n\n"
        finally:
            if not producer.done():
                producer.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/feedback")
async def chat_feedback(
    feedback: ChatFeedback,
    current_user_id: str = Depends(get_current_user_id),
):
    """Submit answer feedback to HiAgent through backend proxy."""
    enforce_rate_limit("chat_feedback", current_user_id, limit=30, window_seconds=60)

    try:
        result = await AgentService.submit_feedback(
            message_id=feedback.message_id,
            like_type=feedback.like_type,
            user_id=current_user_id,
            feedback_info=feedback.feedback_info,
        )
    except Exception as exc:
        logger.error("chat_feedback_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"code": 0, "data": result}


@router.websocket("/chat/ws")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        raw_message = await websocket.receive_text()
        payload = json.loads(raw_message or "{}")
        token = str(payload.get("token") or "").strip()
        user_message = str(payload.get("message") or "").strip()

        current_user_id = verify_token(token)
        if not current_user_id:
            await websocket.send_text(json.dumps({"type": "error", "message": "Not authenticated"}))
            await websocket.close(code=4401)
            return

        if not user_message:
            await websocket.send_text(json.dumps({"type": "error", "message": "Empty message"}))
            await websocket.close(code=4400)
            return

        enforce_rate_limit("chat_ws", current_user_id, limit=10, window_seconds=60)
        logger.info("chat_ws_start", user_id=current_user_id)

        queue: asyncio.Queue[dict | str | None] = asyncio.Queue()

        async def produce_chunks():
            async for chunk in AgentService.chat_stream(
                user_message=user_message,
                user_id=current_user_id,
            ):
                await queue.put(chunk)

            await queue.put(None)

        producer = asyncio.create_task(produce_chunks())

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        queue.get(),
                        timeout=CHAT_WS_HEARTBEAT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                    continue

                if chunk is None:
                    break

                if isinstance(chunk, dict):
                    if chunk.get("type") == "meta":
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "meta",
                                    "message_id": chunk.get("message_id", ""),
                                },
                                ensure_ascii=False,
                            )
                        )
                    continue

                if chunk:
                    await websocket.send_text(
                        json.dumps({"type": "chunk", "chunk": chunk}, ensure_ascii=False)
                    )

            await websocket.send_text(json.dumps({"type": "done"}))
        finally:
            if not producer.done():
                producer.cancel()
    except WebSocketDisconnect:
        logger.info("chat_ws_disconnect")
    except Exception as exc:
        logger.error("chat_ws_exception", error=str(exc))
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            )
        except Exception:
            pass

        await websocket.close(code=1011)
