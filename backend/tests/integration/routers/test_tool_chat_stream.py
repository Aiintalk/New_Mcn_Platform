"""Integration tests for tool_chat_stream router."""
from unittest.mock import AsyncMock, patch

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "system_prompt": "你是专家",
                "model": "gpt-4o",
                "max_tokens": 100,
            },
        )
        assert resp.status_code == 401


class TestChatStream:
    @pytest.mark.asyncio
    async def test_system_prompt_prepended(self, test_client, operator_token):
        """验证 system_prompt 被拼入 messages 首位。"""
        captured_messages = []

        async def fake_stream(messages, db, model_id, user_id, feature, max_tokens, **kwargs):
            captured_messages.extend(messages)
            yield "chunk1"
            yield "chunk2"

        with patch("app.routers.tool_chat_stream.yunwu_adapter.chat_stream", side_effect=fake_stream):
            resp = await test_client.post(
                "/api/tools/chat-stream",
                json={
                    "messages": [{"role": "user", "content": "分析这个视频"}],
                    "system_prompt": "你是千川剪辑预审专家",
                    "model": "gpt-4o",
                    "max_tokens": 8000,
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert captured_messages[0]["role"] == "system"
        assert captured_messages[0]["content"] == "你是千川剪辑预审专家"
        assert captured_messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [],
                "system_prompt": "你是专家",
                "model": "gpt-4o",
                "max_tokens": 8000,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_system_prompt_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/chat-stream",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "system_prompt": "  ",
                "model": "gpt-4o",
                "max_tokens": 8000,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
