"""
Integration tests for admin_seeding_writer router.

Covers:
- Auth (4 scenarios: admin OK / operator forbidden / invalid / unauthenticated)
- GET /configs (1)
- PUT /configs (4: update prompts / update models / not found / writes OperationLog)
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库中有激活的 seeding_writer_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO seeding_writer_configs "
        "(config_key, sp_system_prompt, is_active) "
        "VALUES ('default', '初始卖点Prompt', true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "sp_system_prompt = EXCLUDED.sp_system_prompt, is_active = true"
    ))
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/seeding-writer/configs",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/seeding-writer/configs",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/seeding-writer/configs",
            headers={"Authorization": "Bearer invalid"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token(self, test_client):
        resp = await test_client.get("/api/admin/seeding-writer/configs")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /configs
# ---------------------------------------------------------------------------

class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_returns_seed_config(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/seeding-writer/configs",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) >= 1
        config = body["data"][0]
        assert config["config_key"] == "default"
        # Verify all 6 prompt fields present
        for field in ("sp_system_prompt", "parse_product_prompt",
                      "structure_analysis_prompt", "ai_recommend_prompt",
                      "writing_prompt", "iteration_prompt"):
            assert field in config
        # Verify model fields
        assert "light_model_id" in config
        assert "heavy_model_id" in config
        assert "is_active" in config


# ---------------------------------------------------------------------------
# PUT /configs/{config_key}
# ---------------------------------------------------------------------------

class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_prompts(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/seeding-writer/configs/default",
            json={
                "sp_system_prompt": "新卖点Prompt",
                "writing_prompt": "新写作Prompt {{name}} {{product_name}}",
                "iteration_prompt": "新迭代Prompt",
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["config_key"] == "default"

    @pytest.mark.asyncio
    async def test_update_models(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/seeding-writer/configs/default",
            json={"light_model_id": None, "heavy_model_id": None, "is_active": True},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_config(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/seeding-writer/configs/nonexistent_key",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_writes_operation_log(self, test_client, admin_headers, test_session, admin_user):
        resp = await test_client.put(
            "/api/admin/seeding-writer/configs/default",
            json={"sp_system_prompt": "带日志的Prompt"},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        # Verify OperationLog was written
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'admin_update_seeding_writer_config' "
            "AND user_id = :uid"
        ), {"uid": admin_user.id})).scalar()
        assert log_count >= 1
