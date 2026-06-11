"""
Integration tests for admin credentials router - CRUD and enable/disable.
"""
import pytest

from app.core.response import ErrorCode


class TestListCredentials:
    """GET /api/admin/config/credentials"""

    @pytest.mark.asyncio
    async def test_list_credentials_returns_paginated(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.get(
            "/api/admin/config/credentials", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "pagination" in data["data"]

    @pytest.mark.asyncio
    async def test_list_credentials_filter_by_provider(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.get(
            "/api/admin/config/credentials?provider=openai", headers=admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for item in data["data"]["items"]:
            assert item["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_list_credentials_requires_admin(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/config/credentials", headers=operator_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_credentials_requires_auth(self, test_client):
        resp = await test_client.get("/api/admin/config/credentials")
        assert resp.status_code == 401


class TestCreateCredential:
    """POST /api/admin/config/credentials"""

    @pytest.mark.asyncio
    async def test_create_credential_success(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Test Key",
                "api_key": "sk-1234567890abcdef",
                "weight": 2,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["provider"] == "openai"
        assert data["data"]["label"] == "Test Key"
        assert data["data"]["secret_tail"] == "cdef"  # API returns last 4 chars
        assert data["data"]["weight"] == 2
        assert data["data"]["status"] == "enabled"
        assert "secret_enc" not in data["data"]

    @pytest.mark.asyncio
    async def test_create_credential_with_optional_fields(
        self, test_client, admin_headers, admin_user
    ):
        resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "anthropic",
                "label": "Claude Key",
                "api_key": "sk-ant-short",
                "weight": 1,
                "quota_limit": 10000,
                "config": {"model": "claude-3"},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["quota_limit"] == 10000
        assert data["data"]["config"] == {"model": "claude-3"}
        assert data["data"]["secret_tail"] == "hort"  # API returns last 4 chars

    @pytest.mark.asyncio
    async def test_create_credential_requires_admin(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Hacker Key",
                "api_key": "sk-bad",
            },
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_credential_requires_auth(self, test_client):
        resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "No Auth Key",
                "api_key": "sk-noauth",
            },
        )
        assert resp.status_code == 401

class TestUpdateCredential:
    """PATCH /api/admin/config/credentials/{credential_id}"""

    @pytest.mark.asyncio
    async def test_update_credential_label(
        self, test_client, admin_headers, admin_user
    ):
        # Create first
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Original Label",
                "api_key": "sk-update-test-key",
            },
            headers=admin_headers,
        )
        assert create_resp.status_code == 200
        cred_id = create_resp.json()["data"]["id"]

        # Update label
        resp = await test_client.patch(
            "/api/admin/config/credentials/" + str(cred_id),
            json={"label": "Updated Label"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["label"] == "Updated Label"

    @pytest.mark.asyncio
    async def test_update_credential_weight_and_quota(
        self, test_client, admin_headers, admin_user
    ):
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Weight Test",
                "api_key": "sk-weight-test-key",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.patch(
            "/api/admin/config/credentials/" + str(cred_id),
            json={"weight": 10, "quota_limit": 5000},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["weight"] == 10
        assert data["data"]["quota_limit"] == 5000

    @pytest.mark.asyncio
    async def test_update_nonexistent_credential_returns_not_found(
        self, test_client, admin_headers
    ):
        resp = await test_client.patch(
            "/api/admin/config/credentials/999999",
            json={"label": "Ghost"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_credential_requires_admin(self, test_client, operator_headers):
        resp = await test_client.patch(
            "/api/admin/config/credentials/1",
            json={"label": "Hack"},
            headers=operator_headers,
        )
        assert resp.status_code == 403

class TestDeleteCredential:
    """DELETE /api/admin/config/credentials/{credential_id}"""

    @pytest.mark.asyncio
    async def test_delete_credential_success(
        self, test_client, admin_headers, admin_user
    ):
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "To Delete",
                "api_key": "sk-delete-test-key",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.delete(
            "/api/admin/config/credentials/" + str(cred_id),
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_delete_nonexistent_credential_returns_not_found(
        self, test_client, admin_headers
    ):
        resp = await test_client.delete(
            "/api/admin/config/credentials/999999",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_credential_requires_admin(
        self, test_client, operator_headers
    ):
        resp = await test_client.delete(
            "/api/admin/config/credentials/1",
            headers=operator_headers,
        )
        assert resp.status_code == 403


class TestEnableDisableCredential:
    """POST .../enable and .../disable"""

    @pytest.mark.asyncio
    async def test_enable_credential(
        self, test_client, admin_headers, admin_user
    ):
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Enable Test",
                "api_key": "sk-enable-test-key",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        # Disable first
        await test_client.post(
            "/api/admin/config/credentials/" + str(cred_id) + "/disable",
            headers=admin_headers,
        )

        # Then enable
        resp = await test_client.post(
            "/api/admin/config/credentials/" + str(cred_id) + "/enable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "enabled"

    @pytest.mark.asyncio
    async def test_disable_credential(
        self, test_client, admin_headers, admin_user
    ):
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Disable Test",
                "api_key": "sk-disable-test-key",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.post(
            "/api/admin/config/credentials/" + str(cred_id) + "/disable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_enable_nonexistent_credential_returns_not_found(
        self, test_client, admin_headers
    ):
        resp = await test_client.post(
            "/api/admin/config/credentials/999999/enable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_disable_nonexistent_credential_returns_not_found(
        self, test_client, admin_headers
    ):
        resp = await test_client.post(
            "/api/admin/config/credentials/999999/disable",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_enable_requires_admin(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/config/credentials/1/enable",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_disable_requires_admin(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/config/credentials/1/disable",
            headers=operator_headers,
        )
        assert resp.status_code == 403
