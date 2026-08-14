"""
RAGFlow 检索服务 — 桥接层

负责：
1. 调用 RAGFlow API 进行文档检索（支持混合检索：向量 + 关键词）
2. 将检索结果格式化为 HiAgent 可用的上下文文本
3. 支持降级：检索失败时返回空上下文，不影响主流程
"""
import asyncio
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# RAGFlow 检索 API 超时（秒），嵌入模型在 CPU 上运行较慢
RETRIEVAL_TIMEOUT = 120.0


class RAGFlowRetriever:
    """RAGFlow 文档检索引擎"""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        knowledge_base_id: str = "",
    ):
        self.base_url = (base_url or settings.RAGFLOW_API_BASE).rstrip("/")
        self.api_key = api_key or settings.RAGFLOW_API_KEY or ""
        self.kb_id = knowledge_base_id or settings.RAGFLOW_KNOWLEDGE_BASE_ID or ""

    @property
    def enabled(self) -> bool:
        """是否启用 RAGFlow 检索"""
        return bool(
            settings.RAGFLOW_ENABLED
            and self.api_key
            and self.kb_id
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.2,
        use_keyword: bool = True,
    ) -> list[dict]:
        """
        调用 RAGFlow 检索 API，返回相关文档片段。

        使用混合检索（向量 + 关键词），提升精确匹配能力。

        Args:
            query: 用户查询文本
            top_k: 返回结果数量
            similarity_threshold: 相似度阈值，低于此值的结果将被过滤
            use_keyword: 是否启用关键词检索（混合检索）

        Returns:
            [{"content": "...", "source": "xxx.pdf", "score": 0.92}, ...]
        """
        if not self.enabled:
            logger.info("ragflow_disabled")
            return []

        url = f"{self.base_url}/retrieval"
        payload = {
            "question": query,
            "dataset_ids": [self.kb_id],
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "keyword": use_keyword,  # 混合检索：关键词 + 向量
        }

        logger.info(
            "ragflow_retrieve_start",
            query_length=len(query),
            top_k=top_k,
            keyword=use_keyword,
        )

        try:
            async with httpx.AsyncClient(timeout=RETRIEVAL_TIMEOUT) as client:
                resp = await client.post(
                    url, headers=self._headers(), json=payload
                )

            if resp.status_code != 200:
                logger.warning(
                    "ragflow_retrieve_http_error",
                    status=resp.status_code,
                    response_length=len(resp.text or ""),
                )
                return []

            data = resp.json()
            if data.get("code") != 0:
                logger.warning(
                    "ragflow_retrieve_api_error",
                    code=data.get("code"),
                    message=data.get("message", ""),
                )
                return []

            chunks = self._parse_chunks(data.get("data", {}))
            logger.info(
                "ragflow_retrieve_done",
                result_count=len(chunks),
            )
            return chunks

        except httpx.TimeoutException:
            logger.warning("ragflow_retrieve_timeout")
            return []
        except Exception as e:
            logger.warning("ragflow_retrieve_exception", error=str(e))
            return []

    def _parse_chunks(self, data: dict) -> list[dict]:
        """解析 RAGFlow 检索返回的 chunks。

        RAGFlow retrieval API 返回格式:
        {
            "chunks": [
                {
                    "content": "文档片段内容...",
                    "document_name": "I-Line H 样本.pdf",
                    "similarity": 0.95,
                    ...
                }
            ]
        }
        """
        raw_chunks = data.get("chunks", [])
        if not isinstance(raw_chunks, list):
            return []

        parsed = []
        for chunk in raw_chunks:
            if not isinstance(chunk, dict):
                continue
            content = chunk.get("content", "").strip()
            if not content:
                continue

            source = chunk.get("document_name") or chunk.get("doc_name") or "未知来源"
            score = float(chunk.get("similarity") or chunk.get("score") or 0.0)

            parsed.append({
                "content": content,
                "source": source,
                "score": score,
            })

        return parsed

    def format_context(self, chunks: list[dict], max_chunks: int = 5) -> str:
        """
        将检索结果格式化为 HiAgent Prompt 可用的上下文文本。

        Args:
            chunks: 检索结果列表
            max_chunks: 最多使用的片段数量

        Returns:
            格式化后的上下文字符串，如无结果返回空字符串
        """
        if not chunks:
            return ""

        # 按相似度降序排列
        sorted_chunks = sorted(chunks, key=lambda c: c.get("score", 0), reverse=True)
        selected = sorted_chunks[:max_chunks]

        lines = [
            "【以下为参考文档内容，请基于这些内容回答用户问题。"
            "如果文档中没有相关信息，请明确告知用户。】",
            "",
        ]

        has_content = False
        for i, chunk in enumerate(selected):
            source = chunk.get("source", "未知来源")
            content = chunk.get("content", "").strip()
            score = chunk.get("score", 0.0)

            if not content:
                continue

            has_content = True
            lines.append(f"[参考来源 {i + 1}: {source}] (相似度: {score:.2f})")
            lines.append(content)
            lines.append("")

        if not has_content:
            return ""

        return "\n".join(lines)

    def build_enhanced_message(self, user_message: str, chunks: list[dict]) -> str:
        """
        构建增强后的用户消息：将检索上下文注入到原始问题之前。

        Args:
            user_message: 原始用户问题
            chunks: 检索结果列表

        Returns:
            增强后的完整消息文本
        """
        context = self.format_context(chunks, max_chunks=5)
        if not context:
            # 无上下文时直接返回原始消息
            return user_message

        return (
            f"{context}\n"
            f"【用户问题】\n"
            f"{user_message}"
        )


# 全局单例，启动时延迟初始化
_retriever: Optional[RAGFlowRetriever] = None


def get_retriever() -> RAGFlowRetriever:
    """获取 RAGFlowRetriever 全局单例"""
    global _retriever
    if _retriever is None:
        _retriever = RAGFlowRetriever()
    return _retriever


async def retrieve_context(
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.2,
) -> tuple[list[dict], str]:
    """
    便捷函数：检索并格式化上下文。

    供 AgentService 调用，内置降级逻辑。

    Args:
        query: 用户查询
        top_k: 检索数量
        similarity_threshold: 相似度阈值

    Returns:
        (chunks, formatted_context)
    """
    retriever = get_retriever()

    if not retriever.enabled:
        return [], ""

    try:
        chunks = await retriever.retrieve(
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            use_keyword=True,
        )
        context = retriever.format_context(chunks, max_chunks=top_k)
        return chunks, context
    except Exception as e:
        logger.warning("ragflow_context_failed", error=str(e))
        return [], ""