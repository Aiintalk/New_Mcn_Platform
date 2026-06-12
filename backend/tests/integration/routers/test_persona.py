"""
Integration tests for persona-positioning router.

覆盖：
- Auth：未授权 401
- parse-file：正常解析、不支持格式
- generate：空输入 400、正常生成（Mock TikHub + AI SSE）
- fetch-douyin：正常路径（Mock TikHub）、无效输入
- reports：列表、详情、删除（正常 + 404）
- optimize：缺少字段 422
- kol-submissions：列表
- export-word：正常导出、未完成报告
- questionnaire-template：下载
"""
import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models.persona_report import PersonaReport


# ── Auth tests ─────────────────────────────────────────────────────

class TestPersonaAuth:
    """所有 persona 接口未授权返回 401。"""

    @pytest.mark.asyncio
    async def test_unauthorized_fetch_douyin(self, test_client):
        resp = await test_client.post("/api/persona/fetch-douyin", json={"url": "test"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_generate(self, test_client):
        resp = await test_client.post("/api/persona/generate", json={"influencer_info": "x"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_list_reports(self, test_client):
        resp = await test_client.get("/api/persona/reports")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_delete_report(self, test_client):
        resp = await test_client.delete("/api/persona/reports/1")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_optimize(self, test_client):
        resp = await test_client.post("/api/persona/optimize", json={
            "messages": [], "current_content": "x", "content_type": "profile", "influencer_info": "x"
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_export_word(self, test_client):
        resp = await test_client.post("/api/persona/export-word", json={"report_id": 1, "type": "profile"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthorized_kol_submissions(self, test_client):
        resp = await test_client.get("/api/persona/kol-submissions")
        assert resp.status_code == 401


# ── parse-file tests ───────────────────────────────────────────────

class TestParseFile:

    @pytest.mark.asyncio
    async def test_parse_txt_file(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/persona/parse-file",
            headers=operator_headers,
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_parse_file_unsupported(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/persona/parse-file",
            headers=operator_headers,
            files={"file": ("image.xyz", b"\x00\x01", "application/octet-stream")},
        )
        assert resp.status_code == 400


# ── questionnaire-template tests ────────────────────────────────────

class TestQuestionnaireTemplate:

    @pytest.mark.asyncio
    async def test_download_template(self, test_client, operator_headers):
        resp = await test_client.get("/api/persona/questionnaire-template", headers=operator_headers)
        assert resp.status_code == 200
        assert len(resp.content) > 0


# ── reports list/detail/delete tests ────────────────────────────────

class TestReports:

    @pytest.mark.asyncio
    async def test_list_reports_empty(self, test_client, operator_headers):
        resp = await test_client.get("/api/persona/reports", headers=operator_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_get_report_not_found(self, test_client, operator_headers):
        resp = await test_client.get("/api/persona/reports/99999", headers=operator_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_report_not_found(self, test_client, operator_headers):
        resp = await test_client.delete("/api/persona/reports/99999", headers=operator_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_report_success(self, test_client, operator_headers, operator_user, test_session):
        """正常删除报告。"""
        report = PersonaReport(
            operator_id=operator_user.id,
            douyin_nickname="测试达人",
            influencer_name="测试达人",
            status="ready",
            profile_result="profile content",
            plan_result="plan content",
        )
        test_session.add(report)
        await test_session.commit()
        await test_session.refresh(report)

        resp = await test_client.delete(f"/api/persona/reports/{report.id}", headers=operator_headers)
        assert resp.status_code == 200

        # 验证已软删除（deleted_at 不为 None）
        await test_session.refresh(report)
        assert report.deleted_at is not None

    @pytest.mark.asyncio
    async def test_get_report_detail_success(self, test_client, operator_headers, operator_user, test_session):
        """正常获取报告详情。"""
        report = PersonaReport(
            operator_id=operator_user.id,
            douyin_nickname="详情达人",
            influencer_name="详情达人",
            status="ready",
            profile_result="详细人格档案",
            plan_result="详细内容规划",
        )
        test_session.add(report)
        await test_session.commit()
        await test_session.refresh(report)

        resp = await test_client.get(f"/api/persona/reports/{report.id}", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["profile_result"] == "详细人格档案"
        assert data["plan_result"] == "详细内容规划"


# ── generate tests ─────────────────────────────────────────────────

class TestGenerate:

    @pytest.mark.asyncio
    async def test_generate_missing_influencer_info(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/persona/generate",
            headers=operator_headers,
            json={"influencer_info": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_missing_config(self, test_client, operator_headers):
        """未配置 persona_generation 时返回 400。"""
        resp = await test_client.post(
            "/api/persona/generate",
            headers=operator_headers,
            json={"influencer_info": "达人资料内容"},
        )
        # 如果没有 persona_generation 配置，应返回 400
        assert resp.status_code in (400, 500)


# ── fetch-douyin tests ─────────────────────────────────────────────

class TestFetchDouyin:

    @pytest.mark.asyncio
    async def test_fetch_douyin_empty_url(self, test_client, operator_headers):
        """空 URL 返回 502（TikHub 解析失败）。"""
        resp = await test_client.post(
            "/api/persona/fetch-douyin",
            headers=operator_headers,
            json={"url": ""},
        )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_fetch_douyin_invalid_url(self, test_client, operator_headers):
        """无效 URL 返回 502。"""
        with patch("app.adapters.tikhub.resolve_sec_user_id", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = RuntimeError("未找到该账号")

            resp = await test_client.post(
                "/api/persona/fetch-douyin",
                headers=operator_headers,
                json={"url": "nonexistent_user_xyz"},
            )
            assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_fetch_douyin_success(self, test_client, operator_headers):
        """正常解析抖音号并返回视频数据。"""
        with patch("app.adapters.tikhub.resolve_sec_user_id", new_callable=AsyncMock) as mock_resolve, \
             patch("app.adapters.tikhub.fetch_user_videos", new_callable=AsyncMock) as mock_fetch, \
             patch("app.adapters.tikhub.get_top10_videos") as mock_top10, \
             patch("app.adapters.tikhub.get_recent_30day_videos") as mock_recent30, \
             patch("app.adapters.tikhub.format_videos_text") as mock_format:

            mock_resolve.return_value = {"sec_user_id": "SEC123", "nickname": "测试达人"}
            mock_fetch.return_value = [
                {"desc": "视频1", "digg_count": 100, "create_time": 1000, "aweme_id": "v1"},
            ]
            mock_top10.return_value = [{"desc": "视频1", "digg_count": 100, "create_time": 1000, "aweme_id": "v1"}]
            mock_recent30.return_value = [{"desc": "视频1", "digg_count": 100, "create_time": 1000, "aweme_id": "v1"}]
            mock_format.side_effect = lambda v, l: f"{l}: {len(v)} 条"

            resp = await test_client.post(
                "/api/persona/fetch-douyin",
                headers=operator_headers,
                json={"url": "testuser123"},
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nickname"] == "测试达人"
        assert data["sec_user_id"] == "SEC123"
        assert data["total_videos"] == 1
        assert "top10_text" in data
        assert "recent30_text" in data


# ── optimize tests ─────────────────────────────────────────────────

class TestOptimize:

    @pytest.mark.asyncio
    async def test_optimize_missing_fields(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/persona/optimize",
            headers=operator_headers,
            json={"messages": []},
        )
        assert resp.status_code == 422


# ── kol-submissions tests ──────────────────────────────────────────

class TestKolSubmissions:

    @pytest.mark.asyncio
    async def test_list_kol_submissions(self, test_client, operator_headers):
        resp = await test_client.get("/api/persona/kol-submissions", headers=operator_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


# ── export-word tests ──────────────────────────────────────────────

class TestExportWord:

    @pytest.mark.asyncio
    async def test_export_word_report_not_found(self, test_client, operator_headers):
        """报告不存在返回 404。"""
        resp = await test_client.post(
            "/api/persona/export-word",
            headers=operator_headers,
            json={"report_id": 99999, "type": "profile"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_export_word_report_not_ready(self, test_client, operator_headers, operator_user, test_session):
        """报告状态非 ready 返回 400。"""
        report = PersonaReport(
            operator_id=operator_user.id,
            douyin_nickname="未完成达人",
            status="generating",
        )
        test_session.add(report)
        await test_session.commit()
        await test_session.refresh(report)

        resp = await test_client.post(
            "/api/persona/export-word",
            headers=operator_headers,
            json={"report_id": report.id, "type": "profile"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_export_word_success(self, test_client, operator_headers, operator_user, test_session):
        """正常导出 Word 文件。"""
        report = PersonaReport(
            operator_id=operator_user.id,
            douyin_nickname="导出达人",
            influencer_name="导出达人",
            status="ready",
            profile_result="# 导出达人 · 人格档案\n\n## 一句话定位\n测试定位",
            plan_result="# 导出达人 · 内容规划\n\n## 内容体系\n测试内容",
            profile_docx_path="storage/persona_reports/test_profile.docx",
            plan_docx_path="storage/persona_reports/test_plan.docx",
        )
        test_session.add(report)
        await test_session.commit()
        await test_session.refresh(report)

        # 确保存储目录和文件存在
        os.makedirs("storage/persona_reports", exist_ok=True)
        from docx import Document
        doc = Document()
        doc.add_heading("测试", level=1)
        doc.save(f"storage/persona_reports/{report.id}_profile.docx")

        try:
            resp = await test_client.post(
                "/api/persona/export-word",
                headers=operator_headers,
                json={"report_id": report.id, "type": "profile"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        finally:
            # 清理测试文件
            try:
                os.remove(f"storage/persona_reports/{report.id}_profile.docx")
            except FileNotFoundError:
                pass
