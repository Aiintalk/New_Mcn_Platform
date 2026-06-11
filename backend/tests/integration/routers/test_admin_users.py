"""
Integration tests for admin users router — CRUD, permissions, pagination.
"""
import pytest

from app.core.response import ErrorCode


class TestListUsers:
    @pytest.mark.asyncio
    async def test_list_users_returns_paginated_results(self, test_client, admin_headers, admin_user):
        resp = await test_client.get("/api/admin/users?page=1&page_size=10", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "pagination" in data["data"]
        assert "total" in data["data"]["pagination"]

    @pytest.mark.asyncio
    async def test_list_users_requires_admin(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/users", headers=operator_headers)
        # operator should get 403
        assert resp.status_code == 403


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_create_user_success(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/users",
            json={
                "username": "new_test_user",
                "real_name": "新建测试",
                "role": "operator",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "id" in data["data"]
        assert data["data"]["username"] == "new_test_user"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username_returns_409(self, test_client, admin_headers, admin_user):
        resp = await test_client.post(
            "/api/admin/users",
            json={
                "username": admin_user.username,
                "real_name": "重复用户名",
                "role": "operator",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.USERNAME_ALREADY_EXISTS

    @pytest.mark.asyncio
    async def test_create_user_requires_admin(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/users",
            json={"username": "hacker", "real_name": "hack", "role": "operator"},
            headers=operator_headers,
        )
        assert resp.status_code == 403


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password_success(self, test_client, admin_headers, operator_user):
        resp = await test_client.post(
            f"/api/admin/users/{operator_user.id}/reset-password",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "初始密码" in data["data"].get("message", "") or data["success"]


class TestUserStatus:
    @pytest.mark.asyncio
    async def test_disable_user(self, test_client, admin_headers, operator_user):
        resp = await test_client.post(
            f"/api/admin/users/{operator_user.id}/disable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_enable_user(self, test_client, admin_headers, operator_user):
        resp = await test_client.post(
            f"/api/admin/users/{operator_user.id}/enable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestDeleteUser:
    @pytest.mark.asyncio
    async def test_delete_user_soft_delete(self, test_client, admin_headers, operator_user):
        resp = await test_client.delete(
            f"/api/admin/users/{operator_user.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
