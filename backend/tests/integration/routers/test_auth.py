"""
Integration tests for auth router — tests full request/response cycle
using FastAPI TestClient + test database.
"""
import pytest

from app.core.response import ErrorCode


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_operator_credentials_returns_token(
        self, test_client, operator_user,
    ):
        resp = await test_client.post(
            "/api/auth/login",
            json={"username": operator_user.username, "password": "Test@123456"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["user"]["role"] == "operator"
        assert data["data"]["access_token"]

    @pytest.mark.asyncio
    async def test_login_valid_credentials_returns_token(self, test_client, admin_user):
        resp = await test_client.post(
            "/api/auth/login",
            json={"username": admin_user.username, "password": "Test@123456"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_invalid_password_returns_error(self, test_client, admin_user):
        resp = await test_client.post(
            "/api/auth/login",
            json={"username": admin_user.username, "password": "wrong_password"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.AUTH_INVALID_PASSWORD

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_returns_error(self, test_client):
        resp = await test_client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "anything"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.AUTH_INVALID_PASSWORD


class TestMe:
    @pytest.mark.asyncio
    async def test_me_with_valid_token_returns_user_info(self, test_client, admin_headers, admin_user):
        resp = await test_client.get("/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["username"] == admin_user.username
        assert data["data"]["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self, test_client):
        resp = await test_client.get("/api/auth/me")
        assert resp.status_code == 401


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_mismatch_confirm(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/auth/change-password",
            json={
                "old_password": "Test@123456",
                "new_password": "NewPass@999",
                "confirm_password": "DifferentPass@888",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/auth/change-password",
            json={
                "old_password": "WrongOldPass@123",
                "new_password": "NewPass@999",
                "confirm_password": "NewPass@999",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.AUTH_INVALID_PASSWORD


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self, test_client, admin_headers):
        resp = await test_client.post("/api/auth/logout", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # API returns "已退出登录"
        assert data["message"] is not None

    @pytest.mark.asyncio
    async def test_logout_without_token_returns_401(self, test_client):
        resp = await test_client.post("/api/auth/logout")
        assert resp.status_code == 401
