"""
app/routers/operator_persona_writer.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  GET  /api/tools/persona-writer/kols/personas       — 达人人设列表（Step 1）
  POST /api/tools/persona-writer/fetch-video         — 抖音分享链接解析（Step 2.1）
  POST /api/tools/persona-writer/evaluate-opening    — AI 开头评估流式（Step 2.4）
  POST /api/tools/persona-writer/analyze-structure   — AI 结构拆解流式（Step 3.1）
  POST /api/tools/persona-writer/chat                — AI 写作/追问流式（Step 3.3/3.4）
  POST /api/tools/persona-writer/save-output         — 保存产出
  POST /api/tools/persona-writer/export-word         — 导出 Word 文档
  GET  /api/tools/persona-writer/outputs             — 历史记录（账号隔离）
"""
import asyncio
import time
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.adapters import tikhub as tikhub_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.persona_writer import PersonaWriterConfig
from app.models.task import TaskJob
from app.models.user import User
from app.services import word_export
from app.services.persona_writer_prompt import render_prompt

router = APIRouter(prefix="/tools/persona-writer", tags=["persona-writer"])

TOOL_CODE = "persona-writer"
TOOL_NAME = "人设脚本仿写"
DEFAULT_LIGHT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_HEAVY_MODEL = "claude-opus-4-6"
_RETRY_DELAYS = [2, 4, 6]
_PAGE_SIZE_ALLOWED = {10, 20, 50}
_PERSONA_PREVIEW_CHARS = 400
_LIKES_THRESHOLD = 100000


# ---------------------------------------------------------------------------
# 内部 helpers
# ---------------------------------------------------------------------------

async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """operator / admin 角色校验 + 已改密。"""
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


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_config(db: AsyncSession) -> PersonaWriterConfig:
    """读取激活的 default 配置，不存在则抛 503。"""
    config = (await db.execute(
        select(PersonaWriterConfig)
        .where(PersonaWriterConfig.config_key == "default")
        .where(PersonaWriterConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CONFIG_NOT_FOUND",
                "message": "persona-writer 配置 'default' 未激活，请联系管理员",
            },
        )
    return config


async def _resolve_model_id(config: PersonaWriterConfig, db: AsyncSession, *, is_heavy: bool) -> str:
    """解析配置绑定的模型 ID，留空或失效则返回默认值。"""
    model_db_id = config.heavy_model_id if is_heavy else config.light_model_id
    default_model = DEFAULT_HEAVY_MODEL if is_heavy else DEFAULT_LIGHT_MODEL
    if not model_db_id:
        return default_model
    row = (await db.execute(
        sa_text("SELECT model_id FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": model_db_id},
    )).fetchone()
    return row[0] if row else default_model


async def _get_kol(db: AsyncSession, kol_id: int) -> tuple[str, str, str]:
    """读取达人人设，返回 (name, persona, content_plan)。不存在抛 404。"""
    kol_row = (await db.execute(
        sa_text(
            """
            SELECT name, persona, content_plan
            FROM kols
            WHERE id = :id AND deleted_at IS NULL
            """
        ),
        {"id": kol_id},
    )).fetchone()
    if kol_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "达人人设不存在或已删除"},
        )
    return kol_row[0], kol_row[1] or "", kol_row[2] or ""


# ---------------------------------------------------------------------------
# GET /kols/personas
# ---------------------------------------------------------------------------

@router.get("/kols/personas")
async def get_kol_personas(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 1 达人下拉：返回 persona + content_plan 均非空且未删除的达人。"""
    rows = (
        await db.execute(
            sa_text(
                """
                SELECT k.id,
                       k.name,
                       LEFT(k.persona, :preview_len) AS soul_preview,
                       COALESCE(u.username, '系统预设') AS creator_name
                FROM kols k
                LEFT JOIN users u ON k.created_by = u.id
                WHERE k.persona IS NOT NULL
                  AND k.content_plan IS NOT NULL
                  AND k.deleted_at IS NULL
                  AND k.status IN ('signed', 'pending_renewal')
                ORDER BY k.name
                """
            ),
            {"preview_len": _PERSONA_PREVIEW_CHARS},
        )
    ).fetchall()

    personas = [
        {
            "id": row[0],
            "name": row[1],
            "soul_preview": row[2] or "",
            "creator_name": row[3],
        }
        for row in rows
    ]
    return success_response(data=personas)


# ---------------------------------------------------------------------------
# POST /fetch-video
# ---------------------------------------------------------------------------

class FetchVideoRequest(BaseModel):
    share_url: str


@router.post("/fetch-video")
async def fetch_video(
    body: FetchVideoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 2.1 抖音分享链接解析：调 tikhub_adapter → 返回视频信息 + 点赞门槛判定。"""
    if not body.share_url.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "share_url 不能为空"},
        )

    try:
        result = await tikhub_adapter.fetch_video_by_share_url(body.share_url.strip(), db)
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"code": "EXTERNAL_SERVICE_ERROR", "message": str(e)},
        )

    digg_count = result.get("digg_count", 0)
    likes_pass = digg_count >= _LIKES_THRESHOLD

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="persona_writer_fetch_video",
        target_type="video",
        target_id=None,
        detail={
            "aweme_id": result.get("aweme_id", ""),
            "digg_count": digg_count,
            "likes_pass": likes_pass,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={
        "title": result.get("title", ""),
        "digg_count": digg_count,
        "aweme_id": result.get("aweme_id", ""),
        "play_url": result.get("play_url", ""),
        "likes_pass": likes_pass,
    })


# ---------------------------------------------------------------------------
# POST /evaluate-opening (流式, light 模型)
# ---------------------------------------------------------------------------

class EvaluateOpeningRequest(BaseModel):
    transcript: str


@router.post("/evaluate-opening")
async def evaluate_opening(
    body: EvaluateOpeningRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 2.4 AI 开头评估：调 yunwu（light 模型）+ evaluation_prompt → 裸文本流。"""
    if not body.transcript.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "transcript 不能为空"},
        )

    config = await _get_config(db)
    model_id = await _resolve_model_id(config, db, is_heavy=False)

    template = config.evaluation_prompt or ""
    system_prompt = render_prompt(template, transcript=body.transcript)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.transcript},
    ]
    user_id = current_user.id

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
                        feature="persona_writer_evaluate",
                        max_tokens=2048,
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

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# POST /analyze-structure (流式, light 模型)
# ---------------------------------------------------------------------------

class AnalyzeStructureRequest(BaseModel):
    transcript: str


@router.post("/analyze-structure")
async def analyze_structure(
    body: AnalyzeStructureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 3.1 AI 结构拆解：调 yunwu（light 模型）+ analysis_prompt → 裸文本流。"""
    if not body.transcript.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "transcript 不能为空"},
        )

    config = await _get_config(db)
    model_id = await _resolve_model_id(config, db, is_heavy=False)

    template = config.analysis_prompt or ""
    system_prompt = render_prompt(template, transcript=body.transcript)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.transcript},
    ]
    user_id = current_user.id

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
                        feature="persona_writer_analyze",
                        max_tokens=4096,
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

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------------------------------------------------------------------------
# POST /chat (流式, heavy 模型, writing + iteration 双场景)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    scene: str = "writing"  # writing | iteration
    topic_mode: str = "default"  # custom | default（仅 writing 场景有效）
    persona_id: int = 0
    transcript: str = ""
    structure_analysis: str = ""
    topic: str = ""
    messages: list[dict] = []
    create_job: bool = False
    job_context: dict | None = None


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """Step 3.3/3.4 AI 写作 + 追问：调 yunwu（heavy 模型）→ 裸文本流。"""
    if not body.messages:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "messages 不能为空"},
        )
    if body.scene not in ("writing", "iteration"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "scene 必须为 writing 或 iteration"},
        )
    if not body.persona_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "persona_id 不能为空"},
        )

    config = await _get_config(db)
    model_id = await _resolve_model_id(config, db, is_heavy=True)

    kol_name, kol_persona, kol_content_plan = await _get_kol(db, body.persona_id)

    is_custom = body.topic_mode == "custom"

    if body.scene == "writing":
        template = config.writing_prompt or ""
        system_prompt = render_prompt(
            template,
            name=kol_name,
            soul=kol_persona,
            content_plan=kol_content_plan,
            transcript=body.transcript,
            structure_analysis=body.structure_analysis,
            topic=body.topic,
            is_custom=is_custom,
        )
    else:
        template = config.iteration_prompt or ""
        system_prompt = render_prompt(
            template,
            name=kol_name,
            soul=kol_persona,
            content_plan=kol_content_plan,
            transcript=body.transcript,
            structure_analysis=body.structure_analysis,
            topic=body.topic,
            is_custom=is_custom,
        )

    messages = [{"role": "system", "content": system_prompt}] + body.messages
    user_id = current_user.id
    create_job = body.create_job
    job_context = body.job_context or {}

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
                        feature=f"persona_writer_{body.scene}",
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
        """BackgroundTask：创建 task_job + 写 OperationLog。"""
        if not create_job:
            return
        async with AsyncSessionLocal() as bg_db:
            task_job = TaskJob(
                task_no=f"PW-{int(time.time())}",
                tool_code=TOOL_CODE,
                tool_name=TOOL_NAME,
                status="completed",
                input_payload={
                    "persona_id": body.persona_id,
                    "persona_name": kol_name,
                    "scene": body.scene,
                    "topic_mode": body.topic_mode,
                    "topic": body.topic,
                },
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_by=user_id,
            )
            bg_db.add(task_job)
            await bg_db.flush()
            bg_db.add(OperationLog(
                user_id=current_user.id,
                username=current_user.username,
                role=current_user.role,
                action="persona_writer_chat",
                target_type="task_job",
                target_id=task_job.id,
                detail={
                    "persona_name": kol_name,
                    "scene": body.scene,
                    "topic_mode": body.topic_mode,
                    "model_id": model_id,
                    "job_context": job_context,
                },
                ip=_get_ip(request),
                user_agent=request.headers.get("user-agent"),
            ))
            await bg_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        background=BackgroundTask(write_task_job),
    )


# ---------------------------------------------------------------------------
# POST /save-output
# ---------------------------------------------------------------------------

class SaveOutputRequest(BaseModel):
    content: str
    title: str = ""
    task_id: int | None = None
    topic: str | None = None
    transcript_digest: str | None = None


@router.post("/save-output")
async def save_output(
    body: SaveOutputRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存仿写产出至 outputs 表（账号绑定）。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    word_count = len(body.content.replace(" ", "").replace("\n", "").replace("\t", ""))
    output = Output(
        title=body.title or f"{TOOL_NAME} · {datetime.now().strftime('%Y-%m-%d')}",
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        content=body.content,
        word_count=word_count,
        task_id=body.task_id,
        created_by=current_user.id,
    )
    db.add(output)
    await db.flush()

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="persona_writer_save_output",
        target_type="output",
        target_id=output.id,
        detail={
            "title": body.title,
            "topic": body.topic,
            "transcript_digest": body.transcript_digest,
            "word_count": word_count,
        },
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    filename: str = "人设脚本"


@router.post("/export-word")
async def export_word(
    body: ExportWordRequest,
    current_user: User = Depends(require_operator),
):
    """导出 Word 文档（.docx），返回二进制流（不走标准信封）。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    title = body.filename or "人设脚本"
    metadata_lines = [f"导出日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=title,
        metadata_lines=metadata_lines,
        content=body.content,
    )

    safe_name = body.filename or "人设脚本"
    from urllib.parse import quote
    filename_encoded = quote(f"{safe_name}_{date_str}.docx")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
    )


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def list_outputs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """历史记录：按账号隔离，只返回当前用户的 outputs。"""
    if page_size not in _PAGE_SIZE_ALLOWED:
        page_size = 20

    total = (await db.execute(
        sa_text(
            """
            SELECT COUNT(*) FROM outputs
            WHERE tool_code = :tool_code
              AND created_by = :user_id
              AND deleted_at IS NULL
            """
        ),
        {"tool_code": TOOL_CODE, "user_id": current_user.id},
    )).scalar() or 0

    rows = (await db.execute(
        sa_text(
            """
            SELECT id, title, content, word_count, task_id, created_at
            FROM outputs
            WHERE tool_code = :tool_code
              AND created_by = :user_id
              AND deleted_at IS NULL
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "tool_code": TOOL_CODE,
            "user_id": current_user.id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    )).fetchall()

    items = [
        {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "word_count": row[3],
            "task_id": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 0
    return success_response(data={
        "items": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    })
