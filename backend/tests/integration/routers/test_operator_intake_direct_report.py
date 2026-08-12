"""
Unit tests for module-level helper functions in operator_intake_direct.py.

The router endpoints are covered by test_operator_intake_direct.py; this file
targets the in-module helpers that the endpoint tests mock out or never reach:

- require_operator:            角色与改密校验
- _get_own_session:            会话归属校验（404 分支）
- _get_ip:                     从 request 取 IP（含 x-forwarded-for）
- _get_active_kol:             取未删除的 kol（404 分支）
- _build_full_system_prompt:   拼 base_prompt + 题目提纲（按分类分组、必填/选填标记）
- _generate_operator_session_report: 后台报告生成
    * 成功（thinking 启用）→ ready + ai_report_raw={'thinking_supported': True}
    * 第一次 chat 抛错 → fallback 第二次 → ai_report_raw={'thinking_supported': False}
    * config 缺失 / config.ai_model_id=None / ai_model inactive → 用默认 model
    * config.system_prompt=None → fallback 到 _DEFAULT_REPORT_PROMPT
    * session 不存在 → 静默 return
    * 任意异常（generate_docx 抛错）→ report_status='failed'

外部依赖 mock：
- yunwu_adapter.chat    → patch app.routers.operator_intake_direct.yunwu_adapter.chat
- generate_docx / pdf   → patch app.services.intake_report.generate_docx / generate_pdf
  （后台函数内 `from app.services.intake_report import ...`，patch 源头模块即可）

注意（expire_on_commit=False 坑）：
  后台任务用 `async with AsyncSessionLocal()` 开独立 session 写库；test_session 的
  identity map 缓存了 seed 时的对象属性，断言前必须 expire_all 重新查询。

注意（coverage 与 ASGITransport 坑）：
  coverage.py 在 pytest-asyncio + httpx ASGITransport + greenlet 切换场景下
  对 endpoint 主体的追踪会丢失，因此端点主体（start_session / session_chat 等）
  在 cov 报告里长期显示未覆盖。模块级函数被直接 await 调用，cov 能正常记录，
  所以本文件通过直接调用 helper 来补覆盖率。
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from starlette.datastructures import Headers, Headers as StarletteHeaders

from app.models.credential import AiModel
from app.models.kol import Kol
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeOperatorSession, KolIntakeQuestion,
)
from app.models.user import User
from app.routers.operator_intake_direct import (
    BridgeRequest,
    ChatRequest,
    StartSessionRequest,
    SubmitBody,
    _build_full_system_prompt,
    _generate_operator_session_report,
    _get_active_kol,
    _get_ip,
    _get_own_session,
    list_sessions,
    require_operator,
    session_bridge,
    session_chat,
    session_status,
    session_submit,
    start_session,
    _DEFAULT_REPORT_MODEL,
    _DEFAULT_REPORT_PROVIDER,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_report_test_tables(test_session):
    """清理 kol_intake_* + ai_models，避免 unique 冲突与数据污染。

    命名故意与 test_operator_intake_direct.py 的 _cleanup_intake_tables 不同：
    pytest 把同名 autouse fixture 视为同一 fixture，两个文件一起跑时会互相
    覆盖/叠加导致 setup 异常。

    KolIntakeConfig.config_key 与 AiModel.model_id 都是 unique，不清理会让
    第二个 seed 同 key 的测试 IntegrityError。
    """
    await test_session.execute(delete(KolIntakeOperatorSession))
    await test_session.execute(delete(KolIntakeConfig))
    await test_session.execute(delete(KolIntakeQuestion))
    await test_session.execute(delete(AiModel))
    await test_session.commit()
    yield


async def _seed_question(
    test_session, *,
    order_num: int,
    category: str,
    text: str,
    is_required: bool = True,
    is_active: bool = True,
) -> KolIntakeQuestion:
    q = KolIntakeQuestion(
        order_num=order_num,
        category=category,
        question_text=text,
        is_required=is_required,
        is_active=is_active,
    )
    test_session.add(q)
    await test_session.commit()
    await test_session.refresh(q)
    return q


async def _seed_report_config(
    test_session, *,
    ai_model_id: int | None = None,
    system_prompt: str | None = None,
) -> KolIntakeConfig:
    """seed report_generation config（router 后台任务固定查这个 key）。"""
    config = KolIntakeConfig(
        config_key="report_generation",
        ai_model_id=ai_model_id,
        system_prompt=system_prompt,
        is_active=True,
    )
    test_session.add(config)
    await test_session.commit()
    await test_session.refresh(config)
    return config


async def _seed_ai_model(
    test_session, *, status: str = "active",
) -> AiModel:
    suffix = uuid.uuid4().hex[:8]
    m = AiModel(
        name=f"cov_report_{suffix}",
        provider="yunwu",
        model_id=f"cov-report-model-{suffix}",
        status=status,
    )
    test_session.add(m)
    await test_session.commit()
    await test_session.refresh(m)
    return m


async def _seed_session(
    test_session, operator_user, **kwargs,
) -> KolIntakeOperatorSession:
    sess = KolIntakeOperatorSession(operator_id=operator_user.id, **kwargs)
    test_session.add(sess)
    await test_session.commit()
    await test_session.refresh(sess)
    return sess


async def _refresh_session(test_session, sess_id: int) -> KolIntakeOperatorSession:
    """后台任务用独立 session commit；test_session 因 expire_on_commit=False
    缓存了旧属性。expire_all 后重新查询才能拿到 ready/failed 等新值。

    注意：expire_all() 是同步方法（Sync-style ORM API），不能 await。
    """
    test_session.expire_all()
    return (await test_session.execute(
        select(KolIntakeOperatorSession).where(KolIntakeOperatorSession.id == sess_id)
    )).scalar_one()


# ---------------------------------------------------------------------------
# _build_full_system_prompt
# ---------------------------------------------------------------------------


class TestBuildFullSystemPrompt:
    @pytest.mark.asyncio
    async def test_with_questions_grouped_by_category(
        self, test_session,
    ):
        """多题目多分类：输出含 base_prompt + 提纲标题；同分类只输出一次 header。

        optional_note（"（选填...）"）由该分类**首题**的 is_required 决定：
          - 首题必填 → header 无标注
          - 首题选填 → header 带标注
        """
        # 必填首题分类
        await _seed_question(
            test_session, order_num=1, category="基本信息",
            text="你的名字？", is_required=True,
        )
        await _seed_question(
            test_session, order_num=2, category="基本信息",
            text="备注", is_required=False,
        )
        # 选填首题分类
        await _seed_question(
            test_session, order_num=3, category="扩展信息",
            text="次要问题？", is_required=False,
        )

        result = await _build_full_system_prompt("你是面试官", test_session)

        # base_prompt 在最前
        assert result.startswith("你是面试官")
        assert "【访谈提纲（需覆盖所有★必填项）】" in result
        # 同分类 header 只出现一次（"基本信息"作为 header 出现一次，第二题不再重复）
        assert result.count("基本信息") == 1
        # 必填首题分类的 header 无标注
        assert "基本信息\n" in result
        assert "基本信息（选填" not in result
        # 选填首题分类的 header 带标注
        assert "扩展信息（选填，能问到更好）" in result
        # 必填题带 ★ 前缀和 order_num
        assert "★ 1. 你的名字？" in result
        # 同分类的选填题无 ★，但带前导空格 + order_num
        assert "   2. 备注" in result
        # 选填首题分类的题目也无 ★
        assert "   3. 次要问题？" in result

    @pytest.mark.asyncio
    async def test_required_category_has_no_optional_note(
        self, test_session,
    ):
        """is_required=True 的分类 header 不应有"（选填...）"标注。"""
        await _seed_question(
            test_session, order_num=1, category="必填类",
            text="q1", is_required=True,
        )

        result = await _build_full_system_prompt("base", test_session)

        assert "必填类" in result
        assert "（选填" not in result
        assert "★ 1. q1" in result

    @pytest.mark.asyncio
    async def test_empty_questions_returns_base_plus_header_only(
        self, test_session,
    ):
        """无题目 → 输出 base_prompt + 提纲标题，但无任何题目行（无 ★）。"""
        result = await _build_full_system_prompt("base", test_session)

        assert result.startswith("base")
        assert "【访谈提纲（需覆盖所有★必填项）】" in result
        # 无题目 → 不应出现带 order_num 的题目行（★ 前缀的标题行）
        assert "★ 1." not in result
        assert "★ 2." not in result

    @pytest.mark.asyncio
    async def test_inactive_questions_excluded(
        self, test_session,
    ):
        """is_active=False 的题目被排除（router 只查 is_active=True）。"""
        await _seed_question(
            test_session, order_num=1, category="A",
            text="active q", is_active=True,
        )
        await _seed_question(
            test_session, order_num=2, category="B",
            text="inactive q", is_active=False,
        )

        result = await _build_full_system_prompt("base", test_session)
        assert "active q" in result
        assert "inactive q" not in result


# ---------------------------------------------------------------------------
# _generate_operator_session_report
# ---------------------------------------------------------------------------


class TestGenerateOperatorSessionReport:
    @pytest.mark.asyncio
    async def test_success_with_config_and_active_model_thinking_ok(
        self, test_session, operator_user,
    ):
        """config + active ai_model + thinking 成功 → ready，
        路径走 ai_model.model_id/provider，ai_report_raw={'thinking_supported': True}。"""
        ai_model = await _seed_ai_model(test_session, status="active")
        await _seed_report_config(
            test_session,
            ai_model_id=int(ai_model.id),
            system_prompt="模板:{qa_content}",
        )
        sess = await _seed_session(
            test_session, operator_user,
            messages=[
                {"role": "assistant", "content": "你叫什么？"},
                {"role": "user", "content": "张三"},
            ],
            kol_name="张三",
        )

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="## 报告",
        ) as mocked_chat, patch(
            "app.services.intake_report.generate_docx", return_value="x.docx",
        ) as mocked_docx, patch(
            "app.services.intake_report.generate_pdf", return_value="x.pdf",
        ) as mocked_pdf:
            await _generate_operator_session_report(sess.id)

        # thinking 调用一次（成功）
        mocked_chat.assert_awaited_once()
        _, kwargs = mocked_chat.call_args
        # 使用 config 配置的 model_id / provider（非默认）
        assert kwargs["model_id"] == ai_model.model_id
        assert kwargs["provider"] == ai_model.provider
        # thinking 启用
        assert kwargs["extra_body"] == {
            "thinking": {"type": "enabled", "budget_tokens": 6000},
        }
        # prompt 模板替换 {qa_content}，含配对的问答
        sent_content = kwargs["messages"][0]["content"]
        assert sent_content.startswith("模板:")
        assert "张三" in sent_content
        # 文件生成调用使用 op_{session_id} 前缀，避免与 submissions 表 id 冲突
        mocked_docx.assert_called_once_with(f"op_{sess.id}", "## 报告", "张三")
        mocked_pdf.assert_called_once_with(f"op_{sess.id}", "## 报告", "张三")

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"
        assert fresh.ai_report == "## 报告"
        assert fresh.ai_report_raw == {"thinking_supported": True}
        assert fresh.docx_path == "x.docx"
        assert fresh.pdf_path == "x.pdf"
        assert fresh.report_generated_at is not None

    @pytest.mark.asyncio
    async def test_success_thinking_fails_then_fallback(
        self, test_session, operator_user,
    ):
        """第一次 chat 抛错（thinking 不支持），fallback 第二次成功 →
        ai_report_raw={'thinking_supported': False}。"""
        sess = await _seed_session(test_session, operator_user, messages=[])

        call_count = {"n": 0}

        async def _fake_chat(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("thinking not supported")
            # 验证 fallback 调用不含 thinking extra_body
            assert "extra_body" not in kwargs or "thinking" not in kwargs.get("extra_body", {})
            return "fallback report"

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            side_effect=_fake_chat,
        ), patch(
            "app.services.intake_report.generate_docx", return_value="d.docx",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p.pdf",
        ):
            await _generate_operator_session_report(sess.id)

        # 两次调用：thinking 失败 + fallback 成功
        assert call_count["n"] == 2

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"
        assert fresh.ai_report == "fallback report"
        assert fresh.ai_report_raw == {"thinking_supported": False}

    @pytest.mark.asyncio
    async def test_no_config_uses_default_model_and_default_prompt(
        self, test_session, operator_user,
    ):
        """未 seed report_generation config → 用 _DEFAULT_REPORT_MODEL/PROVIDER
        和 _DEFAULT_REPORT_PROMPT，messages=[] → qa_content="（暂无完整对话记录）"。"""
        sess = await _seed_session(test_session, operator_user, messages=[])

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="default-model report",
        ) as mocked_chat, patch(
            "app.services.intake_report.generate_docx", return_value="d.docx",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p.pdf",
        ):
            await _generate_operator_session_report(sess.id)

        _, kwargs = mocked_chat.call_args
        assert kwargs["model_id"] == _DEFAULT_REPORT_MODEL
        assert kwargs["provider"] == _DEFAULT_REPORT_PROVIDER
        # 默认 prompt 模板含 {qa_content}，空 messages → 兜底字符串
        assert "（暂无完整对话记录）" in kwargs["messages"][0]["content"]

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"
        assert fresh.ai_report == "default-model report"

    @pytest.mark.asyncio
    async def test_config_with_inactive_model_uses_default(
        self, test_session, operator_user,
    ):
        """config 配了 inactive ai_model → ai_model.status != 'active'，
        仍用默认 model（不 failed）。"""
        ai_model = await _seed_ai_model(test_session, status="inactive")
        await _seed_report_config(
            test_session,
            ai_model_id=int(ai_model.id),
            system_prompt="x:{qa_content}",
        )
        sess = await _seed_session(test_session, operator_user, messages=[])

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="r",
        ) as mocked_chat, patch(
            "app.services.intake_report.generate_docx", return_value="d.docx",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p.pdf",
        ):
            await _generate_operator_session_report(sess.id)

        _, kwargs = mocked_chat.call_args
        # inactive → 不用 ai_model 的字段，走默认
        assert kwargs["model_id"] == _DEFAULT_REPORT_MODEL
        assert kwargs["provider"] == _DEFAULT_REPORT_PROVIDER

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"

    @pytest.mark.asyncio
    async def test_config_with_none_ai_model_id_uses_default(
        self, test_session, operator_user,
    ):
        """config 存在但 ai_model_id=None → 走默认 model（条件短路）。"""
        await _seed_report_config(
            test_session, ai_model_id=None, system_prompt="x:{qa_content}",
        )
        sess = await _seed_session(test_session, operator_user, messages=[])

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="r",
        ) as mocked_chat, patch(
            "app.services.intake_report.generate_docx", return_value="d.docx",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p.pdf",
        ):
            await _generate_operator_session_report(sess.id)

        _, kwargs = mocked_chat.call_args
        assert kwargs["model_id"] == _DEFAULT_REPORT_MODEL

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"

    @pytest.mark.asyncio
    async def test_config_without_system_prompt_uses_default_template(
        self, test_session, operator_user,
    ):
        """config.system_prompt=None → fallback 到 _DEFAULT_REPORT_PROMPT。"""
        await _seed_report_config(
            test_session, ai_model_id=None, system_prompt=None,
        )
        # user 消息无 prev assistant → qa_content 兜底
        sess = await _seed_session(
            test_session, operator_user,
            messages=[{"role": "user", "content": "x"}],
        )

        captured = {}

        async def _fake_chat(**kwargs):
            captured["messages"] = kwargs["messages"]
            return "report"

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            side_effect=_fake_chat,
        ), patch(
            "app.services.intake_report.generate_docx", return_value="d",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p",
        ):
            await _generate_operator_session_report(sess.id)

        # _DEFAULT_REPORT_PROMPT 含 "## 基本信息" 结构标记
        sent_content = captured["messages"][0]["content"]
        assert "## 基本信息" in sent_content
        # user 无 prev assistant → 走兜底
        assert "（暂无完整对话记录）" in sent_content

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "ready"

    @pytest.mark.asyncio
    async def test_qa_content_pairs_user_with_prev_assistant(
        self, test_session, operator_user,
    ):
        """user 消息往前找最近的 assistant 内容，配成「问：x\n答：y」；
        空白 content 被跳过。"""
        sess = await _seed_session(
            test_session, operator_user,
            messages=[
                {"role": "assistant", "content": "问1"},
                {"role": "user", "content": "答1"},
                {"role": "assistant", "content": "问2"},
                {"role": "user", "content": "答2"},
                # 空 content 的消息被跳过
                {"role": "user", "content": "   "},
            ],
        )

        captured = {}

        async def _fake_chat(**kwargs):
            captured["messages"] = kwargs["messages"]
            return "report"

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            side_effect=_fake_chat,
        ), patch(
            "app.services.intake_report.generate_docx", return_value="d",
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p",
        ):
            await _generate_operator_session_report(sess.id)

        prompt_content = captured["messages"][0]["content"]
        # 两个问答对都拼接进去
        assert "问：问1\n答：答1" in prompt_content
        assert "问：问2\n答：答2" in prompt_content
        # 空 content 的 user 消息被跳过（不产生额外的"答："）
        assert prompt_content.count("答：") == 2

    @pytest.mark.asyncio
    async def test_session_not_found_returns_silently(
        self, test_session,
    ):
        """session_id 不存在 → 函数静默 return（不抛错、不调 yunwu、不写库）。"""
        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock,
        ) as mocked_chat:
            # 不应抛错
            await _generate_operator_session_report(999999)

        mocked_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_docx_exception_marks_failed(
        self, test_session, operator_user,
    ):
        """generate_docx 抛错 → 外层 except → report_status='failed'，
        ai_report_raw 含 error 字段（截断到 500 字符内）。"""
        sess = await _seed_session(test_session, operator_user, messages=[])

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="r",
        ), patch(
            "app.services.intake_report.generate_docx",
            side_effect=RuntimeError("docx boom"),
        ), patch(
            "app.services.intake_report.generate_pdf", return_value="p",
        ):
            await _generate_operator_session_report(sess.id)

        fresh = await _refresh_session(test_session, sess.id)
        assert fresh.report_status == "failed"
        assert isinstance(fresh.ai_report_raw, dict)
        assert "error" in fresh.ai_report_raw
        assert "docx boom" in fresh.ai_report_raw["error"]


# ---------------------------------------------------------------------------
# require_operator / _get_own_session / _get_ip / _get_active_kol
#
# 这些 helper 通过 ASGITransport 调用端点时，coverage.py 的 greenlet 追踪
# 会丢失行级记录；直接 await 调用能让 cov 正确归因。这里补它们的 403/404
# 等错误分支。
# ---------------------------------------------------------------------------


def _make_raw_request(headers: dict | None = None, client: tuple | None = None) -> Request:
    """构造最小 Starlette Request，用于测 _get_ip。

    client=("host", port) 形式；省略时 request.client is None。
    """
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope: dict = {"type": "http", "headers": raw_headers}
    if client is not None:
        scope["client"] = client
    return Request(scope)


class TestRequireOperator:
    @pytest.mark.asyncio
    async def test_password_not_changed_raises_403(self, operator_user):
        """password_changed_at=None → 403 AUTH_FORCE_CHANGE_PASSWORD（行 52）。"""
        operator_user.password_changed_at = None

        with pytest.raises(HTTPException) as exc:
            await require_operator(operator_user)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "AUTH_FORCE_CHANGE_PASSWORD"
        assert "修改初始密码" in exc.value.detail["message"]

    @pytest.mark.asyncio
    async def test_wrong_role_raises_403(self, operator_user):
        """role 不在 ('operator', 'admin') → 403 PERMISSION_DENIED（行 57）。"""
        operator_user.role = "viewer"

        with pytest.raises(HTTPException) as exc:
            await require_operator(operator_user)

        assert exc.value.status_code == 403
        assert exc.value.detail["code"] == "PERMISSION_DENIED"

    @pytest.mark.asyncio
    async def test_operator_role_returns_user(self, operator_user):
        """role='operator' 且已改密 → 直接返回 user。"""
        result = await require_operator(operator_user)
        assert result.id == operator_user.id

    @pytest.mark.asyncio
    async def test_admin_role_returns_user(self, admin_user):
        """role='admin' 且已改密 → 通过（admin 也允许）。"""
        result = await require_operator(admin_user)
        assert result.id == admin_user.id


class TestGetOwnSession:
    @pytest.mark.asyncio
    async def test_nonexistent_session_raises_404(
        self, test_session, operator_user,
    ):
        """session_id 不存在 → _get_own_session 抛 404（行 72-77）。"""
        with pytest.raises(HTTPException) as exc:
            await _get_own_session(999999, operator_user, test_session)

        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "RESOURCE_NOT_FOUND"
        assert "会话不存在" in exc.value.detail["message"]

    @pytest.mark.asyncio
    async def test_cross_user_session_raises_404(
        self, test_session, operator_user, admin_user,
    ):
        """session 属于其他 user → _get_own_session 过滤 operator_id → 404。"""
        sess = await _seed_session(test_session, operator_user)

        with pytest.raises(HTTPException) as exc:
            await _get_own_session(sess.id, admin_user, test_session)

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_own_session_returned(
        self, test_session, operator_user,
    ):
        """session 存在且归属本 user → 返回 session 对象。"""
        sess = await _seed_session(test_session, operator_user, kol_name="归属校验")

        result = await _get_own_session(sess.id, operator_user, test_session)
        assert result.id == sess.id
        assert result.kol_name == "归属校验"


class TestGetIp:
    def test_forwarded_for_first_segment(self):
        """x-forwarded-for 存在 → 取第一个 IP（行 104）。"""
        req = _make_raw_request(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        assert _get_ip(req) == "1.2.3.4"

    def test_forwarded_for_stripped(self):
        """x-forwarded-for 含空格 → strip 后返回。"""
        req = _make_raw_request(headers={"x-forwarded-for": "  9.9.9.9  , 8.8.8.8"})
        assert _get_ip(req) == "9.9.9.9"

    def test_no_header_uses_client_host(self):
        """无 forwarded header → request.client.host。"""
        req = _make_raw_request(client=("192.168.1.10", 5555))
        assert _get_ip(req) == "192.168.1.10"

    def test_no_header_no_client_returns_unknown(self):
        """无 header 且无 client → "unknown"。"""
        req = _make_raw_request()
        assert _get_ip(req) == "unknown"


class TestGetActiveKol:
    @pytest.mark.asyncio
    async def test_kol_id_none_returns_none(self, test_session):
        """kol_id=None → 直接返回 None，不查 DB。"""
        result = await _get_active_kol(test_session, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_existing_kol_returned(self, test_session):
        """seed 一个 kol → 返回它。"""
        kol = Kol(name="cov_active_kol")
        test_session.add(kol)
        await test_session.commit()
        await test_session.refresh(kol)

        result = await _get_active_kol(test_session, int(kol.id))
        assert result is not None
        assert result.id == kol.id
        assert result.name == "cov_active_kol"

    @pytest.mark.asyncio
    async def test_nonexistent_kol_raises_404(self, test_session):
        """kol_id 不存在 → 404 RESOURCE_NOT_FOUND（行 114-119）。"""
        with pytest.raises(HTTPException) as exc:
            await _get_active_kol(test_session, 999999)

        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "RESOURCE_NOT_FOUND"
        assert "达人不存在" in exc.value.detail["message"]

    @pytest.mark.asyncio
    async def test_deleted_kol_raises_404(self, test_session):
        """deleted_at 不为 null 的 kol → 视为不存在 → 404。"""
        from datetime import datetime, timezone
        kol = Kol(name="cov_deleted_kol", deleted_at=datetime.now(tz=timezone.utc))
        test_session.add(kol)
        await test_session.commit()
        await test_session.refresh(kol)

        with pytest.raises(HTTPException) as exc:
            await _get_active_kol(test_session, int(kol.id))

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# 端点函数直接调用（绕过 ASGITransport）
#
# test_operator_intake_direct.py 通过 httpx.ASGITransport 调端点，coverage.py
# 在 greenlet 切换场景下行追踪会丢失，cov 报告对端点主体不稳定（同一组测试
# 在 67%-73% 间波动）。直接 await 端点函数能绕开 greenlet，让 cov 稳定归因。
# ---------------------------------------------------------------------------


def _make_request_with_ua(
    headers: dict | None = None, client: tuple | None = None,
) -> Request:
    """带默认 user-agent 的 Request（端点函数会读 request.headers.get('user-agent')）。"""
    merged = {"user-agent": "cov-direct-call/1.0"}
    if headers:
        merged.update(headers)
    return _make_raw_request(headers=merged, client=client)


class TestStartSessionDirect:
    @pytest.mark.asyncio
    async def test_start_no_kol_returns_session_id(
        self, test_session, operator_user,
    ):
        """直接 await start_session（无 kol_id）→ success_response 含 session_id。"""
        body = StartSessionRequest()
        req = _make_request_with_ua()

        result = await start_session(
            body, req, db=test_session, current_user=operator_user,
        )

        assert result.success is True
        assert "session_id" in result.data
        assert result.data["kol_id"] is None

    @pytest.mark.asyncio
    async def test_start_with_kol_name(
        self, test_session, operator_user,
    ):
        """带 kol_name → 回显 kol_name。"""
        body = StartSessionRequest(kol_name="直接调用红人")
        req = _make_request_with_ua()

        result = await start_session(
            body, req, db=test_session, current_user=operator_user,
        )

        assert result.data["kol_name"] == "直接调用红人"

    @pytest.mark.asyncio
    async def test_start_invalid_kol_raises_404(
        self, test_session, operator_user,
    ):
        """不存在的 kol_id → _get_active_kol 抛 404 透传。"""
        body = StartSessionRequest(kol_id=999999)
        req = _make_request_with_ua()

        with pytest.raises(HTTPException) as exc:
            await start_session(
                body, req, db=test_session, current_user=operator_user,
            )
        assert exc.value.status_code == 404


class TestSessionStatusDirect:
    @pytest.mark.asyncio
    async def test_status_pending(
        self, test_session, operator_user,
    ):
        """直接 await session_status（pending）→ download_ready=False, ai_report=None。"""
        sess = await _seed_session(test_session, operator_user)

        result = await session_status(
            sess.id, db=test_session, current_user=operator_user,
        )

        assert result.data["report_status"] == "pending"
        assert result.data["download_ready"] is False
        assert result.data["ai_report"] is None

    @pytest.mark.asyncio
    async def test_status_ready(
        self, test_session, operator_user,
    ):
        """ready 状态 → download_ready=True, ai_report 非空。"""
        sess = await _seed_session(
            test_session, operator_user,
            report_status="ready", ai_report="## 报告",
        )

        result = await session_status(
            sess.id, db=test_session, current_user=operator_user,
        )

        assert result.data["report_status"] == "ready"
        assert result.data["download_ready"] is True
        assert "报告" in result.data["ai_report"]

    @pytest.mark.asyncio
    async def test_status_cross_user_404(
        self, test_session, operator_user, admin_user,
    ):
        """operator 的 session，admin 直接调用 → _get_own_session 404。"""
        sess = await _seed_session(test_session, operator_user)

        with pytest.raises(HTTPException) as exc:
            await session_status(
                sess.id, db=test_session, current_user=admin_user,
            )
        assert exc.value.status_code == 404


class TestSessionSubmitDirect:
    @pytest.mark.asyncio
    async def test_submit_pending_returns_generating(
        self, test_session, operator_user,
    ):
        """pending session 直接 await submit → success + report_status='generating'。"""
        from starlette.background import BackgroundTasks

        sess = await _seed_session(test_session, operator_user)
        body = SubmitBody(messages=[{"role": "user", "content": "hi"}])
        bg = BackgroundTasks()
        req = _make_request_with_ua()

        result = await session_submit(
            sess.id, body, bg, req, db=test_session, current_user=operator_user,
        )

        assert result.success is True
        assert result.data["report_status"] == "generating"
        # 直接调用时 BackgroundTasks 不会自动执行（无 ASGITransport 响应周期）
        assert len(bg.tasks) == 1

    @pytest.mark.asyncio
    async def test_submit_already_generating_raises_409(
        self, test_session, operator_user,
    ):
        """非 pending 状态 → 409 VALIDATION_ERROR。"""
        from starlette.background import BackgroundTasks

        sess = await _seed_session(
            test_session, operator_user, report_status="generating",
        )
        body = SubmitBody(messages=[])
        bg = BackgroundTasks()
        req = _make_request_with_ua()

        with pytest.raises(HTTPException) as exc:
            await session_submit(
                sess.id, body, bg, req,
                db=test_session, current_user=operator_user,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "VALIDATION_ERROR"


class TestListSessionsDirect:
    @pytest.mark.asyncio
    async def test_list_empty(self, test_session, operator_user):
        """无 session → 空列表。"""
        result = await list_sessions(
            db=test_session, current_user=operator_user,
        )
        assert result.success is True
        assert result.data == []

    @pytest.mark.asyncio
    async def test_list_returns_own_sessions_with_comp(
        self, test_session, operator_user, admin_user,
    ):
        """有数据 → 走 list comprehension（行 616），且只返回自己的。"""
        test_session.add_all([
            KolIntakeOperatorSession(operator_id=operator_user.id, kol_name="A"),
            KolIntakeOperatorSession(operator_id=operator_user.id, kol_name="B"),
            KolIntakeOperatorSession(operator_id=admin_user.id, kol_name="C"),
        ])
        await test_session.commit()

        result = await list_sessions(
            db=test_session, current_user=operator_user,
        )
        names = {item["kol_name"] for item in result.data}
        assert names == {"A", "B"}
        # 字段结构
        for item in result.data:
            assert "id" in item
            assert "report_status" in item
            assert "messages" not in item


class TestSessionChatDirect:
    @pytest.mark.asyncio
    async def test_chat_no_config_returns_null_reply(
        self, test_session, operator_user,
    ):
        """无 conversation_bridge config → reply=None + error（直接调用）。"""
        sess = await _seed_session(test_session, operator_user)
        body = ChatRequest(messages=[{"role": "user", "content": "hi"}])
        req = _make_request_with_ua()

        result = await session_chat(
            sess.id, body, req, db=test_session, current_user=operator_user,
        )

        assert result.success is True
        assert result.data["reply"] is None
        assert result.data["error"] == "AI对话暂未配置"

    @pytest.mark.asyncio
    async def test_chat_already_submitted_returns_validation_error(
        self, test_session, operator_user,
    ):
        """session.report_status='generating' → error_response VALIDATION_ERROR。"""
        sess = await _seed_session(
            test_session, operator_user, report_status="generating",
        )
        body = ChatRequest(messages=[])
        req = _make_request_with_ua()

        result = await session_chat(
            sess.id, body, req, db=test_session, current_user=operator_user,
        )

        assert result.success is False
        assert result.code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_chat_with_config_mock_yunwu(
        self, test_session, operator_user,
    ):
        """seed config + active ai_model + mock yunwu → reply 返回。"""
        suffix = uuid.uuid4().hex[:8]
        ai_model = AiModel(
            name=f"cov_chat_direct_{suffix}",
            provider="yunwu",
            model_id=f"cov-chat-direct-{suffix}",
            status="active",
        )
        test_session.add(ai_model)
        await test_session.commit()
        await test_session.refresh(ai_model)

        config = KolIntakeConfig(
            config_key="conversation_bridge",
            ai_model_id=int(ai_model.id),
            system_prompt="你是面试官",
            is_active=True,
        )
        test_session.add(config)
        await test_session.commit()

        sess = await _seed_session(test_session, operator_user)
        body = ChatRequest(messages=[{"role": "user", "content": "你好"}])
        req = _make_request_with_ua()

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="你好呀",
        ):
            result = await session_chat(
                sess.id, body, req, db=test_session, current_user=operator_user,
            )

        assert result.data["reply"] == "你好呀"
        assert result.data["role"] == "assistant"


class TestSessionBridgeDirect:
    @pytest.mark.asyncio
    async def test_bridge_no_config_returns_empty(
        self, test_session, operator_user,
    ):
        """无 config → reply=''（直接调用，不调 yunwu）。"""
        sess = await _seed_session(test_session, operator_user)
        body = BridgeRequest(user_answer="x", question_text="y")

        result = await session_bridge(
            sess.id, body, db=test_session, current_user=operator_user,
        )
        assert result.data["reply"] == ""

    @pytest.mark.asyncio
    async def test_bridge_normal_branch_mock_yunwu(
        self, test_session, operator_user,
    ):
        """普通过渡语分支 + mock yunwu → reply 返回（覆盖 instruction 普通分支）。"""
        suffix = uuid.uuid4().hex[:8]
        ai_model = AiModel(
            name=f"cov_bridge_{suffix}",
            provider="yunwu",
            model_id=f"cov-bridge-{suffix}",
            status="active",
        )
        test_session.add(ai_model)
        await test_session.commit()
        await test_session.refresh(ai_model)

        config = KolIntakeConfig(
            config_key="conversation_bridge",
            ai_model_id=int(ai_model.id),
            system_prompt=None,  # 走 _DEFAULT_BRIDGE_SYSTEM_PROMPT
            is_active=True,
        )
        test_session.add(config)
        await test_session.commit()

        sess = await _seed_session(test_session, operator_user)
        body = BridgeRequest(
            user_answer="我做美妆",
            question_text="你做什么内容？",
            next_question_text="下一题",
            is_section_change=True,
            next_section="商业化",
        )

        with patch(
            "app.routers.operator_intake_direct.yunwu_adapter.chat",
            new_callable=AsyncMock, return_value="挺不错",
        ):
            result = await session_bridge(
                sess.id, body, db=test_session, current_user=operator_user,
            )
        assert result.data["reply"] == "挺不错"
