"""Integration tests for tool_extract_frames router."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/extract-frames",
            files={"file": ("v.mp4", b"fake", "video/mp4")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_file_returns_422(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/extract-frames",
            data={"count": "3"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 422  # FastAPI validation: file field missing


class TestExtractFrames:
    @pytest.mark.asyncio
    async def test_returns_frames_and_duration(self, test_client, operator_token):
        fake_frame_b64 = "data:image/jpeg;base64,/9j/fake"

        async def mock_extract(video_path, count):
            return [{"time": 0.0, "base64": fake_frame_b64}], 10.5

        with patch(
            "app.routers.tool_extract_frames._extract_frames",
            side_effect=mock_extract,
        ):
            resp = await test_client.post(
                "/api/tools/extract-frames",
                files={"file": ("v.mp4", b"fake_video_bytes", "video/mp4")},
                data={"count": "3"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "frames" in data
        assert "duration" in data
        assert data["duration"] == 10.5
        assert len(data["frames"]) == 1
        assert data["frames"][0]["base64"] == fake_frame_b64

    @pytest.mark.asyncio
    async def test_ffprobe_failure_returns_400(self, test_client, operator_token):
        async def mock_extract_fail(video_path, count):
            raise ValueError("无法读取视频时长")

        with patch(
            "app.routers.tool_extract_frames._extract_frames",
            side_effect=mock_extract_fail,
        ):
            resp = await test_client.post(
                "/api/tools/extract-frames",
                files={"file": ("v.mp4", b"bad_video", "video/mp4")},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 400
