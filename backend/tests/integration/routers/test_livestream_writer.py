"""
Integration tests for operator_livestream_writer and admin_livestream_writer routers.
覆盖：Auth(401/403) / config / kols/personas / parse-file / chat / admin configs
"""
import io
import zipfile
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Fixtures — seed data
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def seed_configs(test_session):
    for key, prompt in [
        ("generate", "首次生成 System Prompt"),
        ("iterate",  "多轮迭代 System Prompt"),
    ]:
        await test_session.execute(text(
            "INSERT INTO livestream_writer_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


@pytest.fixture
async def kol_with_both_fields(test_session):
    """插入一个 persona 和 content_plan 均非空的 KOL。"""
    await test_session.execute(text(
        "INSERT INTO kols (name, status, persona, content_plan, deleted_at) "
        "VALUES ('测试达人', 'active', '达人人格', '内容规划', NULL) "
        "ON CONFLICT DO NOTHING"
    ))
    await test_session.commit()


@pytest.fixture
async def kol_missing_persona(test_session):
    """插入一个 persona 为 NULL 的 KOL（应被过滤）。"""
    await test_session.execute(text(
        "INSERT INTO kols (name, status, persona, content_plan, deleted_at) "
        "VALUES ('无人格达人', 'active', NULL, '内容规划', NULL) "
        "ON CONFLICT DO NOTHING"
    ))
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_config_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/livestream-writer/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_kols_personas_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/livestream-writer/kols/personas")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post("/api/tools/livestream-writer/parse-file")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/livestream-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_configs_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/livestream-writer/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_configs_operator_forbidden(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/livestream-writer/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /config
# ---------------------------------------------------------------------------

class TestGetConfig:
    @pytest.mark.asyncio
    async def test_returns_two_prompts_and_model(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/livestream-writer/config",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "generate_prompt" in data["data"]
        assert "iterate_prompt" in data["data"]
        assert "model_id" in data["data"]
        assert data["data"]["generate_prompt"] == "首次生成 System Prompt"
        assert data["data"]["iterate_prompt"] == "多轮迭代 System Prompt"

    @pytest.mark.asyncio
    async def test_503_when_config_inactive(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("UPDATE livestream_writer_configs SET is_active = false WHERE config_key = 'generate'")
        )
        await test_session.commit()
        resp = await test_client.get(
            "/api/tools/livestream-writer/config",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 503
        # 恢复
        await test_session.execute(
            text("UPDATE livestream_writer_configs SET is_active = true WHERE config_key = 'generate'")
        )
        await test_session.commit()


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

class TestKolsPersonas:
    @pytest.mark.asyncio
    async def test_empty_list(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/livestream-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"]["personas"], list)

    @pytest.mark.asyncio
    async def test_returns_kol_with_both_fields(
        self, test_client, operator_token, kol_with_both_fields
    ):
        resp = await test_client.get(
            "/api/tools/livestream-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        personas = resp.json()["data"]["personas"]
        names = [p["name"] for p in personas]
        assert "测试达人" in names

    @pytest.mark.asyncio
    async def test_filters_kol_without_persona(
        self, test_client, operator_token, kol_missing_persona
    ):
        resp = await test_client.get(
            "/api/tools/livestream-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        personas = resp.json()["data"]["personas"]
        names = [p["name"] for p in personas]
        assert "无人格达人" not in names

    @pytest.mark.asyncio
    async def test_persona_fields(self, test_client, operator_token, kol_with_both_fields):
        resp = await test_client.get(
            "/api/tools/livestream-writer/kols/personas",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        kol = next(p for p in resp.json()["data"]["personas"] if p["name"] == "测试达人")
        assert "soul" in kol
        assert "contentPlan" in kol
        assert kol["soul"] == "达人人格"
        assert kol["contentPlan"] == "内容规划"


# ---------------------------------------------------------------------------
# POST /parse-file
# ---------------------------------------------------------------------------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_txt_file(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/livestream-writer/parse-file",
            files={"file": ("script.txt", "直播脚本文案内容".encode(), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "直播脚本文案内容" in data["data"]["text"]
        assert data["data"]["filename"] == "script.txt"

    @pytest.mark.asyncio
    async def test_pdf_returns_prompt(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/livestream-writer/parse-file",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "暂不支持" in resp.json()["data"]["text"]

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/livestream-writer/parse-file",
            files={"file": ("data.csv", b"col1,col2", "text/csv")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "UNSUPPORTED_FILE_TYPE"


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_empty_messages_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/livestream-writer/chat",
            json={"messages": [], "systemPrompt": "test prompt"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_empty_system_prompt_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/livestream-writer/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "systemPrompt": "   "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_chat_streams_plain_text(self, test_client, operator_token):
        async def mock_stream(*args, **kwargs):
            for chunk in ["直播", "脚本", "内容"]:
                yield chunk

        with patch(
            "app.routers.operator_livestream_writer.yunwu_adapter.chat_stream",
            side_effect=mock_stream,
        ):
            resp = await test_client.post(
                "/api/tools/livestream-writer/chat",
                json={
                    "messages": [{"role": "user", "content": "生成开播方案"}],
                    "systemPrompt": "你是直播间策划师。",
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "直播脚本内容" in resp.text


# ---------------------------------------------------------------------------
# Admin — GET /configs
# ---------------------------------------------------------------------------

class TestAdminGetConfigs:
    @pytest.mark.asyncio
    async def test_admin_returns_two_configs(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/livestream-writer/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        keys = [c["config_key"] for c in data["data"]]
        assert "generate" in keys
        assert "iterate" in keys

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/livestream-writer/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        cfg = next(c for c in resp.json()["data"] if c["config_key"] == "generate")
        for field in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
            assert field in cfg


# ---------------------------------------------------------------------------
# Admin — PUT /configs/{key}
# ---------------------------------------------------------------------------

class TestAdminUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/livestream-writer/configs/generate",
            json={"system_prompt": "新的首次生成 Prompt", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        row = (await test_session.execute(
            text("SELECT system_prompt FROM livestream_writer_configs WHERE config_key='generate'")
        )).fetchone()
        assert row[0] == "新的首次生成 Prompt"

    @pytest.mark.asyncio
    async def test_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/livestream-writer/configs/nonexistent",
            json={"system_prompt": "x", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_operator_cannot_update(self, test_client, operator_token):
        resp = await test_client.put(
            "/api/admin/livestream-writer/configs/generate",
            json={"system_prompt": "x", "is_active": True},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403
