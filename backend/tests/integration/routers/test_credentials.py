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

    @pytest.mark.asyncio
    async def test_update_credential_api_key_rotates_secret(
        self, test_client, admin_headers, admin_user
    ):
        """PATCH 带 api_key 时应同步更新 secret_enc 和 secret_tail（支持密钥轮换）."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Secret Rotation",
                "api_key": "sk-original-1234",
            },
            headers=admin_headers,
        )
        assert create_resp.status_code == 200
        cred_id = create_resp.json()["data"]["id"]
        assert create_resp.json()["data"]["secret_tail"] == "1234"

        resp = await test_client.patch(
            "/api/admin/config/credentials/" + str(cred_id),
            json={"api_key": "sk-rotated-5678"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # secret_tail 应反映新的 api_key 末 4 位
        assert data["data"]["secret_tail"] == "5678"
        # secret_enc 不应在响应中暴露
        assert "secret_enc" not in data["data"]

    @pytest.mark.asyncio
    async def test_update_credential_without_api_key_keeps_secret(
        self, test_client, admin_headers, admin_user
    ):
        """PATCH 不带 api_key 时不应改动 secret."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Keep Secret",
                "api_key": "sk-unchanged-9012",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.patch(
            "/api/admin/config/credentials/" + str(cred_id),
            json={"label": "Relabeled"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["label"] == "Relabeled"
        # secret_tail 保持原值
        assert data["data"]["secret_tail"] == "9012"

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


class TestTestCredential:
    """POST /api/admin/config/credentials/{credential_id}/test — OSS 凭证连通性测试"""

    @pytest.mark.asyncio
    async def test_test_credential_oss_ok(
        self, test_client, admin_headers, admin_user, monkeypatch
    ):
        """正常路径：mock _make_bucket，返回 status=ok + bucket info."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "oss",
                "label": "OSS OK",
                "api_key": "test-secret-1234",
                "config": {
                    "access_key_id": "LTAI1234",
                    "bucket": "test-bucket",
                    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
                },
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        class FakeBucketInfo:
            name = "test-bucket"
            location = "oss-cn-hangzhou"
            creation_date = "2024-01-01"

        class FakeBucket:
            def get_bucket_info(self):
                return FakeBucketInfo()

        from app.routers import admin_credentials
        monkeypatch.setattr(
            admin_credentials, "_make_bucket", lambda *a, **kw: FakeBucket()
        )

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "ok"
        assert data["data"]["bucket"] == "test-bucket"
        assert "latency_ms" in data["data"]
        assert "secret_enc" not in str(data["data"])

    @pytest.mark.asyncio
    async def test_test_credential_not_found(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/config/credentials/999999/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_test_credential_wrong_provider(
        self, test_client, admin_headers, admin_user
    ):
        """provider 非 oss 时拒绝（当前只支持 OSS 测试）."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "openai",
                "label": "Not OSS",
                "api_key": "sk-not-oss-1234",
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_test_credential_missing_config(
        self, test_client, admin_headers, admin_user
    ):
        """provider=oss 但 config 缺 access_key_id/bucket/endpoint."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "oss",
                "label": "Bad Config",
                "api_key": "test-bad-config-1234",
                "config": {},
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_test_credential_oss_failure(
        self, test_client, admin_headers, admin_user, monkeypatch
    ):
        """mock _make_bucket 抛异常 → status=error（仍走 success 信封）."""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "oss",
                "label": "OSS Fail",
                "api_key": "test-fail-1234",
                "config": {
                    "access_key_id": "LTAI1234",
                    "bucket": "fail-bucket",
                    "endpoint": "oss-cn-hangzhou.aliyuncs.com",
                },
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        from app.routers import admin_credentials

        def fake_make_bucket(*a, **kw):
            raise RuntimeError("OSS auth failed")

        monkeypatch.setattr(admin_credentials, "_make_bucket", fake_make_bucket)

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "error"
        assert "OSS auth failed" in data["data"]["error"]
        assert "latency_ms" in data["data"]

    @pytest.mark.asyncio
    async def test_test_credential_requires_admin(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/config/credentials/1/test",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    # ── ASR 测试端点（provider=asr）──────────────────────────────────

    @pytest.mark.asyncio
    async def test_test_credential_asr_ok(
        self, test_client, admin_headers, admin_user, monkeypatch
    ):
        """ASR 正常路径：mock _make_asr_client，GetTaskResult 返回业务错误也算连通 OK。"""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "asr",
                "label": "ASR OK",
                "api_key": "LTAI1234\nSECRET1234",
                "config": {
                    "app_key": "testappkey",
                    "region": "cn-shanghai",
                },
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        import json as _json

        class FakeClient:
            def do_action_with_exception(self, req):
                # 阿里云对测试 TaskId 通常返回 41050010 TASK_EXPIRED
                # 但只要返回 JSON 响应（非认证异常），说明凭证 OK
                return _json.dumps({
                    "StatusCode": 41050010,
                    "StatusText": "FILE_TRANS_TASK_EXPIRED",
                }).encode("utf-8")

        from app.routers import admin_credentials
        monkeypatch.setattr(
            admin_credentials, "_make_asr_client", lambda *a, **kw: FakeClient()
        )

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "ok"
        assert data["data"]["status_text"] == "FILE_TRANS_TASK_EXPIRED"
        assert "latency_ms" in data["data"]
        assert "secret_enc" not in str(data["data"])

    @pytest.mark.asyncio
    async def test_test_credential_asr_failure(
        self, test_client, admin_headers, admin_user, monkeypatch
    ):
        """ASR 凭证错误：_make_asr_client 抛异常 → status=error。"""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "asr",
                "label": "ASR Fail",
                "api_key": "bad_ak\nbad_sk",
                "config": {"app_key": "appkey", "region": "cn-shanghai"},
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        from app.routers import admin_credentials

        def fake_client(*a, **kw):
            raise RuntimeError("InvalidAccessKeyId")

        monkeypatch.setattr(admin_credentials, "_make_asr_client", fake_client)

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "error"
        assert "InvalidAccessKeyId" in data["data"]["error"]

    @pytest.mark.asyncio
    async def test_test_credential_asr_missing_app_key(
        self, test_client, admin_headers, admin_user
    ):
        """provider=asr 但 config 缺 app_key → VALIDATION_ERROR。"""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "asr",
                "label": "Bad ASR",
                "api_key": "LTAI\nSECRET",
                "config": {},
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_test_credential_asr_invalid_secret_format(
        self, test_client, admin_headers, admin_user
    ):
        """provider=asr 但 secret_enc 不含 \\n → VALIDATION_ERROR。"""
        create_resp = await test_client.post(
            "/api/admin/config/credentials",
            json={
                "provider": "asr",
                "label": "Bad Secret",
                "api_key": "only-one-line",
                "config": {"app_key": "appkey"},
            },
            headers=admin_headers,
        )
        cred_id = create_resp.json()["data"]["id"]

        resp = await test_client.post(
            f"/api/admin/config/credentials/{cred_id}/test",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

