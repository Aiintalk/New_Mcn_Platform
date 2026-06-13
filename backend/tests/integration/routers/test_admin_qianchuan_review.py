"""Integration tests for admin_qianchuan_review router."""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
async def seed_configs(test_session):
    for key, prompt in [('with_excel', 'With Excel Prompt'), ('without_excel', 'Without Excel Prompt')]:
        await test_session.execute(text(
            "INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-review/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_returns_list(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        keys = [c["config_key"] for c in data["data"]]
        assert "with_excel" in keys
        assert "without_excel" in keys

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/qianchuan-review/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        cfg = next(c for c in resp.json()["data"] if c["config_key"] == "with_excel")
        for field in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
            assert field in cfg


class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/with_excel",
            json={"system_prompt": "new"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/with_excel",
            json={"system_prompt": "Updated With Excel Prompt", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        row = (await test_session.execute(
            text("SELECT system_prompt FROM qianchuan_review_configs WHERE config_key='with_excel'")
        )).fetchone()
        assert row[0] == "Updated With Excel Prompt"

    @pytest.mark.asyncio
    async def test_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/qianchuan-review/configs/nonexistent",
            json={"system_prompt": "x"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"
