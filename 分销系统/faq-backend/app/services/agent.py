"""
AI Agent 服务 - 对接 HiAgent API（火山引擎 Volcengine）

调用流程（两步走）：
  第一步: POST {base}/create_conversation  → 拿到 AppConversationID
  第二步: POST {base}/chat_query_v2        → 传入 AppConversationID 发消息

支持两种模式:
  - blocking: 等 AI 生成完一次性返回（chat 方法）
  - streaming: SSE 流式返回，逐字输出（chat_stream 方法）

RAG 增强:
  在调用 HiAgent 之前，先从 RAGFlow 检索相关文档片段，
  将检索结果作为上下文注入到用户消息中，提升回答精度。

.env 配置:
  HIAGENT_API_BASE=https://hiagent-stg.schneider-electric.cn/api/proxy/api/v1
  HIAGENT_API_KEY=your-hiagent-api-key
  RAGFLOW_API_BASE=http://localhost:9380/api/v1
  RAGFLOW_API_KEY=your-ragflow-api-key
  RAGFLOW_KNOWLEDGE_BASE_ID=your-knowledge-base-id
  RAGFLOW_ENABLED=true
"""
import json
from typing import Any, AsyncGenerator

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.hiagent_conversation import HiAgentConversation

logger = get_logger(__name__)


class HiAgentService:
    """HiAgent API 封装（火山引擎 Volcengine）"""

    USER_FACING_NETWORK_ERROR = "网络错误，请重试"
    _UPSTREAM_ERROR_MARKERS = (
        "run workflow failed",
        "query request failed",
        "responsemetadata",
        "agent 执行出错",
        "工具未授权",
        "入参错误",
        "网络异常",
        "status: failed",
    )

    # HiAgent 会话失效/过期时的错误特征，检测到后自动重建会话
    _CONVERSATION_ERROR_MARKERS = (
        "conversation not found",
        "conversation_id",
        "invalid conversation",
        "session expired",
        "会话不存在",
        "会话已过期",
        "app_conversation",
        "conversation is",
    )

    # 记录每个用户的 AppConversationID，用于多轮对话
    _conversations: dict[str, str] = {}

    @staticmethod
    def _base_url() -> str:
        return settings.HIAGENT_API_BASE.rstrip("/")

    @staticmethod
    def _headers(accept: str = "text/event-stream") -> dict:
        """构造请求头（文档要求 Apikey 头）"""
        return {
            "Apikey": settings.HIAGENT_API_KEY,
            "Content-Type": "application/json",
            "Accept": accept,
        }

    @staticmethod
    def _feedback_url() -> str:
        feedback_path = (settings.HIAGENT_FEEDBACK_PATH or "/feedback").strip()
        if not feedback_path.startswith("/"):
            feedback_path = f"/{feedback_path}"
        return f"{HiAgentService._base_url()}{feedback_path}"

    @staticmethod
    def _extract_message_id(payload: Any) -> str:
        """从 HiAgent 响应中尽量提取消息 ID，兼容不同大小写/嵌套结构。"""
        if not isinstance(payload, dict):
            return ""

        for key in ("MessageID", "MessageId", "messageId", "message_id", "_id", "id"):
            value = payload.get(key)
            if value:
                return str(value).strip()

        for value in payload.values():
            if isinstance(value, dict):
                message_id = HiAgentService._extract_message_id(value)
                if message_id:
                    return message_id
            elif isinstance(value, list):
                for item in value:
                    message_id = HiAgentService._extract_message_id(item)
                    if message_id:
                        return message_id

        return ""

    @staticmethod
    def _normalize_agent_error_reply(reply: Any) -> str:
        """隐藏上游工作流/工具错误细节，统一给用户网络重试提示。"""
        text = str(reply or "")
        lowered = text.lower()
        if any(marker in lowered for marker in HiAgentService._UPSTREAM_ERROR_MARKERS):
            return HiAgentService.USER_FACING_NETWORK_ERROR
        return text

    @staticmethod
    async def _create_conversation(user_id: str) -> str:
        """
        第一步：调用 CreateConversation 接口创建会话，拿到 AppConversationID。
        """
        url = f"{HiAgentService._base_url()}/create_conversation"
        body = {"UserID": user_id}
        headers = HiAgentService._headers()

        logger.info("hiagent_create_conversation", url=url, user_id=user_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)

            if resp.status_code != 200:
                logger.error(
                    "hiagent_create_conversation_failed",
                    status=resp.status_code,
                    response_length=len(resp.text or ""),
                )
                raise RuntimeError(f"创建会话失败 ({resp.status_code})")

            data = resp.json()
            logger.info(
                "hiagent_create_conversation_response",
                keys=sorted(data.keys()) if isinstance(data, dict) else [],
            )

            conv = data.get("Conversation", data.get("Data", data))
            if isinstance(conv, dict):
                app_conv_id = conv.get("AppConversationID", "")
            else:
                app_conv_id = ""

            if not app_conv_id:
                raise RuntimeError(f"创建会话成功但未返回 AppConversationID: {data}")

            return app_conv_id

    @staticmethod
    async def _ensure_conversation(user_id: str) -> str:
        """
        确保用户有一个有效的 AppConversationID。

        查询优先级：内存缓存 → 数据库 → HiAgent 创建新会话。
        创建成功后同步写入数据库和内存缓存，解决多实例部署时
        内存字典隔离导致上下文丢失的问题。
        """
        # 1. 内存缓存命中（最快路径）
        cached = HiAgentService._conversations.get(user_id, "")
        if cached:
            return cached

        # 2. 数据库查询（服务重启 / 多实例场景）
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(HiAgentConversation).where(
                    HiAgentConversation.user_id == user_id
                )
                result = await db.execute(stmt)
                row = result.scalar_one_or_none()
                if row and row.app_conversation_id:
                    HiAgentService._conversations[user_id] = row.app_conversation_id
                    logger.info(
                        "hiagent_conversation_restored_from_db",
                        user_id=user_id,
                        app_conv_id=row.app_conversation_id[:16],
                    )
                    return row.app_conversation_id
        except Exception as exc:
            logger.warning("hiagent_db_read_failed", error=str(exc))

        # 3. 创建新会话
        app_conv_id = await HiAgentService._create_conversation(user_id)
        HiAgentService._conversations[user_id] = app_conv_id

        # 4. 持久化到数据库（异步写入，不影响主流程）
        await HiAgentService._persist_conversation(user_id, app_conv_id)

        logger.info("hiagent_new_conversation", app_conv_id=app_conv_id)
        return app_conv_id

    @staticmethod
    async def _persist_conversation(user_id: str, app_conv_id: str) -> None:
        """将会话 ID 持久化到数据库（upsert）。"""
        try:
            async with AsyncSessionLocal() as db:
                existing = await db.get(HiAgentConversation, user_id)
                if existing:
                    existing.app_conversation_id = app_conv_id
                else:
                    db.add(
                        HiAgentConversation(
                            user_id=user_id,
                            app_conversation_id=app_conv_id,
                        )
                    )
                await db.commit()
        except Exception as exc:
            logger.warning("hiagent_db_persist_failed", error=str(exc))

    @staticmethod
    async def _invalidate_conversation(user_id: str) -> None:
        """
        清除指定用户的会话记录（内存 + 数据库）。
        当 HiAgent 返回会话无效/过期错误时调用，下次请求会自动重建。
        """
        HiAgentService._conversations.pop(user_id, None)
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(HiAgentConversation, user_id)
                if row:
                    await db.delete(row)
                    await db.commit()
                    logger.info(
                        "hiagent_conversation_invalidated",
                        user_id=user_id,
                    )
        except Exception as exc:
            logger.warning("hiagent_db_invalidate_failed", error=str(exc))

    @staticmethod
    def _is_conversation_error(error_text: str) -> bool:
        """检测 HiAgent 返回的错误是否与会话失效有关。"""
        lowered = str(error_text or "").lower()
        return any(
            marker in lowered
            for marker in HiAgentService._CONVERSATION_ERROR_MARKERS
        )

    @staticmethod
    def _should_process_stream_event(current_event_type: str | None, inner_event_type: str) -> bool:
        outer_type = str(current_event_type or "").strip().lower()
        inner_type = str(inner_event_type or "").strip().lower()

        if inner_type in {"done", "message_end", "workflow_finished"}:
            return False

        if outer_type in {"error", "ping"}:
            return False

        if not outer_type:
            return True

        return outer_type in {"text", "message", "delta", "chunk"}

    @staticmethod
    def _extract_stream_delta(event_data: dict, prev_answer: str) -> tuple[str, str]:
        delta_answer = event_data.get("answer", "")
        if isinstance(delta_answer, str) and delta_answer:
            if delta_answer == prev_answer:
                return "", prev_answer

            if prev_answer and delta_answer.startswith(prev_answer):
                return delta_answer[len(prev_answer):], delta_answer

            return delta_answer, prev_answer + delta_answer

        full_answer = event_data.get("Answer", "")
        if not isinstance(full_answer, str) or not full_answer or full_answer == prev_answer:
            return "", prev_answer

        if prev_answer and full_answer.startswith(prev_answer):
            return full_answer[len(prev_answer):], full_answer

        return full_answer, full_answer

    # ── RAG 增强 ──────────────────────────────────────────────────
    @staticmethod
    async def _build_rag_enhanced_query(user_message: str) -> str:
        """
        从 RAGFlow 检索相关文档上下文，构建增强后的查询消息。

        降级策略：
        - RAGFLOW_ENABLED=False → 跳过检索
        - RAGFlow API Key 未配置 → 跳过检索
        - 检索超时/网络错误 → 记录日志，返回原始消息

        Returns:
            增强后的消息（含上下文）或原始消息（降级时）
        """
        try:
            from app.services.ragflow_retriever import get_retriever

            retriever = get_retriever()
            if not retriever.enabled:
                logger.info("ragflow_skip_disabled")
                return user_message

            chunks = await retriever.retrieve(
                query=user_message,
                top_k=settings.RAGFLOW_RETRIEVAL_TOP_K,
                similarity_threshold=settings.RAGFLOW_SIMILARITY_THRESHOLD,
                use_keyword=True,
            )

            enhanced = retriever.build_enhanced_message(user_message, chunks)
            if enhanced != user_message:
                logger.info(
                    "ragflow_context_injected",
                    chunk_count=len(chunks),
                    query_length=len(user_message),
                    enhanced_length=len(enhanced),
                )
            else:
                logger.info("ragflow_no_context_found")

            return enhanced

        except Exception as e:
            logger.warning("ragflow_build_enhanced_failed", error=str(e))
            return user_message

    # ── 阻塞模式（保留兼容） ─────────────────────────────────────────
    @staticmethod
    async def _chat_internal(user_message: str, user_id: str, app_conv_id: str) -> tuple[int, dict]:
        """内部方法：执行一次阻塞式 HiAgent 请求，返回 (status, data)。"""
        # RAG 增强：检索相关文档上下文，注入到用户消息中
        enhanced_message = await HiAgentService._build_rag_enhanced_query(user_message)

        url = f"{HiAgentService._base_url()}/chat_query_v2"
        body = {
            "Query": enhanced_message,
            "AppConversationID": app_conv_id,
            "ResponseMode": "blocking",
            "UserID": user_id,
            "QueryExtends": {"Files": []}
        }
        headers = HiAgentService._headers()

        logger.info("hiagent_chat_blocking", url=url, app_conv_id=app_conv_id[:8])

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=body)

            if resp.status_code != 200:
                return resp.status_code, {
                    "reply": HiAgentService.USER_FACING_NETWORK_ERROR,
                    "sources": [],
                    "error_text": resp.text or "",
                }

            data = resp.json()
            reply_text = ""
            if "Data" in data and isinstance(data["Data"], dict):
                reply_text = data["Data"].get("Answer", "")
            if not reply_text:
                reply_text = data.get("Answer", data.get("answer", ""))
            reply_text = HiAgentService._normalize_agent_error_reply(reply_text)

            message_id = HiAgentService._extract_message_id(data)

            logger.info("hiagent_chat_success", reply_length=len(reply_text), message_id=message_id)
            return 200, {
                "reply": reply_text or "（AI 未返回内容）",
                "sources": [],
                "message_id": message_id,
            }

    @staticmethod
    async def chat(user_message: str, user_id: str = "default_user") -> dict:
        """
        阻塞模式：等 AI 全部生成后一次性返回。

        支持会话过期自动重建：当 HiAgent 返回会话相关错误时，
        自动清除旧会话、创建新会话并重试一次。
        """
        if not settings.HIAGENT_API_KEY:
            logger.warning("hiagent_not_configured")
            return {"reply": "AI 问答功能配置中，请联系管理员。", "sources": []}

        try:
            app_conv_id = await HiAgentService._ensure_conversation(user_id)

            status, result = await HiAgentService._chat_internal(
                user_message, user_id, app_conv_id
            )

            # 检测会话失效错误 → 重建会话并重试一次
            if status != 200:
                error_text = result.get("error_text", "")
                if HiAgentService._is_conversation_error(error_text):
                    logger.warning(
                        "hiagent_conversation_error_detected",
                        user_id=user_id,
                        status=status,
                    )
                    await HiAgentService._invalidate_conversation(user_id)
                    app_conv_id = await HiAgentService._ensure_conversation(user_id)
                    _, result = await HiAgentService._chat_internal(
                        user_message, user_id, app_conv_id
                    )
                else:
                    logger.error(
                        "hiagent_chat_failed",
                        status=status,
                        response_length=len(error_text),
                    )

            return result

        except httpx.TimeoutException:
            logger.error("hiagent_timeout")
            return {"reply": HiAgentService.USER_FACING_NETWORK_ERROR, "sources": []}
        except Exception as e:
            logger.error("hiagent_exception", error=str(e))
            return {"reply": HiAgentService.USER_FACING_NETWORK_ERROR, "sources": []}

    # ── 流式模式（SSE） ──────────────────────────────────────────────
    @staticmethod
    async def chat_stream(
        user_message: str, user_id: str = "default_user"
    ) -> AsyncGenerator[str, None]:
        """
        流式模式：逐步 yield 文本片段，前端实时显示。

        HiAgent chat_query_v2 streaming 返回 SSE 格式:
          data: {"event":"message", "Answer":"你", ...}
          data: {"event":"message", "Answer":"你好", ...}
          ...
          data: {"event":"done", ...}

        支持会话过期自动重建：当 HTTP 响应是非 200 且错误信息包含
        会话失效标记时，自动清除旧会话、创建新会话并重试一次。
        """
        if not settings.HIAGENT_API_KEY:
            yield "AI 问答功能配置中，请联系管理员。"
            return

        max_retries = 1  # 允许重试一次（共 2 次尝试）
        for attempt in range(max_retries + 1):
            chunks_yielded = 0
            try:
                app_conv_id = await HiAgentService._ensure_conversation(user_id)

                # RAG 增强：检索相关文档上下文，注入到用户消息中
                enhanced_message = await HiAgentService._build_rag_enhanced_query(user_message)

                url = f"{HiAgentService._base_url()}/chat_query_v2"
                body = {
                    "Query": enhanced_message,
                    "AppConversationID": app_conv_id,
                    "ResponseMode": "streaming",
                    "UserID": user_id,
                    "QueryExtends": {"Files": []},
                }
                headers = HiAgentService._headers()

                logger.info(
                    "hiagent_chat_stream_start",
                    url=url,
                    app_conv_id=app_conv_id[:8],
                    attempt=attempt + 1,
                )

                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream(
                        "POST", url, headers=headers, json=body
                    ) as resp:

                        if resp.status_code != 200:
                            error_body = ""
                            async for chunk in resp.aiter_text():
                                error_body += chunk

                            # 检测会话失效 → 清除并重试
                            if (
                                attempt < max_retries
                                and HiAgentService._is_conversation_error(error_body)
                            ):
                                logger.warning(
                                    "hiagent_stream_conversation_error",
                                    status=resp.status_code,
                                    attempt=attempt + 1,
                                )
                                await HiAgentService._invalidate_conversation(user_id)
                                continue  # 重试

                            logger.error(
                                "hiagent_stream_failed",
                                status=resp.status_code,
                                response_length=len(error_body),
                            )
                            yield HiAgentService.USER_FACING_NETWORK_ERROR
                            return

                        # 逐行解析 SSE
                        prev_answer = ""
                        current_event_type = None
                        emitted_message_id = ""

                        async for line in resp.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue

                            # 记录当前行的 event 类型 (如 event:text, event:error)
                            if line.startswith("event:"):
                                current_event_type = line[6:].strip()
                                continue

                            # 解析 data 行
                            if line.startswith("data:"):
                                json_str = line[5:].strip()

                                # "[DONE]" 或空表示结束
                                if json_str == "[DONE]" or not json_str:
                                    continue

                                try:
                                    event_data = json.loads(json_str)
                                except json.JSONDecodeError:
                                    continue

                                if not isinstance(event_data, dict):
                                    continue

                                message_id = HiAgentService._extract_message_id(
                                    event_data
                                )
                                if message_id and message_id != emitted_message_id:
                                    emitted_message_id = message_id
                                    yield {
                                        "type": "meta",
                                        "message_id": message_id,
                                    }

                                # 内部业务事件类型
                                inner_event_type = event_data.get("event", "")

                                # 流结束事件
                                if not HiAgentService._should_process_stream_event(
                                    current_event_type,
                                    inner_event_type,
                                ):
                                    continue

                                # 提取文本增量
                                delta, prev_answer = HiAgentService._extract_stream_delta(
                                    event_data,
                                    prev_answer,
                                )

                                if delta:
                                    if (
                                        HiAgentService._normalize_agent_error_reply(
                                            delta
                                        )
                                        == HiAgentService.USER_FACING_NETWORK_ERROR
                                    ):
                                        yield HiAgentService.USER_FACING_NETWORK_ERROR
                                        return
                                    chunks_yielded += 1
                                    yield delta
                                elif False:  # legacy fallback kept unreachable for compatibility
                                    # 兜底逻辑：处理可能的累积式 Answer 字段
                                    full_answer = event_data.get("Answer", "")
                                    if full_answer and full_answer != prev_answer:
                                        delta = full_answer[len(prev_answer):]
                                        prev_answer = full_answer
                                        if delta:
                                            chunks_yielded += 1
                                            yield delta

                        logger.info(
                            "hiagent_chat_stream_done",
                            total_length=len(prev_answer),
                            chunks=chunks_yielded,
                        )
                        return  # 成功完成，退出重试循环

            except httpx.TimeoutException:
                if attempt < max_retries:
                    logger.warning(
                        "hiagent_stream_timeout_retry", attempt=attempt + 1
                    )
                    continue
                logger.error("hiagent_stream_timeout")
                yield HiAgentService.USER_FACING_NETWORK_ERROR
                return
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        "hiagent_stream_exception_retry",
                        error=str(e),
                        attempt=attempt + 1,
                    )
                    continue
                logger.error("hiagent_stream_exception", error=str(e))
                yield HiAgentService.USER_FACING_NETWORK_ERROR
                return

        # 所有重试均已耗尽
        yield HiAgentService.USER_FACING_NETWORK_ERROR

    @staticmethod
    async def submit_feedback(
        message_id: str,
        like_type: int | str,
        user_id: str,
        feedback_info: dict | None = None,
    ) -> dict:
        """提交回答反馈到 HiAgent。"""
        if not settings.HIAGENT_API_KEY:
            raise RuntimeError("HiAgent API Key 未配置，无法提交反馈。")

        clean_message_id = str(message_id or "").strip()
        if not clean_message_id:
            raise RuntimeError("缺少 MessageID，无法提交反馈。")

        like_type_map = {
            "like": settings.HIAGENT_LIKE_TYPE,
            "赞": settings.HIAGENT_LIKE_TYPE,
            "dislike": settings.HIAGENT_DISLIKE_TYPE,
            "unlike": settings.HIAGENT_DISLIKE_TYPE,
            "踩": settings.HIAGENT_DISLIKE_TYPE,
            "反赞": settings.HIAGENT_DISLIKE_TYPE,
        }
        if isinstance(like_type, int):
            clean_like_type = like_type
        else:
            like_type_text = str(like_type or "").strip()
            clean_like_type = like_type_map.get(
                like_type_text.lower(),
                like_type_map.get(like_type_text, settings.HIAGENT_DISLIKE_TYPE),
            )

        body = {
            "MessageID": clean_message_id,
            "LikeType": clean_like_type,
            "AppKey": settings.HIAGENT_API_KEY,
            "UserID": user_id,
            "FeedbackInfo": feedback_info or {},
        }

        url = HiAgentService._feedback_url()
        app_key_tail = str(settings.HIAGENT_API_KEY or "")[-6:]
        logger.info(
            "hiagent_feedback_submit",
            url=url,
            user_id=user_id,
            message_id=clean_message_id,
            like_type=clean_like_type,
            app_key_tail=app_key_tail,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers=HiAgentService._headers(accept="application/json"),
                json=body,
            )

        if resp.status_code != 200:
            logger.error(
                "hiagent_feedback_failed",
                status=resp.status_code,
                response_length=len(resp.text or ""),
            )
            raise RuntimeError(f"提交反馈失败 ({resp.status_code})")

        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}

        logger.info(
            "hiagent_feedback_success",
            message_id=clean_message_id,
            like_type=clean_like_type,
            app_key_tail=app_key_tail,
        )
        return {
            "submitted": True,
            "message_id": clean_message_id,
            "like_type": clean_like_type,
            "feedback_url": url,
            "app_key_tail": app_key_tail,
            "upstream": data,
        }


# ── 对外统一接口（保持与原 AgentService 兼容）────────────────────────────
class AgentService:
    """AI 问答服务（HiAgent 版）"""

    @staticmethod
    async def chat(user_message: str, user_id: str = "default_user") -> dict:
        """阻塞模式"""
        return await HiAgentService.chat(user_message, user_id)

    @staticmethod
    async def chat_stream(user_message: str, user_id: str = "default_user") -> AsyncGenerator[str, None]:
        """流式模式"""
        async for chunk in HiAgentService.chat_stream(user_message, user_id):
            yield chunk

    @staticmethod
    async def submit_feedback(
        message_id: str,
        like_type: int | str,
        user_id: str,
        feedback_info: dict | None = None,
    ) -> dict:
        """提交回答反馈"""
        return await HiAgentService.submit_feedback(message_id, like_type, user_id, feedback_info)
