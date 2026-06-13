"""Integration tests for admin_selling_point router."""
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.selling_point import SellingPointConfig


@pytest_asyncio.fixture(autouse=True)
async def seed_selling_point_config(test_session):
    """每个测试前插入 extract 配置行，测试后自动清理。"""
    config = SellingPointConfig(
        config_key="extract",
        system_prompt="默认提取卖点 Prompt",
        is_active=True,
    )
    test_session.add(config)
    await test_session.commit()
    yield
    await test_session.execute(
        text("DELETE FROM selling_point_configs WHERE config_key='extract'")
    )
    await test_session.commit()


class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/selling-point/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/selling-point/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_returns_config_list(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/selling-point/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert any(c["config_key"] == "extract" for c in data["data"])

    @pytest.mark.asyncio
    async def test_config_has_required_fields(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/selling-point/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        config = next(c for c in resp.json()["data"] if c["config_key"] == "extract")
        for field in ("id", "config_key", "ai_model_id", "system_prompt", "is_active", "updated_at"):
            assert field in config


class TestUpdateConfig:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": "new prompt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_update_system_prompt(self, test_client, admin_token, test_session):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": "更新后的 Prompt 内容", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        row = (await test_session.execute(
            text("SELECT system_prompt FROM selling_point_configs WHERE config_key='extract'")
        )).fetchone()
        assert row[0] == "更新后的 Prompt 内容"

    @pytest.mark.asyncio
    async def test_update_nonexistent_key_returns_404(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/selling-point/configs/nonexistent",
            json={"system_prompt": "x"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_update_restores_original_prompt(self, test_client, admin_token, test_session):
        """测试完恢复原始 prompt，避免污染其他测试。"""
        original = (await test_session.execute(
            text("SELECT system_prompt FROM selling_point_configs WHERE config_key='extract'")
        )).scalar()

        await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": "临时修改", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        await test_client.put(
            "/api/admin/selling-point/configs/extract",
            json={"system_prompt": original, "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        row = (await test_session.execute(
            text("SELECT system_prompt FROM selling_point_configs WHERE config_key='extract'")
        )).fetchone()
        assert row[0] == original
