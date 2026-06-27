"""
Integration tests for admin_subtitle router — Sprint 19

Covers:
- Auth (4 scenarios: no token / operator forbidden / admin OK / invalid token)
- GET /configs (returns default config)
- PUT /configs (update prompt + is_active + no-fields)
- GET /batches (admin list all + filter by user_id + cross-user visibility)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

import pytest
from passlib.context import CryptContext
from sqlalchemy import text

from app.core.security import create_access_token
from app.models.user import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(autouse=True)
async def ensure_subtitle_config(test_session):
    await test_session.execute(text(
        "INSERT INTO subtitle_configs "
        "(config_key, mindmap_prompt, mindmap_model_id, is_active) "
        "VALUES ('default', :prompt, NULL, true) "
        "ON CONFLICT (config_key) DO UPDATE SET "
        "mindmap_prompt = EXCLUDED.mindmap_prompt, is_active = true"
    ), {"prompt": "测试 prompt {{transcript}}"})
    await test_session.commit()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_configs_no_token(self, test_client):
        resp = await test_client.get("/api/admin/subtitle/configs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_configs_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_configs_admin_ok(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=admin_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_configs_invalid_token(self, test_client):
        resp = await test_client.get(
            "/api/admin/subtitle/configs",
            headers={"Authorization": "Bearer invalid_token_xxx"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /configs
# ---------------------------------------------------------------------------

class TestGetConfigs:
    @pytest.mark.asyncio
    async def test_returns_default_config(self, test_client, admin_headers):
        resp = await test_client.get("/api/admin/subtitle/configs",
                                     headers=admin_headers)
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert len(data) >= 1
        default = next((c for c in data if c["config_key"] == "default"), None)
        assert default is not None
        assert "{{transcript}}" in default["mindmap_prompt"]
        assert default["is_active"] is True


# ---------------------------------------------------------------------------
# PUT /configs
# ---------------------------------------------------------------------------

class TestUpdateConfigs:
    @pytest.mark.asyncio
    async def test_update_prompt(self, test_client, admin_headers, test_session):
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={"mindmap_prompt": "新的 prompt {{transcript}}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["mindmap_prompt"] == "新的 prompt {{transcript}}"

        # OperationLog 写入
        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs WHERE action = 'admin_subtitle_config_update'"
        ))).scalar()
        assert log_count == 1

    @pytest.mark.asyncio
    async def test_update_is_active(self, test_client, admin_headers):
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_no_fields(self, test_client, admin_headers):
        """无字段更新 → 200 + changes 空"""
        resp = await test_client.put(
            "/api/admin/subtitle/configs",
            headers=admin_headers,
            json={},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /admin/subtitle/batches — admin 查全部批量任务
# ---------------------------------------------------------------------------

class TestAdminBatches:
    @pytest.mark.asyncio
    async def test_admin_list_all_batches(
        self, test_client, admin_headers, operator_headers, test_session
    ):
        """admin 看全部跨用户的批量任务，响应含 created_by_username"""
        # operator 创建 1 个
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/adm1/"}]},
            )

        resp = await test_client.get(
            "/api/admin/subtitle/batches",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["pagination"]["total"] >= 1
        # admin 列表必须含 username 字段
        assert all("created_by_username" in it for it in body["items"])

    @pytest.mark.asyncio
    async def test_admin_list_filter_by_user(
        self, test_client, admin_headers, operator_headers, operator_user, test_session
    ):
        """user_id 过滤只返回该用户的任务"""
        with patch(
            "app.routers.operator_subtitle._run_batch",
            AsyncMock(return_value=None),
        ):
            await test_client.post(
                "/api/tools/subtitle/batch",
                headers=operator_headers,
                json={"items": [{"share_text": "https://v.douyin.com/f1/"}]},
            )

        # 用 operator_user.id 过滤
        resp = await test_client.get(
            f"/api/admin/subtitle/batches?user_id={operator_user.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["pagination"]["total"] >= 1
        assert all(it["created_by"] == operator_user.id for it in body["items"])

    @pytest.mark.asyncio
    async def test_admin_batches_operator_forbidden(self, test_client, operator_headers):
        """operator 访问 admin 端点 → 403"""
        resp = await test_client.get(
            "/api/admin/subtitle/batches",
            headers=operator_headers,
        )
        assert resp.status_code == 403
