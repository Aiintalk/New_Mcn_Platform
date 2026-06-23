"""
Integration tests for admin_kols router — 重点覆盖方案 032：
- create_kol INSERT 不覆盖已有红人
- 重复 douyin_id / sec_uid 预检查返回 RESOURCE_ALREADY_EXISTS
- 软删后可重建（部分唯一索引允许 deleted_at IS NOT NULL 的记录共存）
"""
import uuid

import pytest
from sqlalchemy import text

from app.core.response import ErrorCode


pytestmark = pytest.mark.asyncio


async def _cleanup_kols(test_session):
    """每个测试前清理 kols 表，避免残留数据污染。"""
    await test_session.execute(text("DELETE FROM kols"))
    await test_session.commit()


class TestCreateKol:
    async def test_create_success(self, test_client, admin_headers, test_session):
        await _cleanup_kols(test_session)
        resp = await test_client.post(
            "/api/admin/kols",
            json={
                "name": "测试红人A",
                "douyin_id": "test_unique_id_001",
                "sec_uid": "sec_unique_001",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["douyin_id"] == "test_unique_id_001"
        assert data["data"]["id"] > 0

    async def test_create_does_not_overwrite_existing(self, test_client, admin_headers, test_session):
        """验证 create_kol 是 INSERT 不是 UPDATE：新建红人不会改已有红人的字段。"""
        await _cleanup_kols(test_session)
        # 先建一条
        r1 = await test_client.post(
            "/api/admin/kols",
            json={"name": "原红人", "douyin_id": "origin_001", "avatar_url": "https://example.com/a.png"},
            headers=admin_headers,
        )
        assert r1.status_code == 200
        origin_id = r1.json()["data"]["id"]

        # 再建另一条（不同 douyin_id）
        r2 = await test_client.post(
            "/api/admin/kols",
            json={"name": "新红人", "douyin_id": "new_002"},
            headers=admin_headers,
        )
        assert r2.status_code == 200
        new_id = r2.json()["data"]["id"]

        # 原红人字段不变（INSERT 没覆盖）
        assert new_id != origin_id
        r3 = await test_client.get(f"/api/admin/kols/{origin_id}", headers=admin_headers)
        assert r3.status_code == 200
        origin = r3.json()["data"]
        assert origin["name"] == "原红人"
        assert origin["douyin_id"] == "origin_001"
        assert origin["avatar_url"] == "https://example.com/a.png"

    async def test_duplicate_douyin_id_returns_409(self, test_client, admin_headers, test_session):
        """重复 douyin_id 预检查返回 RESOURCE_ALREADY_EXISTS。"""
        await _cleanup_kols(test_session)
        r1 = await test_client.post(
            "/api/admin/kols",
            json={"name": "第一个", "douyin_id": "dup_douyin_001"},
            headers=admin_headers,
        )
        assert r1.status_code == 200

        r2 = await test_client.post(
            "/api/admin/kols",
            json={"name": "第二个", "douyin_id": "dup_douyin_001"},
            headers=admin_headers,
        )
        assert r2.status_code == 200  # error_response 走 200 + success=False
        data = r2.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_ALREADY_EXISTS
        assert "dup_douyin_001" in data["message"]

    async def test_duplicate_sec_uid_returns_409(self, test_client, admin_headers, test_session):
        """重复 sec_uid 预检查返回 RESOURCE_ALREADY_EXISTS。"""
        await _cleanup_kols(test_session)
        r1 = await test_client.post(
            "/api/admin/kols",
            json={"name": "第一个", "sec_uid": "dup_sec_001"},
            headers=admin_headers,
        )
        assert r1.status_code == 200

        r2 = await test_client.post(
            "/api/admin/kols",
            json={"name": "第二个", "sec_uid": "dup_sec_001"},
            headers=admin_headers,
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_ALREADY_EXISTS
        assert "sec_uid" in data["message"]

    async def test_duplicate_after_soft_delete_succeeds(self, test_client, admin_headers, test_session):
        """软删后用相同 douyin_id 可重新创建（部分唯一索引允许）。"""
        await _cleanup_kols(test_session)
        r1 = await test_client.post(
            "/api/admin/kols",
            json={"name": "原红人", "douyin_id": "recyclable_001"},
            headers=admin_headers,
        )
        assert r1.status_code == 200
        kol_id = r1.json()["data"]["id"]

        # 软删
        r_del = await test_client.delete(f"/api/admin/kols/{kol_id}", headers=admin_headers)
        assert r_del.status_code == 200

        # 相同 douyin_id 可重建
        r2 = await test_client.post(
            "/api/admin/kols",
            json={"name": "新红人", "douyin_id": "recyclable_001"},
            headers=admin_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["success"] is True
        assert r2.json()["data"]["id"] != kol_id  # 是新记录

    async def test_create_multiple_without_douyin_id_succeeds(
        self, test_client, admin_headers, test_session
    ):
        """douyin_id 和 sec_uid 都为空时，可多次创建（不触发唯一约束）。"""
        await _cleanup_kols(test_session)
        for i in range(3):
            r = await test_client.post(
                "/api/admin/kols",
                json={"name": f"无ID红人{i}", "douyin_id": None, "sec_uid": None},
                headers=admin_headers,
            )
            assert r.status_code == 200
            assert r.json()["success"] is True

    async def test_create_requires_admin(self, test_client, operator_headers, test_session):
        await _cleanup_kols(test_session)
        resp = await test_client.post(
            "/api/admin/kols",
            json={"name": "运营建的", "douyin_id": "operator_try_001"},
            headers=operator_headers,
        )
        assert resp.status_code == 403
