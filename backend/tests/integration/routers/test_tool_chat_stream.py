"""Integration tests for tool_chat_stream router."""
from unittest.mock import patch

import pytest
from sqlalchemy import text


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

    @pytest.mark.asyncio
    async def test_passes_default_provider_when_no_ai_model_id(
        self, test_client, operator_token
    ):
        """不传 ai_model_id 时，chat_stream 调用应传 provider='yunwu'，model_id=body.model。"""
        captured_kwargs = {}

        async def fake_stream(messages, db, **kwargs):
            captured_kwargs.update(kwargs)
            yield "chunk1"

        with patch("app.routers.tool_chat_stream.yunwu_adapter.chat_stream", side_effect=fake_stream):
            resp = await test_client.post(
                "/api/tools/chat-stream",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "system_prompt": "你是专家",
                    "model": "gpt-4o",
                    "max_tokens": 100,
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert captured_kwargs["provider"] == "yunwu"
        assert captured_kwargs["model_id"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_passes_provider_from_ai_model_id(
        self, test_client, operator_token, test_session
    ):
        """ai_models 表 provider=siliconflow 时，传 ai_model_id 应使 chat_stream 收到正确的 provider 和 model_id。"""
        # 插入 siliconflow provider 的 ai_model
        await test_session.execute(text(
            "INSERT INTO ai_models (name, provider, model_id, status) "
            "VALUES ('Qwen3-Omni', 'siliconflow', 'Qwen/Qwen3-Omni', 'active') "
            "ON CONFLICT DO NOTHING"
        ))
        row = (await test_session.execute(text(
            "SELECT id FROM ai_models WHERE model_id='Qwen/Qwen3-Omni' AND provider='siliconflow'"
        ))).fetchone()
        ai_model_id = row[0]
        await test_session.commit()

        captured_kwargs = {}

        async def fake_stream(messages, db, **kwargs):
            captured_kwargs.update(kwargs)
            yield "chunk1"

        with patch("app.routers.tool_chat_stream.yunwu_adapter.chat_stream", side_effect=fake_stream):
            resp = await test_client.post(
                "/api/tools/chat-stream",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "system_prompt": "你是专家",
                    "model": "gpt-4o",
                    "max_tokens": 100,
                    "ai_model_id": ai_model_id,
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert captured_kwargs["provider"] == "siliconflow"
        assert captured_kwargs["model_id"] == "Qwen/Qwen3-Omni"
