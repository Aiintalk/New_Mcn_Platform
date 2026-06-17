"""Integration tests for operator_qianchuan_preview and admin_qianchuan_preview."""
from unittest.mock import patch

import pytest
from sqlalchemy import text as sa_text


@pytest.fixture(autouse=True)
async def seed_preview_config(test_session):
    await test_session.execute(sa_text(
        "INSERT INTO qianchuan_preview_configs (config_key, system_prompt, is_active) "
        "VALUES ('default', '你是千川文案审核专家。', true) "
        "ON CONFLICT (config_key) DO NOTHING"
    ))
    await test_session.commit()
    yield


# ── Auth ──────────────────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post("/api/tools/qianchuan-preview/parse-file",
                                      files={"file": ("a.txt", b"hello", "text/plain")})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post("/api/tools/qianchuan-preview/generate",
                                      json={"script_a": "文案A", "script_b": "文案B"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_word_unauthorized(self, test_client):
        resp = await test_client.post("/api/tools/qianchuan-preview/export-word",
                                      json={"content": "报告", "title": "预审"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_configs_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-preview/configs")
        assert resp.status_code == 401


# ── parse-file ────────────────────────────────────────────────────────────

class TestParseFile:
    @pytest.mark.asyncio
    async def test_parse_txt_success(self, test_client, operator_token):
        content = "这是一段千川广告文案内容"
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/parse-file",
            files={"file": ("script.txt", content.encode("utf-8"), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["text"] == content
        assert data["data"]["filename"] == "script.txt"

    @pytest.mark.asyncio
    async def test_parse_unsupported_format_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/parse-file",
            files={"file": ("script.pdf", b"%PDF", "application/pdf")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"

    @pytest.mark.asyncio
    async def test_parse_no_file_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/parse-file",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422


# ── generate ──────────────────────────────────────────────────────────────

class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_empty_script_a_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/generate",
            json={"script_a": "", "script_b": "文案B内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_generate_empty_script_b_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/generate",
            json={"script_a": "文案A内容", "script_b": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_generate_streams_response(self, test_client, operator_token):
        async def fake_stream(**kwargs):
            for chunk in ["这是", "预审", "报告"]:
                yield chunk

        with patch(
            "app.routers.operator_qianchuan_preview.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-preview/generate",
                json={"script_a": "原版爆款文案内容", "script_b": "我方文案内容"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "这是预审报告" in resp.text

    @pytest.mark.asyncio
    async def test_generate_missing_field_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/generate",
            json={"script_a": "文案A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_whitespace_script_a_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/generate",
            json={"script_a": "   ", "script_b": "文案B内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"


# ── export-word ───────────────────────────────────────────────────────────

class TestExportWord:
    @pytest.mark.asyncio
    async def test_export_word_success(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/export-word",
            json={"content": "### 开头对比\n文案A很好", "title": "千川文案预审报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert "attachment" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_word_empty_content_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-preview/export-word",
            json={"content": "", "title": "千川文案预审报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"


# ── admin configs ─────────────────────────────────────────────────────────

class TestAdminConfigs:
    @pytest.mark.asyncio
    async def test_list_configs_success(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-preview/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        configs = data["data"]
        assert len(configs) >= 1
        keys = [c["config_key"] for c in configs]
        assert "default" in keys

    @pytest.mark.asyncio
    async def test_operator_cannot_access_admin_configs(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-preview/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_config_success(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/qianchuan-preview/configs/default",
            json={"ai_model_id": None, "system_prompt": "新的 Prompt 内容", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_config_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/qianchuan-preview/configs/nonexistent",
            json={"ai_model_id": None, "system_prompt": "x", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
