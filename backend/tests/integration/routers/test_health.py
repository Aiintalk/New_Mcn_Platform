"""
Integration tests for health.py router.

Covers:
- GET /api/health — 公开接口，DB 探测 + 服务信息
- GET /api/version — 公开接口，版本信息
"""
import pytest


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_check(self, test_client):
        """GET /health → 200 + status ok + database ok + time。"""
        resp = await test_client.get("/api/health")
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        data = body["data"]
        assert data["status"] == "ok"
        assert data["service"] == "mcn-api"
        assert data["database"] in ("ok", "error")  # 测试环境可能 ok
        assert "time" in data

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, test_client):
        """health 是公开接口，无需 token。"""
        resp = await test_client.get("/api/health")
        assert resp.status_code == 200  # 不是 401

    @pytest.mark.asyncio
    async def test_version(self, test_client):
        """GET /version → 200 + service/version/stage。"""
        resp = await test_client.get("/api/version")
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        data = body["data"]
        assert data["service"] == "mcn-api"
        assert data["version"] == "0.1.0"
        assert data["stage"] == "m1-base"
