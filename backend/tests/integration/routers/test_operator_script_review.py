"""
Integration tests for Sprint 21 千川脚本预审接口.

Covers:
1. 无 token → 401
2. 管理端 GET /config → 返回 default 配置（success=True）
3. 管理端 PUT /config → 更新 direct_prompt 成功
4. 运营端 POST /review direct 模式 → 返回结构化结果（mock AI 调用）
5. 运营端 POST /review value 模式 → 返回结构化结果（mock AI 调用）
6. 运营端 POST /review 缺少 adapted_script → 422
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


_MOCK_AI_RESPONSE = json.dumps({
    "rating": "pass",
    "must_fix": [],
    "suggestions": ["建议1"],
    "passed": ["结构完整"],
})


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_token_admin_get(self, test_client):
        resp = await test_client.get("/api/admin/qianchuan-script-review/config")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_token_operator_post(self, test_client):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/review",
            json={
                "script_type": "direct",
                "original_script": "原版脚本",
                "adapted_script": "仿写脚本",
            },
        )
        assert resp.status_code == 401


class TestAdminGetConfig:
    @pytest.mark.asyncio
    async def test_get_default_config(self, test_client, admin_headers, test_session):
        resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["config_key"] == "default"

    @pytest.mark.asyncio
    async def test_operator_cannot_access_admin(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=operator_headers,
        )
        assert resp.status_code == 403


class TestAdminUpdateConfig:
    @pytest.mark.asyncio
    async def test_update_direct_prompt(self, test_client, admin_headers, test_session):
        payload = {
            "direct_prompt": "新的 direct prompt 内容",
            "value_prompt": None,
            "ai_model_id": None,
            "is_active": True,
        }
        resp = await test_client.put(
            "/api/admin/qianchuan-script-review/config",
            json=payload,
            headers=admin_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True

        # 验证更新已写入
        get_resp = await test_client.get(
            "/api/admin/qianchuan-script-review/config",
            headers=admin_headers,
        )
        get_body = get_resp.json()
        assert get_body["data"]["direct_prompt"] == "新的 direct prompt 内容"


class TestOperatorReview:
    @pytest.mark.asyncio
    async def test_review_direct_mode(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_script_review._call_review_ai",
            new=AsyncMock(return_value=_MOCK_AI_RESPONSE),
        ):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "direct",
                    "original_script": "原版脚本内容",
                    "adapted_script": "仿写脚本内容",
                    "product": {"nickname": "大红瓶", "core_selling_point": "美白"},
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["rating"] == "pass"
        assert body["data"]["must_fix"] == []
        assert "建议1" in body["data"]["suggestions"]
        assert "结构完整" in body["data"]["passed"]

    @pytest.mark.asyncio
    async def test_review_value_mode(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_script_review._call_review_ai",
            new=AsyncMock(return_value=_MOCK_AI_RESPONSE),
        ):
            resp = await test_client.post(
                "/api/operator/qianchuan-script-review/review",
                json={
                    "script_type": "value",
                    "original_script": "原版价值观脚本",
                    "adapted_script": "仿写价值观脚本",
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["rating"] == "pass"

    @pytest.mark.asyncio
    async def test_review_missing_adapted_script(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/qianchuan-script-review/review",
            json={
                "script_type": "direct",
                "original_script": "原版脚本",
            },
            headers=operator_headers,
        )
        assert resp.status_code == 422
