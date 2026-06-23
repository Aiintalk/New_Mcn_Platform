"""
Integration tests for admin_qianchuan_writer router.

Covers:
- 4 auth scenarios (admin OK / operator forbidden / invalid / unauthenticated)
- GET /configs returns seed config
- PUT /configs/default updates prompt + ai_model_id
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库有 default 配置。"""
    await test_session.execute(text(
        "INSERT INTO qianchuan_writer_configs (config_key, system_prompt, ai_model_id, is_active) "
        "VALUES ('default', '管理员测试Prompt {{name}}', NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "system_prompt = EXCLUDED.system_prompt, ai_model_id = NULL, is_active = true"
    ))
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_get_configs_no_token(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-writer/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_configs_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/qianchuan-writer/configs",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_configs_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/qianchuan-writer/configs",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_configs_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/qianchuan-writer/configs",
            headers={"Authorization": "Bearer xxx_invalid"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /configs
# ---------------------------------------------------------------------------

class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_returns_seed_config(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/qianchuan-writer/configs",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        configs = body["data"]
        assert len(configs) >= 1
        default = [c for c in configs if c["config_key"] == "default"][0]
        assert default["is_active"] is True
        assert "{{name}}" in default["system_prompt"]
        assert default["ai_model_id"] is None


# ---------------------------------------------------------------------------
# PUT /configs/{config_key}
# ---------------------------------------------------------------------------

class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_headers, test_session):
        new_prompt = "更新后的Prompt {{name}} {{soul}} {{content_plan}} - v2"
        resp = await test_client.put(
            "/api/admin/qianchuan-writer/configs/default",
            json={"system_prompt": new_prompt, "ai_model_id": None, "is_active": True},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["config_key"] == "default"

        # 验证 DB 已更新
        row = (await test_session.execute(text(
            "SELECT system_prompt FROM qianchuan_writer_configs WHERE config_key='default'"
        ))).fetchone()
        assert row[0] == new_prompt

    @pytest.mark.asyncio
    async def test_update_ai_model_id(self, test_client, admin_headers, test_session):
        # 先确保有一个 ai_model 可用
        model_row = (await test_session.execute(text(
            "INSERT INTO ai_models (model_id, name, provider, status) "
            "VALUES ('test-qc-model', '测试模型', 'yunwu', 'active') "
            "RETURNING id"
        ))).fetchone()
        model_id = model_row[0]
        await test_session.commit()

        resp = await test_client.put(
            "/api/admin/qianchuan-writer/configs/default",
            json={"system_prompt": "x", "ai_model_id": int(model_id), "is_active": True},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_key(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/qianchuan-writer/configs/nonexistent",
            json={"system_prompt": "x", "ai_model_id": None, "is_active": True},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.put(
            "/api/admin/qianchuan-writer/configs/default",
            json={"system_prompt": "x", "ai_model_id": None, "is_active": True},
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_writes_op_log(self, test_client, admin_headers, admin_user, test_session):
        resp = await test_client.put(
            "/api/admin/qianchuan-writer/configs/default",
            json={"system_prompt": "log-test-prompt", "ai_model_id": None, "is_active": True},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        # 验证 operation_logs 写入
        log_row = (await test_session.execute(text(
            "SELECT action, user_id FROM operation_logs "
            "WHERE action='admin_update_qianchuan_writer_config' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log_row is not None
        assert log_row[0] == "admin_update_qianchuan_writer_config"
        assert log_row[1] == admin_user.id
