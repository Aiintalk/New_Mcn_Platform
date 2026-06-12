"""
Integration tests for operator_tiktok_writer router.
覆盖：Auth(401) / chat(400+流式) / export-word(400+docx+outputs写入) / kols/personas(空列表+有数据)
"""
import io
from unittest.mock import patch, AsyncMock

import pytest
from docx import Document
from sqlalchemy import text


class TestAuth:
    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_word_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Alice", "topic": "t", "content": "hello"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_kols_personas_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/tiktok-writer/kols/personas")
        assert resp.status_code == 401


class TestChat:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [], "systemPrompt": "test prompt"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        # 全局 HTTPException 处理器将 detail 包装为 {code, message} 格式
        assert data.get("code") == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_empty_system_prompt_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data.get("code") == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_chat_streams_plain_text(self, test_client, operator_token):
        async def mock_stream(*args, **kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        with patch("app.routers.operator_tiktok_writer.yunwu_adapter.chat_stream", side_effect=mock_stream):
            resp = await test_client.post(
                "/api/tools/tiktok-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "go"}],
                    "systemPrompt": "You are helpful.",
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "Hello world" in resp.text


class TestExportWord:
    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Alice", "topic": "t", "content": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data.get("code") == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_export_returns_docx_bytes(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={
                "personaName": "Alice",
                "topic": "https://tiktok.com/v/123",
                "content": "# Opening\nHello world\n\n**Bold** text",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]
        doc = Document(io.BytesIO(resp.content))
        texts = [p.text for p in doc.paragraphs]
        assert any("Alice" in t for t in texts)

    @pytest.mark.asyncio
    async def test_export_content_disposition_filename(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={"personaName": "Bob", "topic": "t", "content": "Hello"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "TikTok_Script_Bob" in cd

    @pytest.mark.asyncio
    async def test_export_writes_output_record(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/tiktok-writer/export-word",
            json={
                "personaName": "Carol",
                "topic": "https://t.co/abc",
                "content": "Final script content here",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        result = await test_session.execute(
            text("SELECT tool_code, content FROM outputs WHERE tool_code='tiktok-writer' ORDER BY id DESC LIMIT 1")
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "tiktok-writer"
        assert "Final script content here" in row[1]


class TestKolsPersonas:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_personas(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "personas" in data
        assert isinstance(data["personas"], list)

    @pytest.mark.asyncio
    async def test_returns_kols_with_persona(self, test_client, operator_token, test_session):
        await test_session.execute(text("""
            INSERT INTO kols (name, persona, content_plan, status, created_at, updated_at)
            VALUES ('TestCreator', 'Soul content here', 'Content plan here',
                    'active', NOW(), NOW())
        """))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        personas = resp.json()["personas"]
        assert any(p["name"] == "TestCreator" for p in personas)
        target = next(p for p in personas if p["name"] == "TestCreator")
        assert "soul" in target
        assert "contentPlan" in target
        assert "Soul content here" in target["soul"]

    @pytest.mark.asyncio
    async def test_kols_without_persona_excluded(self, test_client, operator_token, test_session):
        await test_session.execute(text("""
            INSERT INTO kols (name, persona, status, created_at, updated_at)
            VALUES ('NullPersonaCreator', NULL, 'active', NOW(), NOW())
        """))
        await test_session.commit()

        resp = await test_client.get(
            "/api/tools/tiktok-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        personas = resp.json()["personas"]
        assert not any(p["name"] == "NullPersonaCreator" for p in personas)
