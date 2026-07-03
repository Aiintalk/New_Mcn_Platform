"""
app/routers/operator_tiktok_review.py

运营端接口（JWT 鉴权，operator / admin 角色）：
  POST /api/tools/tiktok-review/generate   — SSE 流式生成复盘报告
  POST /api/tools/tiktok-review/save       — 保存报告到 outputs 表
  GET  /api/tools/tiktok-review/outputs    — 历史报告列表
  POST /api/tools/tiktok-review/export-word — 导出 Word 文档
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.adapters import yunwu as yunwu_adapter
from app.core.database import AsyncSessionLocal, get_db
from app.core.response import success_response
from app.middlewares.auth import get_current_user
from app.models.log import OperationLog
from app.models.output import Output
from app.models.task import TaskJob
from app.models.tiktok_review import TiktokReviewConfig
from app.models.user import User
from urllib.parse import quote

from app.services import word_export

router = APIRouter(prefix="/tools/tiktok-review", tags=["tiktok-review"])

TOOL_CODE = "tiktok-review"
TOOL_NAME = "TT内容复盘"
DEFAULT_MODEL = "claude-opus-4-6-thinking"
DEFAULT_PROVIDER = "yunwu"


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


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_tr_config(db: AsyncSession) -> TiktokReviewConfig:
    config = (await db.execute(
        select(TiktokReviewConfig)
        .where(TiktokReviewConfig.config_key == "default")
        .where(TiktokReviewConfig.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "CONFIG_NOT_FOUND", "message": "tiktok-review 配置未激活，请联系管理员"},
        )
    return config


async def _resolve_model(config: TiktokReviewConfig, db: AsyncSession) -> tuple[str, str]:
    if not config.ai_model_id:
        return DEFAULT_MODEL, DEFAULT_PROVIDER
    row = (await db.execute(
        sa_text("SELECT model_id, COALESCE(provider, :default_p) FROM ai_models WHERE id = :id AND status = 'active'"),
        {"id": config.ai_model_id, "default_p": DEFAULT_PROVIDER},
    )).fetchone()
    return (row[0], row[1]) if row else (DEFAULT_MODEL, DEFAULT_PROVIDER)


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    original_transcript: str = ""
    original_likes: str = ""
    copycat_transcript: str = ""
    copycat_likes: str = ""


@router.post("/generate")
async def generate(
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """SSE 流式生成复盘报告。X-Task-Id header 供前端保存时使用。"""
    if not body.original_transcript.strip() and not body.copycat_transcript.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "至少需要一侧有文案内容才能分析"},
        )

    config = await _get_tr_config(db)
    system_prompt = config.system_prompt or ""
    model_id, provider = await _resolve_model(config, db)

    user_message = (
        f"## 原版爆款\n"
        f"**点赞数**：{body.original_likes or '未知'}\n"
        f"**文案转录**：\n{body.original_transcript or '未提供'}\n\n"
        f"---\n\n"
        f"## 仿写版\n"
        f"**点赞数**：{body.copycat_likes or '未知'}\n"
        f"**文案转录**：\n{body.copycat_transcript or '未提供'}"
    )

    task_no = f"TR-{int(time.time() * 1000)}"
    task_job = TaskJob(
        task_no=task_no,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        status="processing",
        input_payload={
            "original_likes": body.original_likes,
            "copycat_likes": body.copycat_likes,
        },
        started_at=datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(task_job)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_generate",
        target_type="task_job",
        target_id=None,
        detail={"original_likes": body.original_likes, "copycat_likes": body.copycat_likes},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(task_job)
    task_id = task_job.id

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    user_id = current_user.id
    start_time = time.monotonic()

    async def generate_stream():  # pragma: no cover
        try:
            async with AsyncSessionLocal() as stream_db:
                async for chunk in yunwu_adapter.chat_stream(
                    messages=messages,
                    db=stream_db,
                    model_id=model_id,
                    provider=provider,
                    user_id=user_id,
                    feature="tiktok_review_generate",
                    max_tokens=8192,
                ):
                    yield chunk
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"\n\n[ERROR] {str(e)}"

    async def update_task_status():  # pragma: no cover
        duration_ms = int((time.monotonic() - start_time) * 1000)
        async with AsyncSessionLocal() as bg_db:
            job = await bg_db.get(TaskJob, task_id)
            if job:
                job.status = "success"
                job.finished_at = datetime.now(timezone.utc)
                job.duration_ms = duration_ms
                await bg_db.commit()

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Task-Id": str(task_id)},
        background=BackgroundTask(update_task_status),
    )


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------

class SaveRequest(BaseModel):
    content: str
    title: str = "TT内容复盘报告"
    task_id: int | None = None


@router.post("/save")
async def save_report(
    body: SaveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """保存报告到 outputs 表。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    output = Output(
        title=body.title,
        tool_code=TOOL_CODE,
        tool_name=TOOL_NAME,
        task_id=body.task_id,
        content=body.content,
        word_count=len(body.content),
        created_by=current_user.id,
    )
    db.add(output)
    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_save",
        target_type="output",
        target_id=None,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()
    await db.refresh(output)

    return success_response(data={"output_id": output.id})


# ---------------------------------------------------------------------------
# GET /outputs
# ---------------------------------------------------------------------------

@router.get("/outputs")
async def get_outputs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """operator 只看自己的；admin 看全部。"""
    query = (
        select(Output)
        .where(Output.tool_code == TOOL_CODE)
        .where(Output.deleted_at.is_(None))
    )
    if current_user.role == "operator":
        query = query.where(Output.created_by == current_user.id)

    all_rows = (
        await db.execute(query.order_by(Output.created_at.desc()))
    ).scalars().all()
    total = len(all_rows)

    start = (page - 1) * size
    rows = all_rows[start: start + size]

    items = [
        {
            "id": r.id,
            "title": r.title,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "preview": (r.content or "")[:100],
            "word_count": r.word_count,
        }
        for r in rows
    ]

    return success_response(data={"items": items, "total": total})


# ---------------------------------------------------------------------------
# POST /export-word
# ---------------------------------------------------------------------------

class ExportWordRequest(BaseModel):
    content: str
    title: str = "TT内容复盘报告"


@router.post("/export-word")
async def export_word_doc(
    body: ExportWordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    """生成 Word 文档并返回 docx 二进制流。"""
    if not body.content.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_INPUT", "message": "content 不能为空"},
        )

    date_str = datetime.now().strftime("%Y-%m-%d")
    metadata = [f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]

    docx_bytes = word_export.markdown_to_docx_bytes(
        title=body.title,
        metadata_lines=metadata,
        content=body.content,
    )

    db.add(OperationLog(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        action="tiktok_review_export_word",
        target_type="output",
        target_id=None,
        detail={"title": body.title},
        ip=_get_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    await db.commit()

    filename_ascii = f"TT_review_{date_str}.docx"
    filename_utf8 = f"TT复盘报告_{date_str}.docx"
    # RFC 5987 格式：同时提供 ASCII fallback 和 UTF-8 编码文件名
    content_disposition = (
        f'attachment; filename="{filename_ascii}"; '
        f"filename*=UTF-8''{quote(filename_utf8)}"
    )
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition},
    )
