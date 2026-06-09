"""
app/routers/operator_intake_direct.py

运营直发对话接口（JWT 鉴权，operator / admin 角色）：
  POST /api/operator/intake/direct/start                — 新建会话
  POST /api/operator/intake/direct/{session_id}/chat    — 发消息，AI 返回回复
  POST /api/operator/intake/direct/{session_id}/bridge  — AI 过渡语（前端主导模式）
  POST /api/operator/intake/direct/{session_id}/submit  — 提交，触发报告生成
  GET  /api/operator/intake/direct/{session_id}/status  — 轮询报告状态（含 ai_report）
  GET  /api/operator/intake/direct/{session_id}/download — 下载报告（支持 ?token= 参数）
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response, error_response, ErrorCode
from app.middlewares.auth import get_current_user, get_current_user_optional
from app.models.credential import AiModel
from app.models.kol_intake import (
    KolIntakeConfig, KolIntakeOperatorSession, KolIntakeQuestion,
)
from app.models.user import User

router = APIRouter(prefix="/operator/intake/direct", tags=["operator-intake-direct"])


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    if current_user.password_changed_at is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "AUTH_FORCE_CHANGE_PASSWORD", "message": "请先修改初始密码"},
        )
    if current_user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=403,
            detail={"code": "PERMISSION_DENIED", "message": "无权限访问"},
        )
    return current_user


async def _get_own_session(
    session_id: int, current_user: User, db: AsyncSession
) -> KolIntakeOperatorSession:
    session = (await db.execute(
        select(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.id == session_id)
        .where(KolIntakeOperatorSession.operator_id == current_user.id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "会话不存在"},
        )
    return session


async def _build_full_system_prompt(base_prompt: str, db: AsyncSession) -> str:
    """在 base_prompt 后追加题目提纲（复用 intake_public 相同逻辑）。"""
    questions = (await db.execute(
        select(KolIntakeQuestion)
        .where(KolIntakeQuestion.is_active == True)
        .order_by(KolIntakeQuestion.order_num)
    )).scalars().all()

    lines = [base_prompt, "", "【访谈提纲（需覆盖所有★必填项）】"]
    current_category = None
    for q in questions:
        if q.category != current_category:
            current_category = q.category
            optional_note = "（选填，能问到更好）" if not q.is_required else ""
            lines.append(f"{q.category}{optional_note}")
        prefix = "★ " if q.is_required else "   "
        lines.append(f"{prefix}{q.order_num}. {q.question_text}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    kol_name: str | None = None


@router.post("/start")
async def start_session(
    body: StartSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """新建运营直发对话会话，返回 session_id。"""
    session = KolIntakeOperatorSession(
        operator_id=current_user.id,
        kol_name=body.kol_name,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return success_response(data={
        "session_id": session.id,
        "kol_name":   session.kol_name,
    })


# ---------------------------------------------------------------------------
# POST /{session_id}/chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict] = []


class SubmitBody(BaseModel):
    messages: list[dict] = []


@router.post("/{session_id}/chat")
async def session_chat(
    session_id: int,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """发消息，AI 返回回复；同时将完整 messages 持久化到会话。"""
    session = await _get_own_session(session_id, current_user, db)

    if session.report_status not in ("pending",):
        return error_response(ErrorCode.VALIDATION_ERROR, "会话已提交，无法继续对话")

    config = (await db.execute(
        select(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
    )).scalar_one_or_none()

    if config is None or config.ai_model_id is None:
        return success_response(data={"reply": None, "error": "AI对话暂未配置"})

    ai_model = (await db.execute(
        select(AiModel).where(AiModel.id == config.ai_model_id)
    )).scalar_one_or_none()

    if ai_model is None or ai_model.status != "active":
        return success_response(data={"reply": None, "error": "AI对话暂未配置"})

    base_prompt = config.system_prompt or ""
    full_system = await _build_full_system_prompt(base_prompt, db)

    ai_messages = [{"role": "system", "content": full_system}] + list(body.messages)

    reply = await yunwu_adapter.chat(
        messages=ai_messages,
        db=db,
        model_id=ai_model.model_id,
        provider=ai_model.provider,
        feature="kol_intake_chat",
        max_tokens=300,
        temperature=0.7,
    )

    # 持久化最新 messages
    await db.execute(
        update(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.id == session_id)
        .values(messages=body.messages, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()

    return success_response(data={"reply": reply, "role": "assistant"})


# ---------------------------------------------------------------------------
# POST /{session_id}/bridge
# ---------------------------------------------------------------------------

class BridgeRequest(BaseModel):
    user_answer: str
    question_text: str
    next_question_text: str | None = None
    next_question_hint: str | None = None
    is_last_question: bool = False
    is_section_change: bool = False
    next_section: str | None = None
    is_multi_collect: bool = False
    collect_count: int = 0


@router.post("/{session_id}/bridge")
async def session_bridge(
    session_id: int,
    body: BridgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """
    AI 过渡语接口（前端主导对话模式）。
    逻辑与 /api/intake/{token}/bridge 完全一致，鉴权改为 JWT。
    bridge 调用失败时静默降级，返回 reply=""。
    """
    await _get_own_session(session_id, current_user, db)  # 校验会话归属

    if body.is_multi_collect and body.collect_count > 0:
        instruction = (
            f'用户正在回答一个可以填多条的问题："{body.question_text}"，'
            f'这是他们的第 {body.collect_count} 条回答。\n'
            '请先对这条回答做出真诚的回应（共情、好奇、肯定都可以，要具体到他们说的内容），'
            '然后自然地问他们还有没有其他的。\n'
            '不要说"记下了"这种机械的话。像朋友聊天一样。'
        )
    elif body.is_last_question:
        instruction = (
            f'用户刚回答了最后一道问题："{body.question_text}"。\n'
            '请对回答做出真诚的回应，然后用温暖自然的方式告诉他们所有问题都聊完了，'
            '辛苦了，可以点击提交生成报告了。'
        )
    else:
        section_note = (
            f'\n下一个版块是「{body.next_section}」，简单过渡一下。'
            if body.is_section_change and body.next_section else ''
        )
        hint_note = (
            f'\n提示信息（帮你理解这个问题想问什么，但不要直接念出来）：{body.next_question_hint}'
            if body.next_question_hint else ''
        )
        instruction = (
            f'用户刚回答了问题："{body.question_text}"。\n'
            '请先对回答做出真诚的回应（1-2句，要具体到他们说的内容，不要泛泛而谈），'
            f'然后自然地过渡到下一个话题。{section_note}\n'
            '最后用一句简短的陈述句收尾即可（例如"我们再聊聊下一个话题"），'
            '绝对不能用问句结尾，不能自己造问题，题目由系统直接展示给用户。'
        )

    # 读取 conversation_bridge 配置（模型 + system_prompt 都从这里取）
    config = (await db.execute(
        select(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
    )).scalar_one_or_none()

    if config is None or config.ai_model_id is None:
        return success_response(data={"reply": ""})

    ai_model = (await db.execute(
        select(AiModel).where(AiModel.id == config.ai_model_id)
    )).scalar_one_or_none()

    if ai_model is None:
        return success_response(data={"reply": ""})

    # system_prompt：优先用数据库配置，fallback 用默认值
    _DEFAULT_BRIDGE_SYSTEM_PROMPT = (
        '你是一个红人孵化团队的面试官，正在和一个新红人聊天了解他/她的情况。\n'
        '你的风格：温暖、真诚、有洞察力，像一个聊得来的朋友。\n'
        '- 回应要具体到用户说的内容，不要用万能回复\n'
        '- 语气自然口语化，不要太正式\n'
        '- 简洁，整体不超过2句话\n'
        '- 不要用"好的""收到""了解"这种客服话术开头\n'
        '- 不要重复或改写题目文本，题目由系统直接展示给用户\n'
        '- 用陈述句收尾，不要用问句结尾，不要自己造问题\n'
        '- 不要用emoji'
    )
    system_prompt = config.system_prompt or _DEFAULT_BRIDGE_SYSTEM_PROMPT

    try:
        reply = await yunwu_adapter.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f'{instruction}\n\n用户的回答是：\n"{body.user_answer}"'},
            ],
            db=db,
            model_id=ai_model.model_id,
            provider=ai_model.provider,
            feature="kol_intake_bridge",
            max_tokens=200,
            temperature=0.7,
        )
    except Exception:
        reply = ""  # 静默降级

    return success_response(data={"reply": reply})


# ---------------------------------------------------------------------------
# POST /{session_id}/submit
# ---------------------------------------------------------------------------

@router.post("/{session_id}/submit")
async def session_submit(
    session_id: int,
    body: SubmitBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """提交会话，异步触发报告生成。"""
    session = await _get_own_session(session_id, current_user, db)

    if session.report_status != "pending":
        raise HTTPException(
            status_code=409,
            detail={"code": "VALIDATION_ERROR", "message": "会话已提交，不可重复提交"},
        )

    await db.execute(
        update(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.id == session_id)
        .values(
            messages=body.messages if body.messages else (session.messages or []),
            report_status="generating",
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    background_tasks.add_task(_generate_operator_session_report, session_id)

    return success_response(data={"report_status": "generating"})


# ---------------------------------------------------------------------------
# GET /{session_id}/status
# ---------------------------------------------------------------------------

@router.get("/{session_id}/status")
async def session_status(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """轮询报告生成状态。"""
    session = await _get_own_session(session_id, current_user, db)
    return success_response(data={
        "report_status":  session.report_status,
        "download_ready": session.report_status == "ready",
        "ai_report":      session.ai_report,   # ready 时为报告文本，否则为 null
    })


# ---------------------------------------------------------------------------
# GET /{session_id}/download
# ---------------------------------------------------------------------------

@router.get("/{session_id}/download")
async def session_download(
    session_id: int,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
    token: str | None = Query(default=None),          # 支持 ?token=xxx（window.open 场景）
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """运营下载报告。支持 Authorization header 和 ?token= query 两种鉴权方式。"""
    # fallback：header 没有 token 时使用 query string token
    user = current_user
    if user is None and token:
        from app.core.security import verify_token
        try:
            payload = verify_token(token)
            user = (await db.execute(
                select(User).where(User.id == int(payload["sub"]))
            )).scalar_one_or_none()
        except Exception:
            user = None

    if user is None or user.role not in ("operator", "admin"):
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_TOKEN_MISSING", "message": "缺少有效 Token"},
        )

    session = await _get_own_session(session_id, user, db)

    if session.report_status != "ready":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告尚未生成"},
        )

    file_path = session.docx_path if format == "docx" else session.pdf_path
    abs_path = os.path.abspath(file_path) if file_path else None
    if not abs_path or not os.path.exists(abs_path):
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告文件不存在"},
        )

    suffix = "docx" if format == "docx" else "pdf"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if format == "docx"
        else "application/pdf"
    )
    return FileResponse(
        path=abs_path,
        media_type=media_type,
        filename=f"MCN红人入驻评估报告.{suffix}",
    )


# ---------------------------------------------------------------------------
# Background task: generate report for operator session
# ---------------------------------------------------------------------------

async def _generate_operator_session_report(session_id: int) -> None:
    """
    为运营直发会话异步生成报告（复用 intake_report.py 文件生成逻辑）。
    使用独立 DB session，不复用请求中的 session。
    """
    from app.services.intake_report import generate_docx, generate_pdf

    async with AsyncSessionLocal() as db:
        session = (await db.execute(
            select(KolIntakeOperatorSession)
            .where(KolIntakeOperatorSession.id == session_id)
        )).scalar_one_or_none()
        if session is None:
            return

        try:
            config = (await db.execute(
                select(KolIntakeConfig).where(KolIntakeConfig.config_key == "report_generation")
            )).scalar_one_or_none()

            if config is None or config.ai_model_id is None:
                raise RuntimeError("report_generation AI 未配置")

            ai_model = (await db.execute(
                select(AiModel).where(AiModel.id == config.ai_model_id)
            )).scalar_one_or_none()

            if ai_model is None or ai_model.status != "active":
                raise RuntimeError("report_generation AI 模型不可用")

            # 格式化对话历史为 qa_content
            qa_lines = []
            messages = session.messages or []
            for i, msg in enumerate(messages):
                role = msg.get("role", "")
                content = msg.get("content", "").strip()
                if not content:
                    continue
                if role == "user":
                    prev_assistant = ""
                    for j in range(i - 1, -1, -1):
                        if messages[j].get("role") == "assistant":
                            prev_assistant = messages[j].get("content", "").strip()
                            break
                    if prev_assistant:
                        qa_lines.append(f"问：{prev_assistant}\n答：{content}")

            qa_content = "\n\n".join(qa_lines) if qa_lines else "（暂无完整对话记录）"

            base_prompt = config.system_prompt or ""
            report_prompt = base_prompt.replace("{qa_content}", qa_content)

            report_messages = [{"role": "user", "content": report_prompt}]

            ai_report: str = ""
            ai_report_raw: dict = {}

            try:
                ai_report = await yunwu_adapter.chat(
                    messages=report_messages,
                    db=db,
                    model_id=ai_model.model_id,
                    provider=ai_model.provider,
                    feature="kol_intake_report",
                    max_tokens=8000,
                    temperature=1.0,
                    extra_body={"thinking": {"type": "enabled", "budget_tokens": 6000}},
                )
                ai_report_raw = {"thinking_supported": True}
            except Exception:
                ai_report = await yunwu_adapter.chat(
                    messages=report_messages,
                    db=db,
                    model_id=ai_model.model_id,
                    provider=ai_model.provider,
                    feature="kol_intake_report",
                    max_tokens=8000,
                    temperature=0.7,
                )
                ai_report_raw = {"thinking_supported": False}

            # 使用 session_id 加前缀区分文件，避免与 submissions 表 id 冲突
            file_id_str = f"op_{session_id}"
            docx_path = generate_docx(file_id_str, ai_report, session.kol_name)
            pdf_path  = generate_pdf(file_id_str, ai_report, session.kol_name)

            await db.execute(
                update(KolIntakeOperatorSession)
                .where(KolIntakeOperatorSession.id == session_id)
                .values(
                    ai_report=ai_report,
                    ai_report_raw=ai_report_raw,
                    report_status="ready",
                    report_generated_at=datetime.now(timezone.utc),
                    docx_path=docx_path,
                    pdf_path=pdf_path,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        except Exception as e:
            await db.execute(
                update(KolIntakeOperatorSession)
                .where(KolIntakeOperatorSession.id == session_id)
                .values(
                    report_status="failed",
                    ai_report_raw={"error": str(e)[:500]},
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()


# ---------------------------------------------------------------------------
# GET /sessions  — 当前运营的所有直发会话列表
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """列出当前运营的所有直发会话（摘要，不含 messages）。"""
    sessions = (await db.execute(
        select(KolIntakeOperatorSession)
        .where(KolIntakeOperatorSession.operator_id == current_user.id)
        .order_by(KolIntakeOperatorSession.created_at.desc())
    )).scalars().all()

    return success_response(data=[
        {
            "id":                   s.id,
            "kol_name":             s.kol_name,
            "report_status":        s.report_status,
            "ai_report":            s.ai_report,
            "report_generated_at":  s.report_generated_at.isoformat() if s.report_generated_at else None,
            "created_at":           s.created_at.isoformat() if s.created_at else None,
        }
        for s in sessions
    ])
