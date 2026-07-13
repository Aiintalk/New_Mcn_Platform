"""完整视频成片预审：只用测试替身，不访问真实 Gemini 或 OSS。"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text as sa_text


@pytest.fixture(autouse=True)
async def seed_preview_config(test_session):
    await test_session.execute(sa_text(
        "INSERT INTO ai_models (name, provider, model_id, status) "
        "VALUES ('Gemini 测试模型', 'gemini', 'gemini-test-model', 'active') "
        "ON CONFLICT (model_id) DO UPDATE SET status='active'"
    ))
    model_id = (await test_session.execute(sa_text(
        "SELECT id FROM ai_models WHERE model_id='gemini-test-model'"
    ))).scalar_one()
    await test_session.execute(sa_text(
        "INSERT INTO qianchuan_preview_configs (config_key, system_prompt, is_active) "
        "VALUES ('default', '完整视频测试提示词', true) "
        "ON CONFLICT (config_key) DO UPDATE SET system_prompt=EXCLUDED.system_prompt, ai_model_id=:model_id"
    ), {"model_id": model_id})
    await test_session.commit()
    yield


@pytest.fixture
async def kol_id(test_session, operator_user):
    value = (await test_session.execute(sa_text(
        "INSERT INTO kols (name, status, created_by) VALUES ('成片预审测试红人', 'signed', :user_id) RETURNING id"
    ), {"user_id": operator_user.id})).scalar_one()
    await test_session.commit()
    return value


class TestVideoAnalyze:
    @pytest.mark.asyncio
    async def test_rejects_unsupported_video_format(self, test_client, operator_token, kol_id):
        response = await test_client.post(
            "/api/tools/qianchuan-preview/analyze-video",
            data={"kol_id": str(kol_id)},
            files={
                "original": ("source.avi", b"source", "video/x-msvideo"),
                "edited": ("edited.mp4", b"edited", "video/mp4"),
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_streams_report_from_two_complete_video_files_and_cleans_temporary_objects(
        self, test_client, operator_token, kol_id
    ):
        async def fake_stream(**kwargs):
            assert kwargs["original_path"].read_bytes() == b"complete-original-video"
            assert kwargs["edited_path"].read_bytes() == b"complete-edited-video"
            yield "__STATUS__Gemini 正在读取两条完整视频...\n"
            yield "# 完整视频预审报告"

        uploaded_keys: list[str] = []
        deleted_keys: list[str] = []

        async def fake_upload(oss_key, file_path, content_type, db, user_id):
            uploaded_keys.append(oss_key)
            return oss_key

        async def fake_delete(oss_key, db, user_id):
            deleted_keys.append(oss_key)

        with patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.upload_file_from_path",
            side_effect=fake_upload,
        ), patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.delete_file",
            side_effect=fake_delete,
        ), patch(
            "app.routers.operator_qianchuan_preview.gemini_video.stream_full_video_analysis",
            side_effect=fake_stream,
        ):
            response = await test_client.post(
                "/api/tools/qianchuan-preview/analyze-video",
                data={"kol_id": str(kol_id)},
                files={
                    "original": ("source.mp4", b"complete-original-video", "video/mp4"),
                    "edited": ("edited.mov", b"complete-edited-video", "video/quicktime"),
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert response.status_code == 200
        assert response.headers["x-task-id"]
        assert "完整视频预审报告" in response.text
        assert len(uploaded_keys) == 2
        assert set(uploaded_keys) == set(deleted_keys)

    @pytest.mark.asyncio
    async def test_provider_failure_marks_task_error_and_still_cleans_temporary_objects(
        self, test_client, operator_token, test_session, kol_id
    ):
        async def failing_stream(**kwargs):
            raise RuntimeError("Gemini Files API 超时")
            yield  # pragma: no cover

        delete_temporary_objects = AsyncMock()
        with patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.upload_file_from_path",
            new=AsyncMock(side_effect=lambda key, *args: key),
        ), patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.delete_file",
            new=delete_temporary_objects,
        ), patch(
            "app.routers.operator_qianchuan_preview.gemini_video.stream_full_video_analysis",
            side_effect=failing_stream,
        ):
            response = await test_client.post(
                "/api/tools/qianchuan-preview/analyze-video",
                data={"kol_id": str(kol_id)},
                files={
                    "original": ("source.mp4", b"original", "video/mp4"),
                    "edited": ("edited.mp4", b"edited", "video/mp4"),
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert response.status_code == 200
        assert "分析失败" in response.text
        task_id = int(response.headers["x-task-id"])
        row = (await test_session.execute(sa_text(
            "SELECT status, error_code FROM task_jobs WHERE id=:id"
        ), {"id": task_id})).fetchone()
        assert row == ("error", "EXTERNAL_SERVICE_ERROR")
        assert delete_temporary_objects.await_count == 2


class TestVideoReportSave:
    @pytest.mark.asyncio
    async def test_saves_complete_video_report_to_outputs(self, test_client, operator_token, operator_user, test_session, kol_id):
        user_id = operator_user.id
        await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, input_payload, created_by) "
            "VALUES ('QV-SAVE-001', 'qianchuan-preview', '千川成片预审', 'success', "
            "CAST(:payload AS jsonb), :user_id)"
        ), {"user_id": user_id, "payload": json.dumps({"mode": "full_video", "kol_id": kol_id})})
        await test_session.commit()
        task_id = (await test_session.execute(sa_text(
            "SELECT id FROM task_jobs WHERE task_no='QV-SAVE-001'"
        ))).scalar_one()

        response = await test_client.post(
            "/api/tools/qianchuan-preview/save-video-report",
            json={
                "task_id": task_id,
                "report": "# 完整视频报告",
                "original_filename": "source.mp4",
                "edited_filename": "edited.mov",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["output_id"]

    @pytest.mark.asyncio
    async def test_rejects_a_nonexistent_kol_before_accepting_video(self, test_client, operator_token):
        response = await test_client.post(
            "/api/tools/qianchuan-preview/analyze-video",
            data={"kol_id": "999999"},
            files={
                "original": ("source.mp4", b"original", "video/mp4"),
                "edited": ("edited.mp4", b"edited", "video/mp4"),
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "RESOURCE_NOT_FOUND"
