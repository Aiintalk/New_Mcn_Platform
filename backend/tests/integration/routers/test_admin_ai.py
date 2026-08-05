"""
Integration tests for admin_ai.py router.

Covers 11 endpoints under /api/admin/ai:
- Keys:   GET/POST/PATCH/DELETE /keys, POST /keys/{id}/test
- Models: GET/POST/PATCH/DELETE /models, POST /models/{id}/test
- Stats:  GET /stats

Auth: require_admin → 401 (no token) / 403 (operator).

Response envelope conventions for this router:
- success_response → HTTP 200 + body.success=true
- error_response   → HTTP 200 + body.success=false + body.code (NOT a real HTTP error code)
  • not-found (PATCH/DELETE/test on missing key/model) → code=RESOURCE_NOT_FOUND
  • duplicate model_id on POST /models               → code=VALIDATION_ERROR
- HTTPException (auth middleware) → real HTTP status (401/403)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.credential import AiModel, Credential


class TestAdminAiKeys:
    """GET/POST/PATCH/DELETE /keys + POST /keys/{id}/test."""

    # ------------------------------------------------------------------
    # GET /keys
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_list_keys_admin_ok(self, test_client, admin_headers, test_session):
        """GET /keys → 200 + data.items 结构。"""
        # seed 一个 Credential 让列表非空
        c = Credential(
            provider="yunwu",
            label="cov-list",
            api_key="sk-cov-list",
            base_url="https://yunwu.ai/v1",
        )
        test_session.add(c)
        await test_session.commit()

        resp = await test_client.get("/api/admin/ai/keys", headers=admin_headers)
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"]["items"], list)
        # 结构断言：至少含我们 seed 的那条，且必要字段齐全
        assert any(it["label"] == "cov-list" for it in body["data"]["items"])
        sample = body["data"]["items"][0]
        for k in (
            "id", "provider", "label", "api_key", "base_url", "status",
            "active_requests", "max_concurrent", "max_users",
            "today_calls", "created_at", "updated_at",
        ):
            assert k in sample

    @pytest.mark.asyncio
    async def test_list_keys_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/ai/keys")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_keys_operator_forbidden_403(self, test_client, operator_headers):
        resp = await test_client.get("/api/admin/ai/keys", headers=operator_headers)
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # POST /keys
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_key_ok(self, test_client, admin_headers):
        """POST /keys → 200 + success + _cred_to_dict 结构。"""
        resp = await test_client.post(
            "/api/admin/ai/keys",
            headers=admin_headers,
            json={
                "provider": "yunwu",
                "label": "cov-create",
                "api_key": "sk-cov-create",
                "base_url": "https://yunwu.ai/v1",
                "max_concurrent": 8,
                "max_users": 20,
            },
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["message"] == "Key 添加成功"
        data = body["data"]
        assert data["provider"] == "yunwu"
        assert data["label"] == "cov-create"
        assert data["api_key"] == "sk-cov-create"
        assert data["base_url"] == "https://yunwu.ai/v1"
        assert data["max_concurrent"] == 8
        assert data["max_users"] == 20
        assert data["status"] == "active"
        assert data["id"] > 0

    @pytest.mark.asyncio
    async def test_create_key_uses_default_base_url(self, test_client, admin_headers):
        """不传 base_url → 使用 _DEFAULT_BASE_URLS[provider]。"""
        resp = await test_client.post(
            "/api/admin/ai/keys",
            headers=admin_headers,
            json={"provider": "glm", "label": "cov-glm", "api_key": "sk-glm"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["base_url"] == "https://open.bigmodel.cn/api/paas/v4"

    @pytest.mark.asyncio
    async def test_create_key_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/admin/ai/keys",
            json={"api_key": "sk-x"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_key_operator_forbidden_403(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/admin/ai/keys",
            headers=operator_headers,
            json={"api_key": "sk-x"},
        )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # PATCH /keys/{id}
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_key_ok(self, test_client, admin_headers, test_session):
        """seed 一个 key → PATCH 改 label/status → 200 + 字段已变。"""
        c = Credential(provider="yunwu", label="cov-upd", api_key="sk-upd")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        resp = await test_client.patch(
            f"/api/admin/ai/keys/{c.id}",
            headers=admin_headers,
            json={"label": "cov-upd-new", "status": "disabled", "max_concurrent": 10},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["label"] == "cov-upd-new"
        assert body["data"]["status"] == "disabled"
        assert body["data"]["max_concurrent"] == 10

    @pytest.mark.asyncio
    async def test_update_key_not_found(self, test_client, admin_headers):
        """PATCH 不存在的 key → 200 + success=false + code=RESOURCE_NOT_FOUND。"""
        resp = await test_client.patch(
            "/api/admin/ai/keys/999999",
            headers=admin_headers,
            json={"label": "whatever"},
        )
        body = resp.json()
        assert resp.status_code == 200  # error_response 不改 HTTP 码
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    # ------------------------------------------------------------------
    # DELETE /keys/{id}
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_key_ok(self, test_client, admin_headers, test_session):
        c = Credential(provider="yunwu", label="cov-del", api_key="sk-del")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)
        key_id = c.id

        resp = await test_client.delete(
            f"/api/admin/ai/keys/{key_id}", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["message"] == "Key 已删除"

        # 二次删除同一 id → not-found（同时验证 DB 真删了）
        resp2 = await test_client.delete(
            f"/api/admin/ai/keys/{key_id}", headers=admin_headers
        )
        body2 = resp2.json()
        assert resp2.status_code == 200
        assert body2["success"] is False
        assert body2["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self, test_client, admin_headers):
        resp = await test_client.delete(
            "/api/admin/ai/keys/999999", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    # ------------------------------------------------------------------
    # POST /keys/{id}/test
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_test_key_not_found(self, test_client, admin_headers):
        """不存在 key → error_response RESOURCE_NOT_FOUND（无需 mock httpx）。"""
        resp = await test_client.post(
            "/api/admin/ai/keys/999999/test", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_test_key_ok_with_mock_httpx(
        self, test_client, admin_headers, test_session
    ):
        """mock httpx.AsyncClient 返回 200 → status=ok。"""
        c = Credential(
            provider="yunwu",
            label="cov-test-ok",
            api_key="sk-test-ok",
            base_url="https://yunwu.ai/v1",
        )
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # admin_ai.test_key 内部 `import httpx` 后访问 httpx.AsyncClient
        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.post(
                f"/api/admin/ai/keys/{c.id}/test", headers=admin_headers
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["status"] == "ok"
        assert isinstance(body["data"]["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_test_key_httpx_error_returns_status_error(
        self, test_client, admin_headers, test_session
    ):
        """mock httpx.AsyncClient 抛异常 → 业务层捕获返回 status=error。"""
        c = Credential(provider="yunwu", label="cov-test-err", api_key="sk-x")
        test_session.add(c)
        await test_session.commit()
        await test_session.refresh(c)

        mock_client = AsyncMock()
        mock_client.__aenter__.side_effect = Exception("network down")
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.post(
                f"/api/admin/ai/keys/{c.id}/test", headers=admin_headers
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True  # 仍 success，业务层包装成 status=error
        assert body["data"]["status"] == "error"
        assert "network down" in body["data"]["error"]


class TestAdminAiModels:
    """GET/POST/PATCH/DELETE /models + POST /models/{id}/test."""

    # ------------------------------------------------------------------
    # GET /models
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_list_models_admin_ok(self, test_client, admin_headers, test_session):
        """GET /models → 200 + data.items 结构。"""
        suffix = uuid.uuid4().hex[:8]
        m = AiModel(name="cov-list", provider="yunwu", model_id=f"gpt-{suffix}")
        test_session.add(m)
        await test_session.commit()

        resp = await test_client.get("/api/admin/ai/models", headers=admin_headers)
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"]["items"], list)
        assert any(it["model_id"] == f"gpt-{suffix}" for it in body["data"]["items"])
        sample = body["data"]["items"][0]
        for k in (
            "id", "name", "provider", "model_id", "status",
            "total_calls", "total_tokens", "created_at", "updated_at",
        ):
            assert k in sample

    @pytest.mark.asyncio
    async def test_list_models_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/ai/models")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_models_operator_forbidden_403(
        self, test_client, operator_headers
    ):
        resp = await test_client.get(
            "/api/admin/ai/models", headers=operator_headers
        )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # POST /models
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_model_ok(self, test_client, admin_headers):
        suffix = uuid.uuid4().hex[:8]
        resp = await test_client.post(
            "/api/admin/ai/models",
            headers=admin_headers,
            json={"name": "cov-create", "provider": "yunwu", "model_id": f"m-{suffix}"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["message"] == "模型添加成功"
        assert body["data"]["name"] == "cov-create"
        assert body["data"]["provider"] == "yunwu"
        assert body["data"]["model_id"] == f"m-{suffix}"
        assert body["data"]["status"] == "active"
        assert body["data"]["id"] > 0

    @pytest.mark.asyncio
    async def test_create_model_duplicate(self, test_client, admin_headers, test_session):
        """重复 model_id（unique 约束）→ error_response VALIDATION_ERROR。"""
        suffix = uuid.uuid4().hex[:8]
        existing = AiModel(name="first", provider="yunwu", model_id=f"dup-{suffix}")
        test_session.add(existing)
        await test_session.commit()

        resp = await test_client.post(
            "/api/admin/ai/models",
            headers=admin_headers,
            json={"name": "second", "provider": "yunwu", "model_id": f"dup-{suffix}"},
        )
        body = resp.json()
        assert resp.status_code == 200  # error_response 不改 HTTP 码
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"
        assert f"dup-{suffix}" in body["message"]

    @pytest.mark.asyncio
    async def test_create_model_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/admin/ai/models",
            json={"name": "x", "model_id": "x"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_model_operator_forbidden_403(
        self, test_client, operator_headers
    ):
        resp = await test_client.post(
            "/api/admin/ai/models",
            headers=operator_headers,
            json={"name": "x", "model_id": "x"},
        )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # PATCH /models/{id}
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_model_ok(self, test_client, admin_headers, test_session):
        suffix = uuid.uuid4().hex[:8]
        m = AiModel(name="cov-upd", provider="yunwu", model_id=f"upd-{suffix}")
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        resp = await test_client.patch(
            f"/api/admin/ai/models/{m.id}",
            headers=admin_headers,
            json={"name": "cov-upd-new", "status": "disabled"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["name"] == "cov-upd-new"
        assert body["data"]["status"] == "disabled"
        # model_id 不在 UpdateModelRequest 中，应保持不变
        assert body["data"]["model_id"] == f"upd-{suffix}"

    @pytest.mark.asyncio
    async def test_update_model_not_found(self, test_client, admin_headers):
        resp = await test_client.patch(
            "/api/admin/ai/models/999999",
            headers=admin_headers,
            json={"name": "x"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    # ------------------------------------------------------------------
    # DELETE /models/{id}
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_model_ok(self, test_client, admin_headers, test_session):
        suffix = uuid.uuid4().hex[:8]
        m = AiModel(name="cov-del", provider="yunwu", model_id=f"del-{suffix}")
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)
        mid = m.id

        resp = await test_client.delete(
            f"/api/admin/ai/models/{mid}", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["message"] == "模型已删除"

        # 二次删除 → not-found，同时验证 DB 真删了
        resp2 = await test_client.delete(
            f"/api/admin/ai/models/{mid}", headers=admin_headers
        )
        body2 = resp2.json()
        assert resp2.status_code == 200
        assert body2["success"] is False
        assert body2["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_delete_model_not_found(self, test_client, admin_headers):
        resp = await test_client.delete(
            "/api/admin/ai/models/999999", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    # ------------------------------------------------------------------
    # POST /models/{id}/test
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_test_model_not_found(self, test_client, admin_headers):
        resp = await test_client.post(
            "/api/admin/ai/models/999999/test", headers=admin_headers
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "RESOURCE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_test_model_ok_with_mock_chat(
        self, test_client, admin_headers, test_session
    ):
        """mock yunwu_adapter.chat 不抛错 → status=ok。"""
        suffix = uuid.uuid4().hex[:8]
        m = AiModel(name="cov-test", provider="yunwu", model_id=f"t-{suffix}")
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        with patch(
            "app.routers.admin_ai.yunwu_adapter.chat",
            new=AsyncMock(return_value="ok"),
        ):
            resp = await test_client.post(
                f"/api/admin/ai/models/{m.id}/test", headers=admin_headers
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["status"] == "ok"
        assert isinstance(body["data"]["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_test_model_chat_error_returns_status_error(
        self, test_client, admin_headers, test_session
    ):
        """mock yunwu_adapter.chat 抛异常 → 业务层捕获返回 status=error。"""
        suffix = uuid.uuid4().hex[:8]
        m = AiModel(name="cov-test-err", provider="yunwu", model_id=f"te-{suffix}")
        test_session.add(m)
        await test_session.commit()
        await test_session.refresh(m)

        with patch(
            "app.routers.admin_ai.yunwu_adapter.chat",
            new=AsyncMock(side_effect=RuntimeError("no available key")),
        ):
            resp = await test_client.post(
                f"/api/admin/ai/models/{m.id}/test", headers=admin_headers
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True  # 业务层包装
        assert body["data"]["status"] == "error"
        assert "no available key" in body["data"]["error"]


class TestAdminAiStats:
    """GET /stats — 复杂聚合，做结构 + 参数断言。"""

    @pytest.mark.asyncio
    async def test_stats_admin_ok_structure(self, test_client, admin_headers):
        """GET /stats → 200 + data 含 summary/by_model/token_trend 三个 key。"""
        resp = await test_client.get("/api/admin/ai/stats", headers=admin_headers)
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        data = body["data"]
        assert "summary" in data
        assert "by_model" in data
        assert "token_trend" in data

        summary = data["summary"]
        for k in (
            "total_keys", "healthy_keys", "model_count", "total_tokens",
            "avg_latency_ms", "service_status", "queue_length",
            "current_active", "total_capacity",
        ):
            assert k in summary, f"summary.{k} 缺失"
        assert isinstance(data["by_model"], list)
        assert isinstance(data["token_trend"], list)
        # service_status 取值枚举校验
        assert summary["service_status"] in {
            "healthy", "degraded", "overloaded", "unavailable",
        }

    @pytest.mark.asyncio
    async def test_stats_with_query_params(self, test_client, admin_headers):
        """带 provider/status/start_date/end_date 查询参数不报错。"""
        resp = await test_client.get(
            "/api/admin/ai/stats?provider=yunwu&status=active&start_date=20260101&end_date=20260201",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        # 仍是同一结构
        assert "summary" in body["data"]

    @pytest.mark.asyncio
    async def test_stats_invalid_date_falls_back(self, test_client, admin_headers):
        """非法日期字符串 → 回退到默认（今日/明日），不报错。"""
        resp = await test_client.get(
            "/api/admin/ai/stats?start_date=not-a-date",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True

    @pytest.mark.asyncio
    async def test_stats_no_token_401(self, test_client):
        resp = await test_client.get("/api/admin/ai/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_stats_operator_forbidden_403(
        self, test_client, operator_headers
    ):
        resp = await test_client.get(
            "/api/admin/ai/stats", headers=operator_headers
        )
        assert resp.status_code == 403
