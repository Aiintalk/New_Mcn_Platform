from pathlib import Path

import httpx
import pytest

from unittest.mock import AsyncMock, patch

from app.adapters import gemini_video
from app.adapters.gemini_video import _upload_complete_video
from app.models.log import AiCallLog, ExternalServiceLog


@pytest.mark.asyncio
async def test_upload_complete_video_sends_entire_file_not_frames(tmp_path: Path):
    """供应商上传请求必须含原始完整字节，不允许在适配器中抽帧。"""
    video = tmp_path / "original.mp4"
    complete_video = b"begin-frame" + (b"middle-video-data" * 3) + b"final-frame"
    video.write_bytes(complete_video)
    received: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/upload/v1beta/files"):
            return httpx.Response(200, headers={"x-goog-upload-url": "https://upload.example/upload"})
        if request.url.host == "upload.example":
            received.append(await request.aread())
            return httpx.Response(200, json={"file": {"name": "files/original", "uri": "gemini://files/original"}})
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _upload_complete_video(
            client,
            base_url="https://gemini.example",
            api_key="test-key",
            path=video,
            content_type="video/mp4",
            display_name="原片",
        )

    assert received == [complete_video]
    assert result["uri"] == "gemini://files/original"


class _FakeResponse:
    def __init__(self, *, headers=None, payload=None):
        self.headers = headers or {}
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        yield 'data: {"candidates":[{"content":{"parts":[{"text":"完整报告"}]}}]}'


class _FakeGeminiClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        if str(url).endswith('/upload/v1beta/files'):
            return _FakeResponse(headers={"x-goog-upload-url": "https://upload.example/upload"})
        return _FakeResponse(payload={"file": {"name": "files/video", "uri": "gemini://files/video"}})

    async def get(self, *args, **kwargs):
        return _FakeResponse(payload={"file": {"name": "files/video", "uri": "gemini://files/video", "state": "ACTIVE"}})

    def stream(self, *args, **kwargs):
        return _FakeStream()

    async def delete(self, *args, **kwargs):
        return _FakeResponse()


class _FakeDb:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_full_video_adapter_keeps_ai_pool_id_out_of_external_service_log(tmp_path: Path):
    original = tmp_path / "original.mp4"
    edited = tmp_path / "edited.mp4"
    original.write_bytes(b"original-complete-video")
    edited.write_bytes(b"edited-complete-video")
    db = _FakeDb()

    with patch.object(gemini_video.credential_pool, "_pick_and_lock", new=AsyncMock(return_value=(71, "test-key", "https://gemini.example"))), patch.object(
        gemini_video.credential_pool, "_release", new=AsyncMock()
    ), patch.object(gemini_video.httpx, "AsyncClient", _FakeGeminiClient):
        chunks = [chunk async for chunk in gemini_video.stream_full_video_analysis(
            original_path=original,
            edited_path=edited,
            original_content_type="video/mp4",
            edited_content_type="video/mp4",
            system_prompt="完整视频提示词",
            model_id="gemini-test",
            db=db,
            user_id=1,
            task_id=88,
        )]

    assert "完整报告" in "".join(chunks)
    ai_log = next(item for item in db.added if isinstance(item, AiCallLog))
    external_log = next(item for item in db.added if isinstance(item, ExternalServiceLog) and item.action == "qianchuan_preview_full_video")
    assert ai_log.credential_id == 71
    assert external_log.credential_id is None


@pytest.mark.asyncio
async def test_full_video_adapter_records_gemini_cleanup_failure_against_task(tmp_path: Path):
    original = tmp_path / "original.mp4"
    edited = tmp_path / "edited.mp4"
    original.write_bytes(b"original-complete-video")
    edited.write_bytes(b"edited-complete-video")
    db = _FakeDb()

    with patch.object(gemini_video.credential_pool, "_pick_and_lock", new=AsyncMock(return_value=(71, "test-key", "https://gemini.example"))), patch.object(
        gemini_video.credential_pool, "_release", new=AsyncMock()
    ), patch.object(gemini_video.httpx, "AsyncClient", _FakeGeminiClient), patch.object(
        gemini_video, "_delete_file", new=AsyncMock(side_effect=RuntimeError("Gemini 删除失败"))
    ):
        _ = [chunk async for chunk in gemini_video.stream_full_video_analysis(
            original_path=original,
            edited_path=edited,
            original_content_type="video/mp4",
            edited_content_type="video/mp4",
            system_prompt="完整视频提示词",
            model_id="gemini-test",
            db=db,
            user_id=1,
            task_id=89,
        )]

    cleanup_logs = [
        item for item in db.added
        if isinstance(item, ExternalServiceLog) and item.action == "qianchuan_preview_full_video_cleanup"
    ]
    assert len(cleanup_logs) == 2
    assert {item.task_id for item in cleanup_logs} == {89}
    assert all(item.status == "error" for item in cleanup_logs)
