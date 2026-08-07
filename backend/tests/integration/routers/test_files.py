"""
Integration tests for files.py router.

Covers:
- GET    /files                        — 当前用户文件列表 + page_size clamp + output_id 过滤
- POST   /files                        — 上传到 OSS（mock adapter；空文件 400；OSS 失败 500）
- GET    /files/{id}/download-url      — 签名 URL（含越权拒绝）
- DELETE /files/{id}                   — 软删除（含越权拒绝）
- Auth: 401（无 token）

注：业务层错误（越权）用 error_response 返回 HTTP 200 + body success=false；
   只有 HTTPException 才返回真实 HTTP 错误码（400/500/401）。
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.models.file import File


class TestFiles:
    @pytest.mark.asyncio
    async def test_list_files_operator_ok(self, test_client, operator_headers):
        """GET /files → 200 + items + pagination。"""
        resp = await test_client.get("/api/files", headers=operator_headers)
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert "items" in body["data"]
        assert "pagination" in body["data"]

    @pytest.mark.asyncio
    async def test_list_files_page_size_clamp(self, test_client, operator_headers):
        """非法 page_size → 回退 20。"""
        resp = await test_client.get(
            "/api/files?page_size=99", headers=operator_headers
        )
        assert resp.json()["data"]["pagination"]["page_size"] == 20

    @pytest.mark.asyncio
    async def test_list_files_filter_by_output_empty(
        self, test_client, operator_headers
    ):
        """?output_id=不存在的 → total 0。"""
        resp = await test_client.get(
            "/api/files?output_id=999999", headers=operator_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_upload_file_ok(self, test_client, operator_headers):
        """mock OSS upload → 上传成功，files 表写入。"""
        with patch("app.adapters.oss.upload_file", new_callable=AsyncMock):
            resp = await test_client.post(
                "/api/files",
                headers=operator_headers,
                files={"file": ("cov_upload.txt", b"hello world", "text/plain")},
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["filename"] == "cov_upload.txt"
        assert body["data"]["file_size"] == 11

    @pytest.mark.asyncio
    async def test_upload_empty_file_400(self, test_client, operator_headers):
        """空文件 → 400 INVALID_INPUT。"""
        resp = await test_client.post(
            "/api/files",
            headers=operator_headers,
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_oss_fail_500(self, test_client, operator_headers):
        """OSS adapter 抛错 → 500 OSS_UPLOAD_FAILED。"""
        with patch(
            "app.adapters.oss.upload_file",
            new_callable=AsyncMock,
            side_effect=Exception("oss down"),
        ):
            resp = await test_client.post(
                "/api/files",
                headers=operator_headers,
                files={"file": ("cov.txt", b"hello", "text/plain")},
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_download_url_own_file_ok(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """自己的文件 + mock OSS → 200 + 签名 URL。"""
        f = File(
            filename="cov_dl.txt",
            file_size=10,
            oss_key="uploads/cov/dl",
            content_type="text/plain",
            created_by=operator_user.id,
        )
        test_session.add(f)
        await test_session.commit()
        await test_session.refresh(f)

        with patch(
            "app.adapters.oss.get_download_url",
            new_callable=AsyncMock,
            return_value="https://signed.url/cov",
        ):
            resp = await test_client.get(
                f"/api/files/{f.id}/download-url", headers=operator_headers
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["download_url"] == "https://signed.url/cov"

    @pytest.mark.asyncio
    async def test_download_url_others_file_denied(
        self, test_client, operator_headers, test_session, admin_user
    ):
        """admin 的文件，operator 拿 → 业务层拒绝（HTTP 200 + success=false）。"""
        f = File(
            filename="cov_admin.txt",
            file_size=10,
            oss_key="uploads/cov/admin",
            content_type="text/plain",
            created_by=admin_user.id,
        )
        test_session.add(f)
        await test_session.commit()
        await test_session.refresh(f)

        resp = await test_client.get(
            f"/api/files/{f.id}/download-url", headers=operator_headers
        )
        body = resp.json()
        assert body["success"] is False
        assert body["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_delete_file_ok(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """自己的文件 + mock OSS → 软删除成功。"""
        f = File(
            filename="cov_del.txt",
            file_size=5,
            oss_key="uploads/cov/del",
            content_type="text/plain",
            created_by=operator_user.id,
        )
        test_session.add(f)
        await test_session.commit()
        await test_session.refresh(f)

        with patch("app.adapters.oss.delete_file", new_callable=AsyncMock):
            resp = await test_client.delete(
                f"/api/files/{f.id}", headers=operator_headers
            )
        assert resp.status_code == 200
        assert resp.json()["message"] == "文件已删除"

    @pytest.mark.asyncio
    async def test_list_files_no_token_401(self, test_client):
        resp = await test_client.get("/api/files")
        assert resp.status_code == 401
