"""
Integration tests for admin_persona_writer router.

Covers:
- 4 auth scenarios (admin OK / operator forbidden / invalid / unauthenticated)
- GET /configs returns seed config
- PUT /configs/default updates 4 Prompt + 2 model IDs + writes OperationLog
- PUT /configs/nonexistent returns 404
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def ensure_config(test_session):
    """确保测试库有 default 配置。"""
    await test_session.execute(text(
        "INSERT INTO persona_writer_configs "
        "(config_key, evaluation_prompt, analysis_prompt, writing_prompt, iteration_prompt, "
        "light_model_id, heavy_model_id, is_active) "
        "VALUES (:config_key, :eval_prompt, :analysis_prompt, :writing_prompt, "
        ":iteration_prompt, NULL, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "evaluation_prompt = EXCLUDED.evaluation_prompt, "
        "is_active = true"
    ), {
        "config_key": "default",
        "eval_prompt": "管理员评估Prompt {{transcript}}",
        "analysis_prompt": "管理员分析Prompt",
        "writing_prompt": "管理员写作Prompt {{name}} {{is_custom}}custom{{/is_custom}}",
        "iteration_prompt": "管理员追问Prompt",
    })
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_get_configs_no_token(self, test_client):
        resp = await test_client.get("/api/admin/persona-writer/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_configs_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/persona-writer/configs",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_configs_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/persona-writer/configs",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_configs_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/persona-writer/configs",
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
            "/api/admin/persona-writer/configs",
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True
        configs = body["data"]
        assert len(configs) >= 1
        default = [c for c in configs if c["config_key"] == "default"][0]
        assert default["is_active"] is True
        assert "{{transcript}}" in default["evaluation_prompt"]
        assert default["light_model_id"] is None
        assert default["heavy_model_id"] is None
        # 验证 4 个 prompt 字段都存在
        assert "evaluation_prompt" in default
        assert "analysis_prompt" in default
        assert "writing_prompt" in default
        assert "iteration_prompt" in default


# ---------------------------------------------------------------------------
# PUT /configs/{config_key}
# ---------------------------------------------------------------------------

class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_prompts(self, test_client, admin_headers, test_session):
        new_eval = "更新评估 {{transcript}}"
        new_analysis = "更新分析"
        new_writing = "更新写作 {{name}} {{is_custom}}x{{/is_custom}}"
        new_iteration = "更新追问"
        resp = await test_client.put(
            "/api/admin/persona-writer/configs/default",
            json={
                "evaluation_prompt": new_eval,
                "analysis_prompt": new_analysis,
                "writing_prompt": new_writing,
                "iteration_prompt": new_iteration,
                "light_model_id": None,
                "heavy_model_id": None,
                "is_active": True,
            },
            headers=admin_headers,
        )
        body = resp.json()
        assert body["success"] is True

        row = (await test_session.execute(text(
            "SELECT evaluation_prompt, analysis_prompt, writing_prompt, iteration_prompt "
            "FROM persona_writer_configs WHERE config_key='default'"
        ))).fetchone()
        assert row[0] == new_eval
        assert row[1] == new_analysis
        assert row[2] == new_writing
        assert row[3] == new_iteration

    @pytest.mark.asyncio
    async def test_update_model_ids(self, test_client, admin_headers, test_session):
        model_row = (await test_session.execute(text(
            "INSERT INTO ai_models (model_id, name, provider, status) "
            "VALUES ('test-pw-light', '测试轻模型', 'yunwu', 'active') RETURNING id"
        ))).fetchone()
        light_id = model_row[0]

        model_row2 = (await test_session.execute(text(
            "INSERT INTO ai_models (model_id, name, provider, status) "
            "VALUES ('test-pw-heavy', '测试重模型', 'yunwu', 'active') RETURNING id"
        ))).fetchone()
        heavy_id = model_row2[0]
        await test_session.commit()

        resp = await test_client.put(
            "/api/admin/persona-writer/configs/default",
            json={
                "evaluation_prompt": "x",
                "analysis_prompt": "x",
                "writing_prompt": "x",
                "iteration_prompt": "x",
                "light_model_id": int(light_id),
                "heavy_model_id": int(heavy_id),
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_key(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/persona-writer/configs/nonexistent",
            json={
                "evaluation_prompt": "x",
                "analysis_prompt": "x",
                "writing_prompt": "x",
                "iteration_prompt": "x",
                "light_model_id": None,
                "heavy_model_id": None,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_writes_op_log(self, test_client, admin_headers, admin_user, test_session):
        resp = await test_client.put(
            "/api/admin/persona-writer/configs/default",
            json={
                "evaluation_prompt": "log-test-eval",
                "analysis_prompt": "x",
                "writing_prompt": "x",
                "iteration_prompt": "x",
                "light_model_id": None,
                "heavy_model_id": None,
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log_row = (await test_session.execute(text(
            "SELECT action, user_id FROM operation_logs "
            "WHERE action='admin_update_persona_writer_config' "
            "ORDER BY created_at DESC LIMIT 1"
        ))).fetchone()
        assert log_row is not None
        assert log_row[0] == "admin_update_persona_writer_config"
        assert log_row[1] == admin_user.id
