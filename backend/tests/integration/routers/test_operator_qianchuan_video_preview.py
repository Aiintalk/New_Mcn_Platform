"""完整视频成片预审：只用测试替身，不访问真实 Gemini 或 OSS。"""
import json
from pathlib import Path
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
    updated = await test_session.execute(sa_text(
        "UPDATE qianchuan_preview_configs SET system_prompt='完整视频测试提示词', "
        "ai_model_id=:model_id, is_active=true WHERE config_key='full_video'"
    ), {"model_id": model_id})
    if not updated.rowcount:
        await test_session.execute(sa_text(
            "INSERT INTO qianchuan_preview_configs (config_key, system_prompt, ai_model_id, is_active) "
            "VALUES ('full_video', '完整视频测试提示词', :model_id, true)"
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
        assert "event: report" in response.text
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
        assert "event: error" in response.text
        assert "event: failed" in response.text
        task_id = int(response.headers["x-task-id"])
        row = (await test_session.execute(sa_text(
            "SELECT status, error_code FROM task_jobs WHERE id=:id"
        ), {"id": task_id})).fetchone()
        assert row == ("failed", "EXTERNAL_SERVICE_ERROR")
        assert delete_temporary_objects.await_count == 2

    @pytest.mark.asyncio
    async def test_missing_gemini_credential_fails_task_and_cannot_save_partial_report(
        self, test_client, operator_token, test_session, kol_id
    ):
        config = (await test_session.execute(sa_text(
            "SELECT system_prompt, ai_model_id FROM qianchuan_preview_configs WHERE config_key='full_video'"
        ))).fetchone()
        assert config and config[0] and config[1]
        with patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.upload_file_from_path",
            new=AsyncMock(side_effect=lambda key, *args: key),
        ), patch(
            "app.routers.operator_qianchuan_preview.oss_adapter.delete_file",
            new=AsyncMock(),
        ), patch(
            "app.adapters.gemini_video.credential_pool._pick_and_lock",
            new=AsyncMock(return_value=None),
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

        assert response.status_code == 200, response.text
        assert "event: error" in response.text
        assert "未配置可用的 Gemini 统一凭证" in response.text
        task_id = int(response.headers["x-task-id"])
        row = (await test_session.execute(sa_text(
            "SELECT status FROM task_jobs WHERE id=:id"
        ), {"id": task_id})).fetchone()
        assert row == ("failed",)

        save_response = await test_client.post(
            "/api/tools/qianchuan-preview/save-video-report",
            json={
                "task_id": task_id,
                "report": "# 未完成报告",
                "original_filename": "source.mp4",
                "edited_filename": "edited.mp4",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert save_response.json()["success"] is False
        assert save_response.json()["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_video_over_maximum_bytes_marks_task_failed_and_removes_temp_directory(
        self, test_client, operator_token, test_session, kol_id, tmp_path: Path
    ):
        temp_directory = tmp_path / "qianchuan-preview-over-limit"
        temp_directory.mkdir()
        with patch("app.routers.operator_qianchuan_preview.VIDEO_MAX_BYTES", 1), patch(
            "app.routers.operator_qianchuan_preview.mkdtemp",
            return_value=str(temp_directory),
        ):
            response = await test_client.post(
                "/api/tools/qianchuan-preview/analyze-video",
                data={"kol_id": str(kol_id)},
                files={
                    "original": ("source.mp4", b"too-large", "video/mp4"),
                    "edited": ("edited.mp4", b"edited", "video/mp4"),
                },
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert response.status_code == 400
        assert response.json()["code"] == "VALIDATION_ERROR"
        row = (await test_session.execute(sa_text(
            "SELECT status FROM task_jobs WHERE tool_code='qianchuan-preview' ORDER BY id DESC LIMIT 1"
        ))).fetchone()
        assert row == ("failed",)
        assert not temp_directory.exists()

    @pytest.mark.asyncio
    async def test_local_temp_write_failure_marks_task_failed(self, test_client, operator_token, test_session, kol_id):
        with patch(
            "app.routers.operator_qianchuan_preview._write_video_to_temp",
            side_effect=OSError("磁盘不可写"),
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

        assert response.status_code == 500
        row = (await test_session.execute(sa_text(
            "SELECT status, error_code FROM task_jobs WHERE tool_code='qianchuan-preview' ORDER BY id DESC LIMIT 1"
        ))).fetchone()
        assert row == ("failed", "INTERNAL_ERROR")


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
    async def test_rejects_report_save_when_video_task_failed(self, test_client, operator_token, operator_user, test_session, kol_id):
        await test_session.execute(sa_text(
            "INSERT INTO task_jobs (task_no, tool_code, tool_name, status, input_payload, created_by) "
            "VALUES ('QV-SAVE-FAILED', 'qianchuan-preview', '千川成片预审', 'failed', "
            "CAST(:payload AS jsonb), :user_id)"
        ), {"user_id": operator_user.id, "payload": json.dumps({"mode": "full_video", "kol_id": kol_id})})
        await test_session.commit()
        task_id = (await test_session.execute(sa_text(
            "SELECT id FROM task_jobs WHERE task_no='QV-SAVE-FAILED'"
        ))).scalar_one()

        response = await test_client.post(
            "/api/tools/qianchuan-preview/save-video-report",
            json={
                "task_id": task_id,
                "report": "# 只生成了一半的报告",
                "original_filename": "source.mp4",
                "edited_filename": "edited.mov",
            },
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert response.json()["code"] == "VALIDATION_ERROR"

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
