"""
RAGFlow 检索服务 — 桥接层

负责：
1. 调用 RAGFlow API 进行文档检索（支持混合检索：向量 + 关键词）
2. 将检索结果格式化为 HiAgent 可用的上下文文本
3. 支持多知识库检索（事实层、话术层、友商层、通用知识层）
4. 意图路由：根据用户问题关键词自动选择优先检索的知识库
5. 支持降级：检索失败时返回空上下文，不影响主流程
"""
import asyncio
from enum import Enum
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# RAGFlow 检索 API 超时（秒），嵌入模型在 CPU 上运行较慢
RETRIEVAL_TIMEOUT = 120.0


class KnowledgeBaseLayer(str, Enum):
    """知识库层级枚举"""
    FACT = "fact"              # 事实层：PDF 电气参数
    TALK = "talk"              # 话术层：销售话术指南
    COMPETITOR = "competitor"  # 友商层：竞品参数对比
    GENERAL = "general"        # 通用知识层：安装、测量、认证、政策


# 意图路由关键词规则
# 注意：匹配顺序即优先级，先匹配到的规则优先
INTENT_ROUTES = [
    # 友商层：对比、竞品类问题
    (
        KnowledgeBaseLayer.COMPETITOR,
        ["对比", "vs", "区别", "哪个好", "哪个强", "哪个优", "优势", "比较",
         "XAP", "XL-", "威腾", "Pro VS", "Lmax", "伊顿", "Eaton", "ABB",
         "西门子", "Siemens", "友商", "竞品"],
    ),
    # 话术层：销售话术类问题
    (
        KnowledgeBaseLayer.TALK,
        ["怎么推荐", "怎么说", "怎么推", "客户说", "客户问", "话术", "如何介绍",
         "怎么回答", "应对话术", "怎么卖", "销售", "如何向客户"],
    ),
    # 通用知识层：安装、测量、认证、标准类问题
    (
        KnowledgeBaseLayer.GENERAL,
        ["安装", "测量", "数图", "施工", "维护", "OPEX", "检测",
         "认证", "标准", "CCC", "3C", "CQC", "ASTA", "KEMA",
         "报备", "KA", "商务政策", "银行承兑", "付款",
         "工厂", "公司", "生产基地", "RoHS", "节能",
         "降容", "海拔", "温升", "绝缘", "耐火", "防火",
         "IP防护", "防护等级", "E-Temp", "智能母线", "数字化",
         "配电房", "变压器房", "竖井", "Missing Link", "预留段"],
    ),
]

# 默认检索组合：事实层 + 通用知识层（兜底）
DEFAULT_RETRIEVAL_LAYERS = [KnowledgeBaseLayer.FACT, KnowledgeBaseLayer.GENERAL]


class RAGFlowRetriever:
    """RAGFlow 文档检索引擎（支持多知识库）"""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        knowledge_base_id: str = "",
    ):
        self.base_url = (base_url or settings.RAGFLOW_API_BASE).rstrip("/")
        self.api_key = api_key or settings.RAGFLOW_API_KEY or ""
        self.kb_id = knowledge_base_id or settings.RAGFLOW_KNOWLEDGE_BASE_ID or ""

        # 多知识库 ID 映射
        self._kb_ids: dict[KnowledgeBaseLayer, str] = {}

    def _get_kb_id(self, layer: KnowledgeBaseLayer) -> Optional[str]:
        """获取指定层级的知识库 ID"""
        if layer in self._kb_ids:
            return self._kb_ids[layer]

        mapping = {
            KnowledgeBaseLayer.FACT: settings.RAGFLOW_KNOWLEDGE_BASE_ID,
            KnowledgeBaseLayer.TALK: settings.RAGFLOW_TALK_KB_ID,
            KnowledgeBaseLayer.COMPETITOR: settings.RAGFLOW_COMPETITOR_KB_ID,
            KnowledgeBaseLayer.GENERAL: settings.RAGFLOW_GENERAL_KB_ID,
        }
        kb_id = mapping.get(layer)
        self._kb_ids[layer] = kb_id or ""
        return self._kb_ids[layer]

    @property
    def enabled(self) -> bool:
        """是否启用 RAGFlow 检索（至少有一个知识库可用）"""
        if not settings.RAGFLOW_ENABLED or not self.api_key:
            return False
        # 检查是否有至少一个知识库 ID 可用
        return any(
            self._get_kb_id(layer)
            for layer in KnowledgeBaseLayer
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def route_intent(self, query: str) -> KnowledgeBaseLayer:
        """
        根据用户问题关键词进行意图路由。

        返回优先检索的知识库层级。
        如果未匹配到任何规则，返回 None，使用默认检索组合。
        """
        for layer, keywords in INTENT_ROUTES:
            for kw in keywords:
                if kw.lower() in query.lower():
                    logger.info(
                        "ragflow_intent_routed",
                        layer=layer.value,
                        keyword=kw,
                    )
                    return layer
        return None  # 未匹配到，使用默认组合

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.2,
        use_keyword: bool = True,
    ) -> list[dict]:
        """
        调用 RAGFlow 检索 API，返回相关文档片段。

        使用意图路由：根据查询内容自动选择优先检索的知识库，
        同时也会检索默认组合（事实层 + 通用知识层）作为兜底。

        Args:
            query: 用户查询文本
            top_k: 返回结果数量
            similarity_threshold: 相似度阈值，低于此值的结果将被过滤
            use_keyword: 是否启用关键词检索（混合检索）

        Returns:
            [{"content": "...", "source": "xxx.pdf", "score": 0.92, "layer": "fact"}, ...]
        """
        if not self.enabled:
            logger.info("ragflow_disabled")
            return []

        # 意图路由
        primary_layer = self.route_intent(query)

        # 确定检索的知识库列表
        layers_to_search = []
        if primary_layer:
            # 优先检索匹配的知识库
            layers_to_search.append(primary_layer)
            # 同时加入默认组合（去重）
            for layer in DEFAULT_RETRIEVAL_LAYERS:
                if layer != primary_layer:
                    layers_to_search.append(layer)
        else:
            layers_to_search = DEFAULT_RETRIEVAL_LAYERS

        # 收集所有可用的知识库 ID
        dataset_ids = []
        for layer in layers_to_search:
            kb_id = self._get_kb_id(layer)
            if kb_id:
                dataset_ids.append(kb_id)

        if not dataset_ids:
            logger.info("ragflow_no_available_kb")
            return []

        # 分配 top_k：优先层拿到更多配额
        primary_top_k = top_k
        other_top_k = max(1, top_k // 2)

        all_chunks: list[dict] = []

        for i, ds_id in enumerate(dataset_ids):
            is_primary = (i == 0)
            k = primary_top_k if is_primary else other_top_k

            chunks = await self._retrieve_from_dataset(
                ds_id, query, k, similarity_threshold, use_keyword
            )

            # 标记来源层级
            layer = layers_to_search[i] if i < len(layers_to_search) else "unknown"
            for chunk in chunks:
                chunk["layer"] = layer.value

            all_chunks.extend(chunks)

        # 去重并按相似度排序
        all_chunks = self._deduplicate_chunks(all_chunks)
        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
        all_chunks = all_chunks[:top_k]

        logger.info(
            "ragflow_retrieve_done",
            result_count=len(all_chunks),
            layers_searched=[l.value for l in layers_to_search],
            primary_layer=primary_layer.value if primary_layer else "default",
        )
        return all_chunks

    async def _retrieve_from_dataset(
        self,
        dataset_id: str,
        query: str,
        top_k: int,
        similarity_threshold: float,
        use_keyword: bool,
    ) -> list[dict]:
        """从单个知识库检索"""
        url = f"{self.base_url}/retrieval"
        payload = {
            "question": query,
            "dataset_ids": [dataset_id],
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "keyword": use_keyword,
        }

        try:
            async with httpx.AsyncClient(timeout=RETRIEVAL_TIMEOUT) as client:
                resp = await client.post(
                    url, headers=self._headers(), json=payload
                )

            if resp.status_code != 200:
                logger.warning(
                    "ragflow_retrieve_http_error",
                    status=resp.status_code,
                    dataset_id=dataset_id,
                )
                return []

            data = resp.json()
            if data.get("code") != 0:
                logger.warning(
                    "ragflow_retrieve_api_error",
                    code=data.get("code"),
                    message=data.get("message", ""),
                    dataset_id=dataset_id,
                )
                return []

            return self._parse_chunks(data.get("data", {}))

        except httpx.TimeoutException:
            logger.warning("ragflow_retrieve_timeout", dataset_id=dataset_id)
            return []
        except Exception as e:
            logger.warning("ragflow_retrieve_exception", error=str(e), dataset_id=dataset_id)
            return []

    def _parse_chunks(self, data: dict) -> list[dict]:
        """解析 RAGFlow 检索返回的 chunks。"""
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

    def _deduplicate_chunks(self, chunks: list[dict]) -> list[dict]:
        """按内容去重，保留得分最高的"""
        seen = {}
        for chunk in chunks:
            content = chunk.get("content", "")
            if not content:
                continue
            # 使用前 200 字符作为去重 key
            key = content[:200]
            if key not in seen or chunk.get("score", 0) > seen[key].get("score", 0):
                seen[key] = chunk
        return list(seen.values())

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

        # 知识库层级标签
        layer_labels = {
            "fact": "事实层",
            "talk": "话术层",
            "competitor": "友商层",
            "general": "通用知识层",
        }

        has_content = False
        for i, chunk in enumerate(selected):
            source = chunk.get("source", "未知来源")
            content = chunk.get("content", "").strip()
            score = chunk.get("score", 0.0)
            layer = chunk.get("layer", "")
            layer_label = layer_labels.get(layer, layer)

            if not content:
                continue

            has_content = True
            lines.append(
                f"[参考来源 {i + 1}: {source}] "
                f"(相似度: {score:.2f}, 知识库: {layer_label})"
            )
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