"""
Integration tests for operator_intake_direct.py router.

Covers:
- POST /operator/intake/direct/start                — 新建会话（含 kol_id 校验 404）
- POST /operator/intake/direct/{session_id}/chat    — AI 对话（mock yunwu.chat）
- POST /operator/intake/direct/{session_id}/bridge  — AI 过渡语（mock + 静默降级）
- POST /operator/intake/direct/{session_id}/submit  — 提交（mock 后台任务）
- GET  /operator/intake/direct/{session_id}/status  — 轮询状态
- GET  /operator/intake/direct/{session_id}/download — 下载报告（含 ?token= query）
- GET  /operator/intake/direct/sessions             — 会话列表（隔离）

业务层错误（已提交 / AI 未配置）→ HTTP 200 + body success=false + code；
HTTPException（404 不存在/跨用户、409 重复提交、401 未授权、422 format）→ 真实 HTTP 码。

外部 adapter：
- yunwu_adapter.chat 用 AsyncMock patch 源头模块 `app.routers.operator_intake_direct.yunwu_adapter`
- _generate_operator_session_report 后台任务用 AsyncMock patch，避免真跑 AI / 文件生成
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.credential import AiModel
from app.models.kol import Kol
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeOperatorSession, KolIntakeQuestion,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_intake_tables(test_session):
    """每个测试前清理 kol_intake_* 表，避免 unique 冲突与数据污染。

    KolIntakeConfig.config_key 是 unique，而 router 固定查 'conversation_bridge'，
    不清理会让第二个 seed config 的测试 IntegrityError。
    """
    await test_session.execute(delete(KolIntakeOperatorSession))
    await test_session.execute(delete(KolIntakeConfig))
    await test_session.execute(delete(KolIntakeQuestion))
    await test_session.commit()
    yield


async def _seed_session(test_session, operator_user, **kwargs) -> KolIntakeOperatorSession:
    """seed 一个 KolIntakeOperatorSession，默认 report_status='pending'。"""
    sess = KolIntakeOperatorSession(operator_id=operator_user.id, **kwargs)
    test_session.add(sess)
    await test_session.commit()
    await test_session.refresh(sess)
    return sess


async def _seed_chat_config(
    test_session,
    *,
    ai_model_status: str = "active",
    system_prompt: str = "你是红人面试官",
) -> tuple[KolIntakeConfig, AiModel]:
    """seed conversation_bridge config + ai_model（ai_model.status 可控）。"""
    suffix = uuid.uuid4().hex[:8]
    ai_model = AiModel(
        name=f"cov_chat_{suffix}",
        provider="yunwu",
        model_id=f"cov-chat-model-{suffix}",
        status=ai_model_status,
    )
    test_session.add(ai_model)
    await test_session.commit()
    await test_session.refresh(ai_model)

    config = KolIntakeConfig(
        config_key="conversation_bridge",
        ai_model_id=int(ai_model.id),
        system_prompt=system_prompt,
        is_active=True,
    )
    test_session.add(config)
    await test_session.commit()
    await test_session.refresh(config)
    return config, ai_model


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------


class TestStartSession:
    @pytest.mark.asyncio
    async def test_start_no_kol_ok(self, test_client, operator_headers):
        """无 kol_id → 直接 start，返回 session_id。"""
        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert "session_id" in body["data"]
        assert body["data"]["kol_id"] is None
        assert body["data"]["kol_name"] is None

    @pytest.mark.asyncio
    async def test_start_with_kol_name_only(self, test_client, operator_headers):
        """只有 kol_name（无 kol_id）→ start OK。"""
        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={"kol_name": "测试红人"},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["kol_name"] == "测试红人"
        assert body["data"]["kol_id"] is None

    @pytest.mark.asyncio
    async def test_start_with_valid_kol_id(
        self, test_client, operator_headers, test_session
    ):
        """seed 一个 kol → start with kol_id → 200 + kol_id 回显。"""
        kol = Kol(name="cov_kol_start")
        test_session.add(kol)
        await test_session.commit()
        await test_session.refresh(kol)

        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={"kol_id": int(kol.id), "kol_name": "cov_kol_start"},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["kol_id"] == int(kol.id)

    @pytest.mark.asyncio
    async def test_start_nonexistent_kol_404(self, test_client, operator_headers):
        """不存在的 kol_id → HTTPException 404。"""
        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={"kol_id": 999999},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_with_deleted_kol_404(
        self, test_client, operator_headers, test_session
    ):
        """deleted_at 不为 null 的 kol → _get_active_kol 抛 404。"""
        from datetime import datetime, timezone
        kol = Kol(name="cov_deleted", deleted_at=datetime.now(tz=timezone.utc))
        test_session.add(kol)
        await test_session.commit()
        await test_session.refresh(kol)

        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={"kol_id": int(kol.id)},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_admin_role_ok(self, test_client, admin_headers):
        """admin 角色也能通过 require_operator。"""
        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @pytest.mark.asyncio
    async def test_start_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/intake/direct/start",
            json={},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{session_id}/chat
# ---------------------------------------------------------------------------


class TestSessionChat:
    @pytest.mark.asyncio
    async def test_chat_ok_mock_yunwu(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """seed session + config + active ai_model + mock yunwu → 200 + reply。"""
        sess = await _seed_session(test_session, operator_user)
        await _seed_chat_config(test_session)

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
            return_value="你好呀",
        ):
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/chat",
                json={"messages": [{"role": "user", "content": "你好"}]},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["reply"] == "你好呀"
        assert body["data"]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_chat_no_config_returns_null_reply(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """session 存在但 conversation_bridge config 未配置 → reply=None + error。"""
        sess = await _seed_session(test_session, operator_user)

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/chat",
            json={"messages": [{"role": "user", "content": "hi"}]},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] is None
        assert body["data"]["error"] == "AI对话暂未配置"

    @pytest.mark.asyncio
    async def test_chat_config_without_ai_model_id(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """config 存在但 ai_model_id=None → reply=None + error。"""
        sess = await _seed_session(test_session, operator_user)
        config = KolIntakeConfig(
            config_key="conversation_bridge",
            ai_model_id=None,
            system_prompt="x",
            is_active=True,
        )
        test_session.add(config)
        await test_session.commit()

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/chat",
            json={"messages": []},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] is None
        assert body["data"]["error"] == "AI对话暂未配置"

    @pytest.mark.asyncio
    async def test_chat_ai_model_inactive_returns_null(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """config 配了 ai_model_id，但 ai_model.status != 'active' → reply=None。"""
        sess = await _seed_session(test_session, operator_user)
        await _seed_chat_config(test_session, ai_model_status="inactive")

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/chat",
            json={"messages": []},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] is None
        assert body["data"]["error"] == "AI对话暂未配置"

    @pytest.mark.asyncio
    async def test_chat_session_already_submitted(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """session.report_status='generating' → error_response VALIDATION_ERROR。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="generating"
        )

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/chat",
            json={"messages": []},
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200  # error_response 默认 HTTP 200
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"
        assert "已提交" in body["message"]

    @pytest.mark.asyncio
    async def test_chat_nonexistent_session_404(self, test_client, operator_headers):
        resp = await test_client.post(
            "/api/operator/intake/direct/999999/chat",
            json={"messages": []},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_cross_user_404(
        self, test_client, admin_headers, test_session, operator_user
    ):
        """operator 创建的 session，admin 拿不到（_get_own_session 过滤 operator_id）。"""
        sess = await _seed_session(test_session, operator_user)

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/chat",
            json={"messages": []},
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/intake/direct/1/chat",
            json={"messages": []},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{session_id}/bridge
# ---------------------------------------------------------------------------


class TestSessionBridge:
    @pytest.mark.asyncio
    async def test_bridge_ok_mock_yunwu(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """seed config + active ai_model + mock yunwu → 200 + reply。"""
        sess = await _seed_session(test_session, operator_user)
        await _seed_chat_config(test_session)

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
            return_value="谢谢分享",
        ):
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/bridge",
                json={
                    "user_answer": "我是做美妆的",
                    "question_text": "你的内容方向？",
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["reply"] == "谢谢分享"

    @pytest.mark.asyncio
    async def test_bridge_yunwu_fails_silently(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """yunwu.chat 抛错 → 静默降级 reply=''（HTTP 200）。"""
        sess = await _seed_session(test_session, operator_user)
        await _seed_chat_config(test_session)

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("yunwu down"),
        ):
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/bridge",
                json={"user_answer": "x", "question_text": "y"},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["reply"] == ""

    @pytest.mark.asyncio
    async def test_bridge_no_config_returns_empty(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """config 不存在 → 直接返回 reply=''（不调 yunwu）。"""
        sess = await _seed_session(test_session, operator_user)

        # 显式断言 yunwu 不被调用
        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mocked:
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/bridge",
                json={"user_answer": "x", "question_text": "y"},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == ""
        mocked.assert_not_called()

    @pytest.mark.asyncio
    async def test_bridge_is_last_question_branch(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """is_last_question=True 走告别分支，mock yunwu → reply 正常返回。"""
        sess = await _seed_session(test_session, operator_user)
        await _seed_chat_config(test_session)

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
            return_value="辛苦了，可以提交了",
        ):
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/bridge",
                json={
                    "user_answer": "完了",
                    "question_text": "最后一题",
                    "is_last_question": True,
                },
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == "辛苦了，可以提交了"

    @pytest.mark.asyncio
    async def test_bridge_nonexistent_session_404(
        self, test_client, operator_headers
    ):
        resp = await test_client.post(
            "/api/operator/intake/direct/999999/bridge",
            json={"user_answer": "x", "question_text": "y"},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bridge_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/intake/direct/1/bridge",
            json={"user_answer": "x", "question_text": "y"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /{session_id}/submit
# ---------------------------------------------------------------------------


class TestSessionSubmit:
    @pytest.mark.asyncio
    async def test_submit_ok_mock_background_task(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """seed pending session + mock 后台任务 → 200 + report_status='generating'。"""
        sess = await _seed_session(test_session, operator_user)

        with patch(
            "app.routers.operator_intake_direct._generate_operator_session_report",
            new_callable=AsyncMock,
        ) as mocked_bg:
            resp = await test_client.post(
                f"/api/operator/intake/direct/{sess.id}/submit",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers=operator_headers,
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["report_status"] == "generating"
        # BackgroundTasks 在响应后执行（ASGITransport 会跑完）
        mocked_bg.assert_awaited_once_with(sess.id)

    @pytest.mark.asyncio
    async def test_submit_already_submitted_409(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """report_status='generating' → HTTPException 409。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="generating"
        )

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/submit",
            json={"messages": []},
            headers=operator_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_submit_ready_status_409(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """report_status='ready' → 同样不可重复提交 → 409。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="ready"
        )

        resp = await test_client.post(
            f"/api/operator/intake/direct/{sess.id}/submit",
            json={"messages": []},
            headers=operator_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_submit_nonexistent_session_404(
        self, test_client, operator_headers
    ):
        resp = await test_client.post(
            "/api/operator/intake/direct/999999/submit",
            json={"messages": []},
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_no_token_401(self, test_client):
        resp = await test_client.post(
            "/api/operator/intake/direct/1/submit",
            json={"messages": []},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /{session_id}/status
# ---------------------------------------------------------------------------


class TestSessionStatus:
    @pytest.mark.asyncio
    async def test_status_pending_ok(
        self, test_client, operator_headers, test_session, operator_user
    ):
        sess = await _seed_session(test_session, operator_user)

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/status",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["report_status"] == "pending"
        assert body["data"]["download_ready"] is False
        assert body["data"]["ai_report"] is None

    @pytest.mark.asyncio
    async def test_status_ready_with_report(
        self, test_client, operator_headers, test_session, operator_user
    ):
        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            ai_report="## 基本信息\n这是报告内容",
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/status",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["report_status"] == "ready"
        assert body["data"]["download_ready"] is True
        assert "基本信息" in body["data"]["ai_report"]

    @pytest.mark.asyncio
    async def test_status_nonexistent_session_404(
        self, test_client, operator_headers
    ):
        resp = await test_client.get(
            "/api/operator/intake/direct/999999/status",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_cross_user_404(
        self, test_client, admin_headers, test_session, operator_user
    ):
        """operator 的 session，admin 拿 → 404。"""
        sess = await _seed_session(test_session, operator_user)

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/status",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_no_token_401(self, test_client):
        resp = await test_client.get("/api/operator/intake/direct/1/status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /{session_id}/download
# ---------------------------------------------------------------------------


class TestSessionDownload:
    @pytest.mark.asyncio
    async def test_download_docx_ok(
        self, test_client, operator_headers, test_session, operator_user, tmp_path
    ):
        """seed ready session + 真实 docx 文件 → 200 FileResponse。"""
        file_path = tmp_path / "report.docx"
        file_path.write_bytes(b"fake docx content")

        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            docx_path=str(file_path),
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download?format=docx",
            headers=operator_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        # Starlette 对非 ASCII 文件名用 RFC 5987 编码：filename*=utf-8''...
        assert resp.headers["content-disposition"].startswith("attachment;")
        assert resp.headers["content-disposition"].endswith(".docx")

    @pytest.mark.asyncio
    async def test_download_pdf_with_query_token(
        self, test_client, operator_token, test_session, operator_user, tmp_path
    ):
        """无 Authorization header，用 ?token= 鉴权 → 200 PDF。"""
        file_path = tmp_path / "report.pdf"
        file_path.write_bytes(b"fake pdf content")

        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            pdf_path=str(file_path),
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download"
            f"?format=pdf&token={operator_token}",
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.headers["content-disposition"].startswith("attachment;")
        assert resp.headers["content-disposition"].endswith(".pdf")

    @pytest.mark.asyncio
    async def test_download_no_auth_401(self, test_client):
        """无 header 也无 query token → 401 AUTH_TOKEN_MISSING。"""
        resp = await test_client.get(
            "/api/operator/intake/direct/1/download",
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_download_invalid_query_token_401(
        self, test_client, test_session, operator_user
    ):
        """无效 token 字符串 → verify_token 抛错 → user=None → 401。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="ready", docx_path="/x"
        )
        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download?token=invalid_jwt_xyz",
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_download_report_not_ready_404(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """report_status != 'ready' → HTTPException 404 '报告尚未生成'。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="generating"
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_file_missing_on_disk_404(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """report_status=ready 但 docx_path 指向不存在的文件 → 404。"""
        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            docx_path="/nonexistent/path/xyz.docx",
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_pdf_path_missing_404(
        self, test_client, operator_headers, test_session, operator_user, tmp_path
    ):
        """format=pdf 但只有 docx_path → pdf_path=None → '报告文件不存在' 404。"""
        file_path = tmp_path / "report.docx"
        file_path.write_bytes(b"x")

        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            docx_path=str(file_path),
            pdf_path=None,
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download?format=pdf",
            headers=operator_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_cross_user_404(
        self, test_client, admin_headers, test_session, operator_user, tmp_path
    ):
        """operator 的 session，admin 拿 → _get_own_session 过滤 → 404。"""
        file_path = tmp_path / "report.docx"
        file_path.write_bytes(b"x")

        sess = await _seed_session(
            test_session,
            operator_user,
            report_status="ready",
            docx_path=str(file_path),
        )

        resp = await test_client.get(
            f"/api/operator/intake/direct/{sess.id}/download",
            headers=admin_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_invalid_format_422(
        self, test_client, operator_headers
    ):
        """format=xyz 不符合 pattern → FastAPI 422。"""
        resp = await test_client.get(
            "/api/operator/intake/direct/1/download?format=xyz",
            headers=operator_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_empty_ok(self, test_client, operator_headers):
        """无 session → 200 + 空列表。"""
        resp = await test_client.get(
            "/api/operator/intake/direct/sessions",
            headers=operator_headers,
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 0

    @pytest.mark.asyncio
    async def test_list_returns_own_sessions_only(
        self, test_client, test_session, operator_headers, admin_headers,
        operator_user, admin_user,
    ):
        """operator 创建 2 个 + admin 创建 1 个 → operator 看到 2 个，admin 看到 1 个。"""
        test_session.add_all([
            KolIntakeOperatorSession(operator_id=operator_user.id, kol_name="A"),
            KolIntakeOperatorSession(operator_id=operator_user.id, kol_name="B"),
            KolIntakeOperatorSession(operator_id=admin_user.id, kol_name="C"),
        ])
        await test_session.commit()

        resp_op = await test_client.get(
            "/api/operator/intake/direct/sessions",
            headers=operator_headers,
        )
        body_op = resp_op.json()
        assert resp_op.status_code == 200
        assert len(body_op["data"]) == 2
        assert {s["kol_name"] for s in body_op["data"]} == {"A", "B"}

        resp_ad = await test_client.get(
            "/api/operator/intake/direct/sessions",
            headers=admin_headers,
        )
        body_ad = resp_ad.json()
        assert resp_ad.status_code == 200
        assert len(body_ad["data"]) == 1
        assert body_ad["data"][0]["kol_name"] == "C"

    @pytest.mark.asyncio
    async def test_list_session_structure(
        self, test_client, operator_headers, test_session, operator_user
    ):
        """验证 list item 的字段结构与契约一致。"""
        sess = KolIntakeOperatorSession(
            operator_id=operator_user.id,
            kol_name="cov_struct",
            report_status="ready",
            ai_report="报告内容",
        )
        test_session.add(sess)
        await test_session.commit()

        resp = await test_client.get(
            "/api/operator/intake/direct/sessions",
            headers=operator_headers,
        )
        body = resp.json()
        item = body["data"][0]
        # 字段全部存在
        for key in (
            "id", "kol_name", "report_status",
            "ai_report", "report_generated_at", "created_at",
        ):
            assert key in item, f"missing field {key}"
        assert item["kol_name"] == "cov_struct"
        assert item["report_status"] == "ready"
        assert item["ai_report"] == "报告内容"
        # messages 字段不在列表返回（避免大数据回传）
        assert "messages" not in item

    @pytest.mark.asyncio
    async def test_list_no_token_401(self, test_client):
        resp = await test_client.get(
            "/api/operator/intake/direct/sessions",
        )
        assert resp.status_code == 401
