"""
Integration tests for admin_system.py router.

Covers:
- POST /admin/system/ai-test — admin only，mock ai_adapter
- POST /admin/system/tikhub-test — admin only，mock tikhub_adapter
- Auth: 401 / 403
"""
from unittest.mock import AsyncMock, patch

import pytest


class TestAdminSystem:
    @pytest.mark.asyncio
    async def test_ai_test_admin_ok(self, test_client, admin_headers):
        """POST /admin/system/ai-test → 200（mock adapter 返回连通结果）。"""
        mock_result = {"model": "test-model", "latency_ms": 150, "response": "ok"}
        with patch(
            "app.adapters.ai.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await test_client.post(
                "/api/admin/system/ai-test",
                headers=admin_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_tikhub_test_admin_ok(self, test_client, admin_headers):
        """POST /admin/system/tikhub-test → 200（mock adapter 返回连通结果）。"""
        mock_result = {"status": "ok", "latency_ms": 80}
        with patch(
            "app.adapters.tikhub.test_connection",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await test_client.post(
                "/api/admin/system/tikhub-test",
                headers=admin_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_ai_test_no_token_401(self, test_client):
        resp = await test_client.post("/api/admin/system/ai-test")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_ai_test_operator_403(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/system/ai-test",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tikhub_test_no_token_401(self, test_client):
        resp = await test_client.post("/api/admin/system/tikhub-test")
        assert resp.status_code == 401
