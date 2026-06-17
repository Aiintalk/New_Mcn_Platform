"""Integration tests for operator_persona_review and admin_persona_review routers."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text as sa_text


@pytest.fixture(autouse=True)
async def seed_pr_configs(test_session):
    for key, prompt in [
        ('with_excel', '你是抖音顶级内容操盘大师（有运营数据版）。'),
        ('without_excel', '你是抖音顶级内容操盘大师（无运营数据版）。'),
    ]:
        await test_session.execute(sa_text(
            "INSERT INTO persona_review_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/persona-review/generate",
            json={"scripts": [{"title": "t", "content": "c"}], "excel_data": []},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/persona-review/save",
            json={"task_id": 1, "report": "内容", "script_count": 1, "has_excel": False},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_outputs_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/persona-review/outputs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_configs_unauthorized(self, test_client):
        resp = await test_client.get("/api/admin/persona-review/configs")
        assert resp.status_code == 401


# ---------- generate ----------

class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_empty_scripts_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/persona-review/generate",
            json={"scripts": [], "excel_data": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_streams_response(self, test_client, operator_token):
        async def fake_chat_stream(**kwargs):
            for chunk in ["这是", "复盘", "报告"]:
                yield chunk

        with patch(
            "app.tools.persona_review.service.yunwu_adapter.chat_stream",
            side_effect=fake_chat_stream,
        ):
            resp = await test_client.post(
                "/api/tools/persona-review/generate",
                json={
                    "scripts": [{"title": "减肥日记", "content": "今天开始减肥..."}],
                    "excel_data": [],
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "这是复盘报告" in resp.text

    @pytest.mark.asyncio
    async def test_generate_returns_task_id_header(self, test_client, operator_token):
        async def fake_chat_stream(**kwargs):
            yield "报告内容"

        with patch(
            "app.tools.persona_review.service.yunwu_adapter.chat_stream",
            side_effect=fake_chat_stream,
        ):
            resp = await test_client.post(
                "/api/tools/persona-review/generate",
                json={
                    "scripts": [{"title": "测试", "content": "内容"}],
                    "excel_data": [],
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert "x-task-id" in resp.headers

    @pytest.mark.asyncio
    async def test_generate_with_excel_data(self, test_client, operator_token):
        async def fake_chat_stream(**kwargs):
            yield "复盘报告正文"

        with patch(
            "app.tools.persona_review.service.yunwu_adapter.chat_stream",
            side_effect=fake_chat_stream,
        ):
            resp = await test_client.post(
                "/api/tools/persona-review/generate",
                json={
                    "scripts": [{"title": "减肥日记", "content": "内容"}],
                    "excel_data": [{
                        "video_theme": "减肥日记",
                        "likes": "5000",
                        "completion_rate": "45%",
                        "ad_spend": "200",
                        "date": "",
                        "live_theme": "",
                        "video_type": "",
                        "total_plays": "",
                        "five_sec_rate": "",
                        "comments": "",
                    }],
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_generate_creates_task_job(self, test_client, operator_token, test_session):
        async def fake_chat_stream(**kwargs):
            yield "内容"

        with patch(
            "app.tools.persona_review.service.yunwu_adapter.chat_stream",
            side_effect=fake_chat_stream,
        ):
            resp = await test_client.post(
                "/api/tools/persona-review/generate",
                json={"scripts": [{"title": "t", "content": "c"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        task_id = int(resp.headers.get("x-task-id", 0))
        assert task_id > 0
        row = (await test_session.execute(
            sa_text("SELECT tool_code FROM task_jobs WHERE id=:id"),
            {"id": task_id},
        )).fetchone()
        assert row is not None
        assert row[0] == "persona-review"


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_report_success(self, test_client, operator_token):
        async def fake_chat_stream(**kwargs):
            yield "报告内容"

        with patch(
            "app.tools.persona_review.service.yunwu_adapter.chat_stream",
            side_effect=fake_chat_stream,
        ):
            gen_resp = await test_client.post(
                "/api/tools/persona-review/generate",
                json={"scripts": [{"title": "t", "content": "c"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        task_id = int(gen_resp.headers.get("x-task-id", 1))

        resp = await test_client.post(
            "/api/tools/persona-review/save",
            json={
                "task_id": task_id,
                "report": "这是完整的复盘报告内容",
                "script_count": 3,
                "has_excel": False,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["output_id"] > 0

    @pytest.mark.asyncio
    async def test_save_empty_report_rejected(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/persona-review/save",
            json={"task_id": 1, "report": "   ", "script_count": 1, "has_excel": False},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_save_title_format_no_excel(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/persona-review/save",
            json={"task_id": 1, "report": "复盘内容", "script_count": 5, "has_excel": False},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        output_id = resp.json()["data"]["output_id"]
        row = (await test_session.execute(
            sa_text("SELECT title FROM outputs WHERE id=:id"),
            {"id": output_id},
        )).fetchone()
        assert row[0] == "人设脚本复盘_5条视频_仅脚本"

    @pytest.mark.asyncio
    async def test_save_title_format_with_excel(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/persona-review/save",
            json={"task_id": 1, "report": "复盘内容", "script_count": 3, "has_excel": True},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        output_id = resp.json()["data"]["output_id"]
        row = (await test_session.execute(
            sa_text("SELECT title FROM outputs WHERE id=:id"),
            {"id": output_id},
        )).fetchone()
        assert row[0] == "人设脚本复盘_3条视频_含运营数据"


# ---------- outputs ----------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_empty_initially(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/persona-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"]["items"], list)
        assert isinstance(data["data"]["total"], int)

    @pytest.mark.asyncio
    async def test_outputs_only_own_records(self, test_client, operator_token, admin_token):
        """operator 只能看自己的产出，不看 admin 的"""
        await test_client.post(
            "/api/tools/persona-review/save",
            json={"task_id": 1, "report": "admin的报告", "script_count": 1, "has_excel": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = await test_client.get(
            "/api/tools/persona-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        items = resp.json()["data"]["items"]
        assert all(item["title"] != "人设脚本复盘_1条视频_仅脚本" for item in items) or len(items) == 0

    @pytest.mark.asyncio
    async def test_outputs_pagination(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/persona-review/outputs?page=1&size=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200


# ---------- admin configs ----------

class TestAdminConfigs:
    @pytest.mark.asyncio
    async def test_list_configs(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/admin/persona-review/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        keys = [c["config_key"] for c in data["data"]]
        assert "with_excel" in keys
        assert "without_excel" in keys

    @pytest.mark.asyncio
    async def test_list_configs_forbidden_for_operator(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/admin/persona-review/configs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_config(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/persona-review/configs/with_excel",
            json={"system_prompt": "更新后的 Prompt", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_update_nonexistent_config(self, test_client, admin_token):
        resp = await test_client.put(
            "/api/admin/persona-review/configs/nonexistent_key",
            json={"system_prompt": "xxx", "is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
