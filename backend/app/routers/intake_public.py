"""
app/routers/intake_public.py

公开接口（无需鉴权）：
  GET  /api/intake/{token}          — 校验链接，返回初始状态
  POST /api/intake/{token}/chat     — AI 多轮对话（核心接口）
  POST /api/intake/{token}/submit   — 提交完整对话，触发报告生成
  GET  /api/intake/{token}/status   — 轮询报告生成状态
  GET  /api/intake/{token}/download — 博主下载报告
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response, error_response, ErrorCode
from app.models.kol_intake import (
    KolIntakeLink, KolIntakeSubmission, KolIntakeConfig, KolIntakeQuestion,
)
from app.models.credential import AiModel
from fastapi import Depends

router = APIRouter(prefix="/intake")


# ---------------------------------------------------------------------------
# GET /intake/questions
# ---------------------------------------------------------------------------

@router.get("/questions")
async def get_questions(db: AsyncSession = Depends(get_db)):
    """返回所有启用的题目，供前端驱动对话流程（无需鉴权）。"""
    questions = (await db.execute(
        select(KolIntakeQuestion)
        .where(KolIntakeQuestion.is_active == True)
        .order_by(KolIntakeQuestion.order_num)
    )).scalars().all()

    return success_response(data=[
        {
            "id":            q.id,
            "order_num":     q.order_num,
            "category":      q.category,
            "question_text": q.question_text,
            "question_type": q.question_type,
            "max_items":     q.max_items,
            "is_required":   q.is_required,
        }
        for q in questions
    ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_valid_link(token: str, db: AsyncSession):
    """
    获取有效链接。
    过期 → raise 410；不存在 → raise 404。
    返回 KolIntakeLink 对象。
    """
    from fastapi import HTTPException
    link = (await db.execute(
        select(KolIntakeLink).where(KolIntakeLink.token == token)
    )).scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_NOT_FOUND", "message": "链接不存在"})
    if link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail={"code": "LINK_EXPIRED", "message": "链接已过期"})
    return link


async def _build_full_system_prompt(base_prompt: str, db: AsyncSession) -> str:
    """在 base_prompt 后追加题目提纲。"""
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
# GET /intake/{token}
# ---------------------------------------------------------------------------

@router.get("/{token}")
async def check_link(token: str, db: AsyncSession = Depends(get_db)):
    """校验链接，返回初始状态。首次访问写入 used_at。"""
    link = await _get_valid_link(token, db)

    # 首次访问写入 used_at
    if link.used_at is None:
        await db.execute(
            update(KolIntakeLink)
            .where(KolIntakeLink.id == link.id)
            .values(used_at=datetime.now(timezone.utc))
        )
        await db.commit()

    # 检查是否已提交
    submission = (await db.execute(
        select(KolIntakeSubmission).where(KolIntakeSubmission.link_id == link.id)
    )).scalar_one_or_none()

    already_submitted = submission is not None
    existing_messages = []
    if already_submitted and submission.messages:
        existing_messages = submission.messages

    return success_response(data={
        "valid":              True,
        "kol_name":           link.kol_name,
        "already_submitted":  already_submitted,
        "existing_messages":  existing_messages,
    })


# ---------------------------------------------------------------------------
# POST /intake/{token}/chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict] = []


@router.post("/{token}/chat")
async def intake_chat(
    token: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """AI 多轮对话接口。messages=[] 时 AI 生成开场白。"""
    link = await _get_valid_link(token, db)

    # 已提交的链接不允许继续对话
    if link.submitted_at is not None:
        return error_response(ErrorCode.VALIDATION_ERROR, "问卷已提交，无法继续对话")

    # 读取 conversation_bridge 配置
    config = (await db.execute(
        select(KolIntakeConfig).where(KolIntakeConfig.config_key == "conversation_bridge")
    )).scalar_one_or_none()

    if config is None or config.ai_model_id is None:
        return success_response(data={"reply": None, "error": "AI对话暂未配置"})

    # 获取模型信息
    ai_model = (await db.execute(
        select(AiModel).where(AiModel.id == config.ai_model_id)
    )).scalar_one_or_none()

    if ai_model is None or ai_model.status != "active":
        return success_response(data={"reply": None, "error": "AI对话暂未配置"})

    # 构建完整 system_prompt（base + 题目提纲）
    base_prompt = config.system_prompt or ""
    full_system = await _build_full_system_prompt(base_prompt, db)

    # 构建发送给 AI 的 messages（system 作为第一条消息）
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

    return success_response(data={"reply": reply, "role": "assistant"})


# ---------------------------------------------------------------------------
# POST /intake/{token}/bridge
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


@router.post("/{token}/bridge")
async def intake_bridge(
    token: str,
    body: BridgeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 过渡语接口（前端主导对话流程）。
    - 仅生成对用户回答的回应 + 自然引出下一题的过渡语
    - 题目原文由前端直接显示，不经过 AI 处理
    - bridge 调用失败时静默降级，返回 reply=""
    """
    await _get_valid_link(token, db)

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
        reply = ""  # bridge 失败静默降级

    return success_response(data={"reply": reply})


# ---------------------------------------------------------------------------
# POST /intake/{token}/submit
# ---------------------------------------------------------------------------

class SubmitRequest(BaseModel):
    messages: list[dict]


@router.post("/{token}/submit")
async def intake_submit(
    token: str,
    body: SubmitRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """提交完整对话，触发异步报告生成。"""
    from fastapi import HTTPException
    link = await _get_valid_link(token, db)

    if link.submitted_at is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "VALIDATION_ERROR", "message": "问卷已提交，不可重复提交"},
        )

    # 写入 submission
    submission = KolIntakeSubmission(
        link_id=link.id,
        messages=body.messages,
        report_status="pending",
    )
    db.add(submission)
    await db.flush()  # 获取 id

    # 更新链接 submitted_at
    await db.execute(
        update(KolIntakeLink)
        .where(KolIntakeLink.id == link.id)
        .values(submitted_at=datetime.now(timezone.utc))
    )
    await db.commit()
    await db.refresh(submission)

    # 异步触发报告生成
    background_tasks.add_task(generate_intake_report, submission.id)

    return success_response(data={
        "submission_id": submission.id,
        "report_status": "generating",
    })


# ---------------------------------------------------------------------------
# Background task: generate report
# ---------------------------------------------------------------------------

async def generate_intake_report(submission_id: int) -> None:
    """
    异步生成报告（BackgroundTask）。
    使用独立 DB session，不复用请求中的 session。
    """
    from app.services.intake_report import generate_docx, generate_pdf

    async with AsyncSessionLocal() as db:
        submission = (await db.execute(
            select(KolIntakeSubmission).where(KolIntakeSubmission.id == submission_id)
        )).scalar_one_or_none()
        if submission is None:
            return

        # 标记 generating
        await db.execute(
            update(KolIntakeSubmission)
            .where(KolIntakeSubmission.id == submission_id)
            .values(report_status="generating")
        )
        await db.commit()

        try:
            # 读取 report_generation 配置
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
            messages = submission.messages or []
            for i, msg in enumerate(messages):
                role = msg.get("role", "")
                content = msg.get("content", "").strip()
                if not content:
                    continue
                if role == "user":
                    # 找上一条 assistant 消息作为"问"
                    prev_assistant = ""
                    for j in range(i - 1, -1, -1):
                        if messages[j].get("role") == "assistant":
                            prev_assistant = messages[j].get("content", "").strip()
                            break
                    if prev_assistant:
                        qa_lines.append(f"问：{prev_assistant}\n答：{content}")

            qa_content = "\n\n".join(qa_lines) if qa_lines else "（暂无完整对话记录）"

            # 构建 report prompt
            base_prompt = config.system_prompt or ""
            report_prompt = base_prompt.replace("{qa_content}", qa_content)

            # 尝试 extended thinking，失败降级
            ai_report_raw: dict = {}
            ai_report: str = ""
            thinking_supported = True

            report_messages = [{"role": "user", "content": report_prompt}]

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
                # 降级：普通调用
                thinking_supported = False
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

            # 提取博主昵称（第一轮用户回答）
            kol_name = None
            link = (await db.execute(
                select(KolIntakeLink).where(KolIntakeLink.id == submission.link_id)
            )).scalar_one_or_none()
            if link:
                kol_name = link.kol_name
            # 尝试从对话记录提取
            if not kol_name and messages:
                for msg in messages:
                    if msg.get("role") == "user" and msg.get("content"):
                        kol_name = msg["content"][:20]
                        break

            # 生成文件
            docx_path = generate_docx(submission_id, ai_report, kol_name)
            pdf_path  = generate_pdf(submission_id, ai_report, kol_name)

            # 更新 submission
            await db.execute(
                update(KolIntakeSubmission)
                .where(KolIntakeSubmission.id == submission_id)
                .values(
                    ai_report=ai_report,
                    ai_report_raw=ai_report_raw,
                    report_status="ready",
                    report_generated_at=datetime.now(timezone.utc),
                    docx_path=docx_path,
                    pdf_path=pdf_path,
                )
            )
            await db.commit()

        except Exception as e:
            await db.execute(
                update(KolIntakeSubmission)
                .where(KolIntakeSubmission.id == submission_id)
                .values(
                    report_status="failed",
                    ai_report_raw={"error": str(e)[:500]},
                )
            )
            await db.commit()


# ---------------------------------------------------------------------------
# GET /intake/{token}/status
# ---------------------------------------------------------------------------

@router.get("/{token}/status")
async def intake_status(token: str, db: AsyncSession = Depends(get_db)):
    """轮询报告生成状态。"""
    link = await _get_valid_link(token, db)

    submission = (await db.execute(
        select(KolIntakeSubmission).where(KolIntakeSubmission.link_id == link.id)
    )).scalar_one_or_none()

    if submission is None:
        return success_response(data={"report_status": "not_submitted", "download_ready": False})

    return success_response(data={
        "report_status":  submission.report_status,
        "download_ready": submission.report_status == "ready",
    })


# ---------------------------------------------------------------------------
# GET /intake/{token}/download
# ---------------------------------------------------------------------------

@router.get("/{token}/download")
async def intake_download(
    token: str,
    format: str = Query(default="docx", pattern="^(docx|pdf)$"),
    db: AsyncSession = Depends(get_db),
):
    """博主下载报告。"""
    from fastapi import HTTPException
    link = await _get_valid_link(token, db)

    submission = (await db.execute(
        select(KolIntakeSubmission).where(KolIntakeSubmission.link_id == link.id)
    )).scalar_one_or_none()

    if submission is None or submission.report_status != "ready":
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告尚未生成"},
        )

    file_path = submission.docx_path if format == "docx" else submission.pdf_path
    abs_path = os.path.abspath(file_path) if file_path else None
    if not abs_path or not os.path.exists(abs_path):
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "报告文件不存在"},
        )

    # 写入首次下载时间
    if submission.kol_downloaded_at is None:
        await db.execute(
            update(KolIntakeSubmission)
            .where(KolIntakeSubmission.id == submission.id)
            .values(kol_downloaded_at=datetime.now(timezone.utc))
        )
        await db.commit()

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
