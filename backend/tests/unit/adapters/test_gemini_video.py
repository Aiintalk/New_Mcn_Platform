from pathlib import Path

import httpx
import pytest

from app.adapters.gemini_video import _upload_complete_video


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
