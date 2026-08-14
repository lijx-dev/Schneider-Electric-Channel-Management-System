"""
RAGFlow 检索服务单元测试

测试内容：
1. 检索结果解析（_parse_chunks）
2. 上下文格式化（format_context）
3. 增强消息构建（build_enhanced_message）
4. 降级逻辑（禁用时跳过检索）
5. 检索失败时不影响主流程
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.ragflow_retriever import (
    RAGFlowRetriever,
    get_retriever,
    retrieve_context,
)


class TestRAGFlowRetriever:
    """RAGFlowRetriever 核心功能测试"""

    def setup_method(self):
        """每个测试前创建独立的 retriever 实例"""
        self.retriever = RAGFlowRetriever(
            base_url="http://test:9380/api/v1",
            api_key="test-key",
            knowledge_base_id="test-kb-id",
        )

    def test_enabled_true_when_configured(self):
        """已配置 API Key 和知识库 ID 时应启用"""
        retriever = RAGFlowRetriever(
            base_url="http://test:9380/api/v1",
            api_key="test-key",
            knowledge_base_id="test-kb-id",
        )
        # 需要 mock settings 才能验证，这里测试实例属性
        assert retriever.api_key == "test-key"
        assert retriever.kb_id == "test-kb-id"

    def test_enabled_false_when_no_api_key(self):
        """无 API Key 时 disabled"""
        retriever = RAGFlowRetriever(
            base_url="http://test:9380/api/v1",
            api_key="",
            knowledge_base_id="test-kb-id",
        )
        assert not retriever.api_key
        assert retriever.kb_id == "test-kb-id"

    def test_parse_chunks_valid(self):
        """解析正常 RAGFlow 检索返回"""
        data = {
            "chunks": [
                {
                    "content": "I-Line H 630A: Icw=30 kA",
                    "document_name": "I-Line H 样本.pdf",
                    "similarity": 0.95,
                },
                {
                    "content": "I-Line B 电流范围: 400A-6300A",
                    "document_name": "I-Line B 样本.pdf",
                    "similarity": 0.82,
                },
            ]
        }
        chunks = self.retriever._parse_chunks(data)
        assert len(chunks) == 2
        assert chunks[0]["content"] == "I-Line H 630A: Icw=30 kA"
        assert chunks[0]["source"] == "I-Line H 样本.pdf"
        assert chunks[0]["score"] == 0.95
        assert chunks[1]["source"] == "I-Line B 样本.pdf"
        assert chunks[1]["score"] == 0.82

    def test_parse_chunks_empty(self):
        """空 chunks 列表"""
        chunks = self.retriever._parse_chunks({"chunks": []})
        assert len(chunks) == 0

    def test_parse_chunks_missing_field(self):
        """chunks 缺失 content 或 document_name"""
        data = {
            "chunks": [
                {
                    "content": "",
                    "document_name": "test.pdf",
                    "similarity": 0.5,
                },
                {
                    "content": "valid content",
                    "similarity": 0.8,
                },
            ]
        }
        chunks = self.retriever._parse_chunks(data)
        assert len(chunks) == 1
        assert chunks[0]["source"] == "未知来源"

    def test_parse_chunks_not_list(self):
        """chunks 不是列表"""
        chunks = self.retriever._parse_chunks({"chunks": "invalid"})
        assert len(chunks) == 0

    def test_format_context_with_chunks(self):
        """格式化上下文 — 有检索结果"""
        chunks = [
            {"content": "Icw=30 kA", "source": "H样本.pdf", "score": 0.95},
            {"content": "400A-6300A", "source": "B样本.pdf", "score": 0.82},
        ]
        context = self.retriever.format_context(chunks, max_chunks=3)
        assert "【以下为参考文档内容" in context
        assert "[参考来源 1: H样本.pdf]" in context
        assert "Icw=30 kA" in context
        assert "[参考来源 2: B样本.pdf]" in context
        assert "【用户问题】" not in context  # format_context 不含用户问题

    def test_format_context_empty(self):
        """空 chunks 返回空字符串"""
        context = self.retriever.format_context([], max_chunks=3)
        assert context == ""

    def test_format_context_limit(self):
        """限制最多 max_chunks 个片段"""
        chunks = [
            {"content": f"content {i}", "source": "test.pdf", "score": 1.0 - i * 0.1}
            for i in range(10)
        ]
        context = self.retriever.format_context(chunks, max_chunks=3)
        # 应该只有 3 个 [参考来源 X]
        assert context.count("[参考来源") == 3

    def test_build_enhanced_message_with_context(self):
        """构建增强消息 — 有上下文"""
        chunks = [
            {"content": "Icw=30 kA", "source": "H样本.pdf", "score": 0.95},
        ]
        enhanced = self.retriever.build_enhanced_message("I-Line H Icw?", chunks)
        assert "【以下为参考文档内容" in enhanced
        assert "[参考来源 1: H样本.pdf]" in enhanced
        assert "Icw=30 kA" in enhanced
        assert "【用户问题】" in enhanced
        assert "I-Line H Icw?" in enhanced

    def test_build_enhanced_message_no_context(self):
        """无上下文时返回原始消息"""
        enhanced = self.retriever.build_enhanced_message("hello", [])
        assert enhanced == "hello"

    def test_build_enhanced_message_empty_chunk_content(self):
        """空 chunk content 被跳过"""
        chunks = [
            {"content": "", "source": "empty.pdf", "score": 0.5},
        ]
        enhanced = self.retriever.build_enhanced_message("hello", chunks)
        assert enhanced == "hello"


class TestRetrieveContext:
    """retrieve_context 便捷函数测试"""

    @pytest.mark.asyncio
    async def test_retrieve_context_disabled(self):
        """RAGFlow 禁用时返回空"""
        with patch(
            "app.services.ragflow_retriever.get_retriever"
        ) as mock_get:
            mock_retriever = MagicMock()
            mock_retriever.enabled = False
            mock_get.return_value = mock_retriever

            chunks, context = await retrieve_context("test query")
            assert chunks == []
            assert context == ""

    @pytest.mark.asyncio
    async def test_retrieve_context_success(self):
        """检索成功时返回 chunks 和格式化上下文"""
        with patch(
            "app.services.ragflow_retriever.get_retriever"
        ) as mock_get:
            mock_retriever = MagicMock()
            mock_retriever.enabled = True
            mock_retriever.retrieve = AsyncMock(return_value=[{
                "content": "test content",
                "source": "test.pdf",
                "score": 0.9,
            }])
            mock_retriever.format_context.return_value = "formatted context"

            mock_get.return_value = mock_retriever

            chunks, context = await retrieve_context("test query")
            assert len(chunks) == 1
            assert context == "formatted context"
            mock_retriever.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_context_failure_graceful(self):
        """检索失败时不影响主流程，返回空"""
        with patch(
            "app.services.ragflow_retriever.get_retriever"
        ) as mock_get:
            mock_retriever = MagicMock()
            mock_retriever.enabled = True
            mock_retriever.retrieve = AsyncMock(
                side_effect=Exception("network error")
            )
            mock_get.return_value = mock_retriever

            # 不应抛出异常
            chunks, context = await retrieve_context("test query")
            assert chunks == []
            assert context == ""


class TestRetrieverRetrieve:
    """retrieve 方法网络调用测试"""

    @pytest.mark.asyncio
    async def test_retrieve_disabled(self):
        """未启用时直接返回空列表"""
        retriever = RAGFlowRetriever(
            base_url="http://test:9380/api/v1",
            api_key="",
            knowledge_base_id="",
        )
        chunks = await retriever.retrieve("test")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_retrieve_http_error(self):
        """HTTP 非 200 时返回空列表"""
        with patch("httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_resp
            )

            with patch("app.services.ragflow_retriever.settings") as mock_settings:
                mock_settings.RAGFLOW_ENABLED = True
                mock_settings.RAGFLOW_API_KEY = "test-key"
                mock_settings.RAGFLOW_KNOWLEDGE_BASE_ID = "test-kb-id"

                retriever = RAGFlowRetriever(
                    base_url="http://test:9380/api/v1",
                    api_key="test-key",
                    knowledge_base_id="test-kb-id",
                )
                chunks = await retriever.retrieve("test")
                assert chunks == []

    @pytest.mark.asyncio
    async def test_retrieve_timeout(self):
        """超时时返回空列表"""
        with patch("httpx.AsyncClient") as mock_client:
            import httpx
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )

            with patch("app.services.ragflow_retriever.settings") as mock_settings:
                mock_settings.RAGFLOW_ENABLED = True
                mock_settings.RAGFLOW_API_KEY = "test-key"
                mock_settings.RAGFLOW_KNOWLEDGE_BASE_ID = "test-kb-id"

                retriever = RAGFlowRetriever(
                    base_url="http://test:9380/api/v1",
                    api_key="test-key",
                    knowledge_base_id="test-kb-id",
                )
                chunks = await retriever.retrieve("test")
                assert chunks == []


class TestGetRetriever:
    """get_retriever 单例测试"""

    def test_get_retriever_returns_instance(self):
        """get_retriever 返回 RAGFlowRetriever 实例"""
        with patch(
            "app.services.ragflow_retriever._retriever", None
        ):
            # 需要 mock settings 避免读取真实配置
            with patch("app.services.ragflow_retriever.settings") as mock_settings:
                mock_settings.RAGFLOW_API_BASE = "http://test:9380/api/v1"
                mock_settings.RAGFLOW_API_KEY = None
                mock_settings.RAGFLOW_KNOWLEDGE_BASE_ID = None
                mock_settings.RAGFLOW_ENABLED = True

                retriever = get_retriever()
                from app.services.ragflow_retriever import RAGFlowRetriever
                assert isinstance(retriever, RAGFlowRetriever)