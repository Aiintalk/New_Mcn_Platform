"""
Direct unit tests for module-level functions in intake_public.py.

现有 test_intake_public.py 走 HTTP 端点，这两个模块内函数覆盖率低：
- `_build_full_system_prompt`（~L81-99）：在 base_prompt 后追加题目提纲，
  按 category 分组 + ★必填标记 / 选填注记。
- `generate_intake_report`（~L360-497）：BackgroundTask，开独立 AsyncSessionLocal，
  读 submission/config/ai_model → 调 yunwu.chat（thinking 优先，失败降级普通）
  → 生成 docx/pdf → 更新 submission.report_status。

fixture 约定：
- test_session（tests/conftest.py）已把 AsyncSessionLocal 全局 patch（含
  `app.routers.intake_public.AsyncSessionLocal`），所以 generate_intake_report
  内 `async with AsyncSessionLocal()` 开的独立 session 与 test_session 同库同 engine，
  seed 的数据可见。
- autouse cleanup 清 kol_intake_* + ai_models，防 unique 冲突 / 数据污染。
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.credential import AiModel
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeLink, KolIntakeQuestion, KolIntakeSubmission,
)
from app.routers.intake_public import (
    _build_full_system_prompt, generate_intake_report,
)


# ---------------------------------------------------------------------------
# Cleanup fixture（autouse）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_intake_tables(test_session):
    """每个测试前清 kol_intake_* + ai_models，避免 unique 冲突与跨测试数据污染。

    删除顺序遵循外键依赖（被引用表后删）：submission → link → config → question → ai_model。
    """
    await test_session.execute(delete(KolIntakeSubmission))
    await test_session.execute(delete(KolIntakeLink))
    await test_session.execute(delete(KolIntakeConfig))
    await test_session.execute(delete(KolIntakeQuestion))
    await test_session.execute(delete(AiModel))
    await test_session.commit()
    yield


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _future() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)


def _token() -> str:
    return f"tok_{uuid.uuid4().hex[:16]}"


async def _seed_link(test_session, operator_user, *, kol_name="测试红人"):
    link = KolIntakeLink(
        token=_token(),
        operator_id=operator_user.id,
        kol_name=kol_name,
        expires_at=_future(),
    )
    test_session.add(link)
    await test_session.commit()
    return link


async def _seed_submission(
    test_session, link, *, messages=None, report_status="pending",
):
    sub = KolIntakeSubmission(
        link_id=link.id,
        messages=messages if messages is not None else [],
        report_status=report_status,
    )
    test_session.add(sub)
    await test_session.commit()
    return sub


async def _seed_question(
    test_session, *, order_num, category, question_text,
    is_required=True, is_active=True,
):
    q = KolIntakeQuestion(
        order_num=order_num,
        category=category,
        question_text=question_text,
        question_type="text",
        is_required=is_required,
        is_active=is_active,
    )
    test_session.add(q)
    await test_session.commit()
    return q


async def _seed_ai_model(test_session, *, status="active"):
    m = AiModel(
        name=f"cov_model_{uuid.uuid4().hex[:6]}",
        provider="yunwu",
        model_id=f"cov-model-{uuid.uuid4().hex[:10]}",
        status=status,
    )
    test_session.add(m)
    await test_session.commit()
    return m


async def _seed_report_config(
    test_session, *, ai_model=None, ai_model_id=None, system_prompt=None,
):
    """seed report_generation config（config_key 唯一，先删防冲突）。

    ai_model_id 显式参数优先；否则从 ai_model 推断；都为 None 即 None
    （模拟"config 存在但 ai_model_id 未配置"）。
    """
    await test_session.execute(
        delete(KolIntakeConfig).where(KolIntakeConfig.config_key == "report_generation")
    )
    await test_session.commit()
    if ai_model_id is None and ai_model is not None:
        ai_model_id = int(ai_model.id)
    cfg = KolIntakeConfig(
        config_key="report_generation",
        ai_model_id=ai_model_id,
        system_prompt=system_prompt,
        is_active=True,
    )
    test_session.add(cfg)
    await test_session.commit()
    return cfg


async def _reload_submission(test_session, sub_id) -> KolIntakeSubmission:
    """重新查 submission 拿最新状态。

    generate_intake_report 在独立 session 里 commit 了 update；test_session 因
    identity map 缓存可能拿到旧值，用 populate_existing=True 强制刷新。
    """
    return (await test_session.execute(
        select(KolIntakeSubmission)
        .where(KolIntakeSubmission.id == sub_id)
        .execution_options(populate_existing=True)
    )).scalar_one()


# ---------------------------------------------------------------------------
# _build_full_system_prompt
# ---------------------------------------------------------------------------


class TestBuildFullSystemPrompt:
    @pytest.mark.asyncio
    async def test_required_and_optional_grouped_by_category(
        self, test_session,
    ):
        """不同 category + 必填/选填混合 → 输出含 base、提纲标题、category 名、
        ★ 必填前缀、选填无 ★。
        """
        marker = f"cov_cat_{uuid.uuid4().hex[:6]}"
        cat_a = f"{marker}_A"
        cat_b = f"{marker}_B"
        # A：1 必填
        await _seed_question(
            test_session, order_num=1, category=cat_a,
            question_text="cov_q_a", is_required=True,
        )
        # B：先必填后选填（同 category 内不重复输出 category 行）
        await _seed_question(
            test_session, order_num=2, category=cat_b,
            question_text="cov_q_b_req", is_required=True,
        )
        await _seed_question(
            test_session, order_num=3, category=cat_b,
            question_text="cov_q_b_opt", is_required=False,
        )

        result = await _build_full_system_prompt("BASE_PROMPT", test_session)

        # base prompt 在最前
        assert result.startswith("BASE_PROMPT")
        # 提纲标题
        assert "【访谈提纲（需覆盖所有★必填项）】" in result
        # category 名出现
        assert cat_a in result
        assert cat_b in result
        # 必填题前缀 ★
        assert "★ 1. cov_q_a" in result
        assert "★ 2. cov_q_b_req" in result
        # 选填题无 ★（三个空格缩进）
        assert "   3. cov_q_b_opt" in result

    @pytest.mark.asyncio
    async def test_category_first_question_optional_adds_note(
        self, test_session,
    ):
        """category 首题是选填 → category 行后追加"（选填，能问到更好）"。"""
        marker = f"cov_opt_{uuid.uuid4().hex[:6]}"
        await _seed_question(
            test_session, order_num=1, category=marker,
            question_text="cov_optional_q", is_required=False,
        )

        result = await _build_full_system_prompt("X", test_session)

        # category 行带选填注记
        assert f"{marker}（选填，能问到更好）" in result
        # 选填题无 ★
        assert "   1. cov_optional_q" in result
        # 全量无必填 → 不应出现题目前的 "★ " 前缀
        # （注意提纲标题本身含 ★ 字符，所以查 "★ " 带尾随空格的题目前缀）
        assert "★ " not in result

    @pytest.mark.asyncio
    async def test_inactive_questions_excluded(self, test_session):
        """is_active=False 的题目不应出现在提纲中。"""
        marker = f"cov_inactive_{uuid.uuid4().hex[:6]}"
        await _seed_question(
            test_session, order_num=1, category=marker,
            question_text="cov_active_q", is_required=True, is_active=True,
        )
        await _seed_question(
            test_session, order_num=2, category=marker,
            question_text="cov_inactive_q", is_required=True, is_active=False,
        )

        result = await _build_full_system_prompt("X", test_session)

        assert "cov_active_q" in result
        assert "cov_inactive_q" not in result

    @pytest.mark.asyncio
    async def test_empty_questions_returns_base_plus_header_only(
        self, test_session,
    ):
        """无启用题目 → 输出仅含 base_prompt + 空行 + 提纲标题。"""
        result = await _build_full_system_prompt("HELLO", test_session)
        lines = result.split("\n")
        assert lines[0] == "HELLO"
        assert lines[1] == ""
        assert lines[2] == "【访谈提纲（需覆盖所有★必填项）】"
        assert len(lines) == 3
        # 无题目 → 不应出现题目前的 "★ " 前缀（标题本身的 ★ 不算）
        assert "★ " not in result


# ---------------------------------------------------------------------------
# generate_intake_report
# ---------------------------------------------------------------------------


class TestGenerateIntakeReport:
    @pytest.mark.asyncio
    async def test_happy_path_marks_ready(
        self, test_session, operator_user,
    ):
        """完整配置 + mock yunwu/docx/pdf → status=ready，字段全部写入。

        消息含 assistant+user 配对，qa_lines 非空 → report_prompt 替换 {qa_content}。
        """
        link = await _seed_link(test_session, operator_user, kol_name="小红红人")
        messages = [
            {"role": "assistant", "content": "你叫什么名字？"},
            {"role": "user", "content": "我是小红"},
        ]
        sub = await _seed_submission(test_session, link, messages=messages)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session, ai_model=m,
            system_prompt="基于以下对话生成报告：\n{qa_content}",
        )

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
            return_value="# AI 生成的报告",
        ) as mock_chat, patch(
            "app.services.intake_report.generate_docx",
            return_value="/tmp/cov_report.docx",
        ) as mock_docx, patch(
            "app.services.intake_report.generate_pdf",
            return_value="/tmp/cov_report.pdf",
        ) as mock_pdf:
            await generate_intake_report(sub.id)

        # thinking 路径成功 → chat 只调一次
        mock_chat.assert_awaited_once()
        # docx/pdf 用位置参数：(submission_id, ai_report, kol_name)
        mock_docx.assert_called_once_with(sub.id, "# AI 生成的报告", "小红红人")
        mock_pdf.assert_called_once_with(sub.id, "# AI 生成的报告", "小红红人")

        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "ready"
        assert latest.ai_report == "# AI 生成的报告"
        assert latest.ai_report_raw == {"thinking_supported": True}
        assert latest.docx_path == "/tmp/cov_report.docx"
        assert latest.pdf_path == "/tmp/cov_report.pdf"
        assert latest.report_generated_at is not None

    @pytest.mark.asyncio
    async def test_thinking_failure_falls_back_to_normal_chat(
        self, test_session, operator_user,
    ):
        """thinking chat 抛异常 → 降级普通 chat → 仍 ready，thinking_supported=False。"""
        link = await _seed_link(test_session, operator_user, kol_name="测试")
        messages = [
            {"role": "assistant", "content": "问题？"},
            {"role": "user", "content": "回答"},
        ]
        sub = await _seed_submission(test_session, link, messages=messages)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session, ai_model=m, system_prompt="报告：{qa_content}",
        )

        # 第一次抛（thinking），第二次返回（降级普通 chat）
        mock_chat = AsyncMock(
            side_effect=[RuntimeError("thinking 不支持"), "降级报告内容"],
        )
        with patch(
            "app.routers.intake_public.yunwu_adapter.chat", new=mock_chat,
        ), patch(
            "app.services.intake_report.generate_docx",
            return_value="/tmp/cov_d.docx",
        ), patch(
            "app.services.intake_report.generate_pdf",
            return_value="/tmp/cov_d.pdf",
        ):
            await generate_intake_report(sub.id)

        # chat 被调两次（thinking + 普通）
        assert mock_chat.await_count == 2
        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "ready"
        assert latest.ai_report == "降级报告内容"
        assert latest.ai_report_raw == {"thinking_supported": False}

    @pytest.mark.asyncio
    async def test_config_missing_marks_failed(
        self, test_session, operator_user,
    ):
        """无 report_generation config → RuntimeError → status=failed；chat 未被调。"""
        link = await _seed_link(test_session, operator_user)
        sub = await _seed_submission(test_session, link, messages=[])

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            await generate_intake_report(sub.id)

        mock_chat.assert_not_called()
        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "failed"
        assert latest.ai_report_raw is not None
        assert "error" in latest.ai_report_raw
        # 错误信息记录了 RuntimeError 的字符串
        assert "report_generation" in latest.ai_report_raw["error"]

    @pytest.mark.asyncio
    async def test_config_without_ai_model_id_marks_failed(
        self, test_session, operator_user,
    ):
        """config 存在但 ai_model_id=None → RuntimeError → failed。"""
        link = await _seed_link(test_session, operator_user)
        sub = await _seed_submission(test_session, link, messages=[])
        # 显式传 ai_model_id=None
        await _seed_report_config(test_session, ai_model_id=None, system_prompt="X")

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            await generate_intake_report(sub.id)

        mock_chat.assert_not_called()
        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "failed"
        assert "error" in (latest.ai_report_raw or {})

    @pytest.mark.asyncio
    async def test_ai_model_inactive_marks_failed(
        self, test_session, operator_user,
    ):
        """config 配了 ai_model_id 但 ai_model.status != active → failed。"""
        link = await _seed_link(test_session, operator_user)
        sub = await _seed_submission(test_session, link, messages=[])
        m = await _seed_ai_model(test_session, status="inactive")
        await _seed_report_config(test_session, ai_model=m)

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            await generate_intake_report(sub.id)

        mock_chat.assert_not_called()
        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "failed"
        assert "error" in (latest.ai_report_raw or {})

    @pytest.mark.asyncio
    async def test_nonexistent_submission_returns_silently(self, test_session):
        """submission_id 不存在 → 直接 return，无 DB 写入、无 chat 调用。"""
        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mock_chat:
            # 不应抛异常
            await generate_intake_report(999999999)

        mock_chat.assert_not_called()
        # 不应创建任何 submission
        count = (await test_session.execute(
            select(KolIntakeSubmission).where(KolIntakeSubmission.id == 999999999)
        )).scalar_one_or_none()
        assert count is None

    @pytest.mark.asyncio
    async def test_happy_path_with_empty_messages_uses_default_qa_content(
        self, test_session, operator_user,
    ):
        """messages 无 assistant+user 配对 → qa_content 走"（暂无完整对话记录）"分支。

        覆盖 line 416 的 else 分支与 report_prompt 中 {qa_content} 替换。
        """
        link = await _seed_link(test_session, operator_user, kol_name="单独红人")
        # 只有 user 无前导 assistant → qa_lines 空
        sub = await _seed_submission(
            test_session, link,
            messages=[{"role": "user", "content": "孤立回答"}],
        )
        m = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session, ai_model=m, system_prompt="报告：{qa_content}",
        )

        captured = {}

        async def _capture_chat(*, messages, **kwargs):
            captured["user_msg"] = messages[0]["content"]
            return "AI 报告"

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new=_capture_chat,
        ), patch(
            "app.services.intake_report.generate_docx",
            return_value="/tmp/cov_e.docx",
        ), patch(
            "app.services.intake_report.generate_pdf",
            return_value="/tmp/cov_e.pdf",
        ):
            await generate_intake_report(sub.id)

        # report_prompt 中 {qa_content} 被替换成默认占位文字
        assert "（暂无完整对话记录）" in captured["user_msg"]

        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "ready"
        assert latest.ai_report == "AI 报告"

    @pytest.mark.asyncio
    async def test_empty_or_whitespace_content_messages_skipped(
        self, test_session, operator_user,
    ):
        """messages 中 content 为空/纯空白 → continue 跳过，不进入 qa_lines。

        覆盖 generate_intake_report 内 line ~404-405 的 `if not content: continue` 分支。
        """
        link = await _seed_link(test_session, operator_user, kol_name="测试")
        messages = [
            {"role": "assistant", "content": "问题？"},
            {"role": "user", "content": "   "},  # 纯空白 → strip() 后空 → continue
            {"role": "user", "content": ""},     # 空字符串 → continue
            {"role": "user", "content": "实际回答"},
        ]
        sub = await _seed_submission(test_session, link, messages=messages)
        m = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session, ai_model=m, system_prompt="报告：{qa_content}",
        )

        captured = {}

        async def _capture_chat(*, messages, **kwargs):
            captured["user_msg"] = messages[0]["content"]
            return "AI 报告"

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat", new=_capture_chat,
        ), patch(
            "app.services.intake_report.generate_docx",
            return_value="/tmp/cov_s.docx",
        ), patch(
            "app.services.intake_report.generate_pdf",
            return_value="/tmp/cov_s.pdf",
        ):
            await generate_intake_report(sub.id)

        # 空白/空消息被跳过，只有"实际回答"参与；它找到前导 assistant "问题？"
        assert "问：问题？" in captured["user_msg"]
        assert "答：实际回答" in captured["user_msg"]
        latest = await _reload_submission(test_session, sub.id)
        assert latest.report_status == "ready"

    @pytest.mark.asyncio
    async def test_kol_name_falls_back_to_first_user_message(
        self, test_session, operator_user,
    ):
        """link.kol_name 为空 → 从对话首条 user 消息截取前 20 字符作为 kol_name。

        覆盖 line 462-467 的 fallback 分支。
        """
        # 创建一个 kol_name=None 的 link
        link = KolIntakeLink(
            token=_token(),
            operator_id=operator_user.id,
            kol_name=None,
            expires_at=_future(),
        )
        test_session.add(link)
        await test_session.commit()

        long_answer = "我叫小红的昵称这是测试用例需要超过二十个字符的回答"
        sub = await _seed_submission(
            test_session, link,
            messages=[{"role": "user", "content": long_answer}],
        )
        m = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session, ai_model=m, system_prompt="报告：{qa_content}",
        )

        captured = {}

        def _capture_docx(submission_id, ai_report, kol_name):
            captured["kol_name"] = kol_name
            return "/tmp/cov_kb.docx"

        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="report",
        ), patch(
            "app.services.intake_report.generate_docx",
            side_effect=_capture_docx,
        ), patch(
            "app.services.intake_report.generate_pdf",
            return_value="/tmp/cov_kb.pdf",
        ):
            await generate_intake_report(sub.id)

        # kol_name 取 user 消息前 20 字符
        assert captured["kol_name"] == long_answer[:20]


# ---------------------------------------------------------------------------
# 端点 happy path 补测（为达文件覆盖率 ≥70% 门禁）
# ---------------------------------------------------------------------------
# 两个模块函数（_build_full_system_prompt / generate_intake_report）已被上面
# 直接单测 100% 覆盖，但仅占文件约 57%。这里通过**直接调用端点函数**补几条
# 最薄壁的 happy path，让单独跑本文件也能跨过 70% 门禁。
#
# 注意：用 test_client（ASGITransport）跑端点时，coverage 不追踪 anyio task
# 内的代码执行（已知 httpx+anyio+coverage 限制），所以这里改成直接 await
# 端点函数，把 db=test_session 直接注入。Depends(...) 在直接调用时被忽略。


class TestEndpointHappyPaths:
    """端点 happy path 直接调用补测（绕过 ASGITransport 让 coverage 追踪到端点体）。"""

    @pytest.mark.asyncio
    async def test_get_questions_returns_active_only(
        self, test_session,
    ):
        """get_questions → 仅返回启用题目。"""
        from app.routers.intake_public import get_questions

        marker = f"cov_ep_{uuid.uuid4().hex[:6]}"
        await _seed_question(
            test_session, order_num=2, category=marker,
            question_text="cov_ep_q2", is_active=True,
        )
        await _seed_question(
            test_session, order_num=1, category=marker,
            question_text="cov_ep_q1", is_active=True,
        )
        await _seed_question(
            test_session, order_num=3, category=marker,
            question_text="cov_ep_q_inactive", is_active=False,
        )

        result = await get_questions(db=test_session)
        assert result.success is True
        items = [it for it in result.data if it["category"] == marker]
        assert len(items) == 2
        assert items[0]["order_num"] == 1
        assert items[1]["order_num"] == 2

    @pytest.mark.asyncio
    async def test_check_link_first_visit_returns_valid(
        self, test_session, operator_user,
    ):
        """check_link 首次访问 → valid=true + already_submitted=false。"""
        from app.routers.intake_public import check_link

        link = await _seed_link(test_session, operator_user, kol_name="cov_link_kol")

        result = await check_link(token=link.token, db=test_session)
        assert result.success is True
        assert result.data["valid"] is True
        assert result.data["already_submitted"] is False
        assert result.data["kol_name"] == "cov_link_kol"
        assert result.data["existing_messages"] == []

    @pytest.mark.asyncio
    async def test_check_link_with_submission_returns_messages(
        self, test_session, operator_user,
    ):
        """check_link 已提交 → already_submitted=true + existing_messages 回放。"""
        from app.routers.intake_public import check_link

        link = await _seed_link(test_session, operator_user)
        messages = [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "我是小红"},
        ]
        await _seed_submission(test_session, link, messages=messages)

        result = await check_link(token=link.token, db=test_session)
        assert result.data["already_submitted"] is True
        assert result.data["existing_messages"] == messages

    @pytest.mark.asyncio
    async def test_intake_status_with_submission(
        self, test_session, operator_user,
    ):
        """intake_status submission 状态 generating → download_ready=false。"""
        from app.routers.intake_public import intake_status

        link = await _seed_link(test_session, operator_user)
        await _seed_submission(
            test_session, link, messages=[], report_status="generating",
        )

        result = await intake_status(token=link.token, db=test_session)
        assert result.data["report_status"] == "generating"
        assert result.data["download_ready"] is False

    @pytest.mark.asyncio
    async def test_intake_status_no_submission(
        self, test_session, operator_user,
    ):
        """intake_status 链接有效但未提交 → report_status=not_submitted。"""
        from app.routers.intake_public import intake_status

        link = await _seed_link(test_session, operator_user)
        result = await intake_status(token=link.token, db=test_session)
        assert result.data["report_status"] == "not_submitted"
        assert result.data["download_ready"] is False

    @pytest.mark.asyncio
    async def test_intake_chat_happy_path_with_mock_yunwu(
        self, test_session, operator_user,
    ):
        """intake_chat + mock yunwu → reply + role=assistant。"""
        from app.routers.intake_public import intake_chat, ChatRequest

        link = await _seed_link(test_session, operator_user)
        m = await _seed_ai_model(test_session, status="active")
        # chat 端点固定查 conversation_bridge 配置
        await test_session.execute(
            delete(KolIntakeConfig).where(
                KolIntakeConfig.config_key == "conversation_bridge"
            )
        )
        await test_session.commit()
        test_session.add(KolIntakeConfig(
            config_key="conversation_bridge",
            ai_model_id=int(m.id),
            system_prompt="你是面试官",
            is_active=True,
        ))
        await test_session.commit()
        await _seed_question(
            test_session, order_num=1, category="基本信息",
            question_text="你叫什么？", is_required=True,
        )

        body = ChatRequest(messages=[{"role": "user", "content": "在吗"}])
        with patch(
            "app.routers.intake_public.yunwu_adapter.chat",
            new_callable=AsyncMock,
            return_value="你好，我是 AI 面试官",
        ):
            result = await intake_chat(
                token=link.token, body=body, db=test_session,
            )
        assert result.data["reply"] == "你好，我是 AI 面试官"
        assert result.data["role"] == "assistant"
