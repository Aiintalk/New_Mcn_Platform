"""
Integration tests for admin_logs.py router.

Covers:
- GET /admin/logs/operation — 操作日志分页 + 筛选
- GET /admin/logs/external — 外部服务日志分页 + 筛选
- page_size 校验
- Auth: 401 / 403
"""
import pytest
from sqlalchemy import text


class TestAdminLogs:
    @pytest.mark.asyncio
    async def test_operation_logs_admin_ok(self, test_client, admin_headers, test_session):
        """GET /admin/logs/operation → 200 + 分页结构。"""
        resp = await test_client.get(
            "/api/admin/logs/operation",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        data = body["data"]
        assert "items" in data
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_operation_logs_filter_by_action(self, test_client, admin_headers, test_session):
        """?action=xxx → 只返回该 action 的日志。"""
        # 先 seed 一条日志（如果有 trigger_run 测试产生的日志更好，这里用直查验证过滤生效）
        resp = await test_client.get(
            "/api/admin/logs/operation?action=nonexistent_action_xyz",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["pagination"]["total"] == 0  # 不存在的 action → 0 条

    @pytest.mark.asyncio
    async def test_operation_logs_page_size_clamp(self, test_client, admin_headers):
        """非法 page_size → 回退 20。"""
        resp = await test_client.get(
            "/api/admin/logs/operation?page_size=99",
            headers=admin_headers,
        )
        assert resp.json()["data"]["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_external_logs_admin_ok(self, test_client, admin_headers):
        """GET /admin/logs/external → 200 + 分页结构。"""
        resp = await test_client.get(
            "/api/admin/logs/external",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert "items" in body["data"]
        assert "pagination" in body["data"]

    @pytest.mark.asyncio
    async def test_external_logs_filter_by_service(self, test_client, admin_headers):
        """?service=xxx → 过滤。"""
        resp = await test_client.get(
            "/api/admin/logs/external?service=nonexistent_service_xyz",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_operation_logs_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/logs/operation")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operation_logs_operator_403(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/logs/operation",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_external_logs_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/logs/external")
        assert resp.status_code == 401
