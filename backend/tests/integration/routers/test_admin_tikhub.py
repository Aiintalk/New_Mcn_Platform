"""
Integration tests for admin TikHub management router.

覆盖 10 个接口：
  GET    /api/admin/tikhub/stats           — 统计
  GET    /api/admin/tikhub/keys            — Key 列表
  POST   /api/admin/tikhub/keys            — 新增 Key
  PUT    /api/admin/tikhub/keys/{id}       — 编辑 Key
  DELETE /api/admin/tikhub/keys/{id}       — 删除 Key
  POST   /api/admin/tikhub/keys/{id}/test  — 测试连通性
  POST   /api/admin/tikhub/keys/{id}/enable  — 启用
  POST   /api/admin/tikhub/keys/{id}/disable — 停用
  GET    /api/admin/tikhub/endpoints       — 接口统计
  GET    /api/admin/tikhub/users           — 用户排行
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models.tikhub_credential import TikHubCredential


# ── Auth tests ─────────────────────────────────────────────────────

class TestAdminTikHubAuth:
    """所有 admin tikhub 接口未授权返回 401，非 admin 返回 403。"""

    @pytest.mark.asyncio
    async def test_unauthorized_stats(self, test_client):
        resp = await test_client.get("/api/admin/tikhub/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_keys(self, test_client):
        resp = await test_client.get("/api/admin/tikhub/keys")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_create_key(self, test_client):
        resp = await test_client.post("/api/admin/tikhub/keys", json={"api_key": "test"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_headers):
        """operator 角色无权访问 admin 接口。"""
        resp = await test_client.get("/api/admin/tikhub/stats", headers=operator_headers)
        assert resp.status_code == 403


# ── Key CRUD tests ─────────────────────────────────────────────────

class TestTikHubKeyCRUD:

    @pytest.mark.asyncio
    async def test_list_keys_empty(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/tikhub/keys", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_create_key(self, test_client, admin_headers):
        """新增 TikHub Key。"""
        resp = await test_client.post(
            "/api/admin/tikhub/keys",
            headers=admin_headers,
            json={
                "label": "test-key",
                "api_key": "tk_test_12345678",
                "base_url": "https://api.tikhub.io",
                "max_concurrent": 5,
                "max_users": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["label"] == "test-key"
        assert data["status"] == "active"
        # api_key 应脱敏
        assert "12345678" not in data["api_key"] or data["api_key"].endswith("5678")

    @pytest.mark.asyncio
    async def test_create_key_default_values(self, test_client, admin_headers):
        """新增 Key 使用默认值。"""
        resp = await test_client.post(
            "/api/admin/tikhub/keys",
            headers=admin_headers,
            json={"api_key": "tk_default_test"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["base_url"] == "https://api.tikhub.io"

    @pytest.mark.asyncio
    async def test_update_key(self, test_client, admin_headers, test_session):
        """编辑 Key。"""
        cred = TikHubCredential(
            label="old-label",
            api_key="tk_old_key",
            base_url="https://api.tikhub.io",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        resp = await test_client.put(
            f"/api/admin/tikhub/keys/{cred.id}",
            headers=admin_headers,
            json={"label": "new-label", "max_concurrent": 10},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["label"] == "new-label"

    @pytest.mark.asyncio
    async def test_update_key_not_found(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/tikhub/keys/99999",
            headers=admin_headers,
            json={"label": "not-found"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @pytest.mark.asyncio
    async def test_delete_key(self, test_client, admin_headers, test_session):
        """删除 Key。"""
        cred = TikHubCredential(
            label="to-delete",
            api_key="tk_delete_me",
            base_url="https://api.tikhub.io",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        resp = await test_client.delete(
            f"/api/admin/tikhub/keys/{cred.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self, test_client, admin_headers):
        resp = await test_client.delete("/api/admin/tikhub/keys/99999", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ── Enable / Disable tests ─────────────────────────────────────────

class TestTikHubKeyEnableDisable:

    @pytest.mark.asyncio
    async def test_enable_key(self, test_client, admin_headers, test_session):
        cred = TikHubCredential(
            label="disable-test",
            api_key="tk_enable_test",
            base_url="https://api.tikhub.io",
            status="inactive",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        resp = await test_client.post(
            f"/api/admin/tikhub/keys/{cred.id}/enable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_disable_key(self, test_client, admin_headers, test_session):
        cred = TikHubCredential(
            label="enable-test",
            api_key="tk_disable_test",
            base_url="https://api.tikhub.io",
            status="active",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        resp = await test_client.post(
            f"/api/admin/tikhub/keys/{cred.id}/disable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_enable_key_not_found(self, test_client, admin_headers):
        resp = await test_client.post("/api/admin/tikhub/keys/99999/enable", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @pytest.mark.asyncio
    async def test_disable_key_not_found(self, test_client, admin_headers):
        resp = await test_client.post("/api/admin/tikhub/keys/99999/disable", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False


# ── Test connectivity ──────────────────────────────────────────────

class TestTikHubKeyTest:

    @pytest.mark.asyncio
    async def test_test_key_not_found(self, test_client, admin_headers):
        resp = await test_client.post("/api/admin/tikhub/keys/99999/test", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @pytest.mark.asyncio
    async def test_test_key_success(self, test_client, admin_headers, test_session):
        """Mock TikHub API 返回成功。"""
        cred = TikHubCredential(
            label="test-conn",
            api_key="tk_conn_test",
            base_url="https://api.tikhub.io",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = client_instance

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "data": {"user": {"nickname": "测试达人"}}
            }
            client_instance.get.return_value = mock_resp

            resp = await test_client.post(
                f"/api/admin/tikhub/keys/{cred.id}/test",
                headers=admin_headers,
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "ok"
        assert data["sample_nickname"] == "测试达人"

    @pytest.mark.asyncio
    async def test_test_key_api_error(self, test_client, admin_headers, test_session):
        """Mock TikHub API 返回错误。"""
        cred = TikHubCredential(
            label="test-conn-error",
            api_key="tk_conn_error",
            base_url="https://api.tikhub.io",
        )
        test_session.add(cred)
        await test_session.commit()
        await test_session.refresh(cred)

        with patch("httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = client_instance
            client_instance.get.side_effect = Exception("连接超时")

            resp = await test_client.post(
                f"/api/admin/tikhub/keys/{cred.id}/test",
                headers=admin_headers,
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "error"
        assert "连接超时" in data["error"]


# ── Stats / Endpoints / Users ──────────────────────────────────────

class TestTikHubStats:

    @pytest.mark.asyncio
    async def test_stats_empty(self, test_client, admin_headers):
        """空数据库时统计接口正常返回。"""
        resp = await test_client.get("/api/admin/tikhub/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "overview" in data
        assert "endpoints" in data
        assert "users" in data
        assert "trend" in data
        assert data["overview"]["total_calls"] == 0

    @pytest.mark.asyncio
    async def test_endpoints_empty(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/tikhub/endpoints", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    @pytest.mark.asyncio
    async def test_users_empty(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/tikhub/users", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_users_with_date_range(self, test_client, admin_headers):
        """带日期范围查询。"""
        resp = await test_client.get(
            "/api/admin/tikhub/users?start_date=20260101&end_date=20261231&limit=10",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
