"""
Integration tests for operator_retrospective and admin_retrospective routers.

Covers:
1. test_no_token → 401
2. test_admin_get_config → returns default config
3. test_admin_put_config → updates successfully
4. test_list_sessions_empty → empty list
5. test_create_session → returns session object
6. test_list_sessions_after_create → contains new session
7. test_delete_session → success
8. test_parse_files → returns parsed text (mock document_parser)
9. test_analyze_stream → SSE response (mock yunwu adapter)
"""
import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def ensure_retrospective_config(test_session):
    """确保测试库中有激活的 retrospective_configs 配置。"""
    await test_session.execute(text(
        "INSERT INTO retrospective_configs (config_key, is_active) "
        "VALUES ('default', true) "
        "ON CONFLICT (config_key) DO UPDATE SET is_active = true"
    ))
    await test_session.commit()


async def _create_kol(test_session, name="复盘测试达人"):
    result = await test_session.execute(text(
        "INSERT INTO kols (name, persona, extra_notes, status, created_by) "
        "VALUES (:name, :persona, :extra_notes, 'signed', NULL) "
        "RETURNING id"
    ), {
        "name": name,
        "persona": "真实接地气的生活博主",
        "extra_notes": "风格偏温暖，不用过激词汇",
    })
    kol_id = result.scalar()
    await test_session.commit()
    return kol_id


# ---------------------------------------------------------------------------
# Test 1: No token → 401
# ---------------------------------------------------------------------------

class TestAuth:
    @pytest.mark.asyncio
    async def test_list_no_auth(self, test_client):
        resp = await test_client.get("/api/operator/workspace/1/retrospective")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_no_auth(self, test_client):
        resp = await test_client.post(
            "/api/operator/workspace/1/retrospective",
            json={"title": "测试复盘"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_config_no_auth(self, test_client):
        resp = await test_client.get("/api/admin/retrospective/config")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test 2: Admin GET config → returns default
# ---------------------------------------------------------------------------

class TestAdminGetConfig:
    @pytest.mark.asyncio
    async def test_admin_get_config(self, test_client, admin_headers):
        resp = await test_client.get(
            "/api/admin/retrospective/config",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["config_key"] == "default"
        assert "system_prompt" in data
        assert "is_active" in data

    @pytest.mark.asyncio
    async def test_admin_get_config_operator_forbidden(self, test_client, operator_headers):
        resp = await test_client.get(
            "/api/admin/retrospective/config",
            headers=operator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test 3: Admin PUT config → update succeeds
# ---------------------------------------------------------------------------

class TestAdminPutConfig:
    @pytest.mark.asyncio
    async def test_admin_put_config_success(self, test_client, admin_headers, admin_user):
        resp = await test_client.put(
            "/api/admin/retrospective/config",
            json={
                "system_prompt": "你是复盘分析助手，请根据以下材料生成复盘报告。",
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
            "/api/admin/retrospective/config",
            json={"system_prompt": "更新测试prompt", "is_active": True},
            headers=admin_headers,
        )
        assert resp.json()["success"] is True

        log_count = (await test_session.execute(text(
            "SELECT COUNT(*) FROM operation_logs "
            "WHERE action = 'admin_update_retrospective_config' "
            "AND user_id = :uid"
        ), {"uid": admin_user.id})).scalar()
        assert log_count >= 1


# ---------------------------------------------------------------------------
# Test 4: GET list → empty list
# ---------------------------------------------------------------------------

class TestListSessionsEmpty:
    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="空列表测试达人")
        resp = await test_client.get(
            f"/api/operator/workspace/{kol_id}/retrospective",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["items"] == []
        assert "pagination" in body["data"]


# ---------------------------------------------------------------------------
# Test 5: POST create session → returns session object
# ---------------------------------------------------------------------------

class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="新建测试达人")
        resp = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={
                "title": "2024年Q1复盘",
                "status": "draft",
                "live_data": "直播数据：观看人数1000",
                "material_data": "素材数据",
            },
            headers=operator_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["title"] == "2024年Q1复盘"
        assert data["kol_id"] == kol_id
        assert "id" in data


# ---------------------------------------------------------------------------
# Test 6: GET list → contains new session
# ---------------------------------------------------------------------------

class TestListSessionsAfterCreate:
    @pytest.mark.asyncio
    async def test_list_sessions_after_create(
        self, test_client, operator_headers, test_session
    ):
        kol_id = await _create_kol(test_session, name="列表含新建达人")

        # 先新建
        create_resp = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={"title": "列表测试复盘"},
            headers=operator_headers,
        )
        assert create_resp.json()["success"] is True

        # 再查列表
        list_resp = await test_client.get(
            f"/api/operator/workspace/{kol_id}/retrospective",
            headers=operator_headers,
        )
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["success"] is True
        items = body["data"]["items"]
        assert len(items) >= 1
        titles = [item["title"] for item in items]
        assert "列表测试复盘" in titles


# ---------------------------------------------------------------------------
# Test 7: DELETE → success
# ---------------------------------------------------------------------------

class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="删除测试达人")

        # 新建 session
        create_resp = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={"title": "待删除的复盘"},
            headers=operator_headers,
        )
        session_id = create_resp.json()["data"]["id"]

        # 删除
        del_resp = await test_client.delete(
            f"/api/operator/workspace/{kol_id}/retrospective/{session_id}",
            headers=operator_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        # 验证已删除
        list_resp = await test_client.get(
            f"/api/operator/workspace/{kol_id}/retrospective",
            headers=operator_headers,
        )
        items = list_resp.json()["data"]["items"]
        ids = [item["id"] for item in items]
        assert session_id not in ids


# ---------------------------------------------------------------------------
# Test 8: parse-files → returns parsed text (mock document_parser)
# ---------------------------------------------------------------------------

class TestParseFiles:
    @pytest.mark.asyncio
    async def test_parse_files_keeps_each_filename_and_text_paired(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="解析文件测试达人")

        with patch(
            "app.routers.operator_retrospective.document_parser.parse_files_to_items",
            new_callable=AsyncMock,
        ) as mock_parse:
            mock_parse.return_value = [
                {"name": "first.txt", "text": "第一份正文"},
                {"name": "second.txt", "text": "第二份正文"},
            ]
            resp = await test_client.post(
                f"/api/operator/workspace/{kol_id}/retrospective/parse-files",
                headers=operator_headers,
                files=[
                    ("files", ("first.txt", BytesIO(b"hello world"), "text/plain")),
                    ("files", ("second.txt", BytesIO(b"hello again"), "text/plain")),
                ],
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["files"] == [
            {"name": "first.txt", "text": "第一份正文"},
            {"name": "second.txt", "text": "第二份正文"},
        ]


# ---------------------------------------------------------------------------
# Test 9: analyze stream → SSE response (mock yunwu adapter)
# ---------------------------------------------------------------------------

class TestAnalyzeStream:
    @pytest.mark.asyncio
    async def test_analyze_requires_live_or_material_data(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="缺材料达人")
        create = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={"title": "空材料复盘"}, headers=operator_headers,
        )
        response = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective/{create.json()['data']['id']}/analyze",
            headers=operator_headers,
        )
        assert response.status_code == 400
        assert "至少填写直播汇总数据或素材明细数据" in response.text

    @pytest.mark.asyncio
    async def test_analyze_stream(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="分析流式测试达人")

        # 先新建 session
        create_resp = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={
                "title": "流式分析测试复盘",
                "live_data": "直播数据",
                "material_data": "素材数据",
            },
            headers=operator_headers,
        )
        session_id = create_resp.json()["data"]["id"]

        async def _mock_stream(*args, **kwargs):
            yield "这是复盘报告第一段"
            yield "，这是第二段内容。"

        with patch(
            "app.routers.operator_retrospective.yunwu_adapter.chat_stream",
            side_effect=_mock_stream,
        ):
            resp = await test_client.post(
                f"/api/operator/workspace/{kol_id}/retrospective/{session_id}/analyze",
                headers=operator_headers,
            )

        assert resp.status_code == 200
        assert "event-stream" in resp.headers.get("content-type", "")
        assert "data:" in resp.text

    @pytest.mark.asyncio
    async def test_analyze_uses_full_kol_context(self, test_client, operator_headers, test_session):
        kol_id = await _create_kol(test_session, name="完整档案达人")
        await test_session.execute(text(
            "UPDATE kols SET content_plan='内容计划', experience='真实经历', relationships='关系网', unique_story='独家经历' WHERE id=:id"
        ), {"id": kol_id})
        await test_session.commit()
        created = await test_client.post(
            f"/api/operator/workspace/{kol_id}/retrospective",
            json={"title": "档案复盘", "live_data": "直播数据"}, headers=operator_headers,
        )
        async def _mock_stream(*args, **kwargs):
            assert all(value in kwargs["messages"][1]["content"] for value in ("内容计划", "真实经历", "关系网", "独家经历"))
            yield "报告"
        with patch("app.routers.operator_retrospective.yunwu_adapter.chat_stream", side_effect=_mock_stream):
            response = await test_client.post(
                f"/api/operator/workspace/{kol_id}/retrospective/{created.json()['data']['id']}/analyze",
                headers=operator_headers,
            )
        assert response.status_code == 200
        # 验证 done 标记
        assert '"done": true' in response.text or '"done":true' in response.text
