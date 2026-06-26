"""
Integration tests for admin_subtitle router — Sprint 19
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def ensure_subtitle_config(test_session):
    await test_session.execute(text(
        "INSERT INTO subtitle_configs "
        "(config_key, mindmap_prompt, mindmap_model_id, is_active) "
        "VALUES ('default', :prompt, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "mindmap_prompt = EXCLUDED.mindmap_prompt, is_active = true"
    ), {"prompt": "测试 prompt {{transcript}}"})
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_configs_no_token(self, test_client):
        resp = await test_client.get("/api/admin/subtitle/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_configs_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_configs_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=admin_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_configs_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/subtitle/configs",
            headers={"Authorization": "Bearer invalid_token_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /configs
# ---------------------------------------------------------------------------

class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_returns_default_config(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=admin_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert len(data) >= 1
        default = next((c for c in data if c["config_key"] == "default"), None)
        assert default is not None
        assert "{{transcript}}" in default["mindmap_prompt"]
        assert default["is_active"] is True


# ---------------------------------------------------------------------------
# PUT /configs
# ---------------------------------------------------------------------------

class TestUpdateConfigs:
    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_headers, test_session):
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={"mindmap_prompt": "新的 prompt {{transcript}}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["mindmap_prompt"] == "新的 prompt {{transcript}}"

        # OperationLog 写入
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'admin_subtitle_config_update'"
        ))).scalar()
        assert log_count == 1

    @pytest.mark.asyncio
    async def test_update_is_active(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_no_fields(self, test_client, admin_headers):
        """无字段更新 → 200 + changes 空"""
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={},
        )
        assert resp.status_code == 200
