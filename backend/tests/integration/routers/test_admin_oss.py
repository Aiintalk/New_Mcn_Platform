"""
Integration tests for admin OSS statistics router (app/routers/admin_oss.py).

覆盖 3 个接口：
  GET /api/admin/oss/stats       — 三维统计（overview + operations + users + trend）
  GET /api/admin/oss/operations  — 按 operation 聚合
  GET /api/admin/oss/users       — 按用户聚合

参照 tests/integration/routers/test_admin_tikhub.py。

注意：test_session 不做 per-test rollback（只 session 级 create_all/drop_all），
所以数据会在一个测试类内累积。对"有数据"的断言用 >= 而非 ==；对"空表"用响应结构校验。
"""
import uuid

import pytest

from app.models.oss_call_log import OssCallLog
from app.models.credential import ServiceCredential


# ── Auth tests ─────────────────────────────────────────────────────

class TestAdminOssAuth:
    """所有 admin oss 接口未授权返回 401，非 admin 返回 403。"""

    @pytest.mark.asyncio
    async def test_unauthorized_stats(self, test_client):
        resp = await test_client.get("/api/admin/oss/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_operations(self, test_client):
        resp = await test_client.get("/api/admin/oss/operations")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_users(self, test_client):
        resp = await test_client.get("/api/admin/oss/users")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_operator_forbidden(self, test_client, operator_headers):
        """operator 角色无权访问 admin 接口。"""
        resp = await test_client.get("/api/admin/oss/stats", headers=operator_headers)
        assert resp.status_code == 403


# ── Stats tests ────────────────────────────────────────────────────

class TestOssStats:
    """GET /api/admin/oss/stats 三维统计。"""

    @pytest.mark.asyncio
    async def test_stats_shape(self, test_client, admin_headers):
        """响应结构正确（不依赖是否为空）。"""
        resp = await test_client.get("/api/admin/oss/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # overview 四字段
        assert "total_calls" in data["overview"]
        assert "today_calls" in data["overview"]
        assert "avg_latency_ms" in data["overview"]
        assert "active_keys" in data["overview"]
        assert "total_keys" in data["overview"]
        # 三个数组字段
        assert isinstance(data["operations"], list)
        assert isinstance(data["users"], list)
        assert isinstance(data["trend"], list)

    @pytest.mark.asyncio
    async def test_stats_with_data(self, test_client, admin_headers, admin_user, test_session):
        """插入若干 oss_call_logs，验证聚合正确。"""
        unique_tag = uuid.uuid4().hex[:8]
        cred = ServiceCredential(
            provider="oss",
            label=f"test-cred-{unique_tag}",
            secret_enc="test-secret",
            secret_tail="1234",
            weight=10,
            status="enabled",
            config={"access_key_id": "LTAItest", "bucket": "test", "endpoint": "oss-cn-hangzhou"},
            created_by=int(admin_user.id),
        )
        test_session.add(cred)
        await test_session.flush()

        # 插入 3 条 upload + 1 条 download 日志（都归属 admin_user）
        for _ in range(3):
            test_session.add(OssCallLog(
                credential_id=cred.id,
                user_id=int(admin_user.id),
                operation="upload",
                status="success",
                latency_ms=100,
                oss_key=f"uploads/{admin_user.id}/20260101/abc.txt",
            ))
        test_session.add(OssCallLog(
            credential_id=cred.id,
            user_id=int(admin_user.id),
            operation="download",
            status="success",
            latency_ms=80,
            oss_key=f"uploads/{admin_user.id}/20260101/abc.txt",
        ))
        await test_session.commit()

        resp = await test_client.get("/api/admin/oss/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]

        # overview total_calls 至少包含我们刚插入的 4 条
        assert data["overview"]["total_calls"] >= 4
        # active_keys 至少 1（我们刚创建的 enabled 凭证）
        assert data["overview"]["active_keys"] >= 1

        # operations 应包含 upload + download
        ops = {o["operation"]: o for o in data["operations"]}
        assert "upload" in ops
        assert "download" in ops
        assert ops["upload"]["calls"] >= 3

        # users 应包含当前 admin_user
        user_ids = [u["user_id"] for u in data["users"]]
        assert int(admin_user.id) in user_ids


# ── Operations tests ───────────────────────────────────────────────

class TestOssOperations:
    """GET /api/admin/oss/operations 按 operation 聚合。"""

    @pytest.mark.asyncio
    async def test_operations_shape(self, test_client, admin_headers):
        """响应结构正确。"""
        resp = await test_client.get("/api/admin/oss/operations", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        # 若有数据，每项应有这些字段
        for op in data:
            assert "operation" in op
            assert "calls" in op
            assert "percentage" in op
            assert "avg_latency_ms" in op
            assert "success_rate" in op

    @pytest.mark.asyncio
    async def test_operations_with_data(self, test_client, admin_headers, admin_user, test_session):
        """插入混合 success/fail 日志，验证 success_rate。"""
        unique_tag = uuid.uuid4().hex[:8]
        cred = ServiceCredential(
            provider="oss",
            label=f"op-test-{unique_tag}",
            secret_enc="s",
            secret_tail="1234",
            weight=10,
            status="enabled",
            config={"access_key_id": "LTAI", "bucket": "b", "endpoint": "e"},
            created_by=int(admin_user.id),
        )
        test_session.add(cred)
        await test_session.flush()

        # 3 成功 + 1 失败（同一凭证，会产生 success_rate=0.75）
        for _ in range(3):
            test_session.add(OssCallLog(
                credential_id=cred.id, user_id=int(admin_user.id), operation="delete",
                status="success", latency_ms=100, oss_key="k",
            ))
        test_session.add(OssCallLog(
            credential_id=cred.id, user_id=int(admin_user.id), operation="delete",
            status="fail", latency_ms=200, oss_key="k2", error_message="boom",
        ))
        await test_session.commit()

        resp = await test_client.get("/api/admin/oss/operations", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 应该至少包含 delete
        ops = {o["operation"]: o for o in data}
        assert "delete" in ops
        # success_rate 是 0-1 之间
        assert 0 <= ops["delete"]["success_rate"] <= 1


# ── Users tests ────────────────────────────────────────────────────

class TestOssUsers:
    """GET /api/admin/oss/users 用户排行。"""

    @pytest.mark.asyncio
    async def test_users_shape(self, test_client, admin_headers):
        """响应结构正确（支持 limit 过滤）。"""
        resp = await test_client.get("/api/admin/oss/users?limit=5", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_users_with_data(self, test_client, admin_headers, admin_user, test_session):
        """插入 5 条日志，验证 admin_user 出现在排行中。"""
        unique_tag = uuid.uuid4().hex[:8]
        cred = ServiceCredential(
            provider="oss",
            label=f"users-test-{unique_tag}",
            secret_enc="s",
            secret_tail="1234",
            weight=10,
            status="enabled",
            config={"access_key_id": "LTAI", "bucket": "b", "endpoint": "e"},
            created_by=int(admin_user.id),
        )
        test_session.add(cred)
        await test_session.flush()

        for _ in range(5):
            test_session.add(OssCallLog(
                credential_id=cred.id, user_id=int(admin_user.id), operation="upload",
                status="success", latency_ms=100, oss_key="k",
            ))
        await test_session.commit()

        # limit=100 保证能看到
        resp = await test_client.get(
            "/api/admin/oss/users?limit=100", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        user_ids = [u["user_id"] for u in data["items"]]
        assert int(admin_user.id) in user_ids
        # 找到 admin_user 那条
        admin_entry = next(u for u in data["items"] if u["user_id"] == int(admin_user.id))
        assert admin_entry["calls"] >= 5
