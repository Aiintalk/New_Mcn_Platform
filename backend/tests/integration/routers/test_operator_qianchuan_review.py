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
        assert 'event: content' in resp.text
        assert '"text":"复盘"' in resp.text
        assert 'event: complete' in resp.text
        assert "x-task-id" in resp.headers

    @pytest.mark.asyncio
    async def test_empty_stream_marks_task_failed_and_emits_failed_event(
        self, test_client, operator_token, test_session
    ):
        async def empty_stream(*args, **kwargs):
            if False:
                yield ""

        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            return_value=empty_stream(),
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={"scripts": [{"title": "脚本甲", "content": "脚本内容"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        task_id = int(resp.headers["x-task-id"])
        assert "event: failed" in resp.text
        assert "生成结果为空，请重新生成" in resp.text
        assert "event: complete" not in resp.text
        row = (await test_session.execute(sa_text(
            "SELECT status, error_code, error_message FROM task_jobs WHERE id = :id"
        ), {"id": task_id})).fetchone()
        assert row.status == "failed"
        assert row.error_code == "EMPTY_REPORT"
        assert row.error_message == "生成结果为空，请重新生成"

    @pytest.mark.asyncio
    async def test_exception_stream_marks_task_failed_without_error_text_as_content(
        self, test_client, operator_token, test_session
    ):
        async def failed_stream(*args, **kwargs):
            raise RuntimeError("provider secret detail")
            yield ""  # pragma: no cover

        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            return_value=failed_stream(),
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={"scripts": [{"title": "脚本甲", "content": "脚本内容"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        task_id = int(resp.headers["x-task-id"])
        assert "event: failed" in resp.text
        assert "AI 生成失败，请重新生成" in resp.text
        assert "[ERROR]" not in resp.text
        assert "provider secret detail" not in resp.text
        row = (await test_session.execute(sa_text(
            "SELECT status, error_code FROM task_jobs WHERE id = :id"
        ), {"id": task_id})).fetchone()
        assert row.status == "failed"
        assert row.error_code == "GENERATION_FAILED"

    @pytest.mark.asyncio
    async def test_partial_stream_then_exception_is_failed_not_success(
        self, test_client, operator_token, test_session
    ):
        async def partial_failed_stream(*args, **kwargs):
            yield "前半段"
            raise RuntimeError("stream interrupted")

        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            return_value=partial_failed_stream(),
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={"scripts": [{"title": "脚本甲", "content": "脚本内容"}], "excel_data": []},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        task_id = int(resp.headers["x-task-id"])
        assert 'event: content' in resp.text
        assert '"text":"前半段"' in resp.text
        assert "event: failed" in resp.text
        assert "event: complete" not in resp.text
        status = (await test_session.execute(sa_text(
            "SELECT status FROM task_jobs WHERE id = :id"
        ), {"id": task_id})).scalar_one()
        assert status == "failed"

    @pytest.mark.asyncio
    async def test_zero_excel_matches_returns_diagnostics_without_calling_ai(
        self, test_client, operator_token
    ):
        mock_generate = AsyncMock()
        with patch(
            "app.routers.operator_qianchuan_review.generate_review_stream",
            new=mock_generate,
        ):
            resp = await test_client.post(
                "/api/tools/qianchuan-review/generate",
                json={
                    "scripts": [{"title": "脚本完全不同", "content": "脚本内容"}],
                    "excel_data": [{"video_theme": "素材毫不相干", "spend": "100"}],
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        body = resp.json()
        assert resp.status_code == 400
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"
        assert body["data"] == {
            "matched_count": 0,
            "unmatched_scripts": [{"index": 1, "title": "脚本完全不同"}],
            "unmatched_excel_rows": [{"row": 2, "video_theme": "素材毫不相干"}],
        }
        mock_generate.assert_not_awaited()


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_creates_output(self, test_client, operator_token, operator_user, test_session):
        # 先创建 task_job
        await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('QR-TEST-001', 'qianchuan-review', '千川脚本复盘', 'success', :uid) "
            "ON CONFLICT (task_no) DO NOTHING"
        ), {"uid": operator_user.id})
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

    @pytest.mark.asyncio
    async def test_save_failed_task_returns_409(
        self, test_client, operator_token, operator_user, test_session
    ):
        task_id = (await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('QR-FAILED-SAVE', 'qianchuan-review', '千川脚本复盘', 'failed', :uid) "
            "RETURNING id"
        ), {"uid": operator_user.id})).scalar_one()
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={
                "task_id": task_id,
                "report": "部分失败内容",
                "script_count": 1,
                "has_excel": False,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "TASK_NOT_SUCCESS"

    @pytest.mark.asyncio
    async def test_save_rejects_legacy_error_marker(
        self, test_client, operator_token, operator_user, test_session
    ):
        task_id = (await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, created_by) "
            "VALUES ('QR-ERROR-MARKER', 'qianchuan-review', '千川脚本复盘', 'success', :uid) "
            "RETURNING id"
        ), {"uid": operator_user.id})).scalar_one()
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-review/save",
            json={
                "task_id": task_id,
                "report": "报告前半段\n\n[ERROR] 上游失败",
                "script_count": 1,
                "has_excel": False,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_REPORT"


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
