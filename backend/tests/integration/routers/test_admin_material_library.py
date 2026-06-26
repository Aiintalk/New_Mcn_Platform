"""
Integration tests for admin_material_library router.

Covers:
- Auth (4 scenarios: admin OK / operator forbidden / invalid / unauthenticated)
- GET /configs (returns soul_generator seed config)
- PUT /configs (update prompt / update model / writes OperationLog)
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 material_library_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO material_library_configs "
        "(config_key, ai_model_id, system_prompt, is_active) "
        "VALUES ('soul_generator', null, '初始soul生成Prompt', true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "system_prompt = EXCLUDED.system_prompt, is_active = true"
    ))
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/material-library/configs",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/material-library/configs",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/material-library/configs",
            headers={"Authorization": "Bearer invalid"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token(self, test_client):
        resp = await test_client.get("/api/admin/material-library/configs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /configs
# ---------------------------------------------------------------------------

class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_returns_soul_generator(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/material-library/configs",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1
        cfg = body["data"][0]
        assert cfg["config_key"] == "soul_generator"
        assert "system_prompt" in cfg
        assert "is_active" in cfg


# ---------------------------------------------------------------------------
# PUT /configs
# ---------------------------------------------------------------------------

class TestUpdateConfigs:
    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/material-library/configs",
            headers=admin_headers,
            json={"system_prompt": "更新后的Prompt"},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["system_prompt"] == "更新后的Prompt"

    @pytest.mark.asyncio
    async def test_update_model(self, test_client, admin_headers, test_session):
        # Create an ai_model first to satisfy FK constraint
        await test_session.execute(text(
            "INSERT INTO ai_models (name, provider, model_id, status) "
            "VALUES ('Test Model', 'yunwu', 'test-model-001', 'active') "
            "ON CONFLICT (model_id) DO UPDATE SET name = EXCLUDED.name"
        ))
        await test_session.commit()
        result = await test_session.execute(text(
            "SELECT id FROM ai_models WHERE model_id = 'test-model-001'"
        ))
        model_id = result.scalar()

        resp = await test_client.put(
            "/api/admin/material-library/configs",
            headers=admin_headers,
            json={"ai_model_id": model_id},
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["ai_model_id"] == model_id

    @pytest.mark.asyncio
    async def test_update_writes_operation_log(self, test_client, admin_headers, test_session):
        resp = await test_client.put(
            "/api/admin/material-library/configs",
            headers=admin_headers,
            json={"system_prompt": "test prompt for log"},
        )
        assert resp.status_code == 200

        log_count = await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'admin_material_library_update_config'"
        ))
        assert int(log_count.scalar()) >= 1
