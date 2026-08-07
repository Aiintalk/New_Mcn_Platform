"""
Integration tests for intake_public.py router.

公开接口（无需鉴权）：
- GET  /intake/questions               — 启用题目列表
- GET  /intake/{token}                 — 校验链接 + 初始状态（含首次写入 used_at）
- POST /intake/{token}/chat            — AI 多轮对话（mock yunwu）
- POST /intake/{token}/bridge          — AI 过渡语（mock yunwu，失败静默降级）
- POST /intake/{token}/submit          — 提交对话（mock 后台报告任务）
- GET  /intake/{token}/status          — 报告生成状态
- GET  /intake/{token}/download        — 博主下载报告（FileResponse）

错误信封约定：
- HTTPException → 真实 HTTP 码（404/410/409/422）
- error_response → HTTP 200 + body success=false + code
- success_response → HTTP 200 + body success=true
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.models.credential import AiModel
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeLink, KolIntakeQuestion, KolIntakeSubmission,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


def _past() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=24)


def _token() -> str:
    return f"tok_{uuid.uuid4().hex[:16]}"


async def _seed_link(
    test_session, operator_user, *, token=None, expires_at=None,
    submitted_at=None, used_at=None, kol_name="测试红人",
):
    """种子一个 KolIntakeLink，返回 link 对象（已 commit+refresh）。"""
    link = KolIntakeLink(
        token=token or _token(),
        operator_id=operator_user.id,
        kol_name=kol_name,
        expires_at=expires_at or _future(),
        used_at=used_at,
        submitted_at=submitted_at,
    )
    test_session.add(link)
    await test_session.commit()
    await test_session.refresh(link)
    return link


async def _seed_question(
    test_session, *, order_num, category="基本信息",
    question_text=None, is_required=True, is_active=True,
    question_type="text", max_items=None,
):
    q = KolIntakeQuestion(
        order_num=order_num,
        category=category,
        question_text=question_text or f"问题 {order_num}",
        question_type=question_type,
        max_items=max_items,
        is_required=is_required,
        is_active=is_active,
    )
    test_session.add(q)
    await test_session.commit()
    await test_session.refresh(q)
    return q


async def _seed_ai_model(test_session, *, status="active", provider="yunwu"):
    """种子一个 AiModel，返回 model 对象。"""
    m = AiModel(
        name=f"测试模型 {uuid.uuid4().hex[:6]}",
        provider=provider,
        model_id=f"test-model-{uuid.uuid4().hex[:10]}",
        status=status,
    )
    test_session.add(m)
    await test_session.commit()
    await test_session.refresh(m)
    return m


async def _seed_bridge_config(test_session, ai_model, system_prompt=None):
    """种子 conversation_bridge 配置。

    config_key 有唯一约束，且 test_session 不在测试间回滚，
    因此先删除已有记录再插入，避免 UniqueViolation。
    """
    await test_session.execute(
        delete(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
    )
    await test_session.commit()
    cfg = KolIntakeConfig(
        config_key="conversation_bridge",
        ai_model_id=ai_model.id,
        system_prompt=system_prompt,
        is_active=True,
    )
    test_session.add(cfg)
    await test_session.commit()
    await test_session.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# GET /intake/questions
# ---------------------------------------------------------------------------

class TestIntakeQuestions:
    @pytest.mark.asyncio
    async def test_questions_returns_active_only_ordered(
        self, test_client, test_session,
    ):
        """seed 两条 active + 一条 inactive → 只返回 active，按 order_num 升序。

        用唯一 category marker 过滤，避免其他测试残留数据干扰断言。
        """
        marker = f"cov_cat_{uuid.uuid4().hex[:6]}"
        await _seed_question(
            test_session, order_num=2, category=marker,
            question_text="cov_q2", is_active=True,
        )
        await _seed_question(
            test_session, order_num=1, category=marker,
            question_text="cov_q1", is_active=True,
        )
        await _seed_question(
            test_session, order_num=3, category=marker,
            question_text="cov_q_inactive", is_active=False,
        )

        resp = await test_client.get("/api/intake/questions")
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        items = [it for it in body["data"] if it["category"] == marker]
        assert len(items) == 2
        assert items[0]["order_num"] == 1
        assert items[1]["order_num"] == 2
        # 结构字段齐全
        for it in items:
            assert {"id", "order_num", "category", "question_text",
                    "question_type", "max_items", "is_required"} <= set(it.keys())

    @pytest.mark.asyncio
    async def test_questions_returns_list_shape(self, test_client, test_session):
        """无启用题目（或残留数据存在） → 至少返回 list 结构。"""
        resp = await test_client.get("/api/intake/questions")
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert isinstance(body["data"], list)

    @pytest.mark.asyncio
    async def test_questions_no_auth_required(self, test_client):
        """公开接口，无 token 也能访问（不是 401）。"""
        resp = await test_client.get("/api/intake/questions")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /intake/{token}
# ---------------------------------------------------------------------------

class TestIntakeCheckLink:
    @pytest.mark.asyncio
    async def test_check_link_not_found_404(self, test_client):
        """不存在的 token → 404 HTTPException。"""
        resp = await test_client.get("/api/intake/nonexistent_token_xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_check_link_expired_410(self, test_client, test_session, operator_user):
        """过期链接 → 410 HTTPException。"""
        link = await _seed_link(
            test_session, operator_user, expires_at=_past(),
        )
        resp = await test_client.get(f"/api/intake/{link.token}")
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_check_link_first_visit_writes_used_at(
        self, test_client, test_session, operator_user,
    ):
        """首次访问 → used_at 从 None 被写入；返回 valid=true + already_submitted=false。"""
        link = await _seed_link(test_session, operator_user, used_at=None)
        resp = await test_client.get(f"/api/intake/{link.token}")
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["valid"] is True
        assert body["data"]["already_submitted"] is False
        assert body["data"]["kol_name"] == "测试红人"
        assert body["data"]["existing_messages"] == []

    @pytest.mark.asyncio
    async def test_check_link_with_submission_returns_messages(
        self, test_client, test_session, operator_user,
    ):
        """已提交 → already_submitted=true + existing_messages 回放。"""
        link = await _seed_link(test_session, operator_user)
        messages = [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "我是小红"},
        ]
        sub = KolIntakeSubmission(
            link_id=link.id, messages=messages, report_status="pending",
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}")
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["already_submitted"] is True
        assert body["data"]["existing_messages"] == messages


# ---------------------------------------------------------------------------
# POST /intake/{token}/chat
# ---------------------------------------------------------------------------

class TestIntakeChat:
    @pytest.mark.asyncio
    async def test_chat_not_found_404(self, test_client):
        resp = await test_client.post(
            "/api/intake/nonexistent_token_xyz/chat",
            json={"messages": []},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_expired_410(self, test_client, test_session, operator_user):
        link = await _seed_link(test_session, operator_user, expires_at=_past())
        resp = await test_client.post(
            f"/api/intake/{link.token}/chat", json={"messages": []},
        )
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_chat_already_submitted_validation_error(
        self, test_client, test_session, operator_user,
    ):
        """link.submitted_at 已设置 → error_response（HTTP 200 + success=false + VALIDATION_ERROR）。"""
        link = await _seed_link(test_session, operator_user, submitted_at=_past())
        resp = await test_client.post(
            f"/api/intake/{link.token}/chat", json={"messages": []},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is False
        assert body["code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_chat_no_config_returns_null_reply(
        self, test_client, test_session, operator_user,
    ):
        """无 conversation_bridge 配置 → 200 + reply=None + error 提示。"""
        link = await _seed_link(test_session, operator_user)
        resp = await test_client.post(
            f"/api/intake/{link.token}/chat", json={"messages": []},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] is None
        assert "error" in body["data"]

    @pytest.mark.asyncio
    async def test_chat_ai_model_inactive_returns_null_reply(
        self, test_client, test_session, operator_user,
    ):
        """配置存在但模型 status != active → reply=None。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="inactive")
        await _seed_bridge_config(test_session, m)

        resp = await test_client.post(
            f"/api/intake/{link.token}/chat", json={"messages": []},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] is None

    @pytest.mark.asyncio
    async def test_chat_happy_path_returns_reply(
        self, test_client, test_session, operator_user,
    ):
        """完整配置 + mock yunwu → 返回 AI 回复 + role=assistant。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_bridge_config(test_session, m, system_prompt="你是面试官")
        # 题目提纲也会被拼到 system 里
        await _seed_question(test_session, order_num=1, question_text="你叫什么？")

        with patch(
            "app.adapters.yunwu.chat",
            new_callable=AsyncMock,
            return_value="你好，我是 AI 面试官",
        ):
            resp = await test_client.post(
                f"/api/intake/{link.token}/chat",
                json={"messages": [{"role": "user", "content": "在吗"}]},
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == "你好，我是 AI 面试官"
        assert body["data"]["role"] == "assistant"


# ---------------------------------------------------------------------------
# POST /intake/{token}/bridge
# ---------------------------------------------------------------------------

class TestIntakeBridge:
    @pytest.mark.asyncio
    async def test_bridge_not_found_404(self, test_client):
        resp = await test_client.post(
            "/api/intake/nonexistent_token_xyz/bridge",
            json={
                "user_answer": "我是小红",
                "question_text": "你叫什么",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bridge_no_config_returns_empty_reply(
        self, test_client, test_session, operator_user,
    ):
        """无配置 → 200 + reply=""（静默降级）。"""
        link = await _seed_link(test_session, operator_user)
        resp = await test_client.post(
            f"/api/intake/{link.token}/bridge",
            json={"user_answer": "答", "question_text": "问"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == ""

    @pytest.mark.asyncio
    async def test_bridge_adapter_failure_silently_degrades(
        self, test_client, test_session, operator_user,
    ):
        """adapter 抛异常 → 200 + reply=""（catch + 静默降级）。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_bridge_config(test_session, m)

        with patch(
            "app.adapters.yunwu.chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("yunwu down"),
        ):
            resp = await test_client.post(
                f"/api/intake/{link.token}/bridge",
                json={"user_answer": "答", "question_text": "问"},
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == ""

    @pytest.mark.asyncio
    async def test_bridge_happy_path_returns_reply(
        self, test_client, test_session, operator_user,
    ):
        """正常分支 + mock yunwu → 返回过渡语。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_bridge_config(test_session, m)

        with patch(
            "app.adapters.yunwu.chat",
            new_callable=AsyncMock,
            return_value="听起来很棒，我们继续聊聊下一个话题。",
        ):
            resp = await test_client.post(
                f"/api/intake/{link.token}/bridge",
                json={
                    "user_answer": "我做美妆三年了",
                    "question_text": "你的内容方向是什么？",
                    "next_question_hint": "想知道粉丝画像",
                    "is_last_question": False,
                },
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == "听起来很棒，我们继续聊聊下一个话题。"

    @pytest.mark.asyncio
    async def test_bridge_last_question_branch(
        self, test_client, test_session, operator_user,
    ):
        """is_last_question=True 走收尾分支（mock 验证调用发生）。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_bridge_config(test_session, m)

        mock_chat = AsyncMock(return_value="辛苦了，可以提交了")
        with patch("app.adapters.yunwu.chat", new=mock_chat):
            resp = await test_client.post(
                f"/api/intake/{link.token}/bridge",
                json={
                    "user_answer": "没有更多了",
                    "question_text": "最后题",
                    "is_last_question": True,
                },
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == "辛苦了，可以提交了"
        mock_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bridge_multi_collect_branch(
        self, test_client, test_session, operator_user,
    ):
        """is_multi_collect=True + collect_count>0 → 多条收集分支。"""
        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_bridge_config(test_session, m)

        mock_chat = AsyncMock(return_value="好的，还有其他想说的吗？")
        with patch("app.adapters.yunwu.chat", new=mock_chat):
            resp = await test_client.post(
                f"/api/intake/{link.token}/bridge",
                json={
                    "user_answer": "第一条",
                    "question_text": "代表作品",
                    "is_multi_collect": True,
                    "collect_count": 1,
                },
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["reply"] == "好的，还有其他想说的吗？"
        mock_chat.assert_awaited_once()


# ---------------------------------------------------------------------------
# POST /intake/{token}/submit
# ---------------------------------------------------------------------------

class TestIntakeSubmit:
    @pytest.mark.asyncio
    async def test_submit_not_found_404(self, test_client):
        resp = await test_client.post(
            "/api/intake/nonexistent_token_xyz/submit",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_expired_410(self, test_client, test_session, operator_user):
        link = await _seed_link(test_session, operator_user, expires_at=_past())
        resp = await test_client.post(
            f"/api/intake/{link.token}/submit",
            json={"messages": []},
        )
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_submit_already_submitted_409(
        self, test_client, test_session, operator_user,
    ):
        """link.submitted_at 已设置 → HTTP 409。"""
        link = await _seed_link(test_session, operator_user, submitted_at=_past())
        resp = await test_client.post(
            f"/api/intake/{link.token}/submit",
            json={"messages": []},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_submit_happy_path_creates_submission(
        self, test_client, test_session, operator_user,
    ):
        """mock 后台任务 → 200 + 创建 submission + link.submitted_at 被写入。"""
        link = await _seed_link(test_session, operator_user)
        sent_messages = [{"role": "user", "content": "我是小红"}]

        # patch 后台任务，避免触发真实 AI 调用 + 文件生成
        with patch(
            "app.routers.intake_public.generate_intake_report",
            new_callable=AsyncMock,
        ):
            resp = await test_client.post(
                f"/api/intake/{link.token}/submit",
                json={"messages": sent_messages},
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["success"] is True
        assert body["data"]["report_status"] == "generating"
        sub_id = body["data"]["submission_id"]
        assert sub_id

        # 校验 submission 落库
        from sqlalchemy import select
        sub = (await test_session.execute(
            select(KolIntakeSubmission).where(KolIntakeSubmission.id == sub_id)
        )).scalar_one()
        assert sub.link_id == link.id
        assert sub.messages == sent_messages
        assert sub.report_status == "pending"

        # 校验 link.submitted_at 被写入
        await test_session.refresh(link)
        assert link.submitted_at is not None


# ---------------------------------------------------------------------------
# GET /intake/{token}/status
# ---------------------------------------------------------------------------

class TestIntakeStatus:
    @pytest.mark.asyncio
    async def test_status_not_found_404(self, test_client):
        resp = await test_client.get("/api/intake/nonexistent_token_xyz/status")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_expired_410(self, test_client, test_session, operator_user):
        link = await _seed_link(test_session, operator_user, expires_at=_past())
        resp = await test_client.get(f"/api/intake/{link.token}/status")
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_status_no_submission(
        self, test_client, test_session, operator_user,
    ):
        """链接有效但未提交 → report_status=not_submitted + download_ready=false。"""
        link = await _seed_link(test_session, operator_user)
        resp = await test_client.get(f"/api/intake/{link.token}/status")
        body = resp.json()
        assert resp.status_code == 200
        assert body["data"]["report_status"] == "not_submitted"
        assert body["data"]["download_ready"] is False

    @pytest.mark.asyncio
    async def test_status_generating(
        self, test_client, test_session, operator_user,
    ):
        """submission 状态 generating → download_ready=false。"""
        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id, messages=[], report_status="generating",
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/status")
        body = resp.json()
        assert body["data"]["report_status"] == "generating"
        assert body["data"]["download_ready"] is False

    @pytest.mark.asyncio
    async def test_status_ready(
        self, test_client, test_session, operator_user,
    ):
        """submission 状态 ready → download_ready=true。"""
        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id, messages=[], report_status="ready",
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/status")
        body = resp.json()
        assert body["data"]["report_status"] == "ready"
        assert body["data"]["download_ready"] is True


# ---------------------------------------------------------------------------
# GET /intake/{token}/download
# ---------------------------------------------------------------------------

class TestIntakeDownload:
    @pytest.mark.asyncio
    async def test_download_not_found_404(self, test_client):
        resp = await test_client.get("/api/intake/nonexistent_token_xyz/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_expired_410(self, test_client, test_session, operator_user):
        link = await _seed_link(test_session, operator_user, expires_at=_past())
        resp = await test_client.get(f"/api/intake/{link.token}/download")
        assert resp.status_code == 410

    @pytest.mark.asyncio
    async def test_download_no_submission_404(
        self, test_client, test_session, operator_user,
    ):
        """链接有效但无 submission → 404。"""
        link = await _seed_link(test_session, operator_user)
        resp = await test_client.get(f"/api/intake/{link.token}/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_not_ready_404(
        self, test_client, test_session, operator_user,
    ):
        """submission 存在但 status != ready → 404。"""
        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id, messages=[], report_status="generating",
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_ready_but_file_missing_404(
        self, test_client, test_session, operator_user,
    ):
        """status=ready 但文件路径不存在 → 404。"""
        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id,
            messages=[],
            report_status="ready",
            docx_path="/tmp/nonexistent_report_xyz.docx",
            pdf_path="/tmp/nonexistent_report_xyz.pdf",
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/download")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_download_invalid_format_422(
        self, test_client, test_session, operator_user,
    ):
        """?format=xxx 非法 → 422（Query pattern 校验失败）。"""
        link = await _seed_link(test_session, operator_user)
        resp = await test_client.get(
            f"/api/intake/{link.token}/download?format=invalid"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_download_ready_returns_docx_file(
        self, test_client, test_session, operator_user, tmp_path,
    ):
        """status=ready + 文件存在 → FileResponse（docx）。"""
        # 创建真实文件
        docx_file = tmp_path / "report.docx"
        docx_file.write_bytes(b"fake docx content")
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id,
            messages=[],
            report_status="ready",
            docx_path=str(docx_file),
            pdf_path=str(pdf_file),
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/download?format=docx")
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers.get("content-type", "")
        assert resp.content == b"fake docx content"
        # 文件名：中文报告名（FileResponse 会 URL-encode 非 ASCII，如 filename*=utf-8''MCN%...）
        cd = resp.headers.get("content-disposition", "")
        assert ".docx" in cd

    @pytest.mark.asyncio
    async def test_download_ready_returns_pdf_file(
        self, test_client, test_session, operator_user, tmp_path,
    ):
        """?format=pdf → FileResponse（pdf）。"""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"fake pdf content")

        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id,
            messages=[],
            report_status="ready",
            pdf_path=str(pdf_file),
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/download?format=pdf")
        assert resp.status_code == 200
        assert "pdf" in resp.headers.get("content-type", "").lower()
        assert resp.content == b"fake pdf content"

    @pytest.mark.asyncio
    async def test_download_default_format_is_docx(
        self, test_client, test_session, operator_user, tmp_path,
    ):
        """无 ?format 参数 → 默认 docx。"""
        docx_file = tmp_path / "report.docx"
        docx_file.write_bytes(b"docx default")

        link = await _seed_link(test_session, operator_user)
        sub = KolIntakeSubmission(
            link_id=link.id,
            messages=[],
            report_status="ready",
            docx_path=str(docx_file),
        )
        test_session.add(sub)
        await test_session.commit()

        resp = await test_client.get(f"/api/intake/{link.token}/download")
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers.get("content-type", "")
