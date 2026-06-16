"""Integration tests for tool_transcribe router."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/transcribe",
            files={"file": ("v.mp4", b"fake", "video/mp4")},
        )
        assert resp.status_code == 401


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_file_too_large_returns_400(self, test_client, operator_token):
        big_content = b"x" * (26 * 1024 * 1024)
        resp = await test_client.post(
            "/api/tools/transcribe",
            files={"file": ("big.mp4", big_content, "video/mp4")},
            data={"language": "zh"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_success_returns_text(self, test_client, operator_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "这是转录的文字内容"}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.routers.tool_transcribe.httpx.AsyncClient", return_value=mock_client):
            resp = await test_client.post(
                "/api/tools/transcribe",
                files={"file": ("v.mp4", b"fake_video", "video/mp4")},
                data={"language": "zh"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["text"] == "这是转录的文字内容"

    @pytest.mark.asyncio
    async def test_upstream_429_retries_and_fails(self, test_client, operator_token):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.routers.tool_transcribe.httpx.AsyncClient", return_value=mock_client), \
             patch("app.routers.tool_transcribe.asyncio.sleep", new_callable=AsyncMock):
            resp = await test_client.post(
                "/api/tools/transcribe",
                files={"file": ("v.mp4", b"fake_video", "video/mp4")},
                headers={"Authorization": f"Bearer {operator_token}"},
            )

        assert resp.status_code == 502
        assert mock_client.post.call_count == 3
