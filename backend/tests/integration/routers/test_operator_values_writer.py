"""
Integration tests for operator_values_writer and admin_values_writer routers.

Covers:
1. test_no_auth → 401
2. test_extract_values_no_kol → success=False
3. test_extract_values_success → success=True, values is list
4. test_emotion_direction_streaming → SSE Content-Type contains event-stream
5. test_write_streaming → SSE Content-Type contains event-stream
6. test_admin_get_config → returns default config
7. test_admin_put_config → update succeeds
8. test_save_output_success / empty_content / account_isolation → POST /save-output
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def ensure_values_config(test_session):
    """确保测试库中有激活的 values_writer_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO values_writer_configs "
        "(config_key, is_active) "
        "VALUES ('default', true) "
        "ON CONFLICT (config_key) DO UPDATE SET is_active = true"
    ))
    await test_session.commit()


async def _create_kol(test_session, name="测试达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, persona, background, status, created_by) "
        "VALUES (:name, :persona, :background, 'signed', NULL) "
        "RETURNING id"
    ), {
        "name": name,
        "persona": "真实接地气的生活博主",
        "background": "普通上班族，热爱分享日常",
    })
    kol_id = result.scalar()
    await test_session.commit()
    return kol_id


async def _set_current_product(test_session, kol_id):
    product_id = (await test_session.execute(text(
        "INSERT INTO qianchuan_products (nickname, core_selling_point, mechanism, unique_selling, mechanism_exclusive) "
        "VALUES ('数据库晚霜', '紧致卖点', '买一送一', '独家卖点', false) RETURNING id"
    ))).scalar()
    await test_session.execute(text(
        "INSERT INTO kol_active_products (kol_id, product_id) VALUES (:kol_id, :product_id)"
    ), {"kol_id": kol_id, "product_id": product_id})
    await test_session.commit()


class TestLegacyValuesWorkflow:
    @pytest.mark.asyncio
    async def test_derive_directions_requires_current_product(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="没有商品的达人")
        resp = await test_client.post(
            "/api/operator/values-writer/derive-directions",
            json={"kol_id": kol_id, "opening_line": "锁定开头", "original_script": "锁定开头\n原文正文"},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_derive_directions_reads_database_product_and_full_kol_context(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(test_session, name="完整档案达人")
        await test_session.execute(text(
            "UPDATE kols SET content_plan = '内容计划', experience = '真实经历', relationships = '关系网', "
            "unique_story = '独家经历', extra_notes = '补充信息' WHERE id = :id"
        ), {"id": kol_id})
        await _set_current_product(test_session, kol_id)
        with patch("app.routers.operator_values_writer.yunwu_adapter.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = '[{"type":"诱惑型","title":"被看见","description":"说明","anchor":"锚点"},{"type":"焦虑型","title":"错过","description":"说明","anchor":"锚点"}]'
            resp = await test_client.post(
                "/api/operator/values-writer/derive-directions",
                json={"kol_id": kol_id, "opening_line": "锁定开头", "original_script": "锁定开头\n原文正文"},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        prompt = mock_chat.call_args.kwargs["messages"][0]["content"]
        for value in ("数据库晚霜", "紧致卖点", "独家卖点", "内容计划", "真实经历", "关系网", "独家经历", "补充信息"):
            assert value in prompt
        assert resp.json()["data"]["directions"][0]["type"] == "诱惑型"

    @pytest.mark.asyncio
    async def test_generate_replaces_changed_opening_with_locked_opening(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(test_session, name="锁定开头达人")
        await _set_current_product(test_session, kol_id)

        async def _mock_stream(*args, **kwargs):
            yield "<analysis>12字，2段</analysis><rewrite>模型擅自改了开头。\n后续正文。</rewrite><report>检查完成</report>"

        with patch(
            "app.routers.operator_values_writer.yunwu_adapter.chat_stream",
            side_effect=_mock_stream,
        ):
            response = await test_client.post(
                "/api/operator/values-writer/generate",
                json={
                    "kol_id": kol_id,
                    "opening_line": "锁定开头。",
                    "original_script": "锁定开头。\n原文正文。",
                    "direction": {"type": "诱惑型", "title": "被看见", "description": "说明", "anchor": "锚点"},
                },
                headers=operator_headers,
            )

        payloads = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        generated = "".join(payload.get("delta", "") for payload in payloads)
        assert response.status_code == 200
        assert "<rewrite>锁定开头。\n后续正文。</rewrite>" in generated


# ---------------------------------------------------------------------------
# Test 1: No auth → 401
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_extract_values_no_auth(self, test_client):
        resp = await test_client.post(
            "/api/operator/values-writer/extract-values",
            json={"kol_id": 9999},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_emotion_direction_no_auth(self, test_client):
        resp = await test_client.post(
            "/api/operator/values-writer/emotion-direction",
            json={"kol_id": 1, "selected_values": ["真实"]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_write_no_auth(self, test_client):
        resp = await test_client.post(
            "/api/operator/values-writer/write",
            json={
                "kol_id": 1,
                "selected_values": ["真实"],
                "emotion_direction": "温暖",
            },
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 2: extract-values — kol does not exist → success=False (not 404)
# ---------------------------------------------------------------------------

class TestExtractValuesNoKol:
    @pytest.mark.asyncio
    async def test_extract_values_no_kol(self, test_client, operator_headers):
        with patch(
            "app.routers.operator_values_writer.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = '["真实", "治愈"]'
            resp = await test_client.post(
                "/api/operator/values-writer/extract-values",
                json={"kol_id": 999999},
                headers=operator_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False or body["data"] is None


# ---------------------------------------------------------------------------
# Test 3: extract-values success
# ---------------------------------------------------------------------------

class TestExtractValuesSuccess:
    @pytest.mark.asyncio
    async def test_extract_values_success(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session)

        with patch(
            "app.routers.operator_values_writer.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = '["真实", "治愈", "共鸣"]'
            resp = await test_client.post(
                "/api/operator/values-writer/extract-values",
                json={"kol_id": kol_id},
                headers=operator_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert isinstance(body["data"]["values"], list)
        assert len(body["data"]["values"]) > 0


# ---------------------------------------------------------------------------
# Test 4: emotion-direction — SSE streaming
# ---------------------------------------------------------------------------

class TestEmotionDirectionStreaming:
    @pytest.mark.asyncio
    async def test_emotion_direction_streaming(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="情绪方向测试达人")

        async def _mock_stream(*args, **kwargs):
            yield "温暖"
            yield "治愈"

        with patch(
            "app.routers.operator_values_writer.yunwu_adapter.chat_stream",
            side_effect=_mock_stream,
        ):
            resp = await test_client.post(
                "/api/operator/values-writer/emotion-direction",
                json={"kol_id": kol_id, "selected_values": ["真实", "共鸣"], "tone": "温暖"},
                headers=operator_headers,
            )

        assert resp.status_code == 200
        assert "event-stream" in resp.headers.get("content-type", "")
        # 至少有一个 data: 块
        assert "data:" in resp.text


# ---------------------------------------------------------------------------
# Test 5: write — SSE streaming
# ---------------------------------------------------------------------------

class TestWriteStreaming:
    @pytest.mark.asyncio
    async def test_write_streaming(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="写作测试达人")

        async def _mock_stream(*args, **kwargs):
            yield "在这个嘈杂的世界"
            yield "我选择真实"

        with patch(
            "app.routers.operator_values_writer.yunwu_adapter.chat_stream",
            side_effect=_mock_stream,
        ):
            resp = await test_client.post(
                "/api/operator/values-writer/write",
                json={
                    "kol_id": kol_id,
                    "selected_values": ["真实", "治愈"],
                    "emotion_direction": "温暖且真实",
                    "product_context": "某护肤品",
                },
                headers=operator_headers,
            )

        assert resp.status_code == 200
        assert "event-stream" in resp.headers.get("content-type", "")
        assert "data:" in resp.text


# ---------------------------------------------------------------------------
# Test 6: admin GET config
# ---------------------------------------------------------------------------

class TestAdminGetConfig:
    @pytest.mark.asyncio
    async def test_admin_get_config(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/values-writer/config",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["config_key"] == "default"
        for field in ("extract_values_prompt", "emotion_direction_prompt",
                      "writing_prompt", "iteration_prompt", "model_id", "is_active"):
            assert field in data

    @pytest.mark.asyncio
    async def test_admin_get_config_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/values-writer/config",
            headers=operator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 7: admin PUT config
# ---------------------------------------------------------------------------

class TestAdminPutConfig:
    @pytest.mark.asyncio
    async def test_admin_put_config_success(self, test_client, admin_headers, test_session, admin_user):
        resp = await test_client.put(
            "/api/admin/values-writer/config",
            json={
                "extract_values_prompt": "新的提炼prompt {persona_text}",
                "writing_prompt": "新的写作prompt",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["config_key"] == "default"

    @pytest.mark.asyncio
    async def test_admin_put_config_writes_operation_log(
        self, test_client, admin_headers, test_session, admin_user
    ):
        resp = await test_client.put(
            "/api/admin/values-writer/config",
            json={"iteration_prompt": "迭代优化prompt", "is_active": True},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'admin_update_values_writer_config' "
            "AND user_id = :uid"
        ), {"uid": admin_user.id})).scalar()
        assert log_count >= 1


# ---------------------------------------------------------------------------
# Test 8: POST /save-output
# ---------------------------------------------------------------------------

class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_success(self, test_client, operator_headers, operator_user, test_session):
        resp = await test_client.post(
            "/api/operator/values-writer/save-output",
            json={
                "title": "价值观仿写_测试",
                "content": "我们相信真实的力量",
                "topic": "真实",
            },
            headers=operator_headers,
        )
        body = resp.json()
        assert body["success"] is True
        assert "output_id" in body["data"]

        output_id = body["data"]["output_id"]
        row = (await test_session.execute(text(
            "SELECT tool_code, tool_name, created_by FROM outputs WHERE id = :id"
        ), {"id": output_id})).fetchone()
        assert row[0] == "values-writer"
        assert row[1] == "价值观仿写"
        assert row[2] == operator_user.id

    @pytest.mark.asyncio
    async def test_save_empty_content(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/values-writer/save-output",
            json={"content": "   "},
            headers=operator_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_writes_operation_log(
        self, test_client, operator_headers, operator_user, test_session
    ):
        resp = await test_client.post(
            "/api/operator/values-writer/save-output",
            json={"content": "测试内容", "title": "log_test", "topic": "治愈"},
            headers=operator_headers,
        )
        assert resp.json()["success"] is True

        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'values_writer_save_output' "
            "AND user_id = :uid"
        ), {"uid": operator_user.id})).scalar()
        assert log_count >= 1

    @pytest.mark.asyncio
    async def test_save_account_isolation(
        self, test_client, operator_user, operator_token, admin_token
    ):
        """operator 保存的 output，admin 通过全局 /outputs 看不到（账号隔离）。"""
        resp = await test_client.post(
            "/api/operator/values-writer/save-output",
            json={"title": "operator专属", "content": "内容A"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        # admin 通过全局 GET /outputs?tool_code=values-writer 看不到 operator 的
        resp = await test_client.get(
            "/api/outputs?tool_code=values-writer",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        titles = [item["title"] for item in resp.json()["data"]["items"]]
        assert "operator专属" not in titles
