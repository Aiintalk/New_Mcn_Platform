"""Integration tests for tool_export_word router."""
from urllib.parse import unquote

import pytest


class TestAuth:
    @pytest.mark.asyncio
    async def test_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "# 标题\n内容", "title": "测试报告"},
        )
        assert resp.status_code == 401


class TestExportWord:
    @pytest.mark.asyncio
    async def test_returns_docx_file(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "# 开头剪辑\n\n## 时长与删减\n\n- 删掉第5秒到第8秒", "title": "千川剪辑预审报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "application/vnd.openxmlformats" in resp.headers["content-type"]
        assert "content-disposition" in resp.headers
        assert "千川预审报告_" in unquote(resp.headers["content-disposition"])
        assert len(resp.content) > 1000

    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "", "title": "报告"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_default_title_when_omitted(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/export-word",
            json={"content": "## 节奏问题\n\n内容很好"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "千川预审报告_" in unquote(resp.headers["content-disposition"])
