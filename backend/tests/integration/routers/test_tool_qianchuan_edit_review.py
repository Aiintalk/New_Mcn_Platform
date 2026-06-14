"""Integration tests for tool_qianchuan_edit_review router."""
import pytest
from sqlalchemy import text


class TestAuth:
    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={"title": "测试报告", "report": "报告内容"},
        )
        assert resp.status_code == 401


class TestSaveOutput:
    @pytest.mark.asyncio
    async def test_save_returns_standard_envelope(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "千川剪辑预审_2026-06-14",
                "report": "## 开头剪辑\n\n建议从第2秒切入",
                "original_duration": 32.5,
                "ours_duration": 28.0,
                "original_frame_count": 8,
                "ours_frame_count": 8,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["code"] == "OK"
        assert "id" in body["data"]
        assert "created_at" in body["data"]

    @pytest.mark.asyncio
    async def test_save_writes_to_outputs_table(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "测试标题",
                "report": "报告正文内容",
                "original_duration": 10.0,
                "ours_duration": 12.0,
                "original_frame_count": 5,
                "ours_frame_count": 6,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200

        output_id = resp.json()["data"]["id"]
        row = (await test_session.execute(
            text("SELECT tool_code, tool_name, title, content, word_count, content_json FROM outputs WHERE id=:id"),
            {"id": output_id},
        )).fetchone()

        assert row is not None
        assert row[0] == "qianchuan-edit-review"
        assert row[1] == "千川剪辑预审"
        assert row[2] == "测试标题"
        assert row[3] == "报告正文内容"
        assert row[4] == len("报告正文内容")
        assert row[5]["original_duration"] == 10.0

    @pytest.mark.asyncio
    async def test_save_writes_operation_log(self, test_client, operator_token, test_session):
        await test_session.execute(
            text("DELETE FROM outputs WHERE tool_code='qianchuan-edit-review'")
        )
        await test_session.commit()

        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={
                "title": "日志测试",
                "report": "内容",
                "original_duration": 5.0,
                "ours_duration": 5.0,
                "original_frame_count": 3,
                "ours_frame_count": 3,
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        output_id = resp.json()["data"]["id"]

        log = (await test_session.execute(
            text("SELECT action, target_type, target_id FROM operation_logs WHERE target_id=:id AND target_type='output'"),
            {"id": output_id},
        )).fetchone()

        assert log is not None
        assert log[0] == "qianchuan_edit_review_save_output"

    @pytest.mark.asyncio
    async def test_empty_report_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/qianchuan-edit-review/outputs",
            json={"title": "标题", "report": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
