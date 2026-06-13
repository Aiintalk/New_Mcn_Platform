"""
app/routers/operator_tiktok_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/tools/tiktok-writer/chat          — AI 流式对话（raw text stream）
  POST /api/tools/tiktok-writer/export-word   — 导出 Word 文档
  GET  /api/tools/tiktok-writer/kols/personas — 达人人设列表
"""
import time
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import get_db, AsyncSessionLocal
from app.middlewares.auth import get_current_user
from app.models.kol import Kol
from app.models.output import Output
from app.models.task import TaskJob
from app.models.tiktok_writer import TiktokWriterConfig
from app.models.user import User
from app.services import word_export

router = APIRouter(prefix="/tools/tiktok-writer", tags=["tiktok-writer"])

DEFAULT_MODEL = "claude-opus-4-6-thinking"
_RETRY_DELAYS = [2, 4, 6]


async def _get_tw_config(key: str, db: AsyncSession) -> TiktokWriterConfig:
    """从 DB 读取激活的 tiktok-writer 配置，不存在则抛 503。"""
    config = (await db.execute(
        select(TiktokWriterConfig)
        .where(TiktokWriterConfig.config_key == key)
        .where(TiktokWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": f"tiktok-writer 配置 '{key}' 未激活，请联系管理员"},
        )
    return config


async def _resolve_tw_model(config: TiktokWriterConfig, db: AsyncSession) -> str:
    """解析绑定的模型 ID，无绑定则返回默认值。"""
    from sqlalchemy import text as sa_text
    if not config.ai_model_id:
        return DEFAULT_MODEL
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id},
    )).fetchone()
    return row[0] if row else DEFAULT_MODEL


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


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """返回 hook_eval 和 structure 的 Prompt + 模型，供前端 Step1/2 使用。"""
    hook_cfg = await _get_tw_config("hook_eval", db)
    struct_cfg = await _get_tw_config("structure", db)
    model_id = await _resolve_tw_model(hook_cfg, db)
    return {
        "success": True,
        "data": {
            "hook_eval_prompt": hook_cfg.system_prompt or "",
            "structure_prompt": struct_cfg.system_prompt or "",
            "model_id": model_id,
        },
    }


# ---------------------------------------------------------------------------
# POST /tools/tiktok-writer/chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    messages: list[dict]
    systemPrompt: str
    model: str = DEFAULT_MODEL
    createJob: bool = False
    jobContext: dict | None = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    current_user: User = Depends(require_operator),
):
    """AI 流式对话，返回 raw text stream（非 SSE）。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if not body.systemPrompt.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "systemPrompt 不能为空"},
        )

    messages = [{"role": "system", "content": body.systemPrompt}] + body.messages
    user_id = current_user.id
    create_job = body.createJob
    job_context = body.jobContext or {}
    model_id = body.model or DEFAULT_MODEL

    async def generate():
        delays = [0] + _RETRY_DELAYS
        for i, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with AsyncSessionLocal() as stream_db:
                    async for chunk in yunwu_adapter.chat_stream(
                        messages=messages,
                        db=stream_db,
                        model_id=model_id,
                        user_id=user_id,
                        feature="tiktok_writer_chat",
                        max_tokens=8192,
                    ):
                        yield chunk
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate" in err_str
                if is_rate_limit and i < len(delays) - 1:
                    continue
                yield f"\n\n[ERROR] {str(e)}"
                return

    async def write_task_job():
        if not create_job:
            return
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"TW-{int(time.time())}",
                tool_code="tiktok-writer",
                tool_name="TikTok 脚本仿写",
                status="completed",
                input_payload={
                    "tiktokUrl": job_context.get("tiktokUrl", ""),
                    "likesCount": job_context.get("likesCount", ""),
                    "selectedPersonaName": job_context.get("selectedPersonaName", ""),
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ---------------------------------------------------------------------------
# POST /tools/tiktok-writer/export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    personaName: str = "TikTok"
    topic: str = ""
    content: str
    taskJobId: int | None = None


@router.post("/export-word")
async def export_word(
    body: ExportWordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成 Word 文档并写 outputs 表，返回 docx 二进制流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"{body.personaName} · TikTok Script"
    metadata = [
        f"Topic: {body.topic}" if body.topic.strip() else "Topic: —",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=title,
        metadata_lines=metadata,
        content=body.content,
    )

    output = Output(
        title=f"TikTok Script · {body.personaName} · {date_str}",
        tool_code="tiktok-writer",
        tool_name="TikTok 脚本仿写",
        content=body.content,
        word_count=len(body.content.split()),
        task_id=body.taskJobId,
        created_by=current_user.id,
    )
    db.add(output)
    await db.commit()

    filename = f"TikTok_Script_{body.personaName}_{date_str}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /tools/tiktok-writer/kols/personas
# ---------------------------------------------------------------------------

@router.get("/kols/personas")
async def get_kol_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """查询 kols 表，返回有人设的达人列表。"""
    rows = (
        await db.execute(
            select(Kol.id, Kol.name, Kol.persona, Kol.content_plan)
            .where(Kol.persona.is_not(None))
            .where(Kol.deleted_at.is_(None))
            .order_by(Kol.name)
        )
    ).all()

    personas = [
        {
            "name": row.name,
            "soul": row.persona or "",
            "contentPlan": row.content_plan or "",
        }
        for row in rows
    ]
    return {"personas": personas}
