"""Integration tests for operator_tiktok_review router."""
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from passlib.context import CryptContext
from sqlalchemy import text as sa_text

from app.core.security import create_access_token
from app.models.user import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(autouse=True)
async def seed_tr_config(test_session):
    await test_session.execute(sa_text(
        "INSERT INTO tiktok_review_configs (config_key, system_prompt, is_active) "
        "VALUES ('default', 'Test Prompt', true) ON CONFLICT (config_key) DO NOTHING"
    ))
    await test_session.commit()
    yield


# ---------- Auth ----------

class TestAuth:
    @pytest.mark.asyncio
    async def test_generate_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "a", "original_likes": "1万",
                  "copycat_transcript": "b", "copycat_likes": "500"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_save_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "报告内容", "title": "TT复盘"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_outputs_unauthorized(self, test_client):
        resp = await test_client.get("/api/tools/tiktok-review/outputs")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_export_word_unauthorized(self, test_client):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "报告内容"},
        )
        assert resp.status_code == 401


# ---------- generate ----------

class TestGenerate:
    @pytest.mark.asyncio
    async def test_both_empty_transcripts_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "   ", "original_likes": "",
                  "copycat_transcript": "", "copycat_likes": ""},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_no_config_returns_503(self, test_client, operator_token, test_session):
        await test_session.execute(sa_text(
            "UPDATE tiktok_review_configs SET is_active = false WHERE config_key = 'default'"
        ))
        await test_session.commit()
        resp = await test_client.post(
            "/api/tools/tiktok-review/generate",
            json={"original_transcript": "原版文案", "original_likes": "1万",
                  "copycat_transcript": "仿写文案", "copycat_likes": "500"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 503
        assert resp.json()["code"] == "CONFIG_NOT_FOUND"
        # 恢复
        await test_session.execute(sa_text(
            "UPDATE tiktok_review_configs SET is_active = true WHERE config_key = 'default'"
        ))
        await test_session.commit()

    @pytest.mark.asyncio
    async def test_generate_streams_text(self, test_client, operator_token):
        async def fake_stream(*args, **kwargs):
            yield "复盘"
            yield "结果"

        with patch(
            "app.routers.operator_tiktok_review.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/tiktok-review/generate",
                json={"original_transcript": "原版文案", "original_likes": "1万",
                      "copycat_transcript": "仿写文案", "copycat_likes": "500"},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "复盘" in resp.text
        assert "x-task-id" in resp.headers

    @pytest.mark.asyncio
    async def test_generate_only_one_side_ok(self, test_client, operator_token):
        """只填原版文案（仿写版为空）应允许生成。"""
        async def fake_stream(*args, **kwargs):
            yield "ok"

        with patch(
            "app.routers.operator_tiktok_review.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/tiktok-review/generate",
                json={"original_transcript": "原版文案", "original_likes": "1万",
                      "copycat_transcript": "", "copycat_likes": ""},
                headers={"Authorization": f"Bearer {operator_token}"},
            )
        assert resp.status_code == 200


# ---------- save ----------

class TestSave:
    @pytest.mark.asyncio
    async def test_save_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "  ", "title": "TT复盘"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_save_creates_output(self, test_client, operator_token, test_session):
        resp = await test_client.post(
            "/api/tools/tiktok-review/save",
            json={"content": "这是完整的复盘报告", "title": "TT复盘_2026-06-18"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "output_id" in data["data"]
        assert isinstance(data["data"]["output_id"], int)


# ---------- outputs ----------

class TestOutputs:
    @pytest.mark.asyncio
    async def test_outputs_returns_list(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "items" in data["data"]
        assert "total" in data["data"]

    @pytest.mark.asyncio
    async def test_outputs_pagination(self, test_client, operator_token):
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs?page=1&size=5",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200


# ---------- export-word ----------

class TestExportWord:
    @pytest.mark.asyncio
    async def test_empty_content_returns_400(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "  "},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_export_returns_docx(self, test_client, operator_token):
        import io
        from docx import Document
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "## 开头钩子\n**原版**：开门见山\n**仿写版**：略显平淡"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]
        doc = Document(io.BytesIO(resp.content))
        texts = " ".join(p.text for p in doc.paragraphs)
        assert "TT" in texts or "复盘" in texts

    @pytest.mark.asyncio
    async def test_export_content_disposition(self, test_client, operator_token):
        resp = await test_client.post(
            "/api/tools/tiktok-review/export-word",
            json={"content": "报告内容"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "TT" in cd or "tiktok" in cd.lower()


# ---------- Permission ----------

class TestPermission:
    @pytest.mark.asyncio
    async def test_force_change_password_returns_403(self, test_client, test_session):
        """password_changed_at=None 的用户访问任意接口返回 403。"""
        suffix = uuid.uuid4().hex[:8]
        user = User(
            username=f"test_no_pwd_{suffix}",
            real_name="未改密",
            password_hash=_pwd_context.hash("Test@123456"),
            role="operator",
            status="enabled",
            password_changed_at=None,
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)
        token = create_access_token(
            user_id=int(user.id),
            username=str(user.username),
            role=str(user.role),
            token_version=int(user.token_version),
        )
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "AUTH_FORCE_CHANGE_PASSWORD"

    @pytest.mark.asyncio
    async def test_wrong_role_returns_403(self, test_client, test_session):
        """role=viewer 的用户访问运营端接口返回 403。"""
        suffix = uuid.uuid4().hex[:8]
        user = User(
            username=f"test_viewer_{suffix}",
            real_name="只读用户",
            password_hash=_pwd_context.hash("Test@123456"),
            role="viewer",
            status="enabled",
            password_changed_at=datetime.now(tz=timezone.utc),
        )
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)
        token = create_access_token(
            user_id=int(user.id),
            username=str(user.username),
            role=str(user.role),
            token_version=int(user.token_version),
        )
        resp = await test_client.get(
            "/api/tools/tiktok-review/outputs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_generate_with_forwarded_ip(self, test_client, operator_token):
        """X-Forwarded-For header 应被正确解析（覆盖 _get_ip 分支）。"""
        async def fake_stream(*args, **kwargs):
            yield "ok"

        with patch(
            "app.routers.operator_tiktok_review.yunwu_adapter.chat_stream",
            side_effect=fake_stream,
        ):
            resp = await test_client.post(
                "/api/tools/tiktok-review/generate",
                json={"original_transcript": "内容", "original_likes": "1万",
                      "copycat_transcript": "", "copycat_likes": ""},
                headers={
                    "Authorization": f"Bearer {operator_token}",
                    "X-Forwarded-For": "10.0.0.1, 192.168.1.1",
                },
            )
        assert resp.status_code == 200
