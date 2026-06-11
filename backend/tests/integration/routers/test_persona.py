"""
Integration tests for persona-positioning router.
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


# ── kol-submissions tests ──────────────────────────────────────────

class TestKolSubmissions:

    @pytest.mark.asyncio
    async def test_list_kol_submissions(self, test_client, operator_headers):
        resp = await test_client.get("/api/persona/kol-submissions", headers=operator_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


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
