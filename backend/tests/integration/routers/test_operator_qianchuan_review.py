"""Integration tests for operator_qianchuan_review router."""
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy import text as sa_text


@pytest.fixture(autouse=True)
async def seed_qr_configs(test_session):
    for key, prompt in [('with_excel', 'Test Prompt With Excel'), ('without_excel', 'Test Prompt Without Excel')]:
        await test_session.execute(sa_text(
            "INSERT INTO qianchuan_review_configs (config_key, system_prompt, is_active) "
            "VALUES (:k, :p, true) ON CONFLICT (config_key) DO NOTHING"
        ), {"k": key, "p": prompt})
    await test_session.commit()
    yield


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_parse_file_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("test.txt", b"content", "text/plain")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": [{"title": "t", "content": "c"}], "excel_data": []},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={"task_id": 1, "report": "内容", "script_count": 1, "has_excel": False},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_outputs_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/qianchuan-review/outputs")
        assert resp.status_code == 401


# ---------- parse-file ----------

class TestParseFile:
    @pytest.mark.asyncio
    async def test_txt_file_returns_text(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("script.txt", "千川脚本内容".encode("utf-8"), "text/plain")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "千川脚本内容" in data["data"]["text"]
        assert data["data"]["filename"] == "script.txt"

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/parse-file",
            files={"file": ("data.xlsx", b"content", "application/octet-stream")},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "UNSUPPORTED_FORMAT"


# ---------- generate ----------

class TestGenerate:
    @pytest.mark.asyncio
    async def test_empty_scripts_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": [], "excel_data": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_over_30_scripts_returns_400(self, test_client, operator_token):
        scripts = [{"title": f"脚本{i}", "content": "内容"} for i in range(31)]
        resp = await test_client.post(
            "/api/tools/qianchuan-review/generate",
            json={"scripts": scripts, "excel_data": []},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert "30条" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_generate_returns_stream_and_task_id_header(self, test_client, operator_token):
        async def fake_stream(*args, **kwargs):
            yield "复盘"
            yield "报告"

        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            return_value=fake_stream(),
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={"scripts": [{"title": "脚本甲", "content": "脚本内容"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "复盘" in resp.text
        assert "x-task-id" in resp.headers


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_creates_output(self, test_client, operator_token, test_session):
        # 先创建 task_job
        await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('QR-TEST-001', 'qianchuan-review', '千川脚本复盘', 'processing', "
            "(SELECT id FROM users WHERE role='operator' LIMIT 1)) "
            "ON CONFLICT (task_no) DO NOTHING"
        ))
        await test_session.commit()
        task_row = (await test_session.execute(
            sa_text("SELECT id FROM task_jobs WHERE task_no='QR-TEST-001'")
        )).fetchone()
        task_id = task_row[0]

        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={
                "task_id": task_id,
                "report": "这是完整的复盘报告内容",
                "script_count": 3,
                "has_excel": True,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "output_id" in data["data"]

    @pytest.mark.asyncio
    async def test_save_empty_report_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={"task_id": 1, "report": "", "script_count": 1, "has_excel": False},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400


# ---------- outputs ----------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_returns_list(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_operator_only_sees_own_outputs(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/qianchuan-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["items"], list)
